import os

os.environ["DATABASE_URL"] = "sqlite://"

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.main import app
from app.pipelines.registry import PIPELINES, Pipeline, Step, StepResult
from app.runs import executor, models, service, tasks
from app.runs.models import ProductionLine, Run, now


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


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    storage, queue, delays = FakeStorage(), [], []

    def _db():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    monkeypatch.setattr("app.runs.router.get_storage", lambda: storage)
    monkeypatch.setattr(tasks, "enqueue", lambda run_id, countdown=0: queue.append((run_id, countdown)))
    yield Env(TestClient(app), Session, storage, queue, delays)
    app.dependency_overrides.clear()


def test_manual_run_persists_everything(env):
    lid = env.line({"cost_per_step": 0.5})
    rid = env.run(lid)
    env.drain()
    run = env.get(rid)
    assert run["status"] == "succeeded" and run["trigger"] == "manual"
    assert [s["name"] for s in run["steps"]] == ["prepare", "process", "package"]
    assert run["steps"][1]["output"]["processed"][0] == "ITEM-1"          # saída estruturada persistida
    assert run["steps"][1]["input"]["previous_steps"] == ["prepare"]      # entrada registrada
    assert run["cost"] == pytest.approx(1.5)
    assert run["steps_done"] == 3
    art = run["artifacts"][0]
    dl = env.c.get(f"/api/artifacts/{art['id']}/download")
    assert dl.status_code == 200 and "attachment" in dl.headers["content-disposition"]
    line = env.c.get(f"/api/lines/{lid}").json()
    assert line["products"] == 1 and line["cost_total"] == pytest.approx(1.5) and line["last_run"]["id"] == rid
    assert line["last_run_at"] is not None and line["active_run"] is None


def test_inactive_line_and_unknown_pipeline(env):
    lid = env.line()
    env.c.post(f"/api/lines/{lid}/deactivate")
    assert env.c.post(f"/api/lines/{lid}/run").status_code == 409
    assert env.c.post("/api/lines", json={"name": "x", "pipeline": "nope"}).status_code == 422
    assert env.c.get("/api/lines/xxx").status_code == 404


def test_duplicate_prevention(env):
    lid = env.line()
    rid = env.run(lid)
    assert env.c.post(f"/api/lines/{lid}/run").status_code == 409        # linha já tem execução ativa
    env.drain()
    with env.Session() as s:                                              # tarefa duplicada não reexecuta
        assert executor.execute_run(s, rid, env.storage) is None
    assert len(env.get(rid)["artifacts"]) == 1
    env.run(lid)                                                          # após concluir, pode rodar de novo


def test_retry_with_backoff_does_not_repeat_finished_steps(env):
    lid = env.line({"fail_step": "process", "fail_attempts": 2}, max_attempts=3, backoff_seconds=4)
    rid = env.run(lid)
    env.drain()
    run = env.get(rid)
    assert run["status"] == "succeeded"
    assert env.delays == [4, 8]                                           # backoff exponencial
    prepare, process, _ = run["steps"]
    assert prepare["total_attempts"] == 1 and process["total_attempts"] == 3


def test_failure_then_resume_from_failed_step(env):
    lid = env.line({"fail_step": "process", "fail_attempts": 1, "cost_per_step": 1}, max_attempts=1)
    rid = env.run(lid)
    env.drain()
    run = env.get(rid)
    assert run["status"] == "failed" and "process" in run["error"]
    assert [s["status"] for s in run["steps"]] == ["succeeded", "failed", "pending"]
    assert env.c.post(f"/api/runs/{rid}/resume").status_code == 200
    env.drain()
    run = env.get(rid)
    assert run["status"] == "succeeded"
    assert run["steps"][0]["total_attempts"] == 1                         # prepare não foi repetida
    assert run["cost"] == pytest.approx(3)                                # sem custo duplicado
    assert env.c.post(f"/api/runs/{rid}/resume").status_code == 409       # já concluída


def test_cancel_queued_and_resume(env):
    lid = env.line()
    rid = env.run(lid)
    assert env.c.post(f"/api/runs/{rid}/cancel").json()["status"] == "cancelled"
    env.drain()                                                           # tarefa enfileirada não executa
    assert env.get(rid)["steps"][0]["status"] == "cancelled"
    assert env.c.post(f"/api/runs/{rid}/cancel").status_code == 409
    env.c.post(f"/api/runs/{rid}/resume")
    env.drain()
    assert env.get(rid)["status"] == "succeeded"


def test_cancel_while_running_stops_between_steps(env, monkeypatch):
    def step1(ctx):
        with env.Session() as other:                                       # usuário cancela durante a etapa 1
            service.cancel_run(other, ctx.run_id)
        return StepResult({"a": 1})

    monkeypatch.setitem(PIPELINES, "cx", Pipeline("cx", "cx", "", {}, [Step("one", step1), Step("two", lambda c: StepResult({}))]))
    lid = env.c.post("/api/lines", json={"name": "c", "pipeline": "cx"}).json()["id"]
    env.c.post(f"/api/lines/{lid}/activate")
    rid = env.run(lid)
    env.drain()
    run = env.get(rid)
    assert run["status"] == "cancelled"
    assert [s["status"] for s in run["steps"]] == ["succeeded", "cancelled"]   # etapa em curso termina; seguinte não inicia


def test_run_budget_blocks_next_step_and_resume_after_raising(env):
    lid = env.line({"cost_per_step": 3}, cost_limit_run=5)
    rid = env.run(lid)
    env.drain()
    run = env.get(rid)
    assert run["status"] == "failed" and "orçamento" in run["error"]
    assert [s["status"] for s in run["steps"]] == ["succeeded", "succeeded", "pending"]
    env.c.post(f"/api/runs/{rid}/resume"); env.drain()
    assert env.get(rid)["status"] == "failed"                               # limite ainda baixo: não gasta mais
    env.c.patch(f"/api/lines/{lid}", json={"cost_limit_run": 100})
    env.c.post(f"/api/runs/{rid}/resume"); env.drain()
    run = env.get(rid)
    assert run["status"] == "succeeded" and run["cost"] == pytest.approx(9)


def test_monthly_budget(env):
    lid = env.line({"cost_per_step": 1.5}, cost_limit_month=2)
    rid = env.run(lid)
    env.drain()
    assert env.get(rid)["status"] == "failed"
    r = env.c.post(f"/api/lines/{lid}/run")
    assert r.status_code == 409 and "mensal" in r.json()["detail"]
    assert env.c.get(f"/api/lines/{lid}").json()["cost_month"] == pytest.approx(3.0)


def test_scheduler_tick(env):
    lid = env.line(interval_minutes=10)
    line = env.c.get(f"/api/lines/{lid}").json()
    assert line["next_run_at"] is not None
    started = []
    t0 = now()
    with env.Session() as s:
        s.execute(update(ProductionLine).values(next_run_at=t0 - timedelta(minutes=1)))
        s.commit()
        r = tasks.tick(s, lambda rid, countdown=0: started.append(rid), at=t0)
        assert len(r["started"]) == 1 and started == r["started"]
        # ainda não venceu de novo → nada
        assert tasks.tick(s, lambda *a, **k: started.append("x"), at=t0)["started"] == []
        # vence com execução ativa → pula, sem duplicar, e reagenda
        s.execute(update(ProductionLine).values(next_run_at=t0 - timedelta(seconds=1)))
        s.commit()
        r = tasks.tick(s, lambda *a, **k: started.append("x"), at=t0)
        assert r["started"] == [] and "execução ativa" in r["skipped"][0][1]
        assert len(s.scalars(select(Run)).all()) == 1
    env.queue.extend((rid, 0) for rid in started)
    env.drain()
    run = env.c.get("/api/runs").json()[0]
    assert run["trigger"] == "schedule" and run["status"] == "succeeded"


def test_scheduler_ignores_inactive_and_recovers_stale(env):
    lid = env.line(interval_minutes=1)
    env.c.post(f"/api/lines/{lid}/deactivate")
    assert env.c.get(f"/api/lines/{lid}").json()["next_run_at"] is None
    env.c.post(f"/api/lines/{lid}/activate")
    rid = env.run(lid)
    with env.Session() as s:
        s.execute(update(Run).where(Run.id == rid).values(status="running", heartbeat_at=now() - timedelta(hours=1)))
        s.commit()
        assert tasks.tick(s, lambda *a, **k: None)["recovered"] == [rid]
    assert env.get(rid)["status"] == "failed"


def test_line_edit_and_pipelines_listing(env):
    lid = env.line(interval_minutes=5)
    out = env.c.patch(f"/api/lines/{lid}", json={"name": "Novo", "interval_minutes": None, "cost_limit_month": 10}).json()
    assert out["name"] == "Novo" and out["next_run_at"] is None and out["cost_limit_month"] == 10
    assert env.c.get("/api/pipelines").json()[0]["steps"] == ["prepare", "process", "package"]
    assert env.c.get("/health").json() == {"status": "ok"}
