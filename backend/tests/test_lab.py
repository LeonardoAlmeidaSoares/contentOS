import json

import httpx
import pytest

from app.pipelines.registry import PIPELINES, Pipeline, Step, StepResult
from app.providers.adapters import ADAPTERS
from app.providers.adapters.base import ImageRequest, ProviderError
from app.providers.gateway import (AIGateway, BudgetExceeded, CostUnknown, UncertainDuplicate, check_budgets)
from app.providers.models import AIUsage, Provider


def gw(env, **kw):
    return AIGateway(env.Session, env.storage, **kw)


def count_calls(monkeypatch):
    calls = []
    orig = ADAPTERS["mock"].image

    def counted(conn, model, req, mcfg):
        calls.append(model)
        return orig(conn, model, req, mcfg)

    monkeypatch.setattr(ADAPTERS["mock"], "image", counted)
    return calls


def targets(env, *models):
    pid = env.mock_provider()
    return [{"provider_id": pid, "model": m} for m in models]


def exp(env, models=("mock-image-free",), prompt="a cat", **kw):
    body = {"kind": "image", "prompt": prompt, "targets": targets(env, *models), **kw}
    return env.c.post("/api/lab/experiments", json=body)


# ---------- gateway: orçamento, idempotência, conciliação ----------
def test_unknown_cost_requires_explicit_authorization(env):
    r = exp(env, ("mock-image-nopricing",))
    assert r.status_code == 409 and "allow_unknown_cost" in r.json()["detail"]
    with pytest.raises(CostUnknown):                                    # gateway também recusa (pipelines automáticos)
        gw(env).image(env.mock_provider(), "mock-image-nopricing", ImageRequest("x"), "k1")
    assert exp(env, ("mock-image-nopricing",), allow_unknown_cost=True).status_code == 201
    env.drain()


def test_provider_limit_counts_reservations_and_blocks_preventively(env, monkeypatch):
    calls = count_calls(monkeypatch)
    pid = env.mock_provider()
    env.c.patch(f"/api/providers/{pid}", json={"limit_month_usd": 0.6})
    with env.Session() as s:                                            # reserva "em voo" de outra chamada concorrente
        s.add(AIUsage(provider_id=pid, model="m", capability="image", idempotency_key="other", status="reserved",
                      cost_estimated=0.25, cost_effective=0.25))
        s.commit()
    g = gw(env)
    g.image(pid, "mock-image-paid", ImageRequest("a"), "k-a")           # 0.25 + 0.25 = 0.5 <= 0.6
    with pytest.raises(BudgetExceeded):                                  # 0.5 + 0.25 > 0.6 -> bloqueada ANTES de chamar
        g.image(pid, "mock-image-paid", ImageRequest("b"), "k-b")
    assert calls == ["mock-image-paid"]                                  # provedor chamado uma única vez


def test_idempotent_retry_does_not_charge_twice(env, monkeypatch):
    calls = count_calls(monkeypatch)
    pid = env.mock_provider()
    a = gw(env).image(pid, "mock-image-paid", ImageRequest("dog"), "same-key")
    b = gw(env).image(pid, "mock-image-paid", ImageRequest("dog"), "same-key")
    assert len(calls) == 1 and not a.cached and b.cached
    assert b.files[0].storage_key == a.files[0].storage_key
    with env.Session() as s:
        assert s.query(AIUsage).filter_by(idempotency_key="same-key").count() == 1


def test_failure_releases_budget_and_uncertain_is_never_repeated(env):
    pid = env.mock_provider()
    with pytest.raises(ProviderError):
        gw(env).image(pid, "mock-image-paid", ImageRequest("[fail]"), "kf")
    with env.Session() as s:
        u = s.query(AIUsage).filter_by(idempotency_key="kf").one()
        assert u.status == "failed" and u.cost_effective == 0 and u.error           # falha registrada, custo liberado
        assert s.get(Provider, pid).status == "error"
    assert gw(env).image(pid, "mock-image-paid", ImageRequest("ok"), "kf").text is None  # mesma chave: retry permitido
    with pytest.raises(ProviderError) as e:
        gw(env).image(pid, "mock-image-paid", ImageRequest("[timeout]"), "kt")
    assert e.value.uncertain and not e.value.retryable
    with pytest.raises(UncertainDuplicate):
        gw(env).image(pid, "mock-image-paid", ImageRequest("ok"), "kt")
    with env.Session() as s:                                                         # incerto continua contando custo
        assert float(s.query(AIUsage).filter_by(idempotency_key="kt").one().cost_effective) == 0.25


def test_reconciliation_estimate_vs_actual(env, monkeypatch):
    from app.providers.adapters import base as ab
    ab.set_client_factory(lambda: httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={"data": [{"b64_json": "iVBORw0KGgo="}], "credits": 40}))))
    try:
        pid = env.c.post("/api/providers", json={"name": "R", "service": "recraft", "api_key": "k" * 20}).json()["id"]
        env.c.post(f"/api/providers/{pid}/activate")
        out = gw(env).image(pid, "recraftv3", ImageRequest("x"), "rk")
        assert float(out.cost) == pytest.approx(0.04) and out.cost_source == "provider"
        u = env.c.get(f"/api/providers/{pid}/usage").json()
        assert u["items"][0]["cost_estimated"] == pytest.approx(0.04) and u["month"]["reconciled_actual"] == pytest.approx(0.04)
        assert u["items"][0]["status"] == "succeeded"
    finally:
        ab.set_client_factory(lambda: httpx.Client(timeout=ab.TIMEOUT))


# ---------- laboratório ----------
def test_lab_compare_models_side_by_side_and_rating(env):
    r = exp(env, ("mock-image-free", "mock-image-paid"), negative_prompt="gray", aspect_ratio="3:4")
    assert r.status_code == 201 and len(r.json()["results"]) == 2
    env.drain()
    e = env.c.get(f"/api/lab/experiments/{r.json()['id']}").json()
    free, paid = e["results"]
    assert free["status"] == paid["status"] == "succeeded"
    assert free["images"][0]["width"] == 192 and free["images"][0]["height"] == 256
    assert free["cost_effective"] == 0 and paid["cost_effective"] == pytest.approx(0.25)
    assert paid["duration_ms"] is not None and e["total_cost"] == pytest.approx(0.25)
    art = free["images"][0]["artifact_id"]
    dl = env.c.get(f"/api/artifacts/{art}/download?inline=1")
    assert dl.headers["content-type"] == "image/png" and dl.headers["content-disposition"].startswith("inline")
    arts = env.c.get("/api/artifacts").json()
    assert {a["model"] for a in arts} == {"mock-image-free", "mock-image-paid"} and arts[0]["provider"]   # proveniência
    rated = env.c.patch(f"/api/lab/results/{paid['id']}", json={"rating": 4, "notes": "bom"}).json()
    assert rated["rating"] == 4 and rated["notes"] == "bom"
    assert env.c.patch(f"/api/lab/results/{paid['id']}", json={"rating": 6}).status_code == 422
    hist = env.c.get("/api/lab/experiments").json()
    assert hist[0]["id"] == e["id"] and {r["rating"] for r in hist[0]["results"]} == {None, 4}


def test_lab_estimate_and_validation(env):
    body = {"kind": "image", "prompt": "x", "targets": targets(env, "mock-image-paid", "mock-image-free"), "n": 2}
    est = env.c.post("/api/lab/estimate", json=body).json()
    assert est["total_known"] == pytest.approx(0.5) and not est["has_unknown"] and est["lab_month_limit"] == 10
    assert exp(env, ("mock-image-free",), aspect_ratio="16:9").status_code == 422        # combinação não suportada
    assert exp(env, ("mock-image-paid",), references=["lab/refs/x.png"]).status_code == 422  # sem suporte a referência
    assert exp(env, ("nope",)).status_code == 422
    assert env.c.post("/api/lab/experiments", json={"kind": "image", "prompt": "x", "targets": []}).status_code == 422


def test_lab_budget_blocks_run_and_failure_is_recorded(env):
    big = exp(env, ("mock-image-paid",), n=4)           # 1.0 USD, dentro do teto de 10
    assert big.status_code == 201
    env.drain()
    for i in range(12):                                  # consome o teto do laboratório (10 USD)
        exp(env, ("mock-image-paid",), prompt=f"p{i}", n=4)
    env.drain()
    statuses = [r["status"] for e in env.c.get("/api/lab/experiments").json() for r in e["results"]]
    assert "failed" in statuses                          # os últimos foram bloqueados preventivamente
    blocked = next(e for e in env.c.get("/api/lab/experiments").json() if e["results"][0]["status"] == "failed")
    detail = env.c.get(f"/api/lab/experiments/{blocked['id']}").json()["results"][0]
    assert "Laboratório" in detail["error"]
    spent = env.c.get("/api/lab/budget").json()["lab_month_spent"]
    assert spent <= 10.0001


def test_lab_text_and_failure(env):
    r = env.c.post("/api/lab/experiments", json={"kind": "text", "prompt": "olá", "system": "s", "max_tokens": 64,
                                                 "targets": targets(env, "mock-text")}).json()
    env.drain()
    res = env.c.get(f"/api/lab/experiments/{r['id']}").json()["results"][0]
    assert res["status"] == "succeeded" and "eco: olá" in res["text"] and res["output_tokens"] and res["cost_effective"] is not None
    bad = exp(env, ("mock-image-free",), prompt="[fail]").json()
    env.drain()
    res = env.c.get(f"/api/lab/experiments/{bad['id']}").json()["results"][0]
    assert res["status"] == "failed" and "falha simulada" in res["error"]


def test_lab_reference_images(env):
    up = env.c.post("/api/lab/references", files={"file": ("r.png", b"\x89PNG\r\n\x1a\n" + b"0" * 30, "image/png")})
    assert up.status_code == 201
    assert env.c.post("/api/lab/references", files={"file": ("r.txt", b"hello", "text/plain")}).status_code == 422
    r = exp(env, ("mock-image-free",), references=[up.json()["key"]])
    assert r.status_code == 201
    env.drain()
    assert env.c.get(f"/api/lab/experiments/{r.json()['id']}").json()["results"][0]["status"] == "succeeded"


# ---------- benchmark ----------
def test_benchmark_prepared_not_executed(env):
    prompts = env.c.get("/api/lab/benchmark").json()
    assert [p["category"] for p in prompts] == ["Animais fofos — Bold & Easy", "Fantasia medieval", "Dinossauros infantis",
                                                 "Jardins e flores", "Arquitetura e vilarejos encantados"]
    for p in prompts:
        assert "white background" in p["prompt"] and "no watermark" in p["prompt"].lower() and p["negative_prompt"]
    body = {"targets": targets(env, "mock-image-paid"), "aspect_ratio": "3:4"}
    est = env.c.post("/api/lab/benchmark/estimate", json=body).json()
    assert est["prompts"] == 5 and est["generations"] == 5 and est["total_known"] == pytest.approx(1.25)
    assert env.c.get("/api/lab/experiments").json() == []                      # nada foi executado
    assert env.c.post("/api/lab/benchmark/run", json=body).status_code == 409   # exige confirmação do gasto
    assert env.c.post("/api/lab/benchmark/run", json={**body, "confirm_total_usd": 1.0}).status_code == 409
    ok = env.c.post("/api/lab/benchmark/run", json={**body, "confirm_total_usd": 1.25})
    assert ok.status_code == 201 and len(ok.json()["experiments"]) == 5
    env.drain()
    exps = env.c.get(f"/api/lab/experiments?batch_id={ok.json()['batch_id']}").json()
    assert len(exps) == 5 and all(e["results"][0]["status"] == "succeeded" for e in exps)


# ---------- integração com linhas: orçamento preventivo + retomada sem cobrança duplicada ----------
def test_line_budget_preventive_and_resume_no_double_charge(env, monkeypatch):
    calls = count_calls(monkeypatch)
    pid = env.mock_provider()

    def gen(ctx):
        for i in range(3):
            ctx.ai.image(pid, "mock-image-paid", ImageRequest(f"img{i}"), ctx.ai_key(f"img{i}"))
        return StepResult({"ok": True})

    monkeypatch.setitem(PIPELINES, "aigen", Pipeline("aigen", "aigen", "", {}, [Step("gen", gen)]))
    lid = env.c.post("/api/lines", json={"name": "ia", "pipeline": "aigen", "cost_limit_run": 0.6, "max_attempts": 2,
                                          "backoff_seconds": 0}).json()["id"]
    env.c.post(f"/api/lines/{lid}/activate")
    rid = env.run(lid)
    env.drain()
    run = env.get(rid)
    assert run["status"] == "failed" and "orçamento" in run["error"]
    assert len(calls) == 2 and run["cost"] == pytest.approx(0.5)               # 3ª chamada bloqueada antes de ocorrer
    assert env.delays == []                                                    # orçamento não gera retry
    env.c.patch(f"/api/lines/{lid}", json={"cost_limit_run": 5})
    env.c.post(f"/api/runs/{rid}/resume")
    env.drain()
    run = env.get(rid)
    assert run["status"] == "succeeded" and len(calls) == 3                   # 2 primeiras reaproveitadas pela idempotência
    assert run["cost"] == pytest.approx(0.75) and run["steps"][0]["cost"] == pytest.approx(0.75)
    logs = env.c.get(f"/api/runs/{rid}/logs").json()
    assert any("etapa iniciada" in l["message"] for l in logs) and any(l["level"] == "error" for l in logs)


def test_archive_line_preserves_history(env):
    lid = env.line()
    rid = env.run(lid)
    assert env.c.post(f"/api/lines/{lid}/archive").status_code == 409          # execução ativa
    env.drain()
    arch = env.c.post(f"/api/lines/{lid}/archive").json()
    assert arch["archived_at"] and arch["active"] is False and arch["next_run_at"] is None
    assert env.c.get("/api/lines").json() == []
    assert len(env.c.get("/api/lines?include_archived=true").json()) == 1
    assert env.c.post(f"/api/lines/{lid}/run").status_code == 409
    assert env.c.post(f"/api/lines/{lid}/activate").status_code == 409
    assert env.get(rid)["status"] == "succeeded" and env.c.get(f"/api/runs?line_id={lid}").json()   # histórico preservado
    assert env.c.post(f"/api/lines/{lid}/unarchive").json()["archived_at"] is None
