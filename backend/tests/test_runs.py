import os

os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.storage import get_storage
from app.main import app
from app.runs import executor, models  # noqa: F401
from app.runs.router import execute_run_task


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def put(self, key, data, content_type):
        self.objects[key] = data

    def get(self, key):
        return self.objects[key]

    def ping(self):
        pass


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    storage = FakeStorage()

    def _db():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_storage] = lambda: storage
    monkeypatch.setattr("app.runs.router.get_storage", lambda: storage)
    # executa a tarefa de forma síncrona e sem delay no lugar da fila
    def fake_delay(run_id):
        with Session() as s:
            executor.execute_run(s, run_id, storage, delay=0)
    monkeypatch.setattr(execute_run_task, "delay", fake_delay)
    yield TestClient(app), storage
    app.dependency_overrides.clear()


def test_liveness(env):
    client, _ = env
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health").status_code == 200


def test_run_end_to_end(env):
    client, storage = env
    created = client.post("/api/runs", json={"pipeline": "demo"})
    assert created.status_code == 201
    run = client.get(f"/api/runs/{created.json()['id']}").json()
    assert run["status"] == "succeeded"
    assert [s["status"] for s in run["steps"]] == ["succeeded"] * 3
    assert [s["name"] for s in run["steps"]] == ["prepare", "process", "package"]
    art = run["artifacts"][0]
    assert art["filename"] == "demo-output.json"
    dl = client.get(f"/api/artifacts/{art['id']}/download")
    assert dl.status_code == 200
    assert "attachment" in dl.headers["content-disposition"]
    assert dl.content == storage.objects[f"runs/{run['id']}/demo-output.json"]
    assert len(client.get("/api/runs").json()) == 1


def test_failure_is_persisted(env, monkeypatch):
    client, _ = env
    def boom(ctx):
        raise RuntimeError("falhou")
    monkeypatch.setitem(executor.PIPELINES, "demo", [("prepare", boom), ("process", boom), ("package", boom)])
    # as funções são resolvidas por nome em execute_run via PIPELINES
    run = client.post("/api/runs", json={"pipeline": "demo"}).json()
    run = client.get(f"/api/runs/{run['id']}").json()
    assert run["status"] == "failed"
    assert run["steps"][0]["status"] == "failed"
    assert run["steps"][1]["status"] == "pending"


def test_unknown_pipeline_and_404(env):
    client, _ = env
    assert client.post("/api/runs", json={"pipeline": "x"}).status_code == 422
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/artifacts/nope/download").status_code == 404
