import logging
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.publishing import tasks as pub_tasks
from app.publishing import youtube as yt
from app.publishing.models import YouTubeConnection, YouTubePublication
from app.runs.models import Artifact, Run, RunLog, RunStep

AT1, RT1, AT2 = "AT-secret-token-1", "RT-secret-token-1", "AT-secret-token-2"
VIDEO = b"\x00\x00\x00\x18ftypmp42" + b"v" * 700_000  # conteúdo fictício apenas para a lógica de envio (o MP4 real é testado no stack)
SCOPES = " ".join(yt.SCOPES)


class FakeGoogle:
    """Servidor Google FALSO usado somente nos testes automatizados."""

    def __init__(self):
        self.calls, self.uploads_created, self.received = [], 0, 0
        self.init_error = None       # (status, reason)
        self.refresh_error = None
        self.drop_first_chunk_response = False
        self.granted = SCOPES
        self.complete_id = "VID123"

    def __call__(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        self.calls.append((req.method, url.split("?")[0]))
        if url.startswith(yt.TOKEN_URL):
            f = parse_qs(req.content.decode())
            if f["grant_type"][0] == "refresh_token":
                if self.refresh_error:
                    return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Token has been revoked"})
                return httpx.Response(200, json={"access_token": AT2, "expires_in": 3600})
            return httpx.Response(200, json={"access_token": AT1, "refresh_token": RT1, "expires_in": 3600, "scope": self.granted})
        if url.startswith(yt.REVOKE_URL):
            return httpx.Response(200)
        if url.startswith(f"{yt.API}/channels"):
            return httpx.Response(200, json={"items": [{"id": "UC123", "snippet": {"title": "Canal Teste"}}]})
        if url.startswith(yt.UPLOAD_URL):
            if self.init_error:
                st, reason = self.init_error
                return httpx.Response(st, json={"error": {"code": st, "message": "x", "errors": [{"reason": reason}]}})
            self.uploads_created += 1
            self.body = req.content
            return httpx.Response(200, headers={"location": "https://upload.example/session/abc"})
        if url.startswith("https://upload.example/session/"):
            rng = req.headers["content-range"]
            if rng.startswith("bytes */"):
                total = int(rng.split("/")[1])
                if self.received >= total:
                    return httpx.Response(201, json={"id": self.complete_id})
                return httpx.Response(308, headers={"range": f"bytes=0-{self.received - 1}"} if self.received else {})
            span, total = rng.removeprefix("bytes ").split("/")
            a, b = map(int, span.split("-"))
            assert a == self.received, "bloco fora de ordem"
            self.received = b + 1
            if self.drop_first_chunk_response:
                self.drop_first_chunk_response = False
                raise httpx.ReadTimeout("resposta perdida")
            if self.received >= int(total):
                return httpx.Response(201, json={"id": self.complete_id})
            return httpx.Response(308, headers={"range": f"bytes=0-{self.received - 1}"})
        return httpx.Response(404)


@pytest.fixture
def g(env, monkeypatch):
    fake = FakeGoogle()
    yt.set_client_factory(lambda: httpx.Client(transport=httpx.MockTransport(fake)))
    monkeypatch.setattr(settings, "youtube_client_id", "cid.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "youtube_client_secret", "CLIENT-SECRET-XYZ")
    monkeypatch.setattr(yt, "CHUNK", 256 * 1024)
    monkeypatch.setattr(yt, "RETRY_SLEEP", 0)
    q = []
    monkeypatch.setattr(pub_tasks, "enqueue", lambda pid, resume=False: q.append((pid, resume)))
    fake.queue = q
    yield fake
    yt.set_client_factory(lambda: httpx.Client(timeout=120))


def make_run(env, status="succeeded"):
    with env.Session() as s:
        run = Run(pipeline="video_youtube", trigger="manual", status=status)
        run.steps = [RunStep(position=1, name="script", status="succeeded", output={"title": "Título Teste", "description": "Descrição.", "words": 10}),
                     RunStep(position=2, name="export", status="succeeded", output={"title": "Título Teste", "duration_seconds": 99.0})]
        s.add(run)
        s.flush()
        env.storage.put(f"runs/{run.id}/render/video.mp4", VIDEO, "video/mp4")
        s.add(Artifact(run_id=run.id, filename="video.mp4", content_type="video/mp4", size=len(VIDEO), storage_key=f"runs/{run.id}/render/video.mp4"))
        s.commit()
        return run.id


def connect(env):
    url = env.c.post("/api/youtube/connect").json()["auth_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    r = env.c.post("/api/youtube/callback", json={"redirect_url": f"http://127.0.0.1:8302/?state={state}&code=4/abc&scope=x"})
    assert r.status_code == 200, r.text
    return r.json()


PUB = {"title": "Meu vídeo", "description": "d", "tags": ["a"], "confirm": True}


def decide(env, rid, d, note=""):
    return env.c.post(f"/api/approvals/{rid}/decision", json={"decision": d, "note": note})


def run_upload(env, pid, resume=False):
    with env.Session() as s:
        pub_tasks.run_upload(s, pid, env.storage, resume)


def pubs(env):
    with env.Session() as s:
        return list(s.scalars(select(YouTubePublication)))


# ---- 1-4: regras de aprovação ----
def test_not_approved_cannot_publish(env, g):
    rid = make_run(env)
    connect(env)
    r = env.c.post(f"/api/approvals/{rid}/publish", json=PUB)
    assert r.status_code == 409 and "aprovada" in r.json()["detail"] and not pubs(env) and not g.queue


def test_approve_does_not_publish(env, g):
    rid = make_run(env)
    connect(env)
    before = len(g.calls)
    assert decide(env, rid, "approve").status_code == 200
    assert not pubs(env) and not g.queue and len(g.calls) == before
    d = env.c.get(f"/api/approvals/{rid}").json()
    assert d["review"]["status"] == "approved" and d["can_publish"] is True and d["defaults"]["title"] == "Título Teste"
    assert any("aprovada" in e["text"].lower() for e in d["events"])


@pytest.mark.parametrize("decision", ["request_changes", "reject"])
def test_changes_or_reject_block_publish_and_keep_files(env, g, decision):
    rid = make_run(env)
    connect(env)
    assert decide(env, rid, decision, "").status_code == 409  # motivo obrigatório
    assert decide(env, rid, decision, "narração fraca").status_code == 200
    r = env.c.post(f"/api/approvals/{rid}/publish", json=PUB)
    assert r.status_code == 409 and not pubs(env)
    d = env.c.get(f"/api/approvals/{rid}").json()
    assert d["video_artifact_id"] and d["review"]["note"] == "narração fraca"  # arquivos e histórico preservados
    assert env.storage.get(f"runs/{rid}/render/video.mp4") == VIDEO


def test_publish_requires_explicit_confirmation_and_private_only(env, g):
    rid = make_run(env)
    connect(env)
    decide(env, rid, "approve")
    assert env.c.post(f"/api/approvals/{rid}/publish", json={**PUB, "confirm": False}).status_code == 422
    assert env.c.post(f"/api/approvals/{rid}/publish", json={**PUB, "privacy": "public"}).status_code == 422
    assert not pubs(env)


def test_publish_requires_connected_channel(env, g):
    rid = make_run(env)
    decide(env, rid, "approve")
    r = env.c.post(f"/api/approvals/{rid}/publish", json=PUB)
    assert r.status_code == 409 and "conecte" in r.json()["detail"].lower()


# ---- 5-6: OAuth e segredos ----
def test_oauth_connect_stores_encrypted_and_hides_tokens(env, g, caplog):
    caplog.set_level(logging.DEBUG)
    st = env.c.get("/api/youtube/status").json()
    assert st["configured"] and st["status"] == "pending"
    url = env.c.post("/api/youtube/connect").json()["auth_url"]
    q = parse_qs(urlparse(url).query)
    assert q["scope"][0].split() == yt.SCOPES and q["code_challenge_method"] == ["S256"] and q["access_type"] == ["offline"]
    assert "password" not in url.lower() and "CLIENT-SECRET" not in url
    out = connect(env)
    assert out["channel"]["title"] == "Canal Teste" and out["status"] == "connected"
    with env.Session() as s:
        c = s.scalar(select(YouTubeConnection))
        assert RT1 not in c.refresh_token_enc and AT1 not in c.access_token_enc  # criptografados em repouso
    blob = env.c.get("/api/youtube/status").text + str(out) + caplog.text
    for secret in (RT1, AT1, "CLIENT-SECRET-XYZ"):
        assert secret not in blob


def test_callback_accepts_browser_error_page_text(env, g):
    url = env.c.post("/api/youtube/connect").json()["auth_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    text = (f"O Safari não pode abrir a página “http://127.0.0.1:8302/?state={state}&iss=https://accounts.google.com&code=4/0AUn6Hd-x"
            f"&scope=https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly” porque o Safari não pode se conectar.")
    r = env.c.post("/api/youtube/callback", json={"redirect_url": text})
    assert r.status_code == 200 and r.json()["status"] == "connected"


def test_oauth_rejects_bad_state_missing_scope_and_replay(env, g):
    url = env.c.post("/api/youtube/connect").json()["auth_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    assert env.c.post("/api/youtube/callback", json={"redirect_url": "http://127.0.0.1:8302/?state=errado&code=x"}).status_code == 409
    g.granted = yt.SCOPES[0]  # usuário desmarcou a permissão de leitura
    r = env.c.post("/api/youtube/callback", json={"redirect_url": f"http://127.0.0.1:8302/?state={state}&code=x"})
    assert r.status_code == 409 and "permiss" in r.json()["detail"].lower()
    assert env.c.post("/api/youtube/callback", json={"redirect_url": f"http://127.0.0.1:8302/?state={state}&code=x"}).status_code == 409  # uso único
    denied = env.c.post("/api/youtube/connect").json()
    assert env.c.post("/api/youtube/callback", json={"redirect_url": "http://127.0.0.1:8302/?error=access_denied"}).status_code == 409


def test_not_configured_blocks_connect(env, monkeypatch):
    monkeypatch.setattr(settings, "youtube_client_id", "")
    assert env.c.get("/api/youtube/status").json()["status"] == "unconfigured"
    assert env.c.post("/api/youtube/connect").status_code == 409


def test_refresh_and_revocation(env, g):
    connect(env)
    with env.Session() as s:  # expira o token de acesso
        from datetime import timedelta
        from app.runs.models import now
        c = s.scalar(select(YouTubeConnection))
        c.expires_at = now() - timedelta(minutes=1)
        s.commit()
    assert env.c.post("/api/youtube/check").json()["status"] == "connected"
    assert ("POST", yt.TOKEN_URL) in g.calls[-4:] or sum(1 for c in g.calls if c[1] == yt.TOKEN_URL) == 2
    with env.Session() as s:
        from datetime import timedelta
        from app.runs.models import now
        c = s.scalar(select(YouTubeConnection))
        c.expires_at = now() - timedelta(minutes=1)
        s.commit()
    g.refresh_error = True  # usuário revogou o acesso no Google
    out = env.c.post("/api/youtube/check").json()
    assert out["status"] == "revoked" and "Reconecte" in out["message"]


def test_disconnect_revokes_and_clears(env, g):
    connect(env)
    out = env.c.post("/api/youtube/disconnect").json()
    assert out["status"] == "pending" and out["channel"] is None
    assert ("POST", yt.REVOKE_URL) in g.calls
    with env.Session() as s:
        c = s.scalar(select(YouTubeConnection))
        assert c.refresh_token_enc is None and c.access_token_enc is None


# ---- 7-8: envio ----
def approved_and_connected(env):
    rid = make_run(env)
    connect(env)
    decide(env, rid, "approve")
    return rid


def test_successful_upload_is_private_and_recorded(env, g, caplog):
    caplog.set_level(logging.DEBUG)
    rid = approved_and_connected(env)
    r = env.c.post(f"/api/approvals/{rid}/publish", json=PUB)
    assert r.status_code == 202 and len(g.queue) == 1
    run_upload(env, g.queue[0][0])
    d = env.c.get(f"/api/approvals/{rid}").json()
    p = d["publications"][0]
    assert p["status"] == "succeeded" and p["video_id"] == "VID123" and p["url"].endswith("VID123") and p["privacy"] == "private"
    import json
    meta = json.loads(g.body)
    assert meta["status"]["privacyStatus"] == "private" and meta["snippet"]["title"] == "Meu vídeo"
    assert g.received == len(VIDEO) and g.uploads_created == 1
    with env.Session() as s:  # nenhum segredo em logs de evento nem em logging
        blob = " ".join(l.message for l in s.scalars(select(RunLog))) + caplog.text + str(p)
    for secret in (RT1, AT1, AT2, "session/abc", "CLIENT-SECRET-XYZ"):
        assert secret not in blob


def test_failed_upload_never_records_success(env, g):
    rid = approved_and_connected(env)
    g.init_error = (403, "quotaExceeded")
    env.c.post(f"/api/approvals/{rid}/publish", json=PUB)
    run_upload(env, g.queue[0][0])
    (p,) = pubs(env)
    assert p.status == "failed" and p.video_id is None and p.url is None and "Limite de uso" in p.error
    d = env.c.get(f"/api/approvals/{rid}").json()
    assert d["can_publish"] is True  # após falha definitiva é possível tentar de novo (nova confirmação)
    g.init_error = None
    assert env.c.post(f"/api/approvals/{rid}/publish", json=PUB).status_code == 202


def test_duplicate_requests_upload_once(env, g):
    rid = approved_and_connected(env)
    assert env.c.post(f"/api/approvals/{rid}/publish", json=PUB).status_code == 202
    assert env.c.post(f"/api/approvals/{rid}/publish", json=PUB).status_code == 409  # clique duplo
    pid = g.queue[0][0]
    run_upload(env, pid)
    run_upload(env, pid)  # tarefa entregue duas vezes
    assert g.uploads_created == 1 and len(pubs(env)) == 1
    assert env.c.post(f"/api/approvals/{rid}/publish", json=PUB).status_code == 409  # já publicado
    assert decide(env, rid, "reject", "x").status_code == 409  # decisão trava após o envio


def test_lost_response_resumes_without_duplicate(env, g):
    rid = approved_and_connected(env)
    env.c.post(f"/api/approvals/{rid}/publish", json=PUB)
    g.drop_first_chunk_response = True  # o servidor recebeu o bloco, mas a resposta se perdeu
    run_upload(env, g.queue[0][0])
    (p,) = pubs(env)
    assert p.status == "succeeded" and g.uploads_created == 1 and g.received == len(VIDEO)


def test_unconfirmable_network_failure_is_uncertain_then_resumed(env, g, monkeypatch):
    rid = approved_and_connected(env)
    env.c.post(f"/api/approvals/{rid}/publish", json=PUB)
    pid = g.queue[0][0]
    real = g.__call__
    down = {"on": True}

    def flaky(req):
        if down["on"] and str(req.url).startswith("https://upload.example"):
            raise httpx.ConnectError("sem rede")
        return real(req)

    yt.set_client_factory(lambda: httpx.Client(transport=httpx.MockTransport(flaky)))
    run_upload(env, pid)
    (p,) = pubs(env)
    assert p.status == "uncertain" and p.video_id is None and "Verificar envio" in p.error
    assert env.c.post(f"/api/approvals/{rid}/publish", json=PUB).status_code == 409  # não duplica enquanto incerto
    down["on"] = False
    run_upload(env, pid, resume=True)
    (p,) = pubs(env)
    assert p.status == "succeeded" and g.uploads_created == 1


def test_revoked_authorization_during_upload_fails_cleanly(env, g):
    rid = approved_and_connected(env)
    env.c.post(f"/api/approvals/{rid}/publish", json=PUB)
    with env.Session() as s:
        from datetime import timedelta
        from app.runs.models import now
        c = s.scalar(select(YouTubeConnection))
        c.expires_at = now() - timedelta(minutes=5)
        s.commit()
    g.refresh_error = True
    run_upload(env, g.queue[0][0])
    (p,) = pubs(env)
    assert p.status == "failed" and "Reconecte" in p.error and g.uploads_created == 0
    assert env.c.get("/api/youtube/status").json()["status"] == "revoked"
