"""Pipeline "video_youtube": tema -> roteiro (Gemini) -> cenas -> imagens livres -> narração local -> legendas -> MP4.

Cada etapa só devolve dados/arquivos; leitura de artefatos anteriores via `ctx.read` (somente leitura). Sem publicação.
"""
import json
import math
import os
import re
import subprocess
import tempfile

from app.core.config import settings
from app.media import sources, tts
from app.pipelines.registry import OutFile, Pipeline, Step, StepContext, StepResult, register
from app.providers.adapters.base import TextRequest
from app.studio.schemas import FactoryConfig

WPM = 140  # palavras por minuto de narração (referência para dimensionar o roteiro)
MAX_SECTIONS = 12  # trava contra loops de regeneração / custo
MAX_SCENES = 220
SCENE_WORDS = (18, 48)  # cenas muito longas são divididas; muito curtas são agrupadas
GAP = 0.35  # silêncio ao fim de cada cena (s)


class StepError(Exception):
    def __init__(self, msg, retryable=False):
        super().__init__(msg)
        self.retryable = retryable


def _cfg(ctx) -> FactoryConfig:
    try:
        return FactoryConfig.model_validate(ctx.config)
    except Exception as exc:  # noqa: BLE001
        raise StepError(f"configuração da fábrica inválida: {exc}") from None


def _provider_and_model() -> tuple[str, str]:
    from app.studio import assistant
    try:
        return assistant.provider_id(), settings.gemini_text_model
    except assistant.NotConfigured as exc:
        raise StepError(f"Gemini não configurado: {exc}") from None


def _ask(ctx, suffix: str, system: str, prompt: str, max_tokens: int) -> dict:
    from app.studio import assistant
    pid, model = _provider_and_model()
    out = ctx.ai.text(pid, model, TextRequest(prompt, system, max_tokens, json_mode=True), ctx.ai_key(suffix))
    ctx.log(f"Gemini ({suffix}): {out.input_tokens or '?'} tokens de entrada / {out.output_tokens or '?'} de saída, "
            f"custo US$ {out.cost}{' (reaproveitado)' if out.cached else ''}")
    try:
        return assistant.parse_json(out.text or "")
    except assistant.AssistantError as exc:
        raise StepError(f"resposta do Gemini inválida: {exc}") from None


def _words(t: str) -> int:
    return len(t.split())


# ---------------------------------------------------------------- 1. roteiro
SCRIPT_SYS = ("Você é roteirista de vídeos de YouTube em português do Brasil. Responda SOMENTE com JSON válido. "
              "Narração falada em primeira pessoa do narrador, sem rubricas, sem emojis, sem marcações de cena, "
              "sem números por extenso errados, frases curtas e claras para leitura em voz alta.")


def script(ctx: StepContext) -> StepResult:
    c = _cfg(ctx)
    if c.script_text.strip():
        title = c.topic or c.script_text.strip().splitlines()[0][:100]
        ctx.log("usando roteiro fornecido pelo usuário (sem chamada de IA)")
        return StepResult({"title": title, "description": c.topic or title, "source": "user",
                           "sections": [{"heading": "", "text": c.script_text.strip()}]},
                          message="roteiro fornecido")
    total_words = int(c.video_minutes * WPM)
    n = max(1, min(MAX_SECTIONS, math.ceil(total_words / 260)))
    identity = (f"Fábrica: {c.name}. Tema do canal: {c.theme}. Público: {c.audience or 'geral'}. "
                f"Estilo narrativo: {c.narrative_style or 'natural'}. Estilo visual: {c.visual_style or 'realista'}.")
    topic_line = (f"Tema do vídeo: {c.topic}." if c.topic else
                  "Escolha você um tema de vídeo original, específico e interessante dentro do tema do canal.")
    outline = _ask(ctx, "outline", SCRIPT_SYS,
                   f"{identity}\n{topic_line}\nPlaneje um vídeo de cerca de {total_words} palavras de narração em {n} seção(ões). "
                   'Devolva {"title": str (título atraente, até 90 caracteres), "description": str (2-3 frases para a descrição), '
                   '"sections": [{"heading": str, "summary": str}]} com exatamente '
                   f"{n} seção(ões).", 2048)
    sections = [s for s in (outline.get("sections") or []) if isinstance(s, dict)][:n]
    if not sections or not str(outline.get("title", "")).strip():
        raise StepError("o Gemini não devolveu um plano de roteiro utilizável")
    per = max(80, total_words // len(sections))
    done, prev_tail = [], ""
    for i, sec in enumerate(sections, start=1):
        data = _ask(ctx, f"section{i}", SCRIPT_SYS,
                    f"{identity}\nVídeo: {outline['title']}.\nEscreva a seção {i} de {len(sections)}: "
                    f"\"{sec.get('heading', '')}\" — {sec.get('summary', '')}.\n"
                    f"{'Esta é a abertura: comece com um gancho forte.' if i == 1 else 'Continue naturalmente após: ' + prev_tail}\n"
                    f"{'Encerre com uma conclusão e chamada para ação breve.' if i == len(sections) else 'Não conclua o vídeo.'}\n"
                    f"Cerca de {per} palavras. Divida em cenas de 20 a 45 palavras. Devolva "
                    '{"scenes": [{"narration": str, "query": str (2-4 palavras EM INGLÊS para buscar uma foto real que ilustre a cena), '
                    '"query_alt": str (consulta mais genérica em inglês)}]}.', 8192)
        scenes = [s for s in (data.get("scenes") or []) if isinstance(s, dict) and str(s.get("narration", "")).strip()]
        if not scenes:
            raise StepError(f"seção {i} sem cenas utilizáveis")
        done.append({"heading": sec.get("heading", ""), "scenes": [
            {"narration": str(s["narration"]).strip(), "query": str(s.get("query", "")).strip(),
             "query_alt": str(s.get("query_alt", "")).strip()} for s in scenes]})
        prev_tail = " ".join(done[-1]["scenes"][-1]["narration"].split()[-25:])
    words = sum(_words(s["narration"]) for d in done for s in d["scenes"])
    return StepResult({"title": str(outline["title"])[:120], "description": str(outline.get("description", ""))[:1000],
                       "source": "gemini", "sections": done, "words": words},
                      message=f"roteiro com {words} palavras em {len(done)} seção(ões)")


# ---------------------------------------------------------------- 2. cenas
def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+|\n+", text) if s.strip()]


def _chunk(text: str) -> list[str]:
    """Agrupa frases em blocos de narração de tamanho de cena."""
    out, cur = [], []
    for sent in _split_sentences(text):
        if cur and _words(" ".join(cur + [sent])) > SCENE_WORDS[1]:
            out.append(" ".join(cur))
            cur = []
        cur.append(sent)
        if _words(" ".join(cur)) >= SCENE_WORDS[0] + 10:
            out.append(" ".join(cur))
            cur = []
    if cur:
        if out and _words(" ".join(cur)) < SCENE_WORDS[0] // 2:
            out[-1] += " " + " ".join(cur)
        else:
            out.append(" ".join(cur))
    return out


def scenes(ctx: StepContext) -> StepResult:
    c = _cfg(ctx)
    sc = ctx.previous["script"]
    generic = [w for w in re.findall(r"[A-Za-zÀ-ú]{4,}", c.theme or sc["title"])][:3]
    fallback_q = " ".join(generic) or "landscape"
    out = []
    for sec in sc["sections"]:
        if "scenes" in sec:  # roteiro estruturado pelo Gemini
            for s in sec["scenes"]:
                parts = _chunk(s["narration"]) if _words(s["narration"]) > SCENE_WORDS[1] + 12 else [s["narration"]]
                for p in parts:
                    out.append({"narration": p, "queries": [q for q in (s["query"], s["query_alt"], fallback_q) if q]})
        else:  # texto livre do usuário: divisão determinística; busca pelo tema
            for p in _chunk(sec["text"]):
                out.append({"narration": p, "queries": [q for q in (c.topic, fallback_q) if q] or ["landscape"]})
    out = out[:MAX_SCENES]
    if not out:
        raise StepError("roteiro sem conteúdo para dividir em cenas")
    for i, s in enumerate(out, start=1):
        s["index"] = i
    words = sum(_words(s["narration"]) for s in out)
    return StepResult({"scenes": out, "title": sc["title"]},
                      message=f"{len(out)} cenas, ~{words / WPM:.1f} min de narração estimados")


# ---------------------------------------------------------------- 3. imagens
def _ext(data: bytes) -> str:
    return "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpg"


def images(ctx: StepContext) -> StepResult:
    c = _cfg(ctx)
    used: set[str] = set()
    files, entries, warns, missing = [], [], [], 0
    for s in ctx.previous["scenes"]["scenes"]:
        img, w = sources.find_image(s["queries"], used, c.image_sources)
        warns += w
        if img is None:
            missing += 1
            entries.append({"index": s["index"], "key": None})
            continue
        fn = f"cena_{s['index']:03d}.{_ext(img.data)}"
        mime = "image/png" if fn.endswith("png") else "image/jpeg"
        meta = {"source": img.source, "title": img.title, "author": img.author, "license": img.license, "url": img.url,
                "size": len(img.data)}
        files.append(OutFile(fn, mime, img.data, provider=img.source, meta=meta))
        entries.append({"index": s["index"], "key": f"runs/{ctx.run_id}/images/{fn}", **{k: meta[k] for k in
                        ("source", "title", "author", "license", "url")}})
    if missing == len(entries):
        raise StepError("nenhuma imagem encontrada nas fontes livres" + (f" ({'; '.join(sorted(set(warns)))})" if warns else "")
                        + ". Configure PEXELS_API_KEY ou verifique a conexão.", retryable=bool(warns))
    if missing:
        ctx.log(f"{missing} cena(s) sem imagem: serão exibidas como cartão escuro (identificado no relatório)", "warn")
    return StepResult({"images": entries, "missing": missing}, files=files,
                      message=f"{len(entries) - missing}/{len(entries)} imagens obtidas" + (f"; {missing} cartões" if missing else ""))


# ---------------------------------------------------------------- 4. narração
def narration(ctx: StepContext) -> StepResult:
    c = _cfg(ctx)
    files, entries, engine = [], [], None
    voice = c.voice.model_dump()
    with tempfile.TemporaryDirectory() as td:
        for s in ctx.previous["scenes"]["scenes"]:
            wav = os.path.join(td, f"{s['index']}.wav")
            try:
                engine = tts.synthesize(s["narration"], wav, voice)
            except tts.TTSError as exc:
                raise StepError(str(exc)) from None
            dur = tts.wav_duration(wav)
            fn = f"cena_{s['index']:03d}.wav"
            data = open(wav, "rb").read()
            files.append(OutFile(fn, "audio/wav", data, provider=f"tts-local:{engine}", meta={"size": len(data), "seconds": round(dur, 2)}))
            entries.append({"index": s["index"], "key": f"runs/{ctx.run_id}/narration/{fn}", "seconds": dur})
    total = sum(e["seconds"] for e in entries)
    return StepResult({"audio": entries, "engine": engine, "seconds": total}, files=files,
                      message=f"narração local ({engine}) de {total / 60:.1f} min")


# ---------------------------------------------------------------- 5. legendas
def _ts(t: float, ass=False) -> str:
    cs = int(round(t * 100))
    h, r = divmod(cs, 360000)
    m, r = divmod(r, 6000)
    s, cs = divmod(r, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}" if ass else f"{h:02d}:{m:02d}:{s:02d},{cs * 10:03d}"


def captions(text: str, start: float, dur: float, max_chars=42) -> list[tuple[float, float, str]]:
    """Quebra a narração em legendas de até 2 linhas, distribuindo o tempo real do áudio por nº de caracteres."""
    words, chunks, cur = text.split(), [], ""
    for w in words:
        if cur and (len(cur) + 1 + len(w) > max_chars * 2 - 6 or (re.search(r"[.!?]$", cur) and len(cur) > 25)):
            chunks.append(cur)
            cur = ""
        cur = f"{cur} {w}".strip()
    if cur:
        chunks.append(cur)
    total = sum(len(c) for c in chunks) or 1
    out, t = [], start
    for ch in chunks:
        d = dur * len(ch) / total
        out.append((t, t + d, ch))
        t += d
    return out


def _wrap(text: str, width=42) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = ""
        cur = f"{cur} {w}".strip()
    return lines + ([cur] if cur else [])


def subtitles(ctx: StepContext) -> StepResult:
    c = _cfg(ctx)
    sc, au = ctx.previous["scenes"]["scenes"], {a["index"]: a["seconds"] for a in ctx.previous["narration"]["audio"]}
    h = 720 if c.editing.resolution == "720p" else 1080
    caps, t = [], 0.0
    for s in sc:
        d = au[s["index"]]
        caps += captions(s["narration"], t, d)
        t += d + GAP
    srt = "\n".join(f"{i}\n{_ts(a)} --> {_ts(b)}\n" + "\n".join(_wrap(x)) + "\n" for i, (a, b, x) in enumerate(caps, 1))
    ass = ("[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\n\n[V4+ Styles]\n"
           "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
           "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
           "Style: Default,DejaVu Sans,%d,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.5,1,2,60,60,%d,1\n\n"
           "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n") % (
        h * 16 // 9, h, round(h * 0.05), round(h * 0.07))
    ass += "".join(f"Dialogue: 0,{_ts(a, True)},{_ts(b, True)},Default,,0,0,0,," + r"\N".join(_wrap(x)) + "\n" for a, b, x in caps)
    srt_b, ass_b = srt.encode(), ass.encode()
    return StepResult({"captions": len(caps), "ass_key": f"runs/{ctx.run_id}/subtitles/legendas.ass", "seconds": t},
                      files=[OutFile("legendas.srt", "application/x-subrip", srt_b, meta={"size": len(srt_b)}),
                             OutFile("legendas.ass", "text/x-ssa", ass_b, meta={"size": len(ass_b)})],
                      message=f"{len(caps)} legendas sincronizadas com o áudio")


# ---------------------------------------------------------------- 6. montagem
def _run(cmd: list[str], what: str, cwd: str | None = None) -> None:
    r = subprocess.run(cmd, capture_output=True, timeout=3600, cwd=cwd)
    if r.returncode != 0:
        raise StepError(f"FFmpeg falhou ({what}): {r.stderr.decode(errors='ignore')[-400:]}")


def render(ctx: StepContext) -> StepResult:
    c = _cfg(ctx)
    W, H = (1280, 720) if c.editing.resolution == "720p" else (1920, 1080)
    FPS = 25
    imgs = {e["index"]: e for e in ctx.previous["images"]["images"]}
    aud = {a["index"]: a for a in ctx.previous["narration"]["audio"]}
    with tempfile.TemporaryDirectory() as td:
        clips = []
        for n, s in enumerate(ctx.previous["scenes"]["scenes"]):
            i = s["index"]
            dur = aud[i]["seconds"] + GAP
            wav = os.path.join(td, f"a{i}.wav")
            open(wav, "wb").write(ctx.read(aud[i]["key"]))
            clip = os.path.join(td, f"c{i}.mp4")
            frames = max(1, int(round(dur * FPS)))
            if imgs[i]["key"]:
                ext = imgs[i]["key"].rsplit(".", 1)[-1]
                img = os.path.join(td, f"i{i}.{ext}")
                open(img, "wb").write(ctx.read(imgs[i]["key"]))
                if c.editing.ken_burns:
                    z = ("min(zoom+0.0007,1.18)" if n % 2 == 0 else "if(eq(on,0),1.18,max(zoom-0.0007,1.0))")
                    vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
                          f"zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},format=yuv420p")
                else:
                    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},format=yuv420p"
                vin = ["-i", img]
            else:
                vin, vf = ["-f", "lavfi", "-i", f"color=c=0x0b2530:s={W}x{H}:r={FPS}"], "format=yuv420p"
            _run(["ffmpeg", "-y", *vin, "-i", wav, "-vf", vf, "-af", "apad", "-frames:v", str(frames), "-t", f"{dur:.3f}",
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", str(FPS), "-c:a", "aac", "-b:a", "128k",
                  "-ar", "44100", "-ac", "2", clip], f"cena {i}")
            clips.append(clip)
            for f in (img if imgs[i]["key"] else None, wav):
                if f:
                    os.remove(f)
        lst = os.path.join(td, "list.txt")
        open(lst, "w").write("".join(f"file '{p}'\n" for p in clips))
        joined, final = os.path.join(td, "joined.mp4"), os.path.join(td, "video.mp4")
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined], "concatenação")
        if c.editing.subtitles:
            ass = os.path.join(td, "legendas.ass")
            open(ass, "wb").write(ctx.read(ctx.previous["subtitles"]["ass_key"]))
            _run(["ffmpeg", "-y", "-i", joined, "-vf", "subtitles=legendas.ass:fontsdir=/usr/share/fonts", "-c:v", "libx264",
                  "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", final],
                 "legendas", cwd=td)  # nome relativo evita escape de caminho no filtro
        else:
            _run(["ffmpeg", "-y", "-i", joined, "-c", "copy", "-movflags", "+faststart", final], "finalização")
        data = open(final, "rb").read()
    return StepResult({"video_key": f"runs/{ctx.run_id}/render/video.mp4", "width": W, "height": H, "size": len(data)},
                      files=[OutFile("video.mp4", "video/mp4", data, provider="ffmpeg",
                                     meta={"size": len(data), "width": W, "height": H})],
                      message=f"vídeo {W}x{H} montado ({len(data) / 1e6:.1f} MB)")


# ---------------------------------------------------------------- 7. exportação
def _probe(path: str) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                       capture_output=True, timeout=120)
    if r.returncode != 0:
        raise StepError("o arquivo gerado não é um vídeo válido (ffprobe recusou)")
    return json.loads(r.stdout)


def export(ctx: StepContext) -> StepResult:
    c = _cfg(ctx)
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "video.mp4")
        open(path, "wb").write(ctx.read(ctx.previous["render"]["video_key"]))
        info = _probe(path)
        kinds = {s["codec_type"]: s for s in info["streams"]}
        dur = float(info["format"]["duration"])
        expect = ctx.previous["subtitles"]["seconds"]
        if "video" not in kinds or "audio" not in kinds or kinds["video"]["codec_name"] != "h264":
            raise StepError("vídeo inválido: faltam trilhas H.264/áudio")
        if dur < 1 or abs(dur - expect) > max(3.0, expect * 0.03):
            raise StepError(f"duração do vídeo ({dur:.1f}s) diverge da narração ({expect:.1f}s)")
        thumb = os.path.join(td, "t.jpg")
        _run(["ffmpeg", "-y", "-ss", str(min(2.0, dur / 2)), "-i", path, "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", thumb],
             "miniatura")
        tdata = open(thumb, "rb").read()
    credits = []
    seen = set()
    for e in ctx.previous["images"]["images"]:
        if e.get("key") and e["url"] not in seen:
            seen.add(e["url"])
            credits.append(f"{e['title']} — {e['author'] or 'autor desconhecido'} ({e['license']}, {e['source']}): {e['url']}")
    title, desc = ctx.previous["script"]["title"], ctx.previous["script"]["description"]
    meta = {"title": title, "description": desc, "duration_seconds": round(dur, 2), "width": kinds["video"]["width"],
            "height": kinds["video"]["height"], "video_codec": kinds["video"]["codec_name"], "audio_codec": kinds["audio"]["codec_name"],
            "script_source": ctx.previous["script"]["source"], "voice_engine": ctx.previous["narration"]["engine"],
            "scenes": len(ctx.previous["scenes"]["scenes"]), "scenes_without_image": ctx.previous["images"]["missing"],
            "credits": credits if c.editing.credits else []}
    mb = json.dumps(meta, ensure_ascii=False, indent=2).encode()
    return StepResult({"title": title, "duration_seconds": round(dur, 2), "valid": True, "credits": len(credits)},
                      files=[OutFile("miniatura.jpg", "image/jpeg", tdata, meta={"size": len(tdata)}),
                             OutFile("metadados.json", "application/json", mb, meta={"size": len(mb)})],
                      message=f"MP4 válido: {dur:.0f}s, {kinds['video']['width']}x{kinds['video']['height']}")


register(Pipeline(
    "video_youtube", "Vídeo para YouTube", "Roteiro (Gemini), imagens livres, narração local, legendas e MP4 (sem publicação).",
    FactoryConfig().identity(),
    [Step("script", script), Step("scenes", scenes), Step("images", images), Step("narration", narration),
     Step("subtitles", subtitles), Step("render", render), Step("export", export)]))
