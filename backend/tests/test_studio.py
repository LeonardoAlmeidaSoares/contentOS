import json
import os
import shutil
import subprocess

import httpx
import pytest

from app.core.config import settings
from app.media import sources
from app.providers.adapters import base as ab
from app.studio import assistant

ffmpeg_ok = shutil.which("ffmpeg") and (shutil.which("espeak-ng") or shutil.which("piper"))


@pytest.fixture
def studio(env, monkeypatch):
    monkeypatch.setattr(assistant, "SessionLocal", env.Session)
    monkeypatch.setattr(assistant, "get_storage", lambda: env.storage)
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-FAKE-KEY")
    return env


def gemini_reply(monkeypatch, payloads):
    """Gemini falso (apenas para testes): devolve os JSONs em sequência no formato real de generateContent."""
    seen, it = [], iter(payloads)

    def respond(req: httpx.Request):
        seen.append(req)
        body = {"candidates": [{"content": {"parts": [{"text": json.dumps(next(it))}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50}}
        return httpx.Response(200, json=body)

    ab.set_client_factory(lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    return seen


@pytest.fixture(autouse=True)
def _restore_http():
    yield
    ab.set_client_factory(lambda: httpx.Client(timeout=ab.TIMEOUT))


def test_chat_without_key_gives_instruction(env, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    r = env.c.post("/api/studio/chat", json={"messages": [{"role": "user", "content": "terror"}]})
    assert r.status_code == 412 and "GEMINI_API_KEY" in r.json()["detail"]
    assert env.c.get("/api/studio/status").json()["gemini"]["configured"] is False


READY = {"status": "ready", "message": "Pronto!", "config": {
    "name": "Noites Sombrias", "theme": "histórias de terror", "audience": "adultos", "video_minutes": 10,
    "frequency_per_week": 3, "narrative_style": "sombria", "visual_style": "cinematográfico",
    "voice": {"engine": "piper", "speed": 0.9, "pitch": 30, "description": "grave"},
    "editing": {"subtitles": True, "ken_burns": True, "resolution": "720p", "credits": True}}}


def test_chat_proposal_create_and_cost_recorded(studio, monkeypatch):
    seen = gemini_reply(monkeypatch, [READY])
    r = studio.c.post("/api/studio/chat", json={"messages": [{"role": "user", "content": "canal de terror, 10 min, 3x por semana"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready" and body["proposal"]["preview"][0]["label"] == "Nome da fábrica"
    assert body["usage"]["cost"] == 0 and body["usage"]["input_tokens"] == 100
    assert "AIza-FAKE-KEY" not in r.text and seen[0].headers["x-goog-api-key"] == "AIza-FAKE-KEY"
    assert ":generateContent" in str(seen[0].url)
    c = studio.c.post("/api/studio/factories", json={"config": body["proposal"]["config"]})
    assert c.status_code == 201
    f = studio.c.get(f"/api/studio/factories/{c.json()['id']}").json()
    assert f["config"]["video_minutes"] == 10 and f["interval_minutes"] == 7 * 24 * 60 // 3


def test_chat_missing_theme_asks_question(studio, monkeypatch):
    gemini_reply(monkeypatch, [{"status": "ready", "message": "", "config": {"theme": ""}}])
    b = studio.c.post("/api/studio/chat", json={"messages": [{"role": "user", "content": "quero um canal"}]}).json()
    assert b["status"] == "need_info" and b["questions"] and b["proposal"] is None


def test_rate_limit_message(studio, monkeypatch):
    ab.set_client_factory(lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, json={"error": {}}))))
    r = studio.c.post("/api/studio/chat", json={"messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 502 and "Limite de uso" in r.json()["detail"]


def test_adjust_keeps_config_valid(studio, monkeypatch):
    gemini_reply(monkeypatch, [READY, {**READY, "message": "Duração agora 5 min", "config": {**READY["config"], "video_minutes": 5}}])
    c = studio.c.post("/api/studio/chat", json={"messages": [{"role": "user", "content": "terror"}]}).json()
    fid = studio.c.post("/api/studio/factories", json={"config": c["proposal"]["config"]}).json()["id"]
    a = studio.c.post(f"/api/studio/factories/{fid}/adjust", json={"instruction": "vídeos de 5 minutos"}).json()
    assert a["proposal"]["config"]["video_minutes"] == 5
    studio.c.put(f"/api/studio/factories/{fid}", json={"config": a["proposal"]["config"]})
    assert studio.c.get(f"/api/studio/factories/{fid}").json()["config"]["video_minutes"] == 5


def test_range_download(env):
    from app.runs.models import Artifact, Run
    with env.Session() as s:
        run = Run(pipeline="demo", trigger="manual")
        s.add(run)
        s.flush()
        env.storage.put("k", b"0123456789", "video/mp4")
        art = Artifact(run_id=run.id, filename="v.mp4", content_type="video/mp4", size=10, storage_key="k")
        s.add(art)
        s.commit()
        aid = art.id
    r = env.c.get(f"/api/artifacts/{aid}/download", headers={"Range": "bytes=2-4"})
    assert r.status_code == 206 and r.content == b"234" and r.headers["content-range"] == "bytes 2-4/10"


SCRIPT = ("A casa ficava no fim da estrada. Ninguém sabia quem a construiu. Em noites de chuva, uma luz acendia na janela mais alta. "
          "Os moradores evitavam olhar para ela. Certa noite, um viajante bateu à porta e ouviu passos lentos do lado de dentro. "
          "A porta se abriu sozinha, e o frio tomou conta do corredor. Ele entendeu tarde demais que não estava só.")


@pytest.mark.skipif(not ffmpeg_ok, reason="requer ffmpeg e um motor de voz local (rodar no container)")
def test_video_pipeline_produces_valid_mp4(studio, monkeypatch, tmp_path):
    img = tmp_path / "a.jpg"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=s=1600x900", "-frames:v", "1", str(img)], check=True, capture_output=True)
    n = {"i": 0}

    def fake_find(queries, used, sources_pref="auto"):
        n["i"] += 1
        if n["i"] == 2:  # uma cena sem imagem -> cartão identificado
            return None, []
        return sources.Image(img.read_bytes(), "wikimedia", f"https://example.test/{n['i']}", "Teste", "Autor", "CC BY 4.0"), []

    monkeypatch.setattr("app.pipelines.video.sources.find_image", fake_find)
    cfg = {**READY["config"], "video_minutes": 1, "voice": {"engine": "espeak" if not shutil.which("piper") else "piper", "speed": 1.0}}
    lid = studio.c.post("/api/studio/factories", json={"config": cfg}).json()["id"]
    r = studio.c.post(f"/api/studio/factories/{lid}/produce", json={"topic": "A casa da estrada", "script_text": SCRIPT})
    assert r.status_code == 201, r.text
    studio.drain()
    run = studio.get(r.json()["id"])
    assert run["status"] == "succeeded", run
    names = {a["filename"] for a in run["artifacts"]}
    assert {"video.mp4", "legendas.srt", "miniatura.jpg", "metadados.json"} <= names
    assert [s["status"] for s in run["steps"]] == ["succeeded"] * 7
    vid = next(a for a in run["artifacts"] if a["filename"] == "video.mp4")
    p = tmp_path / "v.mp4"
    p.write_bytes(studio.c.get(f"/api/artifacts/{vid['id']}/download").content)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(p)],
                                      capture_output=True, check=True).stdout)
    assert {s["codec_type"] for s in probe["streams"]} == {"video", "audio"} and float(probe["format"]["duration"]) > 5
    meta = json.loads(studio.storage.get(next(a for a in run["artifacts"] if a["filename"] == "metadados.json") and
                                         f"runs/{run['id']}/export/metadados.json"))
    assert meta["scenes_without_image"] == 1 and meta["script_source"] == "user" and run["cost"] == 0
