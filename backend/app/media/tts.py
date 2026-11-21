"""Narração local e gratuita: Piper (neural, preferido) com fallback para eSpeak NG. Sem rede, sem custo."""
import os
import shutil
import subprocess
import wave

from app.core.config import settings


class TTSError(Exception):
    retryable = False


def available_engines() -> list[str]:
    out = []
    if shutil.which("piper") is not None or _piper_cmd():
        if os.path.exists(settings.tts_piper_model):
            out.append("piper")
    if shutil.which("espeak-ng"):
        out.append("espeak")
    return out


def _piper_cmd() -> list[str] | None:
    if shutil.which("piper"):
        return ["piper"]
    return None


def pick_engine(preferred: str) -> str:
    av = available_engines()
    if not av:
        raise TTSError("nenhum motor de voz local instalado (Piper/eSpeak NG ausentes na imagem do worker)")
    return preferred if preferred in av else av[0]


def synthesize(text: str, out_wav: str, voice: dict) -> str:
    """Gera WAV em `out_wav`. `voice`: {engine, speed(0.7-1.4), pitch(0-99, eSpeak)}. Devolve o motor usado."""
    engine = pick_engine(voice.get("engine", "piper"))
    speed = min(max(float(voice.get("speed", 1.0)), 0.6), 1.5)
    if engine == "piper":
        cmd = _piper_cmd() + ["-m", settings.tts_piper_model, "-f", out_wav, "--length-scale", f"{1 / speed:.2f}",
                              "--sentence-silence", "0.35"]
        r = subprocess.run(cmd, input=text.encode(), capture_output=True, timeout=300)
    else:
        v = voice.get("espeak_voice", "pt-br")
        cmd = ["espeak-ng", "-v", v, "-s", str(int(150 * speed)), "-p", str(int(voice.get("pitch", 40))), "-w", out_wav, text]
        r = subprocess.run(cmd, capture_output=True, timeout=300)
    if r.returncode != 0 or not os.path.exists(out_wav) or os.path.getsize(out_wav) < 100:
        raise TTSError(f"falha na síntese de voz ({engine}): {r.stderr.decode(errors='ignore')[:200]}")
    return engine


def wav_duration(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())
