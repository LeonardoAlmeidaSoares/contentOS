import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ADMIN_TOKEN"] = "test-admin-token-123456"
os.environ["CREDENTIALS_KEY"] = "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oNgqRdU0="  # chave fixa só para testes
os.environ["LAB_MONTH_LIMIT_USD"] = "10"
os.environ["STALE_RUN_MINUTES"] = "15"
os.environ["GEMINI_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.lab.seed import seed
from app.main import app
from app.runs import executor, tasks


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def put(self, key, data, content_type):
        self.objects[key] = data

    def get(self, key):
        return self.objects[key]

    def ping(self):
        pass


class Env:
    def __init__(self, client, Session, storage, queue, delays):
        self.c, self.Session, self.storage, self.queue, self.delays = client, Session, storage, queue, delays

    def drain(self):
        """Executa a fila como o worker faria (retries imediatos; o backoff é registrado em `delays`)."""
        while self.queue:
            run_id, countdown = self.queue.pop(0)
            with self.Session() as s:
                delay = executor.execute_run(s, run_id, self.storage)
            if delay is not None:
                self.delays.append(delay)
                self.queue.append((run_id, delay))

    def line(self, config=None, **kw):
        body = {"name": "L", "pipeline": "demo", "config": {"step_delay": 0, **(config or {})}, **kw}
        line = self.c.post("/api/lines", json=body).json()
        self.c.post(f"/api/lines/{line['id']}/activate")
        return line["id"]

    def run(self, line_id):
        r = self.c.post(f"/api/lines/{line_id}/run")
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def get(self, run_id):
        return self.c.get(f"/api/runs/{run_id}").json()

    def mock_provider(self):
        return next(p for p in self.c.get("/api/providers").json() if p["service"] == "mock")["id"]


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    storage, queue, delays = FakeStorage(), [], []
    with Session() as s:
        seed(s)

    def _db():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    monkeypatch.setattr("app.runs.router.get_storage", lambda: storage)
    monkeypatch.setattr("app.lab.router.get_storage", lambda: storage)
    monkeypatch.setattr(tasks, "enqueue", lambda run_id, countdown=0: queue.append((run_id, countdown)))
    yield Env(TestClient(app, headers={"Authorization": "Bearer test-admin-token-123456"}), Session, storage, queue, delays)
    app.dependency_overrides.clear()
