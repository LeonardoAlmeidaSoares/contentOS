import re
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.storage import get_storage
from app.pipelines.registry import PIPELINES, load_all
from app.runs import service, tasks
from app.runs.models import ACTIVE_STATUSES, Artifact, ProductionLine, Run, RunLog, now

load_all()
router = APIRouter(prefix="/api", tags=["engine"])


# ---------- schemas ----------
class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    position: int
    name: str
    status: str
    message: str | None
    input: dict | None
    output: dict | None
    cost: float
    attempts: int
    total_attempts: int
    started_at: datetime | None
    finished_at: datetime | None


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    run_id: str
    step_name: str | None
    filename: str
    content_type: str
    size: int
    provider: str | None
    model: str | None
    meta: dict | None
    created_at: datetime


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    line_id: str | None
    line_name: str | None
    pipeline: str
    trigger: str
    status: str
    error: str | None
    cost: float
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    steps_total: int = 0
    steps_done: int = 0


class RunOut(RunSummary):
    steps: list[StepOut]
    artifacts: list[ArtifactOut]


class LineIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    pipeline: str
    config: dict = {}
    interval_minutes: int | None = Field(None, ge=1)
    cost_limit_run: Decimal | None = Field(None, ge=0)
    cost_limit_month: Decimal | None = Field(None, ge=0)
    max_attempts: int = Field(3, ge=1, le=10)
    backoff_seconds: int = Field(5, ge=0, le=3600)

    @field_validator("pipeline")
    @classmethod
    def _known(cls, v):
        if v not in PIPELINES or PIPELINES[v].internal:
            raise ValueError(f"pipeline desconhecido: {v}")
        return v


class LinePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = None
    config: dict | None = None
    interval_minutes: int | None = Field(None, ge=1)
    cost_limit_run: Decimal | None = Field(None, ge=0)
    cost_limit_month: Decimal | None = Field(None, ge=0)
    max_attempts: int | None = Field(None, ge=1, le=10)
    backoff_seconds: int | None = Field(None, ge=0, le=3600)


class LineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    pipeline: str
    active: bool
    config: dict
    interval_minutes: int | None
    cost_limit_run: float | None
    cost_limit_month: float | None
    max_attempts: int
    backoff_seconds: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    # agregados
    cost_month: float = 0
    cost_total: float = 0
    products: int = 0
    active_run: RunSummary | None = None
    last_run: RunSummary | None = None


class PipelineOut(BaseModel):
    name: str
    label: str
    description: str
    default_config: dict
    steps: list[str]


# ---------- helpers ----------
def run_summary(run: Run) -> RunSummary:
    s = RunSummary.model_validate(run)
    s.steps_total = len(run.steps)
    s.steps_done = sum(1 for x in run.steps if x.status == "succeeded")
    return s


def run_full(run: Run) -> RunOut:
    base = run_summary(run).model_dump()
    return RunOut(**base, steps=[StepOut.model_validate(s) for s in run.steps],
                  artifacts=[ArtifactOut.model_validate(a) for a in run.artifacts])


def line_out(db: Session, line: ProductionLine) -> LineOut:
    out = LineOut.model_validate(line)
    runs = db.scalars(select(Run).where(Run.line_id == line.id).order_by(Run.created_at.desc())).all()
    out.cost_total = float(sum((r.cost for r in runs), Decimal(0)))
    out.cost_month = float(service.month_cost(db, line.id))
    out.products = db.scalar(select(func.count(Artifact.id)).join(Run).where(Run.line_id == line.id)) or 0
    out.active_run = next((run_summary(r) for r in runs if r.status in ACTIVE_STATUSES), None)
    out.last_run = run_summary(runs[0]) if runs else None
    return out


def _line(db: Session, line_id: str) -> ProductionLine:
    line = db.get(ProductionLine, line_id)
    if not line:
        raise HTTPException(404, "linha não encontrada")
    return line


def _conflict(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except service.Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except LookupError:
        raise HTTPException(404, "execução não encontrada") from None


# ---------- pipelines ----------
@router.get("/pipelines", response_model=list[PipelineOut])
def pipelines():
    return [PipelineOut(name=p.name, label=p.label, description=p.description,
                        default_config=p.default_config, steps=[s.name for s in p.steps])
            for p in PIPELINES.values() if not p.internal]


# ---------- lines ----------
@router.get("/lines", response_model=list[LineOut])
def list_lines(include_archived: bool = False, db: Session = Depends(get_db)):
    q = select(ProductionLine).order_by(ProductionLine.created_at)
    if not include_archived:
        q = q.where(ProductionLine.archived_at.is_(None))
    return [line_out(db, ln) for ln in db.scalars(q)]


@router.post("/lines", response_model=LineOut, status_code=201)
def create_line(body: LineIn, db: Session = Depends(get_db)):
    line = ProductionLine(**body.model_dump())
    db.add(line)
    db.commit()
    return line_out(db, line)


@router.get("/lines/{line_id}", response_model=LineOut)
def get_line(line_id: str, db: Session = Depends(get_db)):
    return line_out(db, _line(db, line_id))


@router.patch("/lines/{line_id}", response_model=LineOut)
def update_line(line_id: str, body: LinePatch, db: Session = Depends(get_db)):
    line = _line(db, line_id)
    if line.archived_at:
        raise HTTPException(409, "linha arquivada: desarquive para editar")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(line, k, v)
    if "interval_minutes" in body.model_fields_set:
        service.schedule_next(line)
    db.commit()
    return line_out(db, line)


@router.post("/lines/{line_id}/activate", response_model=LineOut)
def activate(line_id: str, db: Session = Depends(get_db)):
    line = _line(db, line_id)
    if line.archived_at:
        raise HTTPException(409, "linha arquivada")
    line.active = True
    service.schedule_next(line)
    db.commit()
    return line_out(db, line)


@router.post("/lines/{line_id}/deactivate", response_model=LineOut)
def deactivate(line_id: str, db: Session = Depends(get_db)):
    line = _line(db, line_id)
    line.active = False
    line.next_run_at = None
    db.commit()
    return line_out(db, line)


@router.post("/lines/{line_id}/archive", response_model=LineOut)
def archive(line_id: str, db: Session = Depends(get_db)):
    """Arquiva preservando todo o histórico; exige que não haja execução ativa."""
    line = _line(db, line_id)
    if db.scalar(select(func.count(Run.id)).where(Run.line_id == line.id, Run.status.in_(ACTIVE_STATUSES))):
        raise HTTPException(409, "há execução ativa: cancele ou aguarde antes de arquivar")
    line.active, line.next_run_at, line.archived_at = False, None, now()
    db.commit()
    return line_out(db, line)


@router.post("/lines/{line_id}/unarchive", response_model=LineOut)
def unarchive(line_id: str, db: Session = Depends(get_db)):
    line = _line(db, line_id)
    line.archived_at = None
    db.commit()
    return line_out(db, line)


@router.post("/lines/{line_id}/run", response_model=RunOut, status_code=201)
def run_line(line_id: str, db: Session = Depends(get_db)):
    run = _conflict(service.start_run, db, _line(db, line_id), "manual")
    tasks.enqueue(run.id)
    return run_full(run)


# ---------- runs ----------
@router.get("/runs", response_model=list[RunSummary])
def list_runs(line_id: str | None = None, include_lab: bool = False, db: Session = Depends(get_db)):
    q = select(Run).order_by(Run.created_at.desc()).limit(100)
    if not include_lab:
        q = q.where(Run.trigger != "lab")
    if line_id:
        q = q.where(Run.line_id == line_id)
    return [run_summary(r) for r in db.scalars(q)]


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "execução não encontrada")
    return run_full(run)


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    step_name: str | None
    level: str
    message: str
    created_at: datetime


@router.get("/runs/{run_id}/logs", response_model=list[LogOut])
def run_logs(run_id: str, db: Session = Depends(get_db)):
    return db.scalars(select(RunLog).where(RunLog.run_id == run_id).order_by(RunLog.created_at, RunLog.id)).all()


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
def cancel(run_id: str, db: Session = Depends(get_db)):
    return run_full(_conflict(service.cancel_run, db, run_id))


@router.post("/runs/{run_id}/resume", response_model=RunOut)
def resume(run_id: str, db: Session = Depends(get_db)):
    run = _conflict(service.resume_run, db, run_id)
    tasks.enqueue(run.id)
    return run_full(run)


# ---------- artifacts ----------
@router.get("/artifacts", response_model=list[ArtifactOut])
def list_artifacts(line_id: str | None = None, db: Session = Depends(get_db)):
    q = select(Artifact).order_by(Artifact.created_at.desc()).limit(100)
    if line_id:
        q = q.join(Run).where(Run.line_id == line_id)
    return db.scalars(q).all()


@router.get("/artifacts/{artifact_id}/download")
def download(artifact_id: str, request: Request, inline: bool = False, db: Session = Depends(get_db)):
    art = db.get(Artifact, artifact_id)
    if not art:
        raise HTTPException(404, "artefato não encontrado")
    data = get_storage().get(art.storage_key)
    headers = {"Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{art.filename}"',
               "Accept-Ranges": "bytes"}
    m = re.match(r"bytes=(\d*)-(\d*)$", request.headers.get("range", ""))  # necessário para reprodução/seek de vídeo
    if m and (m.group(1) or m.group(2)):
        total = len(data)
        start = int(m.group(1)) if m.group(1) else max(0, total - int(m.group(2)))
        end = min(int(m.group(2)), total - 1) if m.group(1) and m.group(2) else total - 1
        if start >= total or start > end:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        return Response(data[start:end + 1], status_code=206, media_type=art.content_type, headers=headers)
    return Response(data, media_type=art.content_type, headers=headers)
