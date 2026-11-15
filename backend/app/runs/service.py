"""Regras de negócio de linhas e execuções (criação, orçamento, cancelamento, retomada)."""
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.pipelines.registry import PIPELINES
from app.providers.ledger import ledger_sum
from app.runs.models import ACTIVE_STATUSES, ProductionLine, Run, RunStep, now


class Conflict(Exception):
    """Operação recusada por estado/regra (vira HTTP 409)."""


def month_start(t: datetime) -> datetime:
    return t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def month_cost(db: Session, line_id: str, at: datetime | None = None) -> Decimal:
    at = at or now()
    total = db.scalar(select(func.coalesce(func.sum(Run.cost), 0)).where(
        Run.line_id == line_id, Run.created_at >= month_start(at)))
    return Decimal(total or 0)


def run_spent(db: Session, run: Run) -> Decimal:
    """Gasto da execução: etapas concluídas (já consolidadas) + consumo de IA das demais (reservas incluídas)."""
    done = [s for s in run.steps if s.status == "succeeded"]
    open_names = [s.name for s in run.steps if s.status != "succeeded"]
    return sum((s.cost for s in done), Decimal(0)) + ledger_sum(db, run_id=run.id, step_names=open_names)


def refresh_cost(db: Session, run: Run) -> None:
    run.cost = run_spent(db, run)


def budget_error(db: Session, run: Run, line: ProductionLine) -> str | None:
    if line.cost_limit_run is not None and run.cost >= line.cost_limit_run:
        return f"limite de custo por execução atingido ({run.cost} ≥ {line.cost_limit_run})"
    if line.cost_limit_month is not None:
        spent = month_cost(db, line.id)  # já inclui o custo parcial desta execução
        if spent >= line.cost_limit_month:
            return f"limite de custo mensal atingido ({spent} ≥ {line.cost_limit_month})"
    return None


def schedule_next(line: ProductionLine, base: datetime | None = None) -> None:
    if line.active and line.interval_minutes:
        line.next_run_at = (base or now()) + timedelta(minutes=line.interval_minutes)
    else:
        line.next_run_at = None


def start_run(db: Session, line: ProductionLine, trigger: str = "manual") -> Run:
    if line.archived_at is not None:
        raise Conflict("linha arquivada")
    if not line.active:
        raise Conflict("linha inativa")
    if line.cost_limit_month is not None and month_cost(db, line.id) >= line.cost_limit_month:
        raise Conflict("limite de custo mensal atingido")
    pipeline = PIPELINES[line.pipeline]
    run = Run(line_id=line.id, pipeline=line.pipeline, trigger=trigger, config=dict(line.config))
    run.steps = [RunStep(position=i, name=s.name) for i, s in enumerate(pipeline.steps, start=1)]
    line.last_run_at = now()
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("já existe uma execução ativa para esta linha") from None
    return run


def cancel_run(db: Session, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise LookupError
    if run.status not in ACTIVE_STATUSES:
        raise Conflict(f"execução já finalizada ({run.status})")
    # Fila/espera de retry: cancela direto (atômico). Em execução: sinaliza e o executor para entre etapas.
    res = db.execute(update(Run).where(Run.id == run_id, Run.status.in_(("queued", "retrying"))).values(
        status="cancelled", finished_at=now(), error="cancelada pelo usuário", cancel_requested=True))
    if res.rowcount:
        for s in run.steps:
            if s.status in ("pending", "retrying"):
                s.status = "cancelled"
    else:
        run.cancel_requested = True
    db.commit()
    db.refresh(run)
    return run


def resume_run(db: Session, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise LookupError
    if run.status not in ("failed", "cancelled"):
        raise Conflict(f"só é possível retomar execuções falhas ou canceladas (atual: {run.status})")
    run.status, run.error, run.cancel_requested, run.finished_at = "queued", None, False, None
    for s in run.steps:  # etapas concluídas são preservadas e não reexecutam
        if s.status != "succeeded":
            s.status, s.attempts, s.message = "pending", 0, None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("já existe uma execução ativa para esta linha") from None
    return run


def create_lab_run(db: Session, config: dict) -> Run:
    """Execução avulsa do laboratório (sem linha): usa o mesmo motor, com 1 tentativa."""
    run = Run(line_id=None, pipeline="lab", trigger="lab", config=config)
    run.steps = [RunStep(position=1, name="generate")]
    db.add(run)
    db.commit()
    return run
