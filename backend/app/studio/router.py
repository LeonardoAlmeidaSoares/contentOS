"""API do ContentOS Studio: criação conversacional de fábricas, ajustes por linguagem natural e produção de vídeos."""
import shutil

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.media import tts
from app.runs import service, tasks
from app.runs.models import ProductionLine
from app.runs.router import _conflict, run_full
from app.studio import assistant
from app.studio.schemas import FactoryConfig, preview

router = APIRouter(prefix="/api/studio", tags=["studio"])
PIPELINE = "video_youtube"


class Msg(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=30)


class CreateIn(BaseModel):
    config: dict


class AdjustIn(BaseModel):
    instruction: str = Field(min_length=3, max_length=1500)


class ProduceIn(BaseModel):
    topic: str = Field("", max_length=300)
    script_text: str = Field("", max_length=40000)


def _guard(fn, *a):
    try:
        return fn(*a)
    except assistant.NotConfigured as exc:
        raise HTTPException(412, str(exc)) from None
    except assistant.AssistantError as exc:
        raise HTTPException(502, str(exc)) from None


def _line(db: Session, lid: str) -> ProductionLine:
    line = db.get(ProductionLine, lid)
    if not line or line.pipeline != PIPELINE:
        raise HTTPException(404, "fábrica não encontrada")
    return line


@router.get("/status")
def status():
    """Dependências do estúdio, para a interface mostrar instruções claras."""
    return {
        "gemini": {"configured": bool(settings.gemini_api_key), "model": settings.gemini_text_model,
                   "help": "Crie uma chave gratuita em https://aistudio.google.com/apikey, defina GEMINI_API_KEY no arquivo .env "
                           "e execute 'docker compose up -d'."},
        "images": {"wikimedia": True, "pexels": bool(settings.pexels_api_key),
                   "help": "Wikimedia Commons funciona sem chave. Para mais variedade, defina PEXELS_API_KEY (gratuita)."},
        "voice": {"engines": tts.available_engines()},
        "ffmpeg": shutil.which("ffmpeg") is not None,
    }


@router.post("/chat")
def chat(body: ChatIn):
    return _guard(assistant.interpret, [m.model_dump() for m in body.messages])


@router.post("/factories", status_code=201)
def create_factory(body: CreateIn, db: Session = Depends(get_db)):
    try:
        cfg = FactoryConfig.model_validate(body.config)
    except Exception:
        raise HTTPException(422, "configuração inválida") from None
    if not cfg.theme:
        raise HTTPException(422, "informe o tema da fábrica")
    cfg.name = cfg.name or cfg.theme[:60]
    interval = int(7 * 24 * 60 / cfg.frequency_per_week) if cfg.frequency_per_week else None
    line = ProductionLine(name=cfg.name, description=cfg.theme, pipeline=PIPELINE, active=False, config=cfg.identity(),
                          interval_minutes=interval, cost_limit_run=1, cost_limit_month=10, max_attempts=3, backoff_seconds=20)
    db.add(line)
    db.commit()
    return {"id": line.id}


@router.get("/factories/{lid}")
def factory(lid: str, db: Session = Depends(get_db)):
    line = _line(db, lid)
    cfg = FactoryConfig.model_validate(line.config)
    return {"id": line.id, "config": cfg.identity(), "preview": preview(cfg), "active": line.active,
            "interval_minutes": line.interval_minutes}


@router.post("/factories/{lid}/adjust")
def adjust(lid: str, body: AdjustIn, db: Session = Depends(get_db)):
    line = _line(db, lid)
    return _guard(assistant.adjust, FactoryConfig.model_validate(line.config).identity(), body.instruction)


@router.put("/factories/{lid}")
def apply(lid: str, body: CreateIn, db: Session = Depends(get_db)):
    line = _line(db, lid)
    try:
        cfg = FactoryConfig.model_validate(body.config)
    except Exception:
        raise HTTPException(422, "configuração inválida") from None
    line.config, line.name, line.description = cfg.identity(), cfg.name or line.name, cfg.theme
    line.interval_minutes = int(7 * 24 * 60 / cfg.frequency_per_week) if cfg.frequency_per_week else None
    service.schedule_next(line)
    db.commit()
    return factory(lid, db)


@router.post("/factories/{lid}/produce", status_code=201)
def produce(lid: str, body: ProduceIn, db: Session = Depends(get_db)):
    line = _line(db, lid)
    run = _conflict(service.start_run, db, line, "manual",
                    {"topic": body.topic.strip(), "script_text": body.script_text.strip()}, False)
    tasks.enqueue(run.id)
    return run_full(run)
