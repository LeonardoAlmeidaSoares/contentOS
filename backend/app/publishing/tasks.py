"""Tarefa Celery de upload ao YouTube. Nunca registra tokens/URLs de sessão; falhas não geram sucesso falso."""
from sqlalchemy import update

from app.celery_app import celery
from app.core import crypto
from app.core.db import SessionLocal
from app.core.storage import get_storage
from app.publishing import service
from app.publishing import youtube as yt
from app.publishing.models import YouTubePublication
from app.runs.models import Artifact, now


def enqueue(pub_id: str, resume: bool = False) -> None:
    upload_task.apply_async(args=[pub_id, resume])


@celery.task(name="youtube.upload")
def upload_task(pub_id: str, resume: bool = False) -> None:
    with SessionLocal() as db:
        run_upload(db, pub_id, get_storage(), resume)


def _fail(db, pub, run_id, msg, status="failed", level="error"):
    db.refresh(pub)
    pub.status, pub.error, pub.finished_at = status, msg[:500], now()
    service.event(db, run_id, "youtube", f"Envio {'incerto' if status == 'uncertain' else 'falhou'}: {msg}", level)
    db.commit()


def run_upload(db, pub_id: str, storage, resume: bool = False) -> None:
    # claim atômico: só uma execução assume (preparing -> uploading; retomada: uncertain/uploading -> uploading)
    froms = ("preparing", "uncertain", "uploading") if resume else ("preparing",)
    claimed = db.execute(update(YouTubePublication).where(YouTubePublication.id == pub_id, YouTubePublication.status.in_(froms))
                         .values(status="uploading", error=None)).rowcount
    db.commit()
    if not claimed:
        return
    pub = db.get(YouTubePublication, pub_id)
    run_id = pub.run_id
    try:
        if service.review_status(db, run_id) != "approved":  # defesa em profundidade
            return _fail(db, pub, run_id, "a produção não está aprovada")
        conn = service.connection(db)
        if conn.channel_id != pub.channel_id or conn.status != "connected":
            return _fail(db, pub, run_id, "o canal conectado mudou ou foi desconectado; reconecte e tente de novo")
        access = service.access_token(db, conn)
        art = db.query(Artifact).filter_by(run_id=run_id, filename="video.mp4").first()
        data = storage.get(art.storage_key)
        meta = {"title": pub.title, "description": pub.description, "tags": pub.tags or [], "made_for_kids": pub.made_for_kids}
        if not pub.session_url_enc:
            session = yt.init_upload(access, meta, len(data))  # ainda não existe vídeo: falhar aqui é seguro
            pub.session_url_enc = crypto.encrypt(session)
            db.commit()
        else:
            session = crypto.decrypt(pub.session_url_enc)

        def progress(n):
            pub.bytes_sent = n
            db.commit()

        start, res = 0, None
        if resume and pub.session_url_enc:  # retomada: confirma com o YouTube o que já foi recebido
            kind, val = yt.query_session(session, len(data))
            res, start = (val, 0) if kind == "done" else (None, val)
        if res is None:
            res = yt.upload(session, data, start, progress)
        vid = res.get("id")
        if not vid:
            return _fail(db, pub, run_id, "resposta de conclusão sem ID de vídeo; verifique no YouTube Studio antes de tentar de novo", "uncertain", "warn")
        pub.status, pub.video_id, pub.url, pub.finished_at, pub.bytes_sent = "succeeded", vid, f"https://www.youtube.com/watch?v={vid}", now(), len(data)
        service.event(db, run_id, "youtube", f"Vídeo enviado como privado (ID {vid})")
        db.commit()
    except yt.YTError as exc:
        db.rollback()
        if exc.kind == "network" and pub.session_url_enc and pub.bytes_sent >= 0:
            # sessão aberta e rede instável: o vídeo pode ter sido concluído. Não repetimos sozinhos (evita duplicidade).
            _fail(db, pub, run_id, exc.message + ". Use “Verificar envio” para retomar com segurança.", "uncertain", "warn")
        else:
            _fail(db, pub, run_id, exc.message)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        _fail(db, pub, run_id, f"erro inesperado ({exc.__class__.__name__})", "uncertain" if pub.session_url_enc else "failed")
