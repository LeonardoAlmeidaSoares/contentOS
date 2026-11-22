"""Etapa 1 — Fábrica = canal: Padrão versionado, aprovação, piloto e produção que obedece ao padrão (motores de voz falsos, FFmpeg real)."""
import json
import shutil
import subprocess

import pytest

from app.pipelines import video
from app.runs.models import Run
from app.studio.models import ChannelStandard
from app.studio.schemas import FactoryConfig
from tests.test_voices import FakeEngine, vo  # noqa: F401  (fixture `vo`: motores falsos + storage de teste)

ffmpeg_ok = shutil.which("ffmpeg") and shutil.which("ffprobe")
SCRIPT = ("A casa ficava no fim da estrada. Ninguém sabia quem a construiu. Em noites de chuva, uma luz acendia na janela mais alta. "
          "Os moradores evitavam olhar para ela. Certa noite, um viajante bateu à porta e ouviu passos lentos do lado de dentro. "
          "A porta se abriu sozinha, e o frio tomou conta do corredor. Ele entendeu tarde demais que não estava só.")


def std_cfg(**kw):
    base = {"name": "Relatos da Meia-Noite", "channel_name": "Relatos da Meia-Noite", "niche": "histórias de terror",
            "theme": "histórias de terror", "language": "pt-BR", "audience": "adultos", "tone": "sombrio e contido",
            "narrative_style": "narrador calmo", "visual_style": "fotos sombrias", "forbidden_terms": ["gore"],
            "formats": [{"id": "horizontal", "enabled": True, "min_seconds": 10, "max_seconds": 120}],
            "voice": {"provider": "piper", "voice_id": "v1", "language": "pt-BR", "fallback": False, "style": "calmo"}}
    base.update(kw)
    return base


def create(vo, **kw):
    r = vo.c.post("/api/studio/channels", json={"config": std_cfg(**kw), "origin": "manual"})
    assert r.status_code == 201, r.text
    return r.json()["id"], r.json()["standard"]


def approve(vo, sid, **body):
    return vo.c.post(f"/api/studio/standards/{sid}/approve", json=body)


@pytest.fixture
def prod(vo, monkeypatch, tmp_path):
    """Ambiente de produção real (FFmpeg) com busca de imagens falsa."""
    if not ffmpeg_ok:
        pytest.skip("requer ffmpeg/ffprobe (rodar no container)")
    img = tmp_path / "a.jpg"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=s=1600x900", "-frames:v", "1", str(img)], check=True, capture_output=True)
    n = {"i": 0}

    def fake_find(queries, used, sources_pref="auto"):
        from app.media import sources
        n["i"] += 1
        return sources.Image(img.read_bytes(), "wikimedia", f"https://example.test/{n['i']}", "Teste", "Autor", "CC BY 4.0"), []

    monkeypatch.setattr("app.pipelines.video.sources.find_image", fake_find)
    from tests.test_voices import tone
    vo.fake["piper"].synthesize = lambda text, voice_id, params: tone(5.0, 22050)  # cenas de 5 s => vídeo de ~15 s
    return vo


def probe(prod, run, tmp_path):
    vid = next(a for a in run["artifacts"] if a["filename"] == "video.mp4")
    p = tmp_path / "v.mp4"
    p.write_bytes(prod.c.get(f"/api/artifacts/{vid['id']}/download").content)
    out = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(p)],
                                    capture_output=True, check=True).stdout)
    return next(s for s in out["streams"] if s["codec_type"] == "video"), float(out["format"]["duration"])


# ------------------------------------------------------------------ persistência, versionamento e aprovação
def test_standard_versioning_and_approval(vo):
    lid, s1 = create(vo)
    assert s1["version"] == 1 and s1["status"] == "proposed" and not s1["problems"]
    r = vo.c.post(f"/api/studio/factories/{lid}/channel/produce", json={"format": "horizontal", "topic": "x"})
    assert r.status_code == 409 and "aprove" in r.json()["detail"]  # sem versão aprovada não há produção
    assert approve(vo, s1["id"]).json()["status"] == "approved"
    v2 = vo.c.post(f"/api/studio/factories/{lid}/standards", json={"config": std_cfg(tone="mais intenso", formats=[
        {"id": "horizontal", "enabled": True, "min_seconds": 15, "max_seconds": 150}])}).json()
    assert v2["version"] == 2 and v2["status"] == "proposed"
    assert {c["field"] for c in v2["changelog"]} == {"tone", "formats"}
    ch = vo.c.get(f"/api/studio/factories/{lid}/channel").json()
    assert ch["current"]["version"] == 1  # a nova proposta não altera a versão vigente
    assert approve(vo, v2["id"]).status_code == 200
    ch = vo.c.get(f"/api/studio/factories/{lid}/channel").json()
    assert ch["current"]["version"] == 2 and [s["status"] for s in ch["standards"]] == ["approved", "superseded"]
    assert ch["standards"][1]["config"]["tone"] == "sombrio e contido"  # versão anterior preservada intacta
    assert vo.c.post(f"/api/studio/standards/{s1['id']}/reject").status_code == 409  # só propostas podem ser rejeitadas
    with vo.Session() as s:
        assert s.query(ChannelStandard).filter_by(line_id=lid, status="approved").count() == 1


def test_reject_and_validation_problems(vo):
    lid, s1 = create(vo)
    assert vo.c.post(f"/api/studio/standards/{s1['id']}/reject").json()["status"] == "rejected"
    assert approve(vo, s1["id"]).status_code == 409
    for bad, msg in [({"formats": []}, "formato"), ({"voice": {**std_cfg()["voice"], "language": "en-US"}}, "idioma da voz"),
                     ({"voice": {**std_cfg()["voice"], "voice_id": "inexistente"}}, "não existe")]:
        r = vo.c.post("/api/studio/channels", json={"config": std_cfg(**bad)})
        assert r.status_code == 422 and msg in r.json()["detail"], r.text


def test_ai_suggested_fields_need_explicit_confirmation(vo):
    r = vo.c.post("/api/studio/channels", json={"config": std_cfg(), "pending": ["Formatos", "Voz"], "origin": "chat"})
    sid = r.json()["standard"]["id"]
    assert approve(vo, sid).status_code == 409
    ok = approve(vo, sid, confirm_pending=True)
    assert ok.status_code == 200 and ok.json()["pending"] == []


def test_legacy_factory_still_works_without_standard(vo):
    lid = vo.c.post("/api/studio/factories", json={"config": {"theme": "curiosidades", "voice": {"engine": "piper"}}}).json()["id"]
    ch = vo.c.get(f"/api/studio/factories/{lid}/channel").json()
    assert ch["legacy"] and ch["current"] is None
    # ao criar o padrão a partir da fábrica antiga, a edição direta passa a ser bloqueada (versionada)
    v = vo.c.post(f"/api/studio/factories/{lid}/standards", json={"config": std_cfg(name="Curiosidades", theme="curiosidades",
                                                                                   niche="curiosidades")})
    assert v.status_code == 201
    assert vo.c.put(f"/api/studio/factories/{lid}", json={"config": std_cfg()}).status_code == 409
    assert vo.c.post(f"/api/studio/factories/{lid}/produce", json={"topic": "x"}).status_code == 409


# ------------------------------------------------------------------ produção obedece ao padrão
def test_horizontal_production_uses_approved_version_and_is_validated(prod, tmp_path):
    lid, s1 = create(prod)
    approve(prod, s1["id"])
    r = prod.c.post(f"/api/studio/factories/{lid}/channel/produce", json={"format": "horizontal", "script_text": SCRIPT, "topic": "A casa"})
    assert r.status_code == 201, r.text
    prod.drain()
    run = prod.get(r.json()["id"])
    assert run["status"] == "succeeded", run
    with prod.Session() as s:
        row = s.get(Run, run["id"])
        assert (row.standard_id, row.standard_version, row.format) == (s1["id"], 1, "horizontal")
        assert row.config["standard_version"] == 1 and row.config["voice"]["voice_id"] == "v1"
    ex = next(st for st in run["steps"] if st["name"] == "export")["output"]
    assert ex["validation"]["ok"] and {c["name"] for c in ex["validation"]["checks"]} >= {
        "resolução", "proporção", "duração na faixa do formato", "áudio presente", "voz do padrão", "idioma da voz"}
    v, dur = probe(prod, run, tmp_path)
    assert (v["width"], v["height"]) == (1280, 720) and 10 <= dur <= 120
    meta = json.loads(prod.storage.get(f"runs/{run['id']}/export/metadados.json"))
    assert meta["standard_version"] == 1 and meta["format"] == "horizontal" and meta["validation"]["ok"]


def test_vertical_format_is_really_9x16(prod, tmp_path):
    cfg = std_cfg(formats=[{"id": "horizontal", "enabled": True, "min_seconds": 10, "max_seconds": 120},
                           {"id": "vertical", "enabled": True, "min_seconds": 10, "max_seconds": 120}])
    lid, s1 = create(prod, **{k: cfg[k] for k in ("formats",)})
    approve(prod, s1["id"])
    r = prod.c.post(f"/api/studio/factories/{lid}/channel/produce", json={"format": "vertical", "script_text": SCRIPT, "topic": "A casa"})
    prod.drain()
    run = prod.get(r.json()["id"])
    assert run["status"] == "succeeded", run
    v, _ = probe(prod, run, tmp_path)
    assert (v["width"], v["height"]) == (720, 1280)


def test_format_not_enabled_is_refused(prod):
    lid, s1 = create(prod)
    approve(prod, s1["id"])
    r = prod.c.post(f"/api/studio/factories/{lid}/channel/produce", json={"format": "vertical", "script_text": SCRIPT, "topic": "x"})
    assert r.status_code == 422 and "não está habilitado" in r.json()["detail"]


def test_duration_outside_range_fails_in_controlled_way(prod):
    lid, s1 = create(prod, formats=[{"id": "horizontal", "enabled": True, "min_seconds": 300, "max_seconds": 600}])
    approve(prod, s1["id"])
    r = prod.c.post(f"/api/studio/factories/{lid}/channel/produce", json={"format": "horizontal", "script_text": SCRIPT, "topic": "A casa"})
    prod.drain()
    run = prod.get(r.json()["id"])
    assert run["status"] == "failed" and "fora da faixa" in run["error"]
    assert not any(a["filename"] == "video.mp4" for a in run["artifacts"])  # nada foi montado nem aceito


def test_forbidden_term_fails_before_any_media(prod):
    lid, s1 = create(prod)
    approve(prod, s1["id"])
    r = prod.c.post(f"/api/studio/factories/{lid}/channel/produce",
                    json={"format": "horizontal", "script_text": SCRIPT + " Havia muito gore na sala.", "topic": "A casa"})
    prod.drain()
    run = prod.get(r.json()["id"])
    assert run["status"] == "failed" and "termos proibidos" in run["error"] and "gore" in run["error"]


def test_voice_language_mismatch_never_uses_another_voice(prod):
    lid, s1 = create(prod)
    approve(prod, s1["id"])
    with prod.Session() as s:  # simula padrão corrompido/legado (a API já bloqueia): o pipeline também se recusa
        row = s.get(ChannelStandard, s1["id"])
        row.config = {**row.config, "voice": {**row.config["voice"], "language": "en-US"}}
        s.commit()
    r = prod.c.post(f"/api/studio/factories/{lid}/channel/produce", json={"format": "horizontal", "script_text": SCRIPT, "topic": "x"})
    prod.drain()
    run = prod.get(r.json()["id"])
    assert run["status"] == "failed" and "idioma da voz" in run["error"]


def test_pilot_follows_proposed_standard_and_is_never_publishable(prod):
    lid, s1 = create(prod)  # versão ainda PROPOSTA: piloto é permitido, produção não
    r = prod.c.post(f"/api/studio/standards/{s1['id']}/pilot", json={"format": "horizontal", "script_text": SCRIPT, "topic": "Piloto"})
    assert r.status_code == 201, r.text
    prod.drain()
    run = prod.get(r.json()["id"])
    assert run["status"] == "succeeded" and run["trigger"] == "pilot"
    ex = next(st for st in run["steps"] if st["name"] == "export")["output"]
    assert ex["validation"]["ok"] and ex["standard_version"] == 1
    assert run["id"] not in [a["run_id"] for a in prod.c.get("/api/approvals?status=all").json()]
    assert prod.c.get(f"/api/approvals/{run['id']}").status_code == 404
    assert prod.c.post(f"/api/approvals/{run['id']}/decision", json={"decision": "approved"}).status_code in (404, 422)


def test_running_production_keeps_its_version_snapshot(prod):
    lid, s1 = create(prod)
    approve(prod, s1["id"])
    r = prod.c.post(f"/api/studio/factories/{lid}/channel/produce", json={"format": "horizontal", "script_text": SCRIPT, "topic": "A casa"})
    v2 = prod.c.post(f"/api/studio/factories/{lid}/standards", json={"config": std_cfg(tone="outro tom")}).json()
    approve(prod, v2["id"])  # nova versão aprovada ANTES de o worker executar
    prod.drain()
    run = prod.get(r.json()["id"])
    with prod.Session() as s:
        row = s.get(Run, run["id"])
        assert row.standard_version == 1 and row.config["tone"] == "sombrio e contido"


# ------------------------------------------------------------------ validação técnica do arquivo (unidade)
def kinds(w=1280, h=720):
    return {"video": {"width": w, "height": h, "codec_name": "h264"}, "audio": {"codec_name": "aac"}}


def cfg_for(**kw):
    c = FactoryConfig.model_validate({**std_cfg(**kw), "format": "horizontal", "standard_id": "s", "standard_version": 1})
    return c


def test_validate_output_detects_each_divergence(vo):
    narr = {"engine": "piper", "voice": "v1"}
    assert video.validate_output(cfg_for(), kinds(), 30, narr, -20.0)["ok"]
    assert not video.validate_output(cfg_for(), kinds(720, 1280), 30, narr, -20.0)["ok"]  # vertical onde se pediu 16:9
    assert not video.validate_output(cfg_for(), kinds(), 200, narr, -20.0)["ok"]  # acima da faixa
    assert not video.validate_output(cfg_for(), kinds(), 30, narr, -80.0)["ok"]  # áudio mudo
    assert not video.validate_output(cfg_for(), kinds(), 30, narr, None)["ok"]  # sem áudio mensurável
    other = video.validate_output(cfg_for(), kinds(), 30, {"engine": "espeak", "voice": "pt"}, -20.0)  # voz diferente
    assert not other["ok"] and any(c["name"] == "voz do padrão" and not c["ok"] for c in other["checks"])
