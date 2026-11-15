"""Pipeline técnico de demonstração: valida fila, worker, banco e MinIO sem APIs pagas."""
import json
import time
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.core.storage import Storage
from app.runs.models import Artifact, Run


@dataclass
class Ctx:
    db: Session
    run: Run
    storage: Storage
    data: dict
    delay: float = 2.0


def prepare(ctx: Ctx) -> str:
    time.sleep(ctx.delay)
    ctx.data["items"] = [f"item-{i}" for i in range(1, 6)]
    return f"{len(ctx.data['items'])} itens preparados"


def process(ctx: Ctx) -> str:
    time.sleep(ctx.delay)
    ctx.data["processed"] = [i.upper() for i in ctx.data["items"]]
    return f"{len(ctx.data['processed'])} itens processados"


def package(ctx: Ctx) -> str:
    time.sleep(ctx.delay)
    payload = {"run_id": ctx.run.id, "pipeline": "demo", "items": ctx.data["processed"]}
    body = json.dumps(payload, indent=2, ensure_ascii=False).encode()
    key = f"runs/{ctx.run.id}/demo-output.json"
    ctx.storage.put(key, body, "application/json")
    ctx.db.add(
        Artifact(run_id=ctx.run.id, filename="demo-output.json", content_type="application/json",
                 size=len(body), storage_key=key)
    )
    return f"arquivo gerado e armazenado ({len(body)} bytes)"


STEPS: list[tuple[str, Callable[[Ctx], str]]] = [
    ("prepare", prepare),
    ("process", process),
    ("package", package),
]
