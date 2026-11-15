from fastapi import APIRouter, Response
from sqlalchemy import text

from app.celery_app import celery
from app.core.db import engine
from app.core.storage import get_storage

router = APIRouter(tags=["health"])


@router.get("/health")
def liveness():
    return {"status": "ok"}


def _check_db():
    with engine.connect() as c:
        c.execute(text("select 1"))


def _check_redis():
    with celery.connection_for_read() as conn:
        conn.ensure_connection(max_retries=1)


def _check_storage():
    get_storage().ping()


@router.get("/health/ready")
def readiness(response: Response):
    checks = {}
    for name, fn in (("postgres", _check_db), ("redis", _check_redis), ("minio", _check_storage)):
        try:
            fn()
            checks[name] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks[name] = f"error: {exc.__class__.__name__}"
    ok = all(v == "ok" for v in checks.values())
    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "degraded", "checks": checks}
