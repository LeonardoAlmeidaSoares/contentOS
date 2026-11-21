from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core import crypto
from app.core.db import get_db
from app.providers.adapters import ADAPTERS
from app.providers.adapters.base import Conn, ProviderError
from app.providers.gateway import scrub
from app.providers.ledger import ledger_sum
from app.providers.models import AIUsage, Provider
from app.runs.models import now
from app.runs.service import month_start

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    service: str
    base_url: str | None = None
    api_key: str | None = None  # somente escrita
    config: dict = {}
    models: list[dict] | None = None
    limit_month_usd: Decimal | None = Field(None, ge=0)


class ProviderPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    base_url: str | None = None
    api_key: str | None = None  # vazio/ausente = manter
    clear_credentials: bool = False
    config: dict | None = None
    models: list[dict] | None = None
    limit_month_usd: Decimal | None = Field(None, ge=0)


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    service: str
    service_label: str = ""
    base_url: str | None
    has_credentials: bool = False
    credentials_hint: str | None
    config: dict
    models: list[dict]
    capabilities: list[str] = []
    active: bool
    status: str
    status_message: str | None
    status_checked_at: datetime | None
    limit_month_usd: float | None
    month_cost: float = 0
    created_at: datetime


class UsageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    model: str
    capability: str
    scope: str
    run_id: str | None
    status: str
    cost_estimated: float
    cost_actual: float | None
    cost_effective: float
    cost_source: str
    cost_unknown: bool
    input_tokens: int | None
    output_tokens: int | None
    images: int
    duration_ms: int | None
    request_id: str | None
    error: str | None
    created_at: datetime


def out(db: Session, p: Provider) -> ProviderOut:
    o = ProviderOut.model_validate(p)
    o.service_label = ADAPTERS[p.service].label
    o.has_credentials = bool(p.credentials_enc)
    o.capabilities = sorted({c for m in p.models for c in m.get("capabilities", [])})
    o.month_cost = float(ledger_sum(db, provider_id=p.id, since=month_start(now())))
    return o


def _validate_models(models: list[dict]) -> list[dict]:
    seen = set()
    for m in models:
        if not isinstance(m.get("id"), str) or not m["id"]:
            raise HTTPException(422, "cada modelo precisa de 'id'")
        if m["id"] in seen:
            raise HTTPException(422, f"modelo duplicado: {m['id']}")
        seen.add(m["id"])
        if not set(m.get("capabilities", [])) <= {"text", "image"}:
            raise HTTPException(422, f"capacidades suportadas nesta fase: text, image ({m['id']})")
    return models


def _get(db: Session, pid: str) -> Provider:
    p = db.get(Provider, pid)
    if not p:
        raise HTTPException(404, "provedor não encontrado")
    return p


@router.get("/services")
def services():
    return [{"service": a.service, "label": a.label, "default_base_url": a.default_base_url, "needs_key": a.needs_key,
             "capabilities": list(a.capabilities), "known_models": a.known_models, "pricing_source": a.pricing_source}
            for a in ADAPTERS.values()]


@router.get("", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db)):
    return [out(db, p) for p in db.scalars(select(Provider).order_by(Provider.created_at))]


@router.post("", response_model=ProviderOut, status_code=201)
def create(body: ProviderIn, db: Session = Depends(get_db)):
    ad = ADAPTERS.get(body.service)
    if not ad:
        raise HTTPException(422, f"serviço desconhecido: {body.service}")
    p = Provider(name=body.name, service=body.service, base_url=body.base_url or ad.default_base_url, config=body.config,
                 models=_validate_models(body.models if body.models is not None else [dict(m) for m in ad.known_models]),
                 limit_month_usd=body.limit_month_usd)
    if body.api_key:
        p.credentials_enc, p.credentials_hint = crypto.encrypt(body.api_key), crypto.hint(body.api_key)
    db.add(p)
    db.commit()
    return out(db, p)


@router.get("/{pid}", response_model=ProviderOut)
def get(pid: str, db: Session = Depends(get_db)):
    return out(db, _get(db, pid))


@router.patch("/{pid}", response_model=ProviderOut)
def patch(pid: str, body: ProviderPatch, db: Session = Depends(get_db)):
    p = _get(db, pid)
    data = body.model_dump(exclude_unset=True)
    if body.api_key:
        p.credentials_enc, p.credentials_hint = crypto.encrypt(body.api_key), crypto.hint(body.api_key)
    if body.clear_credentials:
        p.credentials_enc = p.credentials_hint = None
        p.active = False
    if body.models is not None:
        p.models = _validate_models(body.models)
    for k in ("name", "base_url", "config", "limit_month_usd"):
        if k in data:
            setattr(p, k, data[k])
    db.commit()
    return out(db, p)


@router.post("/{pid}/activate", response_model=ProviderOut)
def activate(pid: str, db: Session = Depends(get_db)):
    p = _get(db, pid)
    if ADAPTERS[p.service].needs_key and not p.credentials_enc and not (
            p.service == "gemini" and (p.config or {}).get("key_source") == "env" and settings.gemini_api_key):
        raise HTTPException(409, "cadastre a credencial antes de ativar")
    p.active = True
    db.commit()
    return out(db, p)


@router.post("/{pid}/deactivate", response_model=ProviderOut)
def deactivate(pid: str, db: Session = Depends(get_db)):
    p = _get(db, pid)
    p.active = False
    db.commit()
    return out(db, p)


@router.post("/{pid}/test", response_model=ProviderOut)
def test_connection(pid: str, db: Session = Depends(get_db)):
    """Teste gratuito (listagem/saldo) — nunca executa geração paga."""
    p = _get(db, pid)
    ad = ADAPTERS[p.service]
    secret = crypto.decrypt(p.credentials_enc) if p.credentials_enc else None
    if not secret and p.service == "gemini" and (p.config or {}).get("key_source") == "env":
        secret = settings.gemini_api_key or None
    conn = Conn(p.service, (p.base_url or ad.default_base_url or "").rstrip("/"), secret, dict(p.config or {}))
    try:
        if ad.needs_key and not secret:
            raise ProviderError("GEMINI_API_KEY não configurada no servidor" if p.service == "gemini" else "credencial não cadastrada")
        msg = ad.test(conn)
        p.status, p.status_message = "ok", msg
        if p.service == "ollama" and not p.models:  # descobre os modelos instalados
            p.models = ad.discover(conn)
    except ProviderError as exc:
        p.status, p.status_message = "error", scrub(str(exc), secret)[:500]
    p.status_checked_at = now()
    db.commit()
    return out(db, p)


@router.get("/{pid}/usage")
def usage(pid: str, limit: int = 50, db: Session = Depends(get_db)):
    p = _get(db, pid)
    rows = db.scalars(select(AIUsage).where(AIUsage.provider_id == p.id).order_by(AIUsage.created_at.desc()).limit(min(limit, 200))).all()
    ms = month_start(now())
    agg = db.execute(select(func.coalesce(func.sum(AIUsage.cost_estimated), 0), func.coalesce(func.sum(AIUsage.cost_actual), 0),
                            func.count()).where(AIUsage.provider_id == p.id, AIUsage.status == "succeeded",
                                                AIUsage.cost_actual.is_not(None), AIUsage.created_at >= ms)).one()
    failures = db.scalar(select(func.count(AIUsage.id)).where(AIUsage.provider_id == p.id, AIUsage.status.in_(("failed", "uncertain")),
                                                              AIUsage.created_at >= ms))
    return {"items": [UsageOut.model_validate(r) for r in rows],
            "month": {"spent": float(ledger_sum(db, provider_id=p.id, since=ms)),
                      "limit": float(p.limit_month_usd) if p.limit_month_usd is not None else None,
                      "reconciled_calls": agg[2], "reconciled_estimated": float(agg[0]), "reconciled_actual": float(agg[1]),
                      "failures": failures}}
