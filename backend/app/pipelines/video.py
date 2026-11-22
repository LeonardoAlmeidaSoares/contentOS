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
from app.media import sources
from app.voices import engines as _engines, service as voices
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
def _identity(c: FactoryConfig) -> str:
    """Identidade do canal passada ao modelo: a IA decide o *como*, nunca substitui estas decisões."""
    t = c.target()
    parts = [f"Fábrica: {c.name}.", f"Canal: {c.channel_name or c.name}." if c.channel_name else "",
             f"Nicho: {c.niche}." if c.niche else "", f"Tema do canal: {c.theme}.", f"Público: {c.audience or 'geral'}.",
             f"Idioma obrigatório: {c.language}.", f"Tom: {c.tone}." if c.tone else "",
             f"Estilo narrativo: {c.narrative_style or 'natural'}.", f"Estilo visual: {c.visual_style or 'realista'}.",
             f"Referências criativas: {c.references}." if c.references else "",
             f"RESTRIÇÕES EDITORIAIS (obrigatórias): {c.restrictions}." if c.restrictions else "",
             f"Termos PROIBIDOS (nunca use): {', '.join(c.forbidden_terms)}." if c.forbidden_terms else "",
             (f"Formato: {'vídeo vertical curto (Shorts/Reels)' if t.id == 'vertical' else 'vídeo horizontal'}; a narração deve durar "
              f"entre {t.min_seconds} e {t.max_seconds} segundos.") if t else ""]
    return " ".join(p for p in parts if p)


def _forbidden(c: FactoryConfig, text: str) -> None:
    hits = sorted({t for t in c.forbidden_terms if t.strip() and re.search(rf"(?<!\w){re.escape(t.strip())}(?!\w)", text, re.I)})
    if hits:
        raise StepError("o roteiro contém termos proibidos pelo padrão do canal: " + ", ".join(hits))

SCRIPT_SYS = ("Você é roteirista de vídeos de YouTube em português do Brasil. Responda SOMENTE com JSON válido. "
              "Narração falada em primeira pessoa do narrador, sem rubricas, sem emojis, sem marcações de cena, "
              "sem números por extenso errados, frases curtas e claras para leitura em voz alta.")


def script(ctx: StepContext) -> StepResult:
    c = _cfg(ctx)
    if c.script_text.strip():
        title = c.topic or c.script_text.strip().splitlines()[0][:100]
        _forbidden(c, c.script_text)
        ctx.log("usando roteiro fornecido pelo usuário (sem chamada de IA)")
        return StepResult({"title": title, "description": c.topic or title, "source": "user",
                           "sections": [{"heading": "", "text": c.script_text.strip()}]},
                          message="roteiro fornecido")
    total_words = int(c.minutes() * WPM)
    n = max(1, min(MAX_SECTIONS, math.ceil(total_words / 260)))
    identity = _identity(c)
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
    _forbidden(c, " ".join(str(outline["title"]).split() + [s["narration"] for d in done for s in d["scenes"]]))
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
def _voice_plan(c: FactoryConfig, ctx) -> tuple[str, str, dict]:
    """Define provedor/voz da narração. Indisponibilidade (não falha em execução) => Piper/eSpeak, registrado e visível no resultado."""
    v = c.voice
    if v.language.lower() != c.language.lower():
        raise StepError(f"o idioma da voz ({v.language}) difere do idioma do canal ({c.language}); a produção não foi iniciada com outra voz")
    provider, voice_id = voices.effective(v)
    params = {"speed": v.speed, "pitch": v.pitch, "style": v.style}
    engine = voices.ENGINES.get(provider)
    why = None
    if engine is None:
        why = f"provedor de voz desconhecido: {provider}"
    else:
        ok, reason = engine.available()
        if not ok:
            why = reason
        elif voice_id not in {x.id for x in engine.voices()}:
            why = f"voz '{voice_id}' inexistente em {engine.label}"
    if why is None:
        return provider, voice_id, params
    chain = [p for p in ("piper", "espeak") if p != provider]
    legacy = v.provider is None  # fábricas antigas sempre tiveram fallback para eSpeak
    if not (v.fallback or legacy):
        raise StepError(f"voz da fábrica indisponível ({why}) e o fallback está desativado")
    for p in chain:
        ok, _ = voices.ENGINES[p].available()
        if ok:
            ctx.log(f"voz '{provider}/{voice_id}' indisponível ({why}); usando {p} como fallback", "warn")
            ctx.fallback = {"requested": f"{provider}/{voice_id}", "reason": why}
            return p, voices.default_voice(p), params
    raise StepError(f"nenhum motor de voz disponível ({why})")


def narration(ctx: StepContext) -> StepResult:
    c = _cfg(ctx)
    ctx.fallback = None
    provider, voice_id, params = _voice_plan(c, ctx)
    files, entries, cost, tin, tout, model = [], [], 0.0, 0, 0, None
    for s in ctx.previous["scenes"]["scenes"]:
        try:
            r = voices.synthesize(provider, voice_id, s["narration"], params, gateway=ctx.ai, key=ctx.ai_key(f"tts{s['index']}"))
        except _engines.Unavailable as exc:
            raise StepError(f"voz indisponível: {exc}") from None
        except _engines.VoiceError as exc:  # nunca conclui sem áudio real; retry só para falhas transitórias
            raise StepError(f"falha na narração (cena {s['index']}, {provider}): {exc}", retryable=exc.retryable) from None
        cost += r.cost
        model, tin, tout = r.model or model, tin + (r.input_tokens or 0), tout + (r.output_tokens or 0)
        fn = f"cena_{s['index']:03d}.wav"
        files.append(OutFile(fn, "audio/wav", r.wav, provider=f"tts:{provider}", model=voice_id,
                             meta={"size": len(r.wav), "seconds": round(r.seconds, 2)}))
        entries.append({"index": s["index"], "key": f"runs/{ctx.run_id}/narration/{fn}", "seconds": r.seconds})
    total = sum(e["seconds"] for e in entries)
    t = c.target()
    est = total + GAP * len(entries)
    if t and not (t.min_seconds <= est <= t.max_seconds):  # falha controlada antes de gastar tempo de montagem
        raise StepError(f"a narração ({est:.0f}s) ficou fora da faixa do formato {t.id} ({t.min_seconds}–{t.max_seconds}s) definida no "
                        f"padrão do canal; ajuste a pauta/roteiro ou a faixa de duração")
    out = {"audio": entries, "engine": provider, "voice": voice_id, "seconds": total, "model": model,
           "style": params["style"] if voices.ENGINES[provider].controls.get("style") else None,
           "input_tokens": tin or None, "output_tokens": tout or None, "cost": cost}
    if ctx.fallback:
        out["fallback"] = ctx.fallback
    return StepResult(out, files=files,
                      message=f"narração ({provider}/{voice_id}{', FALLBACK' if ctx.fallback else ''}) de {total / 60:.1f} min")


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
    W, h = c.dims()
    vertical = h > W
    cw = 26 if vertical else 42  # largura de linha da legenda (caracteres)
    caps, t = [], 0.0
    for s in sc:
        d = au[s["index"]]
        caps += captions(s["narration"], t, d, max_chars=cw)
        t += d + GAP
    srt = "\n".join(f"{i}\n{_ts(a)} --> {_ts(b)}\n" + "\n".join(_wrap(x, cw)) + "\n" for i, (a, b, x) in enumerate(caps, 1))
    ass = ("[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\n\n[V4+ Styles]\n"
           "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
           "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
           "Style: Default,DejaVu Sans,%d,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.5,1,2,60,60,%d,1\n\n"
           "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n") % (
        W, h, round(min(W, h) * 0.05 * (0.9 if vertical else 1)), round(h * (0.12 if vertical else 0.07)))
    ass += "".join(f"Dialogue: 0,{_ts(a, True)},{_ts(b, True)},Default,,0,0,0,," + r"\N".join(_wrap(x, cw)) + "\n" for a, b, x in caps)
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
    W, H = c.dims()
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
                # zoompan expands one image into all frames. A static image must
                # instead loop for the entire narration, or FFmpeg stops early.
                vin = ["-i", img] if c.editing.ken_burns else ["-loop", "1", "-framerate", str(FPS), "-i", img]
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


def _mean_volume(path: str) -> float | None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-vn", "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, timeout=600)
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", r.stderr.decode(errors="ignore"))
    return float(m.group(1)) if m else None


def validate_output(c: FactoryConfig, kinds: dict, dur: float, narr: dict, volume: float | None) -> dict:
    """Confere o arquivo final contra o padrão do canal. Qualquer divergência => a produção NÃO é considerada concluída."""
    W, H = c.dims()
    t = c.target()
    v, checks = kinds["video"], []

    def chk(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    chk("resolução", (v["width"], v["height"]) == (W, H), f"{v['width']}x{v['height']} (esperado {W}x{H})")
    fmt = t.id if t else "horizontal"
    chk("proporção", abs(v["width"] / v["height"] - W / H) < 0.01, f"{'9:16' if fmt == 'vertical' else '16:9'} esperado ({fmt})")
    if t:
        chk("duração na faixa do formato", t.min_seconds <= dur <= t.max_seconds, f"{dur:.1f}s (faixa {t.min_seconds}–{t.max_seconds}s)")
    chk("áudio presente", "audio" in kinds and volume is not None and volume > -50,
        f"média {volume:.1f} dB" if volume is not None else "sem trilha de áudio mensurável")
    if c.standard_id:
        exp = voices.effective(c.voice)
        got = (narr.get("engine"), narr.get("voice"))
        fb = narr.get("fallback")
        chk("voz do padrão", got == exp or (bool(fb) and c.voice.fallback),
            f"usada {got[0]}/{got[1]}; padrão {exp[0]}/{exp[1]}" + (" (fallback autorizado)" if fb else ""))
        chk("idioma da voz", c.voice.language.lower() == c.language.lower(), f"{c.voice.language} / canal {c.language}")
    return {"ok": all(x["ok"] for x in checks), "checks": checks, "expected": {"format": fmt, "width": W, "height": H,
            "min_seconds": t.min_seconds if t else None, "max_seconds": t.max_seconds if t else None},
            "actual": {"width": v["width"], "height": v["height"], "duration_seconds": round(dur, 2), "mean_volume_db": volume},
            "standard": {"id": c.standard_id, "version": c.standard_version}}


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
        validation = validate_output(c, kinds, dur, ctx.previous["narration"], _mean_volume(path))
        if not validation["ok"]:
            raise StepError("o vídeo gerado não atende ao padrão do canal: " + "; ".join(
                f"{x['name']} ({x['detail']})" for x in validation["checks"] if not x["ok"]))
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
    meta = {"standard_id": c.standard_id, "standard_version": c.standard_version, "format": c.format or None,
            "channel": c.channel_name or c.name, "validation": validation, "pilot": c.pilot, "title": title, "description": desc, "duration_seconds": round(dur, 2), "width": kinds["video"]["width"],
            "height": kinds["video"]["height"], "video_codec": kinds["video"]["codec_name"], "audio_codec": kinds["audio"]["codec_name"],
            "script_source": ctx.previous["script"]["source"], "voice_engine": ctx.previous["narration"]["engine"], "voice": ctx.previous["narration"].get("voice"),
            "voice_model": ctx.previous["narration"].get("model"), "voice_style": ctx.previous["narration"].get("style"),
            "narration_seconds": round(ctx.previous["narration"]["seconds"], 2),
            "narration_tokens": [ctx.previous["narration"].get("input_tokens"), ctx.previous["narration"].get("output_tokens")],
            "narration_cost_usd": ctx.previous["narration"].get("cost"),
            "voice_fallback": ctx.previous["narration"].get("fallback"),
            "scenes": len(ctx.previous["scenes"]["scenes"]), "scenes_without_image": ctx.previous["images"]["missing"],
            "credits": credits if c.editing.credits else []}
    mb = json.dumps(meta, ensure_ascii=False, indent=2).encode()
    return StepResult({"title": title, "duration_seconds": round(dur, 2), "valid": True, "credits": len(credits),
                       "validation": validation, "standard_version": c.standard_version, "format": c.format or None},
                      files=[OutFile("miniatura.jpg", "image/jpeg", tdata, meta={"size": len(tdata)}),
                             OutFile("metadados.json", "application/json", mb, meta={"size": len(mb)})],
                      message=f"MP4 válido: {dur:.0f}s, {kinds['video']['width']}x{kinds['video']['height']}")


register(Pipeline(
    "video_youtube", "Vídeo para YouTube", "Roteiro (Gemini), imagens livres, narração local, legendas e MP4 (sem publicação).",
    FactoryConfig().identity(),
    [Step("script", script), Step("scenes", scenes), Step("images", images), Step("narration", narration),
     Step("subtitles", subtitles), Step("render", render), Step("export", export)]))
