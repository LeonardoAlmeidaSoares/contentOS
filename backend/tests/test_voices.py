"""Laboratório de Vozes: catálogo, amostras, identidade, integração com o pipeline. Motores falsos só em testes (áudio WAV real)."""
import base64
import io
import json
import math
import struct
import wave

import httpx
import pytest

from app.core.config import settings
from app.pipelines.registry import StepContext
from app.pipelines import video
from app.providers.adapters import base as ab
from app.studio import assistant
from app.voices import service
from app.voices.engines import Engine, Unavailable, VoiceError, Voice


def tone(sec=1.0, rate=24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 20))) for i in range(int(rate * sec))))
    return buf.getvalue()


class FakeEngine(Engine):
    def __init__(self, id="piper", ok=True, fail=None, style=False):
        super().__init__(id, "Fake " + id, "local", {"speed": (0.6, 1.5), "style": style, "pitch": None})
        self.ok, self.fail, self.calls = ok, fail, []

    def available(self):
        return (True, "") if self.ok else (False, "indisponível no teste")

    def voices(self):
        return [Voice("v1", "Voz 1")]

    def default_voice(self):
        return "v1"

    def synthesize(self, text, voice_id, params):
        self.calls.append((text, voice_id, params))
        if self.fail:
            raise self.fail
        return tone(0.5 if len(text) < 50 else 1.0, 22050)


@pytest.fixture
def vo(env, monkeypatch):
    monkeypatch.setattr(assistant, "SessionLocal", env.Session)
    monkeypatch.setattr(assistant, "get_storage", lambda: env.storage)
    monkeypatch.setattr("app.voices.router.get_storage", lambda: env.storage)
    monkeypatch.setattr("app.voices.router.SessionLocal", env.Session)
    monkeypatch.setattr(settings, "gemini_api_key", "")
    fake = {"piper": FakeEngine("piper"), "kokoro": FakeEngine("kokoro", ok=False), "espeak": FakeEngine("espeak"),
            "gemini": service.ENGINES["gemini"]}
    monkeypatch.setattr(service, "ENGINES", fake)
    service._cache.update(t=0.0, voices=[], key="")
    env.fake = fake
    yield env
    ab.set_client_factory(lambda: httpx.Client(timeout=ab.TIMEOUT))


def gemini_audio(monkeypatch, *, raw_pcm=False, status=200):
    seen = []

    def respond(req: httpx.Request):
        if "/voices" in str(req.url):  # biblioteca estendida: só pt-BR deve entrar no catálogo
            return httpx.Response(200, json={"voices": [
                {"id": "pt-br-storyteller-10", "display_name": "Storyteller 10", "language_code": "pt-BR", "gender": "male", "pitch": "low",
                 "accent": "Brazilian Portuguese", "persona": "Storyteller & Narrator", "description": "x"},
                {"id": "kore", "display_name": "Kore", "language_code": "en-US", "gender": "female", "pitch": "high"},
                {"id": "pt-pt-x", "display_name": "PT", "language_code": "pt-PT"}]})
        seen.append(json.loads(req.content))
        if status != 200:
            return httpx.Response(status, json={"error": {}})
        wav = tone(1.0, 24000)
        data, mime = (wav[44:], "audio/l16; rate=24000; channels=1") if raw_pcm else (wav, "audio/wav")
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": mime,
            "data": base64.b64encode(data).decode()}}]}}], "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 25}})

    ab.set_client_factory(lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    return seen


def test_catalog_shows_unavailable_with_reason(vo):
    p = {x["id"]: x for x in vo.c.get("/api/voices/providers").json()["providers"]}
    assert p["kokoro"]["available"] is False and p["kokoro"]["reason"]
    assert p["gemini"]["available"] is False and "GEMINI_API_KEY" in p["gemini"]["reason"]
    assert p["gemini"]["controls"]["speed"] is None and p["gemini"]["controls"]["style"] is True  # não promete velocidade
    assert p["piper"]["available"] and p["piper"]["voices"][0]["id"] == "v1"


def test_sample_real_audio_and_playback(vo):
    r = vo.c.post("/api/voices/samples", json={"provider": "piper", "voice": "v1", "text": "Olá, mundo narrado.", "speed": 0.9})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["seconds"] > 0.4 and s["cost"] == 0 and s["params"] == {"speed": 0.9}
    a = vo.c.get(s["audio_url"])
    assert a.status_code == 200 and a.headers["content-type"] == "audio/wav" and a.content[:4] == b"RIFF"
    assert vo.c.get("/api/voices/samples").json()[0]["id"] == s["id"]
    assert vo.c.delete(f"/api/voices/samples/{s['id']}").status_code == 204


def test_samples_have_distinct_stored_audio(vo):
    """Regressão: todas as amostras eram gravadas em 'voices/samples/None.wav' (sobrescrita) e tocavam o mesmo áudio."""
    a = vo.c.post("/api/voices/samples", json={"provider": "piper", "voice": "v1", "text": "Primeira amostra curta."}).json()
    vo.fake["espeak"].synthesize = lambda text, v, p: tone(2.0, 16000)
    b = vo.c.post("/api/voices/samples", json={"provider": "espeak", "voice": "v1", "text": "Segunda amostra bem diferente."}).json()
    ca, cb = vo.c.get(a["audio_url"]).content, vo.c.get(b["audio_url"]).content
    assert ca != cb and "None" not in a["audio_url"]
    with vo.Session() as s:
        from app.voices.models import VoiceSample
        keys = [v.storage_key for v in s.query(VoiceSample)]
        assert len(set(keys)) == 2 and not any("None" in k for k in keys)


def test_sample_unavailable_and_invalid_and_failure(vo):
    r = vo.c.post("/api/voices/samples", json={"provider": "kokoro", "voice": "v1", "text": "texto de teste"})
    assert r.status_code == 412 and "indispon" in r.json()["detail"]
    assert vo.c.post("/api/voices/samples", json={"provider": "piper", "voice": "nada", "text": "texto de teste"}).status_code == 422
    vo.fake["piper"].fail = VoiceError("explodiu")
    r = vo.c.post("/api/voices/samples", json={"provider": "piper", "voice": "v1", "text": "texto de teste"})
    assert r.status_code == 502 and vo.c.get("/api/voices/samples").json() == []  # nada salvo em falha


def test_style_ignored_when_unsupported(vo):
    vo.c.post("/api/voices/samples", json={"provider": "piper", "voice": "v1", "text": "texto de teste", "style": "misterioso", "pitch": 10})
    assert vo.fake["piper"].calls[0][2] == {}  # piper não tem estilo nem pitch: nada é enviado/prometido


@pytest.mark.parametrize("raw", [False, True])
def test_gemini_tts_through_gateway(vo, monkeypatch, raw):
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-FAKE")
    seen = gemini_audio(monkeypatch, raw_pcm=raw)
    r = vo.c.post("/api/voices/samples", json={"provider": "gemini", "voice": "pt-br-storyteller-10", "text": "Era uma vez, numa noite escura.",
                                               "style": "grave e pausada"})
    assert r.status_code == 201, r.text
    assert r.json()["seconds"] == pytest.approx(1.0, abs=0.05) and r.json()["cost"] == 0
    body = seen[0]
    assert body["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert body["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "pt-br-storyteller-10"
    assert body["generationConfig"]["speechConfig"]["languageCode"] == "pt-BR"  # nunca deixar o idioma para detecção automática
    assert body["contents"][0]["parts"][0]["speech_metadata"] == {"style": "grave e pausada"}
    assert "AIza-FAKE" not in r.text
    assert vo.c.get(r.json()["audio_url"]).content[:4] == b"RIFF"
    from app.providers.models import AIUsage
    with vo.Session() as s:
        u = s.query(AIUsage).one()
        assert u.capability == "speech" and u.scope == "lab" and u.status == "succeeded"


def test_gemini_catalog_only_native_pt_br_voices(vo, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-FAKE")
    gemini_audio(monkeypatch)
    g = next(p for p in vo.c.get("/api/voices/providers").json()["providers"] if p["id"] == "gemini")
    assert [v["id"] for v in g["voices"]] == ["pt-br-storyteller-10"] and g["voices"][0]["gender"] == "male"
    r = vo.c.post("/api/voices/samples", json={"provider": "gemini", "voice": "kore", "text": "texto de teste"})
    assert r.status_code == 422  # voz en-US não é aceita


def test_gemini_rate_limit_is_clear_error(vo, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-FAKE")
    gemini_audio(monkeypatch, status=429)
    r = vo.c.post("/api/voices/samples", json={"provider": "gemini", "voice": "pt-br-storyteller-10", "text": "texto de teste"})
    assert r.status_code == 502 and "Limite de uso" in r.json()["detail"]


def make_factory(vo, voice):
    cfg = {"name": "F", "theme": "terror", "voice": voice, "video_minutes": 1}
    return vo.c.post("/api/studio/factories", json={"config": cfg}).json()["id"]


def test_identity_save_and_legacy(vo):
    lid = make_factory(vo, {"engine": "piper", "speed": 1.0})
    g = vo.c.get(f"/api/voices/factories/{lid}").json()
    assert g["legacy"] is True and g["provider"] == "piper" and g["voice_id"] == "v1"
    r = vo.c.put(f"/api/voices/factories/{lid}", json={"provider": "piper", "voice_id": "v1", "speed": 0.85,
                                                       "instructions": "grave e pausada"})
    assert r.status_code == 200 and r.json()["legacy"] is False and r.json()["voice"]["speed"] == 0.85
    assert vo.c.get(f"/api/studio/factories/{lid}").json()["config"]["voice"]["provider"] == "piper"  # contrato antigo intacto
    assert vo.c.put(f"/api/voices/factories/{lid}", json={"provider": "kokoro", "voice_id": "v1"}).status_code == 412
    assert vo.c.put(f"/api/voices/factories/{lid}", json={"provider": "piper", "voice_id": "x"}).status_code == 422


def ctx_for(voice, scenes=("Primeira frase narrada.", "Segunda frase narrada.")):
    cfg = {"name": "F", "theme": "t", "voice": voice}
    prev = {"scenes": {"scenes": [{"index": i + 1, "narration": n} for i, n in enumerate(scenes)]}}
    return StepContext("run1", "narration", cfg, prev, 1)


def test_pipeline_narration_ok_and_sync_durations(vo):
    out = video.narration(ctx_for({"provider": "piper", "voice_id": "v1", "speed": 0.9})).output
    assert out["engine"] == "piper" and "fallback" not in out and len(out["audio"]) == 2
    assert all(a["seconds"] > 0.4 for a in out["audio"])
    assert vo.fake["piper"].calls[0][2]["speed"] == 0.9


def test_pipeline_fallback_to_piper_is_recorded(vo):
    ctx = ctx_for({"provider": "kokoro", "voice_id": "pm_alex"})
    res = video.narration(ctx)
    assert res.output["engine"] == "piper" and res.output["fallback"]["requested"] == "kokoro/pm_alex"
    assert "FALLBACK" in res.message and any(lv == "warn" for lv, _ in ctx.logs)


def test_pipeline_no_fallback_when_disabled_fails(vo):
    with pytest.raises(video.StepError, match="fallback está desativado"):
        video.narration(ctx_for({"provider": "kokoro", "voice_id": "pm_alex", "fallback": False}))


def test_pipeline_runtime_failure_never_completes(vo):
    vo.fake["piper"].fail = VoiceError("modelo corrompido")
    with pytest.raises(video.StepError, match="falha na narração"):
        video.narration(ctx_for({"provider": "piper", "voice_id": "v1"}))


def test_pipeline_legacy_engine_without_piper_uses_espeak(vo):
    vo.fake["piper"].ok = False
    out = video.narration(ctx_for({"engine": "piper"})).output
    assert out["engine"] == "espeak"


def test_pipeline_gemini_uses_gateway_and_is_idempotent(vo, monkeypatch):
    from app.providers.gateway import AIGateway
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-FAKE")
    monkeypatch.setattr(settings, "gemini_tts_model", "gemini-3.8-flash-lite-tts")
    seen = gemini_audio(monkeypatch)
    gw = AIGateway(vo.Session, vo.storage, scope="lab")
    ctx = ctx_for({"provider": "gemini", "voice_id": "pt-br-storyteller-10", "style": "misterioso"})
    ctx.ai = gw
    out = video.narration(ctx).output
    assert out["engine"] == "gemini" and len(seen) == 2
    assert out["model"] == "gemini-3.8-flash-lite-tts" and out["voice"] == "pt-br-storyteller-10" and out["input_tokens"] == 40
    assert out["style"] == "misterioso" and out["cost"] == 0
    assert {s["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] for s in seen} == {"pt-br-storyteller-10"}
    from app.providers.models import AIUsage
    with vo.Session() as s:
        reqs = [u.result["request"] for u in s.query(AIUsage).all()]
        assert reqs and all(r["voice"] == "pt-br-storyteller-10" and r["language"] == "pt-BR" for r in reqs)
    video.narration(ctx)  # retry: reaproveita (sem nova chamada/cobrança)
    assert len(seen) == 2


def test_interpret_validates_against_catalog(vo, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-FAKE")

    def reply(payload):
        def respond(req):
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}, "finishReason": "STOP"}],
                                             "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1}})
        ab.set_client_factory(lambda: httpx.Client(transport=httpx.MockTransport(respond)))

    reply({"provider": "piper", "voice": "v1", "speed": 0.8, "style": "grave e misteriosa", "explanation": "ok", "unsupported": ["grave"]})
    r = vo.c.post("/api/voices/interpret", json={"instruction": "masculina, grave, pausada e misteriosa"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["speed"] == 0.8 and j["style"] == "" and any("estilo" in u for u in j["unsupported"])  # piper não tem estilo
    reply({"provider": "piper", "voice": "inventada"})
    assert vo.c.post("/api/voices/interpret", json={"instruction": "qualquer coisa"}).status_code == 502
    monkeypatch.setattr(settings, "gemini_api_key", "")
    assert vo.c.post("/api/voices/interpret", json={"instruction": "qualquer coisa"}).status_code == 412
