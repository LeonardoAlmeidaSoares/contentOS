from app.celery_app import celery
from app.core.db import SessionLocal
from app.core.storage import get_storage
from app.runs.executor import execute_run


@celery.task(name="runs.execute")
def execute_run_task(run_id: str) -> None:
    with SessionLocal() as db:
        execute_run(db, run_id, get_storage())
