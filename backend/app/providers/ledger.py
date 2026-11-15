"""Consultas ao livro-razão de consumo (AIUsage)."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.providers.models import COUNTED, AIUsage


def ledger_sum(db: Session, *, provider_id=None, run_id=None, step_names=None, scope=None, since: datetime | None = None) -> Decimal:
    q = select(func.coalesce(func.sum(AIUsage.cost_effective), 0)).where(AIUsage.status.in_(COUNTED))
    if provider_id:
        q = q.where(AIUsage.provider_id == provider_id)
    if run_id:
        q = q.where(AIUsage.run_id == run_id)
    if step_names is not None:
        q = q.where(AIUsage.step_name.in_(list(step_names)))
    if scope:
        q = q.where(AIUsage.scope == scope)
    if since:
        q = q.where(AIUsage.created_at >= since)
    return Decimal(db.scalar(q) or 0)
