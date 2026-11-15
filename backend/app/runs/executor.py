"""Execução sequencial de etapas com persistência de progresso."""
from sqlalchemy.orm import Session

from app.core.storage import Storage
from app.pipelines import demo
from app.runs.models import Run, RunStep, now

PIPELINES = {"demo": demo.STEPS}


def create_run(db: Session, pipeline: str) -> Run:
    run = Run(pipeline=pipeline)
    run.steps = [RunStep(position=i, name=name) for i, (name, _) in enumerate(PIPELINES[pipeline], start=1)]
    db.add(run)
    db.commit()
    return run


def execute_run(db: Session, run_id: str, storage: Storage, delay: float = 2.0) -> None:
    run = db.get(Run, run_id)
    if run is None or run.status not in ("queued",):
        return  # idempotência: não reexecuta runs já iniciados/finalizados
    run.status, run.started_at = "running", now()
    db.commit()

    ctx = demo.Ctx(db=db, run=run, storage=storage, data={}, delay=delay)
    fns = dict(PIPELINES[run.pipeline])
    for step in run.steps:
        step.status, step.started_at = "running", now()
        db.commit()
        try:
            step.message = fns[step.name](ctx)
            step.status = "succeeded"
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            step.status, step.message = "failed", str(exc)
            run.status, run.error = "failed", f"{step.name}: {exc}"
            step.finished_at = run.finished_at = now()
            db.commit()
            return
        step.finished_at = now()
        db.commit()

    run.status, run.finished_at = "succeeded", now()
    db.commit()
