"""Executor: etapas sequenciais, resultados persistidos, retry com backoff, cancelamento e orçamento."""
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.storage import Storage
from app.pipelines.registry import PIPELINES, StepContext, load_all
from app.runs.models import Artifact, ProductionLine, Run, RunStep, now
from app.runs.service import budget_error

load_all()


def _finish(db: Session, run: Run, status: str, error: str | None = None) -> None:
    run.status, run.error, run.finished_at = status, error, now()
    db.commit()


def execute_run(db: Session, run_id: str, storage: Storage) -> int | None:
    """Executa/continua uma run. Devolve segundos até a próxima tentativa (retry) ou None."""
    # Claim atômico: só uma instância assume a run (idempotência contra tarefas duplicadas)
    claimed = db.execute(update(Run).where(Run.id == run_id, Run.status.in_(("queued", "retrying")))
                         .values(status="running", heartbeat_at=now())).rowcount
    db.commit()
    if not claimed:
        return None
    run = db.get(Run, run_id)
    db.refresh(run)
    run.started_at = run.started_at or now()
    line: ProductionLine | None = run.line
    pipeline = PIPELINES[run.pipeline]
    config = dict(line.config) if line else {}
    max_attempts = line.max_attempts if line else 1
    backoff = line.backoff_seconds if line else 0
    steps_by_name = {s.name: s for s in run.steps}

    for step_def in pipeline.steps:
        step = steps_by_name[step_def.name]
        if step.status == "succeeded":
            continue  # não repete etapa concluída (importante para etapas pagas)
        db.refresh(run)
        if run.cancel_requested:
            for s in run.steps:
                if s.status in ("pending", "retrying"):
                    s.status = "cancelled"
            _finish(db, run, "cancelled", "cancelada pelo usuário")
            return None
        if (err := budget_error(db, run, line) if line else None):
            _finish(db, run, "failed", f"orçamento: {err}")
            return None

        previous = {n: s.output for n, s in steps_by_name.items() if s.status == "succeeded"}
        step.status, step.started_at, step.finished_at = "running", step.started_at or now(), None
        step.attempts += 1
        step.total_attempts += 1
        step.input = {"config": config, "previous_steps": list(previous)}
        run.heartbeat_at = now()
        db.commit()

        try:
            result = step_def.fn(StepContext(run.id, config, previous, step.total_attempts))
            for f in result.files:  # upload idempotente (mesma chave em retomadas)
                key = f"runs/{run.id}/{step.name}/{f.filename}"
                storage.put(key, f.data, f.content_type)
                db.add(Artifact(run_id=run.id, step_name=step.name, filename=f.filename,
                                content_type=f.content_type, size=len(f.data), storage_key=key))
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            step = db.get(RunStep, step.id)
            run = db.get(Run, run_id)
            if step.attempts < max_attempts:
                delay = backoff * 2 ** (step.attempts - 1)
                step.status = "retrying"
                step.message = f"tentativa {step.attempts}/{max_attempts} falhou: {exc}; nova tentativa em {delay}s"
                run.status = "retrying"
                run.heartbeat_at = now()
                db.commit()
                return delay
            step.status, step.message, step.finished_at = "failed", f"{exc}", now()
            _finish(db, run, "failed", f"{step.name}: {exc}")
            return None

        step.status, step.finished_at = "succeeded", now()
        step.output, step.message = result.output, result.message
        step.cost = Decimal(str(result.cost))
        run.cost = (run.cost or Decimal(0)) + step.cost
        run.heartbeat_at = now()
        db.commit()

    _finish(db, run, "succeeded")
    return None
