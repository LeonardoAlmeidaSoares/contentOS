"""Executor: etapas sequenciais, resultados persistidos, retry com backoff, cancelamento, orçamento e logs."""
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app.core.storage import Storage
from app.pipelines.registry import PIPELINES, StepContext, load_all
from app.providers.gateway import AIGateway
from app.providers.ledger import ledger_sum
from app.runs.models import Artifact, ProductionLine, Run, RunLog, RunStep, now
from app.runs.service import budget_error, refresh_cost

load_all()


def log(db: Session, run: Run, step: str | None, msg: str, level: str = "info") -> None:
    db.add(RunLog(run_id=run.id, step_name=step, level=level, message=msg[:4000]))


def _finish(db: Session, run: Run, status: str, error: str | None = None) -> None:
    refresh_cost(db, run)
    run.status, run.error, run.finished_at = status, error, now()
    log(db, run, None, f"execução {status}" + (f": {error}" if error else ""), "error" if status == "failed" else "info")
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
    config = dict(run.config) if run.config is not None else (dict(line.config) if line else {})
    max_attempts = line.max_attempts if line else 1
    backoff = line.backoff_seconds if line else 0
    steps_by_name = {s.name: s for s in run.steps}
    session_factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    gateway = AIGateway(session_factory, storage, run_id=run.id, line_id=line.id if line else None,
                        scope="lab" if run.trigger == "lab" else "line")

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
        refresh_cost(db, run)
        if (err := budget_error(db, run, line) if line else None):
            log(db, run, step.name, f"bloqueada antes da etapa: {err}", "warn")
            _finish(db, run, "failed", f"orçamento: {err}")
            return None

        previous = {n: s.output for n, s in steps_by_name.items() if s.status == "succeeded"}
        step.status, step.started_at, step.finished_at = "running", step.started_at or now(), None
        step.attempts += 1
        step.total_attempts += 1
        step.input = {"config": config, "previous_steps": list(previous)}
        run.heartbeat_at = now()
        log(db, run, step.name, f"etapa iniciada (tentativa {step.attempts}/{max_attempts})")
        db.commit()

        gateway.step_name = step.name
        ctx = StepContext(run.id, step.name, config, previous, step.total_attempts, ai=gateway)
        try:
            result = step_def.fn(ctx)
            for f in result.files:  # upload idempotente (mesma chave em retomadas)
                key = f.storage_key or f"runs/{run.id}/{step.name}/{f.filename}"
                if not f.storage_key:
                    storage.put(key, f.data, f.content_type)
                size = int((f.meta or {}).get("size") or len(f.data))
                db.add(Artifact(run_id=run.id, step_name=step.name, filename=f.filename, content_type=f.content_type,
                                size=size, storage_key=key, provider=f.provider, model=f.model, meta=f.meta))
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            step = db.get(RunStep, step.id)
            run = db.get(Run, run_id)
            for lvl, m in ctx.logs:
                log(db, run, step.name, m, lvl)
            retryable = getattr(exc, "retryable", True)
            log(db, run, step.name, f"falha: {exc}", "error")
            if retryable and step.attempts < max_attempts:
                delay = backoff * 2 ** (step.attempts - 1)
                step.status = "retrying"
                step.message = f"tentativa {step.attempts}/{max_attempts} falhou: {exc}; nova tentativa em {delay}s"
                run.status = "retrying"
                run.heartbeat_at = now()
                refresh_cost(db, run)
                db.commit()
                return delay
            step.status, step.message, step.finished_at = "failed", f"{exc}", now()
            prefix = "orçamento: " if exc.__class__.__name__ == "BudgetExceeded" else ""
            _finish(db, run, "failed", f"{step.name}: {prefix}{exc}")
            return None

        for lvl, m in ctx.logs:
            log(db, run, step.name, m, lvl)
        step.status, step.finished_at = "succeeded", now()
        step.output, step.message = result.output, result.message
        step.cost = Decimal(str(result.cost)) + ledger_sum(db, run_id=run.id, step_names=[step.name])
        log(db, run, step.name, f"etapa concluída: {result.message} (custo US$ {step.cost})")
        refresh_cost(db, run)
        run.heartbeat_at = now()
        db.commit()

    _finish(db, run, "succeeded")
    return None
