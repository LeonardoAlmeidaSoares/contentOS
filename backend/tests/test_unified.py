"""Integration boundaries: approved identity, narrator changes and advanced execution."""
from app.runs import service, tasks
from app.runs.models import ProductionLine
from tests.test_channels import approve, create
from tests.test_voices import vo  # noqa: F401


def test_advanced_routes_cannot_bypass_standard(vo):
    lid, proposed = create(vo)
    approve(vo, proposed["id"])
    vo.c.post(f"/api/lines/{lid}/activate")
    before = len(vo.queue)
    assert vo.c.post(f"/api/lines/{lid}/run").status_code == 409
    assert vo.c.post(f"/api/studio/factories/{lid}/produce", json={"topic": "x"}).status_code == 409
    assert vo.c.patch(f"/api/lines/{lid}", json={"config": {"theme": "bypass"}}).status_code == 409
    assert vo.c.patch(f"/api/lines/{lid}", json={"interval_minutes": 1}).status_code == 409
    assert vo.c.patch(f"/api/lines/{lid}", json={"cost_limit_month": 5}).status_code == 200
    line = vo.c.get(f"/api/lines/{lid}").json()
    assert vo.c.patch(f"/api/lines/{lid}", json={"name": line["name"], "description": line["description"],
        "config": line["config"], "interval_minutes": line["interval_minutes"], "cost_limit_month": 7}).status_code == 200
    assert len(vo.queue) == before


def test_voice_choice_proposes_version_and_keeps_approved_narrator(vo):
    lid, proposed = create(vo)
    approve(vo, proposed["id"])
    changed = vo.c.put(f"/api/voices/factories/{lid}", json={"provider": "espeak", "voice_id": "v1"})
    assert changed.status_code == 200, changed.text
    data = changed.json()
    assert data["proposal"]["version"] == 2
    assert data["provider"] == "piper" and data["standard_version"] == 1
    channel = vo.c.get(f"/api/studio/factories/{lid}/channel").json()
    assert channel["current"]["config"]["voice"]["provider"] == "piper"
    assert approve(vo, data["proposal"]["id"]).status_code == 200
    effective = vo.c.get(f"/api/voices/factories/{lid}").json()
    assert effective["provider"] == "espeak" and effective["standard_version"] == 2


def test_voice_choice_keeps_pending_ai_confirmation(vo):
    from tests.test_channels import std_cfg
    response = vo.c.post("/api/studio/channels", json={"config": std_cfg(), "pending": ["voz", "tom"], "origin": "chat"})
    lid = response.json()["id"]
    changed = vo.c.put(f"/api/voices/factories/{lid}", json={"provider": "espeak", "voice_id": "v1"}).json()
    assert changed["awaiting_approval"]
    assert approve(vo, changed["proposal"]["id"]).status_code == 409


def test_scheduler_skips_versioned_factory(vo):
    lid, proposed = create(vo)
    approve(vo, proposed["id"])
    with vo.Session() as db:
        line = db.get(ProductionLine, lid)
        line.active = True
        from app.runs.models import now
        line.next_run_at = now()
        db.commit()
        emitted = []
        result = tasks.tick(db, enqueue_fn=emitted.append)
        assert len(result["skipped"]) == 1 and not emitted


def test_service_uses_canonical_standard_not_untrusted_identity(vo):
    lid, proposed = create(vo)
    approve(vo, proposed["id"])
    with vo.Session() as db:
        line = db.get(ProductionLine, lid)
        run = service.start_run(db, line, require_active=False,
            base_config={"theme": "ignored"}, standard=(proposed["id"], 1),
            overrides={"format": "horizontal", "topic": "teste", "voice": {"provider": "attacker"}, "pilot": True})
        assert run.config["voice"]["provider"] == "piper"
        assert run.config["theme"] != "ignored" and run.config["pilot"] is False
        assert run.standard_version == 1 and run.format == "horizontal"
        summary = vo.c.get(f"/api/runs/{run.id}").json()
        assert summary["standard_version"] == 1 and summary["standard_id"] == proposed["id"]
