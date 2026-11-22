"""Catálogo unificado (locais + Gemini TTS) e síntese. Provedores de nuvem passam SEMPRE pelo AIGateway (orçamento/ledger)."""
from dataclasses import dataclass

from app.core.config import settings
from app.providers.adapters.base import ProviderError, SpeechRequest
from app.providers.adapters.gemini import TTS_MODELS
from app.providers.gateway import AIError
from app.studio.schemas import Voice as VoiceCfg
from app.voices.engines import LOCAL, Engine, Unavailable, VoiceError, Voice, wav_info

# As 30 vozes "pré-construídas" da doc (Kore, Charon…) são en-US "General American": lidas em português soam como
# americanos falando português (causa do feedback do PO em 2026-11-21). O catálogo usa só as vozes pt-BR nativas da
# biblioteca estendida (GET /v1beta/voices, language_code=pt-BR) e envia speechConfig.languageCode=pt-BR.
_cache: dict = {"t": 0.0, "voices": [], "key": ""}
APPROVED = ("pt-br-storyteller-10", "pt-br-storyteller-11", "pt-br-storyteller-5")  # naturalidade pt-BR aprovada pelo PO (2026-11-21)
PITCH_PT = {"low": "grave", "medium": "médio", "high": "agudo"}


def gemini_pt_br_voices() -> list[Voice]:
    import time
    key = settings.gemini_api_key
    if not key:
        return []
    if _cache["voices"] and _cache["key"] == key and time.time() - _cache["t"] < 3600:
        return _cache["voices"]
    from app.providers.adapters.base import request
    out, tok = [], None
    try:
        while True:
            url = "https://generativelanguage.googleapis.com/v1beta/voices?pageSize=1000" + (f"&pageToken={tok}" if tok else "")
            j = request("GET", url, headers={"x-goog-api-key": key}).json()
            out += [v for v in j.get("voices", []) if v.get("language_code") == "pt-BR"]
            tok = j.get("next_page_token")
            if not tok:
                break
    except ProviderError:
        return _cache["voices"] if _cache["key"] == key else []
    out.sort(key=lambda v: (0 if v["id"] in APPROVED else 1, 0 if "storyteller" in v["id"] else 1, v["id"]))
    voices = [Voice(v["id"], ("★ " if v["id"] in APPROVED else "") + f"{v.get('display_name', v['id'])} ({PITCH_PT.get(v.get('pitch'), v.get('pitch', ''))})",
                    "pt-BR", v.get("gender"), f"{v.get('accent', '')}; {v.get('persona', '')}. {v.get('description', '')}"[:300])
              for v in out]
    _cache.update(t=time.time(), voices=voices, key=key)
    return voices


FALLBACK = ("piper", None)  # Piper (voz padrão) é o fallback do sistema
MAX_SAMPLE_CHARS = 500


class GeminiTTS(Engine):
    def __init__(self):
        super().__init__("gemini", "Gemini TTS (nuvem)", "cloud", {"speed": None, "style": True, "pitch": None},
                         cost="Camada gratuita sem faturamento (US$ 0); com faturamento ~US$ 0,50–1,00 / 1M tokens de texto e "
                              "US$ 6–20 / 1M de áudio (25 tokens/s). Registrado no ledger como custo do gateway.",
                         limits="Sem controle numérico de velocidade (ritmo só via instrução de estilo); só vozes pt-BR nativas "
                                "(107, biblioteca estendida); limites de taxa da camada gratuita.",
                         requirements="GEMINI_API_KEY no .env (chave de projeto SEM faturamento para custo zero).",
                         quality_note="Neural generativo, aceita instruções de estilo; avalie pronúncia pt-BR de ouvido.")

    def available(self):
        return (True, "") if settings.gemini_api_key else (False, "GEMINI_API_KEY não configurada no servidor")

    def voices(self):
        return gemini_pt_br_voices()

    @property
    def model(self) -> str:
        m = settings.gemini_tts_model
        return m if m in TTS_MODELS else TTS_MODELS[0]


ENGINES: dict[str, Engine] = {**LOCAL, "gemini": GeminiTTS()}


@dataclass
class Result:
    wav: bytes
    seconds: float
    cost: float
    provider: str
    voice: str
    cached: bool = False
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


def catalog() -> list[dict]:
    out = []
    for e in ENGINES.values():
        ok, why = e.available()
        out.append({"id": e.id, "label": e.label, "kind": e.kind, "available": ok, "reason": why, "requirements": e.requirements,
                    "cost": e.cost, "limits": e.limits, "quality_note": e.quality_note, "languages": ["pt-BR"],
                    "controls": {"speed": e.controls.get("speed"), "style": e.controls.get("style"), "pitch": e.controls.get("pitch")},
                    "voices": [v.__dict__ for v in e.voices()],
                    "model": getattr(e, "model", None)})
    return out


def default_voice(provider: str) -> str | None:
    e = ENGINES[provider]
    if provider == "piper":
        return e.default_voice()
    vs = e.voices()
    return vs[0].id if vs else None


def check(provider: str, voice: str) -> Engine:
    e = ENGINES.get(provider)
    if e is None:
        raise VoiceError(f"provedor de voz desconhecido: {provider}")
    if voice not in {v.id for v in e.voices()}:
        raise VoiceError(f"voz '{voice}' não existe em {e.label}")
    return e


def synthesize(provider: str, voice: str, text: str, params: dict | None = None, *, gateway=None, key: str | None = None) -> Result:
    """Gera áudio real. Erros: Unavailable (motor ausente/não configurado) ou VoiceError (falha; `retryable` indica retry)."""
    params = params or {}
    text = text.strip()
    if not text:
        raise VoiceError("texto vazio")
    e = check(provider, voice)
    ok, why = e.available()
    if not ok:
        raise Unavailable(why)
    if e.id != "gemini":
        wav = e.synthesize(text, voice, params)
        return Result(wav, wav_info(wav)[0], 0.0, e.id, voice)
    if gateway is None or key is None:
        raise VoiceError("Gemini TTS requer o gateway de IA")
    from app.studio import assistant
    try:
        pid = assistant.provider_id()
        out = gateway.speech(pid, e.model, SpeechRequest(text, voice, (params.get("style") or "").strip() or None, params.get("language") or "pt-BR"), key)
    except (ProviderError, AIError) as exc:
        err = VoiceError(assistant.friendly(exc) if isinstance(exc, ProviderError) else str(exc))
        err.retryable = bool(getattr(exc, "retryable", False))
        raise err from None
    f = out.files[0]
    wav = gateway.storage.get(f.storage_key)
    return Result(wav, wav_info(wav)[0], float(out.cost), "gemini", voice, out.cached, e.model, out.input_tokens, out.output_tokens)


def effective(v: VoiceCfg) -> tuple[str, str | None]:
    """Provedor/voz efetivos de uma identidade vocal (fábricas antigas: `engine` legado + voz padrão)."""
    p = v.provider or v.engine
    return p, v.voice_id or default_voice(p)
