from datetime import timedelta

from sqlalchemy import select

from app.celery_app import celery
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.storage import get_storage
from app.runs.executor import execute_run
from app.runs.models import ProductionLine, Run, now
from app.runs.service import Conflict, schedule_next, start_run


def enqueue(run_id: str, countdown: int = 0) -> None:
    execute_run_task.apply_async(args=[run_id], countdown=countdown)


@celery.task(name="runs.execute")
def execute_run_task(run_id: str) -> None:
    with SessionLocal() as db:
        delay = execute_run(db, run_id, get_storage())
    if delay is not None:
        enqueue(run_id, countdown=delay)


def tick(db, enqueue_fn=enqueue, at=None) -> dict:
    """Agendador: dispara linhas vencidas e recupera execuções órfãs (worker interrompido)."""
    at = at or now()
    started, skipped, recovered = [], [], []
    for line in db.scalars(select(ProductionLine).where(
            ProductionLine.active.is_(True), ProductionLine.next_run_at.is_not(None),
            ProductionLine.next_run_at <= at)):
        try:
            run = start_run(db, line, "schedule")
            started.append(run.id)
            enqueue_fn(run.id)
        except Conflict as exc:  # execução ativa, orçamento mensal ou linha desativada: pula este ciclo
            db.rollback()
            skipped.append((line.id, str(exc)))
        db.refresh(line)
        schedule_next(line, at)
        db.commit()
    stale = at - timedelta(minutes=settings.stale_run_minutes)
    for run in db.scalars(select(Run).where(Run.status == "running", Run.heartbeat_at < stale)):
        run.status, run.error, run.finished_at = "failed", "worker interrompido (sem heartbeat); retome a execução", at
        recovered.append(run.id)
    db.commit()
    return {"started": started, "skipped": skipped, "recovered": recovered}


@celery.task(name="scheduler.tick")
def scheduler_tick() -> dict:
    with SessionLocal() as db:
        return tick(db)
