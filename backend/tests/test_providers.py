import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import crypto
from app.core.config import settings
from app.main import app
from app.providers.adapters import ADAPTERS
from app.providers.adapters import base as ab
from app.providers.adapters.base import Conn, ImageRequest, ProviderError, TextRequest
from app.providers.models import Provider

KEY = "sk-SECRET-1234567890abcd"
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * 20).decode()


@pytest.fixture
def transport():
    """Substitui o HTTP real; devolve a lista de requisições capturadas."""
    seen, handler = [], {}

    def respond(req: httpx.Request):
        seen.append(req)
        return handler["fn"](req)

    ab.set_client_factory(lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    yield seen, handler
    ab.set_client_factory(lambda: httpx.Client(timeout=ab.TIMEOUT))


def mcfg(service, model_id):
    return next(m for m in ADAPTERS[service].known_models if m["id"] == model_id)


# ---------- segurança ----------
def test_auth_required_and_login(env):
    anon = TestClient(app)
    assert anon.get("/api/lines").status_code == 401
    assert anon.get("/api/providers").status_code == 401
    assert anon.get("/health").status_code == 200 and anon.get("/api/health").status_code == 200
    assert anon.post("/api/auth/login", json={"token": "errado"}).status_code == 401
    assert anon.post("/api/auth/login", json={"token": settings.admin_token}).status_code == 200
    assert "httponly" in anon.post("/api/auth/login", json={"token": settings.admin_token}).headers["set-cookie"].lower()
    assert anon.get("/api/auth/me").status_code == 200          # cookie de sessão
    assert anon.get("/api/lines").status_code == 200
    anon.post("/api/auth/logout")
    assert anon.get("/api/lines").status_code == 401


def test_fail_closed_without_admin_token(env, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "")
    assert TestClient(app).get("/api/lines").status_code == 503


def test_credentials_encrypted_and_never_exposed(env):
    r = env.c.post("/api/providers", json={"name": "OAI", "service": "openai", "api_key": KEY})
    assert r.status_code == 201
    pid = r.json()["id"]
    for body in (r.text, env.c.get("/api/providers").text, env.c.get(f"/api/providers/{pid}").text):
        assert KEY not in body and "SECRET" not in body
    assert r.json()["has_credentials"] and r.json()["credentials_hint"] == "…abcd"
    with env.Session() as s:
        raw = s.get(Provider, pid).credentials_enc
    assert KEY not in raw and crypto.decrypt(raw) == KEY
    env.c.patch(f"/api/providers/{pid}", json={"name": "OAI2"})              # sem api_key: mantém
    with env.Session() as s:
        assert crypto.decrypt(s.get(Provider, pid).credentials_enc) == KEY
    assert env.c.post(f"/api/providers/{pid}/activate").json()["active"] is True
    out = env.c.patch(f"/api/providers/{pid}", json={"clear_credentials": True}).json()
    assert out["has_credentials"] is False and out["active"] is False
    assert env.c.post(f"/api/providers/{pid}/activate").status_code == 409  # exige credencial


def test_test_connection_scrubs_secret(env, transport):
    seen, handler = transport
    pid = env.c.post("/api/providers", json={"name": "OAI", "service": "openai", "api_key": KEY}).json()["id"]
    handler["fn"] = lambda req: httpx.Response(200, json={"data": [{"id": "a"}, {"id": "b"}]})
    out = env.c.post(f"/api/providers/{pid}/test").json()
    assert out["status"] == "ok" and "2 modelos" in out["status_message"]
    assert seen[0].url == "https://api.openai.com/v1/models" and seen[0].headers["authorization"] == f"Bearer {KEY}"
    handler["fn"] = lambda req: httpx.Response(401, text=f"bad key {KEY}")
    out = env.c.post(f"/api/providers/{pid}/test").json()
    assert out["status"] == "error" and KEY not in out["status_message"] and "401" in out["status_message"]


def test_ollama_test_discovers_models(env, transport):
    seen, handler = transport
    handler["fn"] = lambda req: httpx.Response(200, json={"models": [{"name": "llama3:8b"}]})
    pid = env.c.post("/api/providers", json={"name": "Ollama", "service": "ollama", "models": [],
                                              "base_url": "http://ollama:11434"}).json()["id"]
    out = env.c.post(f"/api/providers/{pid}/test").json()
    assert out["status"] == "ok" and out["models"][0]["id"] == "llama3:8b"
    assert str(seen[0].url) == "http://ollama:11434/api/tags"


# ---------- adaptadores (formato conforme documentação oficial) ----------
def test_openai_image_request_and_computed_cost(transport):
    seen, handler = transport
    handler["fn"] = lambda req: httpx.Response(200, json={
        "data": [{"b64_json": PNG}],
        "usage": {"input_tokens": 100, "output_tokens": 1056, "input_tokens_details": {"text_tokens": 100, "image_tokens": 0}}})
    ad, m = ADAPTERS["openai"], mcfg("openai", "gpt-image-2")
    est = ad.estimate("image", m, ImageRequest("a cat", aspect_ratio="2:3", quality="low"))
    assert est.cost is not None and float(est.cost) == pytest.approx(0.005, abs=1e-4)   # tabela low:1024x1536
    res = ad.image(Conn("openai", "https://api.openai.com/v1", KEY), "gpt-image-2", ImageRequest("a cat", aspect_ratio="2:3", quality="low"), m)
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/images/generations" and body["size"] == "1024x1536" and body["quality"] == "low"
    assert body["model"] == "gpt-image-2" and body["output_format"] == "png"
    # custo conciliado por tokens: 100*5/1e6 + 1056*30/1e6
    assert float(res.cost_actual) == pytest.approx(100 * 5 / 1e6 + 1056 * 30 / 1e6) and res.cost_source == "computed"


def test_openai_estimate_rules():
    ad, m = ADAPTERS["openai"], mcfg("openai", "gpt-image-2")
    assert ad.estimate("image", m, ImageRequest("x", aspect_ratio="16:9")).error          # proporção não suportada
    assert ad.estimate("image", m, ImageRequest("x", quality="auto")).error
    assert ad.estimate("image", m, ImageRequest("x", references=[("image/png", b"x")])).cost is None  # custo não estimável


def test_openai_text_responses_api(transport):
    seen, handler = transport
    handler["fn"] = lambda req: httpx.Response(200, json={
        "id": "resp_1", "output": [{"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": "Olá"}]}],
        "usage": {"input_tokens": 10, "output_tokens": 20}})
    m = mcfg("openai", "gpt-5-mini")
    res = ADAPTERS["openai"].text(Conn("openai", "https://api.openai.com/v1", KEY), "gpt-5-mini", TextRequest("oi", "seja breve", 50), m)
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/responses" and body["max_output_tokens"] == 50 and body["instructions"] == "seja breve" and body["store"] is False
    assert res.text == "Olá" and res.request_id == "resp_1"
    assert float(res.cost_actual) == pytest.approx((10 * 0.25 + 20 * 2.0) / 1e6)
    est = ADAPTERS["openai"].estimate("text", m, TextRequest("oi", None, 50))
    assert float(est.cost) == pytest.approx((3 * 0.25 + 50 * 2.0) / 1e6, rel=0.5)         # teto de saída incluído


def test_recraft_actual_cost_from_credits(transport):
    seen, handler = transport
    handler["fn"] = lambda req: httpx.Response(200, json={"data": [{"b64_json": PNG}], "credits": 40})
    m = mcfg("recraft", "recraftv3")
    res = ADAPTERS["recraft"].image(Conn("recraft", "https://external.api.recraft.ai/v1", KEY), "recraftv3",
                                    ImageRequest("dog", negative_prompt="gray", aspect_ratio="3:4"), m)
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/images/generations" and body["size"] == "3:4" and body["negative_prompt"] == "gray"
    assert body["response_format"] == "b64_json" and seen[0].headers["authorization"] == f"Bearer {KEY}"
    assert float(res.cost_actual) == pytest.approx(0.04) and res.cost_source == "provider"
    assert float(ADAPTERS["recraft"].estimate("image", m, ImageRequest("x", n=2)).cost) == pytest.approx(0.08)


def test_gemini_interactions_api(transport):
    seen, handler = transport
    handler["fn"] = lambda req: httpx.Response(200, json={"id": "i1", "steps": [
        {"type": "thought"}, {"type": "model_output", "content": [{"type": "image", "mime_type": "image/jpeg", "data": PNG}]}]})
    m = mcfg("gemini", "gemini-nano-banana-2.1")
    conn = Conn("gemini", "https://generativelanguage.googleapis.com/v1beta", KEY)
    res = ADAPTERS["gemini"].image(conn, "gemini-nano-banana-2.1", ImageRequest("x", aspect_ratio="3:4", resolution="2K"), m)
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1beta/interactions" and seen[0].headers["x-goog-api-key"] == KEY
    assert seen[0].headers["api-revision"] == "2026-05-20"
    assert body["response_format"] == {"type": "image", "mime_type": "image/jpeg", "aspect_ratio": "3:4", "image_size": "2K"}
    assert len(res.images) == 1 and res.request_id == "i1"
    assert float(ADAPTERS["gemini"].estimate("image", m, ImageRequest("x", resolution="2K")).cost) == pytest.approx(0.0504)
    assert ADAPTERS["gemini"].estimate("image", m, ImageRequest("x", resolution="8K")).error
    handler["fn"] = lambda req: httpx.Response(200, json={"id": "i2", "steps": [{"type": "model_output", "content": [{"type": "text", "text": "ok"}]}]})
    t = ADAPTERS["gemini"].text(conn, "gemini-3.1-flash-lite", TextRequest("hi", None, 77), mcfg("gemini", "gemini-3.1-flash-lite"))
    assert t.text == "ok" and json.loads(seen[-1].content)["generation_config"] == {"max_output_tokens": 77}


def test_ollama_text_and_http_errors(transport):
    seen, handler = transport
    handler["fn"] = lambda req: httpx.Response(200, json={"response": "oi", "prompt_eval_count": 3, "eval_count": 4})
    res = ADAPTERS["ollama"].text(Conn("ollama", "http://x:11434", None), "llama3", TextRequest("hi", None, 9), {})
    assert json.loads(seen[0].content) == {"model": "llama3", "prompt": "hi", "stream": False, "options": {"num_predict": 9}}
    assert res.text == "oi" and float(res.cost_actual) == 0
    handler["fn"] = lambda req: httpx.Response(400, text="bad")
    with pytest.raises(ProviderError) as e:
        ADAPTERS["ollama"].text(Conn("ollama", "http://x:11434", None), "llama3", TextRequest("hi"), {})
    assert not e.value.retryable and not e.value.uncertain

    def boom(req):
        raise httpx.ReadTimeout("t")
    handler["fn"] = boom
    with pytest.raises(ProviderError) as e:
        ADAPTERS["ollama"].text(Conn("ollama", "http://x:11434", None), "llama3", TextRequest("hi"), {})
    assert e.value.uncertain
