from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.storage import get_storage
from app.runs.executor import PIPELINES, create_run
from app.runs.models import Artifact, Run
from app.runs.tasks import execute_run_task

router = APIRouter(prefix="/api", tags=["runs"])


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    position: int
    name: str
    status: str
    message: str | None
    started_at: datetime | None
    finished_at: datetime | None


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    filename: str
    content_type: str
    size: int
    created_at: datetime


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    pipeline: str
    status: str
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    steps: list[StepOut]
    artifacts: list[ArtifactOut]


class RunCreate(BaseModel):
    pipeline: str = "demo"


@router.post("/runs", response_model=RunOut, status_code=201)
def start_run(body: RunCreate, db: Session = Depends(get_db)):
    if body.pipeline not in PIPELINES:
        raise HTTPException(422, f"pipeline desconhecido: {body.pipeline}")
    run = create_run(db, body.pipeline)
    execute_run_task.delay(run.id)
    return run


@router.get("/runs", response_model=list[RunOut])
def list_runs(db: Session = Depends(get_db)):
    return db.scalars(select(Run).order_by(Run.created_at.desc()).limit(50)).all()


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "execução não encontrada")
    return run


@router.get("/artifacts", response_model=list[ArtifactOut])
def list_artifacts(db: Session = Depends(get_db)):
    return db.scalars(select(Artifact).order_by(Artifact.created_at.desc()).limit(100)).all()


@router.get("/artifacts/{artifact_id}/download")
def download(artifact_id: str, db: Session = Depends(get_db)):
    art = db.get(Artifact, artifact_id)
    if not art:
        raise HTTPException(404, "artefato não encontrado")
    data = get_storage().get(art.storage_key)
    return Response(
        data, media_type=art.content_type,
        headers={"Content-Disposition": f'attachment; filename="{art.filename}"'},
    )
