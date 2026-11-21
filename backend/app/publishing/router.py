"""API de aprovações e publicação no YouTube (somente privado nesta versão)."""
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.publishing import service, tasks
from app.publishing import youtube as yt
from app.publishing.models import LIVE_PUB, VideoReview, YouTubePublication
from app.runs.models import Run, RunLog

router = APIRouter(prefix="/api", tags=["publishing"])
GOOGLE_HELP = ("Crie um cliente OAuth do tipo “App para computador” no Google Cloud, informe YOUTUBE_CLIENT_ID e "
               "YOUTUBE_CLIENT_SECRET no .env e execute 'docker compose up -d'.")


def _guard(fn, *a):
    try:
        return fn(*a)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except service.Blocked as exc:
        raise HTTPException(409, str(exc)) from None
    except service.Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except yt.YTError as exc:
        raise HTTPException(502, exc.message) from None


# ---------- helpers de serialização ----------
def _art(run: Run, name: str) -> str | None:
    return next((a.id for a in run.artifacts if a.filename == name), None)


def _step_out(run: Run, name: str) -> dict:
    return next((s.output or {} for s in run.steps if s.name == name), {})


def _defaults(run: Run) -> dict:
    sc, ex, im = _step_out(run, "script"), _step_out(run, "export"), _step_out(run, "images")
    title = (ex.get("title") or sc.get("title") or "Vídeo")[:100]
    desc = (sc.get("description") or "").strip()
    desc += "\n\nNarração gerada por voz sintética."
    credits, seen = [], set()
    for e in im.get("images", []):
        if e.get("key") and e["url"] not in seen:
            seen.add(e["url"])
            credits.append(f"• {e['title']} — {e['author'] or 'autor desconhecido'} ({e['license']}) {e['url']}")
    if credits:
        desc += "\n\nCréditos das imagens:\n" + "\n".join(credits[:25])
    return {"title": title.replace("<", "").replace(">", ""), "description": desc[:4800], "tags": []}


def _pub_out(p: YouTubePublication) -> dict:
    return {"id": p.id, "status": p.status, "title": p.title, "privacy": p.privacy, "channel_title": p.channel_title,
            "video_id": p.video_id, "url": p.url, "error": p.error, "created_at": p.created_at, "finished_at": p.finished_at,
            "progress": p.bytes_sent}


def _summary(db: Session, run: Run, rev: VideoReview | None) -> dict:
    ex = _step_out(run, "export")
    pubs = db.scalars(select(YouTubePublication).where(YouTubePublication.run_id == run.id)
                      .order_by(YouTubePublication.created_at.desc())).all()
    return {"run_id": run.id, "factory_id": run.line_id, "factory_name": run.line_name,
            "title": _defaults(run)["title"], "duration_seconds": ex.get("duration_seconds"), "created_at": run.created_at,
            "video_artifact_id": _art(run, "video.mp4"), "thumbnail_artifact_id": _art(run, "miniatura.jpg"),
            "review": {"status": rev.status if rev else "pending", "note": rev.note if rev else "",
                       "decided_at": rev.decided_at if rev else None},
            "publication": _pub_out(pubs[0]) if pubs else None}


# ---------- aprovações ----------
@router.get("/approvals")
def list_approvals(status: str = "pending", db: Session = Depends(get_db)):
    runs = db.scalars(select(Run).where(Run.pipeline == "video_youtube", Run.status == "succeeded")
                      .order_by(Run.created_at.desc()).limit(200)).all()
    revs = {r.run_id: r for r in db.scalars(select(VideoReview))}
    out = [_summary(db, r, revs.get(r.id)) for r in runs]
    return out if status == "all" else [o for o in out if o["review"]["status"] == status]


@router.get("/approvals/{run_id}")
def approval_detail(run_id: str, db: Session = Depends(get_db)):
    run = _guard(service.reviewable_run, db, run_id)
    rev = db.scalar(select(VideoReview).where(VideoReview.run_id == run_id))
    out = _summary(db, run, rev)
    conn = service.connection(db)
    blockers = []
    if out["review"]["status"] != "approved":
        blockers.append({"pending": "Aprove a produção para poder publicar.", "changes_requested": "Há alterações solicitadas.",
                         "rejected": "A produção foi rejeitada."}[out["review"]["status"]])
    if not service.configured():
        blockers.append("A integração com o YouTube ainda não foi configurada.")
    elif conn.status != "connected":
        blockers.append("Conecte um canal do YouTube em Configurações.")
    if service.live_publication(db, run_id):
        blockers.append("Esta produção já tem um envio em andamento ou concluído.")
    events = db.scalars(select(RunLog).where(RunLog.run_id == run_id, RunLog.step_name.in_(("review", "youtube")))
                        .order_by(RunLog.created_at)).all()
    meta = _step_out(run, "export")
    out.update({
        "defaults": _defaults(run), "blockers": blockers, "can_publish": not blockers,
        "channel": {"title": conn.channel_title} if conn.status == "connected" else None,
        "events": [{"at": e.created_at, "text": e.message, "level": e.level} for e in events],
        "publications": [_pub_out(p) for p in db.scalars(select(YouTubePublication).where(YouTubePublication.run_id == run_id)
                                                          .order_by(YouTubePublication.created_at.desc()))],
        "scenes": len(_step_out(run, "scenes").get("scenes", [])), "words": _step_out(run, "script").get("words"),
        "subtitles_artifact_id": _art(run, "legendas.srt"), "has_credits": bool(meta.get("credits"))})
    return out


class Decision(BaseModel):
    decision: Literal["approve", "request_changes", "reject"]
    note: str = Field("", max_length=2000)


@router.post("/approvals/{run_id}/decision")
def decide(run_id: str, body: Decision, db: Session = Depends(get_db)):
    _guard(service.decide, db, run_id, body.decision, body.note)
    return approval_detail(run_id, db)


class PublishIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field("", max_length=4900)
    tags: list[str] = Field(default_factory=list, max_length=15)
    made_for_kids: bool = False
    privacy: Literal["private"] = "private"  # público/agendamento: fora do escopo desta versão
    confirm: Literal[True]  # confirmação explícita do PO

    @field_validator("title", "description")
    @classmethod
    def _no_angle(cls, v: str) -> str:
        if "<" in v or ">" in v:
            raise ValueError("não use os caracteres < e >")
        return v.strip()

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        v = [t.strip() for t in v if t.strip()]
        if any(len(t) > 30 for t in v) or sum(len(t) for t in v) > 450:
            raise ValueError("tags longas demais")
        return v


@router.post("/approvals/{run_id}/publish", status_code=202)
def publish(run_id: str, body: PublishIn, db: Session = Depends(get_db)):
    meta = {"title": body.title, "description": body.description, "tags": body.tags, "made_for_kids": body.made_for_kids}
    pub = _guard(service.create_publication, db, run_id, meta)
    tasks.enqueue(pub.id)
    return _pub_out(pub)


@router.post("/publications/{pub_id}/resume", status_code=202)
def resume_publication(pub_id: str, db: Session = Depends(get_db)):
    """Verifica/retoma com segurança um envio incerto: consulta o YouTube antes de enviar qualquer byte."""
    pub = db.get(YouTubePublication, pub_id)
    if not pub:
        raise HTTPException(404, "envio não encontrado")
    if pub.status not in ("uncertain", "uploading"):
        raise HTTPException(409, "este envio não precisa de verificação")
    tasks.enqueue(pub.id, True)
    return _pub_out(pub)


# ---------- conexão YouTube ----------
def _conn_out(db: Session) -> dict:
    c = service.connection(db)
    return {"configured": service.configured(), "help": GOOGLE_HELP, "status": c.status if service.configured() else "unconfigured",
            "channel": {"id": c.channel_id, "title": c.channel_title} if c.status == "connected" else None,
            "message": c.status_message, "connected_at": c.connected_at, "redirect_uri": settings.youtube_redirect_uri,
            "scopes": c.scopes.split() if c.scopes else []}


@router.get("/youtube/status")
def youtube_status(db: Session = Depends(get_db)):
    return _conn_out(db)


@router.post("/youtube/connect")
def youtube_connect(db: Session = Depends(get_db)):
    return {"auth_url": _guard(service.start_connect, db)}


class CallbackIn(BaseModel):
    redirect_url: str = Field(min_length=10, max_length=2000)


@router.post("/youtube/callback")
def youtube_callback(body: CallbackIn, db: Session = Depends(get_db)):
    _guard(service.finish_connect, db, body.redirect_url)
    return _conn_out(db)


@router.post("/youtube/check")
def youtube_check(db: Session = Depends(get_db)):
    """Confirma com o Google que a autorização continua válida (consome ~1 unidade de cota)."""
    c = service.connection(db)
    try:
        ch = yt.my_channel(service.access_token(db, c))
        if ch is None:
            c.status, c.status_message = "revoked", "o canal não existe mais"
            db.commit()
    except yt.YTError as exc:
        if exc.kind == "auth":
            c.status, c.status_message = "revoked", exc.message
            db.commit()
        else:
            raise HTTPException(502, exc.message) from None
    return _conn_out(db)


@router.post("/youtube/disconnect")
def youtube_disconnect(db: Session = Depends(get_db)):
    _guard(service.disconnect, db)
    return _conn_out(db)
