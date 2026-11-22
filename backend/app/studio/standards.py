"""Padrão do Canal: versões persistentes e aprovadas que orientam as produções (Etapa 1 da missão "fábricas autônomas").

Regras:
- Toda versão é imutável; alterar = propor nova versão. Só a versão `approved` orienta produções (piloto pode usar `proposed`).
- A produção recebe um *snapshot* do padrão (config da execução) e registra `standard_id`/`standard_version`.
- Fábricas antigas (sem padrão) continuam produzindo como antes; podem criar o padrão a partir da config atual.
"""
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.runs import service, tasks
from app.runs.models import ProductionLine, Run, now
from app.runs.router import _conflict, run_full
from app.studio import assistant
from app.studio.models import ChannelStandard
from app.studio.schemas import FORMAT_LABELS, LABELS, FactoryConfig, preview as config_preview
from app.voices import service as voices

PIPELINE = "video_youtube"
router = APIRouter(prefix="/api/studio", tags=["studio-channels"])

FIELD_LABELS = {**LABELS, "channel_name": "Nome do canal", "niche": "Nicho", "description": "Descrição do canal",
                "platform": "Plataforma", "external_channel_id": "Canal externo", "formats": "Formatos",
                "tone": "Tom", "editing_rhythm": "Ritmo de edição", "references": "Referências criativas",
                "restrictions": "Restrições editoriais", "forbidden_terms": "Termos proibidos", "language": "Idioma"}


class StandardError_(Exception):
    pass


# ------------------------------------------------------------------ validação e diferenças
def problems(cfg: FactoryConfig) -> list[str]:
    """Pendências que impedem um padrão de ser usado em produção (mensagens apresentáveis)."""
    out = []
    if not cfg.name.strip():
        out.append("Informe o nome da fábrica.")
    if not (cfg.niche.strip() or cfg.theme.strip()):
        out.append("Informe o nicho do canal.")
    if not cfg.language.strip():
        out.append("Informe o idioma principal.")
    enabled = [f for f in cfg.formats if f.enabled]
    if not enabled:
        out.append("Habilite pelo menos um formato (horizontal ou vertical) com a faixa de duração.")
    if len({f.id for f in cfg.formats}) != len(cfg.formats):
        out.append("Cada formato pode aparecer apenas uma vez.")
    v = cfg.voice
    provider, voice_id = voices.effective(v)
    if v.language.lower() != cfg.language.lower():
        out.append(f"O idioma da voz ({v.language}) difere do idioma do canal ({cfg.language}).")
    eng = voices.ENGINES.get(provider)
    if eng is None:
        out.append(f"Provedor de voz desconhecido: {provider}.")
    elif provider != "gemini" and voice_id not in {x.id for x in eng.voices()}:
        out.append(f"A voz '{voice_id}' não existe em {eng.label}.")
    elif provider == "gemini" and not str(voice_id or "").startswith("pt-br-") and cfg.language.lower() == "pt-br":
        out.append("Escolha uma voz pt-BR do Gemini TTS.")
    return out


def _fmt(v) -> str:
    if isinstance(v, list) and v and isinstance(v[0], dict) and "id" in v[0] and "min_seconds" in v[0]:
        return "; ".join(f"{FORMAT_LABELS.get(f['id'], f['id'])} {f['min_seconds']}–{f['max_seconds']}s{'' if f['enabled'] else ' (desativado)'}"
                         for f in v) or "—"
    if isinstance(v, dict) and "provider" in v:
        return f"{v.get('provider') or v.get('engine')} · {v.get('voice_id') or 'padrão'} · estilo: {v.get('style') or '—'}"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)[:200]
    return str(v if v not in (None, "") else "—")


def diff(old: dict | None, new: dict) -> list[dict]:
    out = []
    for k in new:
        if old is None or old.get(k) != new[k]:
            out.append({"field": k, "label": FIELD_LABELS.get(k, k), "from": _fmt(old.get(k)) if old else None, "to": _fmt(new[k])})
    return out


# ------------------------------------------------------------------ operações
def standards_of(db: Session, line_id: str) -> list[ChannelStandard]:
    return list(db.scalars(select(ChannelStandard).where(ChannelStandard.line_id == line_id).order_by(ChannelStandard.version.desc())))


def current(db: Session, line_id: str) -> ChannelStandard | None:
    return db.scalar(select(ChannelStandard).where(ChannelStandard.line_id == line_id, ChannelStandard.status == "approved"))


def propose(db: Session, line: ProductionLine, cfg: FactoryConfig, *, note: str = "", pending: list[str] | None = None,
            origin: str = "manual") -> ChannelStandard:
    bad = problems(cfg)
    if bad:
        raise HTTPException(422, " ".join(bad))
    cfg.format, cfg.topic, cfg.script_text, cfg.pilot = "", "", "", False
    ident = cfg.identity()
    latest = db.scalar(select(ChannelStandard).where(ChannelStandard.line_id == line.id).order_by(ChannelStandard.version.desc()))
    base = latest.config if latest else (line.config or None)
    for _ in range(3):  # corrida de duas propostas simultâneas: tenta a próxima versão
        ver = (db.scalar(select(func.max(ChannelStandard.version)).where(ChannelStandard.line_id == line.id)) or 0) + 1
        s = ChannelStandard(line_id=line.id, version=ver, status="proposed", config=ident, changelog=diff(base, ident) if latest else [],
                            pending=pending or [], note=note[:1000], origin=origin)
        db.add(s)
        try:
            db.commit()
            return s
        except IntegrityError:
            db.rollback()
    raise HTTPException(409, "não foi possível criar a versão agora; tente novamente")


def approve(db: Session, sid: str, confirm_pending: bool) -> ChannelStandard:
    s = db.get(ChannelStandard, sid)
    if s is None:
        raise HTTPException(404, "versão não encontrada")
    if s.status != "proposed":
        raise HTTPException(409, f"só versões propostas podem ser aprovadas (atual: {s.status})")
    if s.pending and not confirm_pending:
        raise HTTPException(409, "há campos sugeridos pela IA que você não definiu; confirme-os explicitamente para aprovar")
    cfg = FactoryConfig.model_validate(s.config)
    bad = problems(cfg)
    if bad:
        raise HTTPException(422, " ".join(bad))
    db.execute(update(ChannelStandard).where(ChannelStandard.line_id == s.line_id, ChannelStandard.status == "approved")
               .values(status="superseded"))
    s.status, s.decided_at, s.pending = "approved", now(), []
    line = db.get(ProductionLine, s.line_id)
    line.config, line.name, line.description = s.config, cfg.name or line.name, cfg.niche or cfg.theme  # espelha a versão vigente
    db.commit()
    return s


def reject(db: Session, sid: str) -> ChannelStandard:
    s = db.get(ChannelStandard, sid)
    if s is None:
        raise HTTPException(404, "versão não encontrada")
    if s.status != "proposed":
        raise HTTPException(409, f"só versões propostas podem ser rejeitadas (atual: {s.status})")
    s.status, s.decided_at = "rejected", now()
    db.commit()
    return s


def start_production(db: Session, line: ProductionLine, s: ChannelStandard, fmt: str, topic: str, script_text: str,
                     trigger: str) -> Run:
    cfg = FactoryConfig.model_validate(s.config)
    target = next((f for f in cfg.formats if f.enabled and f.id == fmt), None)
    if target is None:
        raise HTTPException(422, f"o formato '{fmt}' não está habilitado neste padrão")
    over = {"format": fmt, "topic": topic.strip(), "script_text": script_text.strip(), "standard_id": s.id,
            "standard_version": s.version, "pilot": trigger == "pilot"}
    run = _conflict(service.start_run, db, line, trigger, over, False, base_config=s.config, standard=(s.id, s.version))
    tasks.enqueue(run.id)
    return run


# ------------------------------------------------------------------ prévia conceitual
PREVIEW_SYS = ("Você é diretor criativo de canais de vídeo. Responda SOMENTE com JSON válido em português do Brasil. "
               "Mostre como o canal soaria, respeitando rigorosamente o padrão recebido (nicho, tom, restrições, idioma).")


def make_preview(s: ChannelStandard) -> dict:
    cfg = FactoryConfig.model_validate(s.config)
    ident = {k: v for k, v in s.config.items() if k not in ("voice", "editing")}
    ident["voz"] = {"provedor": cfg.voice.provider or cfg.voice.engine, "voz": cfg.voice.voice_id, "estilo": cfg.voice.style}
    data, out = assistant.call_json(
        PREVIEW_SYS, "Padrão do canal: " + json.dumps(ident, ensure_ascii=False) +
        '\nDevolva {"titles": [3 títulos de vídeo], "script_sample": "abertura de roteiro com 3 a 5 frases, no tom do canal", '
        '"visual_direction": "2-3 frases sobre as imagens e a edição", "narration_direction": "2-3 frases sobre como o narrador deve falar"}.',
        max_tokens=1500, key=f"preview:{s.id}:{uuid.uuid4()}")
    pv = {"titles": [str(t)[:120] for t in (data.get("titles") or [])][:3], "script_sample": str(data.get("script_sample", ""))[:1200],
          "visual_direction": str(data.get("visual_direction", ""))[:600], "narration_direction": str(data.get("narration_direction", ""))[:600],
          "generated_at": datetime.utcnow().isoformat() + "Z", "cost": float(out.cost)}
    if not pv["script_sample"]:
        raise assistant.AssistantError("A IA não devolveu a prévia. Tente novamente.")
    return pv


# ------------------------------------------------------------------ API
class ChannelIn(BaseModel):
    config: dict
    pending: list[str] = Field(default_factory=list, max_length=40)
    origin: str = Field("manual", pattern="^(chat|manual|legacy)$")
    note: str = Field("", max_length=1000)


class ApproveIn(BaseModel):
    confirm_pending: bool = False


class ProduceIn(BaseModel):
    format: str = Field(pattern="^(horizontal|vertical)$")
    topic: str = Field("", max_length=300)
    script_text: str = Field("", max_length=40000)


def _cfg(raw: dict) -> FactoryConfig:
    try:
        return FactoryConfig.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"configuração inválida: {str(exc)[:300]}") from None


def _line(db: Session, lid: str) -> ProductionLine:
    line = db.get(ProductionLine, lid)
    if not line or line.pipeline != PIPELINE:
        raise HTTPException(404, "fábrica não encontrada")
    return line


def _std_out(s: ChannelStandard) -> dict:
    cfg = FactoryConfig.model_validate(s.config)
    return {"id": s.id, "version": s.version, "status": s.status, "config": s.config, "preview_rows": config_preview(cfg),
            "changelog": s.changelog, "pending": s.pending, "note": s.note, "origin": s.origin, "preview": s.preview,
            "created_at": s.created_at, "decided_at": s.decided_at, "problems": problems(cfg)}


def _run_out(r: Run) -> dict:
    ex = next((s.output or {} for s in r.steps if s.name == "export"), {})
    return {"id": r.id, "status": r.status, "trigger": r.trigger, "format": r.format, "standard_version": r.standard_version,
            "created_at": r.created_at, "finished_at": r.finished_at, "cost": float(r.cost), "error": r.error,
            "title": ex.get("title"), "duration_seconds": ex.get("duration_seconds"), "validation": ex.get("validation"),
            "steps_done": sum(1 for s in r.steps if s.status == "succeeded"), "steps_total": len(r.steps)}


@router.post("/channels", status_code=201)
def create_channel(body: ChannelIn, db: Session = Depends(get_db)):
    cfg = _cfg(body.config)
    cfg.name = cfg.name or cfg.channel_name or cfg.niche[:60]
    cfg.theme = cfg.theme or cfg.niche
    bad = problems(cfg)
    if bad:
        raise HTTPException(422, " ".join(bad))
    line = ProductionLine(name=cfg.name, description=cfg.niche or cfg.theme, pipeline=PIPELINE, active=False, config={},
                          cost_limit_run=1, cost_limit_month=10, max_attempts=3, backoff_seconds=20)
    db.add(line)
    db.commit()
    s = propose(db, line, cfg, note=body.note, pending=body.pending, origin=body.origin)
    return {"id": line.id, "standard": _std_out(s)}


@router.get("/factories/{lid}/channel")
def channel(lid: str, db: Session = Depends(get_db)):
    line = _line(db, lid)
    stds = standards_of(db, lid)
    runs = db.scalars(select(Run).where(Run.line_id == lid).order_by(Run.created_at.desc()).limit(20)).all()
    cur = next((s for s in stds if s.status == "approved"), None)
    return {"id": line.id, "name": line.name, "legacy": not stds, "legacy_config": FactoryConfig.model_validate(line.config).identity() if not stds else None,
            "current": _std_out(cur) if cur else None, "standards": [_std_out(s) for s in stds], "runs": [_run_out(r) for r in runs]}


@router.post("/factories/{lid}/standards", status_code=201)
def propose_version(lid: str, body: ChannelIn, db: Session = Depends(get_db)):
    line = _line(db, lid)
    cfg = _cfg(body.config)
    cfg.name = cfg.name or line.name
    cfg.theme = cfg.theme or cfg.niche
    return _std_out(propose(db, line, cfg, note=body.note, pending=body.pending, origin=body.origin))


@router.post("/standards/{sid}/approve")
def approve_version(sid: str, body: ApproveIn, db: Session = Depends(get_db)):
    return _std_out(approve(db, sid, body.confirm_pending))


@router.post("/standards/{sid}/reject")
def reject_version(sid: str, db: Session = Depends(get_db)):
    return _std_out(reject(db, sid))


@router.post("/standards/{sid}/preview")
def preview_version(sid: str, db: Session = Depends(get_db)):
    s = db.get(ChannelStandard, sid)
    if s is None:
        raise HTTPException(404, "versão não encontrada")
    try:
        s.preview = make_preview(s)
    except assistant.NotConfigured as exc:
        raise HTTPException(412, str(exc)) from None
    except assistant.AssistantError as exc:
        raise HTTPException(502, str(exc)) from None
    db.commit()
    return _std_out(s)


@router.post("/standards/{sid}/pilot", status_code=201)
def pilot(sid: str, body: ProduceIn, db: Session = Depends(get_db)):
    """Vídeo-piloto opcional: respeita o padrão proposto, nunca entra na fila de publicação."""
    s = db.get(ChannelStandard, sid)
    if s is None:
        raise HTTPException(404, "versão não encontrada")
    if s.status not in ("proposed", "approved"):
        raise HTTPException(409, f"não é possível gerar piloto de uma versão {s.status}")
    return run_full(start_production(db, db.get(ProductionLine, s.line_id), s, body.format, body.topic, body.script_text, "pilot"))


@router.post("/factories/{lid}/channel/produce", status_code=201)
def produce_channel(lid: str, body: ProduceIn, db: Session = Depends(get_db)):
    line = _line(db, lid)
    s = current(db, lid)
    if s is None:
        raise HTTPException(409, "esta fábrica não tem Padrão do Canal aprovado; aprove uma versão antes de produzir")
    if not body.topic.strip() and not body.script_text.strip():
        raise HTTPException(422, "informe a pauta do vídeo (o banco de pautas chega na próxima etapa)")
    return run_full(start_production(db, line, s, body.format, body.topic, body.script_text, "manual"))
