"""Motores de voz LOCAIS (Piper, eSpeak NG, Kokoro). Todos devolvem WAV (bytes). Sem rede, sem custo.

Cada motor declara disponibilidade real (binário + modelo presentes) e seu catálogo de vozes. Nada é simulado:
motor ausente => `available() == (False, motivo)`.
"""
import glob
import io
import os
import re
import shutil
import subprocess
import tempfile
import threading
import wave
from dataclasses import dataclass, field

from app.core.config import settings


class VoiceError(Exception):
    retryable = False


class Unavailable(VoiceError):
    """Motor/provedor não instalado ou não configurado."""


@dataclass
class Voice:
    id: str
    label: str
    language: str = "pt-BR"
    gender: str | None = None  # só quando a fonte documenta
    note: str = ""


@dataclass
class Engine:
    id: str
    label: str
    kind: str  # local | cloud
    controls: dict = field(default_factory=dict)  # {"speed": (min, max) | None, "style": bool, "pitch": (min,max)|None}
    cost: str = ""
    limits: str = ""
    requirements: str = ""
    quality_note: str = ""

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def voices(self) -> list[Voice]:
        raise NotImplementedError

    def synthesize(self, text: str, voice_id: str, params: dict) -> bytes:
        raise NotImplementedError


def wav_info(data: bytes) -> tuple[float, int]:
    """(duração em segundos, taxa de amostragem); levanta VoiceError se não for WAV PCM válido."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            if w.getnframes() == 0:
                raise VoiceError("áudio vazio")
            return w.getnframes() / float(w.getframerate()), w.getframerate()
    except (wave.Error, EOFError):
        raise VoiceError("áudio gerado inválido") from None


def _speed(params: dict, lo=0.6, hi=1.5) -> float:
    return min(max(float(params.get("speed") or 1.0), lo), hi)


# ---------------------------------------------------------------- Piper
PIPER_META = {  # fonte: rhasspy/piper-voices (model cards); gênero conforme a descrição do dataset
    "faber": ("Faber", "male", "medium"), "cadu": ("Cadu", "male", "medium"),
    "jeff": ("Jeff", "male", "medium"), "edresson": ("Edresson", "male", "low"),
}


class Piper(Engine):
    def __init__(self):
        super().__init__("piper", "Piper (local)", "local", {"speed": (0.6, 1.5), "style": False, "pitch": None},
                         cost="Gratuito (roda no servidor).", limits="Sem controle de estilo/emoção; só velocidade.",
                         requirements="Binário `piper` e modelos .onnx em /opt/piper (já na imagem).",
                         quality_note="Neural leve e rápido; entonação mais monótona. É o fallback do sistema.")

    def _models(self) -> dict[str, str]:
        d = os.path.dirname(settings.tts_piper_model) or "/opt/piper"
        out = {}
        for f in sorted(glob.glob(os.path.join(d, "pt_BR-*.onnx"))):
            m = re.match(r"pt_BR-(.+?)-(low|medium|high|x_low)\.onnx$", os.path.basename(f))
            if m:
                out[f"{m.group(1)}-{m.group(2)}"] = f
        return out

    def available(self):
        if not shutil.which("piper"):
            return False, "binário `piper` não instalado no servidor"
        if not self._models():
            return False, "nenhum modelo pt_BR de Piper encontrado em /opt/piper"
        return True, ""

    def voices(self):
        out = []
        for vid in self._models():
            name, q = vid.rsplit("-", 1)
            label, gender, _ = PIPER_META.get(name, (name.title(), None, q))
            out.append(Voice(vid, f"{label} ({q})", "pt-BR", gender, "pt_BR-" + vid))
        return out

    def default_voice(self) -> str | None:
        base = os.path.basename(settings.tts_piper_model)
        m = re.match(r"pt_BR-(.+)\.onnx$", base)
        models = self._models()
        return m.group(1) if m and m.group(1) in models else next(iter(models), None)

    def synthesize(self, text, voice_id, params):
        ok, why = self.available()
        if not ok:
            raise Unavailable(why)
        model = self._models().get(voice_id)
        if not model:
            raise VoiceError(f"voz Piper desconhecida: {voice_id}")
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "o.wav")
            r = subprocess.run(["piper", "-m", model, "-f", out, "--length-scale", f"{1 / _speed(params):.2f}",
                                "--sentence-silence", "0.35"], input=text.encode(), capture_output=True, timeout=300)
            if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 100:
                raise VoiceError(f"falha na síntese (piper): {r.stderr.decode(errors='ignore')[:200]}")
            return open(out, "rb").read()


# ---------------------------------------------------------------- eSpeak NG
class ESpeak(Engine):
    def __init__(self):
        super().__init__("espeak", "eSpeak NG (local)", "local", {"speed": (0.6, 1.5), "style": False, "pitch": (0, 99)},
                         cost="Gratuito.", limits="Voz robótica; serve apenas como último recurso.",
                         requirements="Binário `espeak-ng`.", quality_note="Sintetizador formântico: claramente artificial.")

    def available(self):
        return (True, "") if shutil.which("espeak-ng") else (False, "binário `espeak-ng` não instalado")

    def voices(self):
        return [Voice("pt-br", "eSpeak pt-BR", "pt-BR", None, "robótica")]

    def synthesize(self, text, voice_id, params):
        ok, why = self.available()
        if not ok:
            raise Unavailable(why)
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "o.wav")
            r = subprocess.run(["espeak-ng", "-v", voice_id or "pt-br", "-s", str(int(150 * _speed(params))),
                                "-p", str(int(params.get("pitch", 40))), "-w", out, text], capture_output=True, timeout=300)
            if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 100:
                raise VoiceError(f"falha na síntese (espeak): {r.stderr.decode(errors='ignore')[:200]}")
            return open(out, "rb").read()


# ---------------------------------------------------------------- Kokoro (kokoro-onnx, modelo int8)
KOKORO_DIR = os.environ.get("KOKORO_DIR", "/opt/kokoro")
KOKORO_MODEL, KOKORO_VOICES = "kokoro-v1.0.int8.onnx", "voices-v1.0.bin"
_kokoro_lock, _kokoro = threading.Lock(), None


class Kokoro(Engine):
    def __init__(self):
        super().__init__("kokoro", "Kokoro 82M (local)", "local", {"speed": (0.6, 1.5), "style": False, "pitch": None},
                         cost="Gratuito (CPU do servidor).", limits="3 vozes pt-BR (1 feminina, 2 masculinas); só velocidade; "
                         "modelo int8 (~90 MB) — qualidade levemente inferior ao fp32.",
                         requirements=f"pacote `kokoro-onnx` e arquivos {KOKORO_MODEL} + {KOKORO_VOICES} em {KOKORO_DIR}.",
                         quality_note="Treinado principalmente em inglês; o suporte a pt-BR é secundário — avalie de ouvido.")

    def available(self):
        try:
            import kokoro_onnx  # noqa: F401
        except Exception:  # noqa: BLE001
            return False, "pacote `kokoro-onnx` não instalado no servidor"
        for f in (KOKORO_MODEL, KOKORO_VOICES):
            if not os.path.exists(os.path.join(KOKORO_DIR, f)):
                return False, f"modelo ausente: {f} em {KOKORO_DIR} (download não autorizado/realizado)"
        return True, ""

    def voices(self):
        return [Voice("pf_dora", "Dora", "pt-BR", "female", "pf_dora"), Voice("pm_alex", "Alex", "pt-BR", "male", "pm_alex"),
                Voice("pm_santa", "Santa", "pt-BR", "male", "pm_santa")]

    def _load(self):
        global _kokoro
        with _kokoro_lock:
            if _kokoro is None:
                from kokoro_onnx import Kokoro as K
                _kokoro = K(os.path.join(KOKORO_DIR, KOKORO_MODEL), os.path.join(KOKORO_DIR, KOKORO_VOICES))
            return _kokoro

    def synthesize(self, text, voice_id, params):
        ok, why = self.available()
        if not ok:
            raise Unavailable(why)
        if voice_id not in {v.id for v in self.voices()}:
            raise VoiceError(f"voz Kokoro desconhecida: {voice_id}")
        try:
            samples, rate = self._load().create(text, voice=voice_id, speed=_speed(params), lang="pt-br")
        except Exception as exc:  # noqa: BLE001
            raise VoiceError(f"falha na síntese (kokoro): {exc.__class__.__name__}: {str(exc)[:160]}") from None
        import numpy as np
        pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(int(rate))
            w.writeframes(pcm)
        return buf.getvalue()


LOCAL: dict[str, Engine] = {e.id: e for e in (Piper(), Kokoro(), ESpeak())}
