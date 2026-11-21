"""Regras de negócio: revisão humana, conexão do canal e criação de envios (sem I/O de rede de upload)."""
import secrets
from datetime import timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import settings
from app.publishing import youtube as yt
from app.publishing.models import LIVE_PUB, VideoReview, YouTubeConnection, YouTubePublication
from app.runs.models import Run, RunLog, now

DECISIONS = {"approve": "approved", "request_changes": "changes_requested", "reject": "rejected"}
EVENT_TEXT = {"approved": "Produção aprovada", "changes_requested": "Alterações solicitadas", "rejected": "Produção rejeitada"}


def aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Conflict(Exception):
    pass


class Blocked(Exception):
    """Pré-condição de negócio não atendida (mensagem apresentável)."""


def event(db: Session, run_id: str, step: str, msg: str, level: str = "info") -> None:
    db.add(RunLog(run_id=run_id, step_name=step, level=level, message=msg[:1000]))


def reviewable_run(db: Session, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if run is None or run.pipeline != "video_youtube":
        raise LookupError("produção não encontrada")
    return run


def live_publication(db: Session, run_id: str) -> YouTubePublication | None:
    return db.scalar(select(YouTubePublication).where(YouTubePublication.run_id == run_id,
                                                      YouTubePublication.status.in_(LIVE_PUB)))


def review_status(db: Session, run_id: str) -> str:
    r = db.scalar(select(VideoReview).where(VideoReview.run_id == run_id))
    return r.status if r else "pending"


def decide(db: Session, run_id: str, decision: str, note: str) -> VideoReview:
    run = reviewable_run(db, run_id)
    if run.status != "succeeded":
        raise Blocked("só é possível revisar produções concluídas")
    if live_publication(db, run_id):
        raise Conflict("esta produção já tem um envio ao YouTube em andamento ou concluído; a decisão não pode mais mudar")
    status = DECISIONS[decision]
    if status != "approved" and not note.strip():
        raise Blocked("descreva o motivo (ou as alterações desejadas)")
    rev = db.scalar(select(VideoReview).where(VideoReview.run_id == run_id))
    if rev is None:
        rev = VideoReview(run_id=run_id, status=status, note=note.strip())
        db.add(rev)
    else:
        rev.status, rev.note, rev.decided_at = status, note.strip(), now()
    event(db, run_id, "review", EVENT_TEXT[status] + (f": {note.strip()}" if note.strip() else ""))
    db.commit()  # aprovar NÃO dispara publicação: publicar é outra ação, explícita
    return rev


# ---------- conexão ----------
def connection(db: Session) -> YouTubeConnection:
    c = db.scalar(select(YouTubeConnection))
    if c is None:
        c = YouTubeConnection()
        db.add(c)
        db.commit()
    return c


def configured() -> bool:
    return bool(settings.youtube_client_id and settings.youtube_client_secret)


def start_connect(db: Session) -> str:
    if not configured():
        raise Blocked("credenciais OAuth do Google não configuradas (YOUTUBE_CLIENT_ID e YOUTUBE_CLIENT_SECRET)")
    c = connection(db)
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    c.pending_state, c.pending_verifier_enc, c.pending_at = state, crypto.encrypt(verifier), now()
    db.commit()
    return yt.auth_url(state, verifier)


def finish_connect(db: Session, redirect_url: str) -> YouTubeConnection:
    c = connection(db)
    code, state, error = yt.parse_redirect(redirect_url)
    if error:
        raise Blocked("O Google informou que a autorização foi negada." if error == "access_denied" else f"Autorização recusada ({error}).")
    if not c.pending_state or not c.pending_verifier_enc or not c.pending_at or now() - aware(c.pending_at) > timedelta(minutes=15):
        raise Blocked("Nenhuma conexão em andamento (ou expirou). Clique em “Conectar canal” novamente.")
    if not code or not state or not secrets.compare_digest(state, c.pending_state):
        raise Blocked("O endereço colado não corresponde a esta conexão. Copie a URL completa da barra de endereços.")
    verifier = crypto.decrypt(c.pending_verifier_enc)
    c.pending_state = c.pending_verifier_enc = c.pending_at = None  # uso único
    db.commit()
    tok = yt.exchange_code(code, verifier)
    granted = set((tok.get("scope") or "").split())
    if not set(yt.SCOPES) <= granted:
        raise Blocked("Faltou conceder todas as permissões solicitadas (enviar vídeos e ler o canal). Tente de novo marcando todas.")
    if not tok.get("refresh_token"):
        raise Blocked("O Google não devolveu permissão offline. Remova o acesso do ContentOS em myaccount.google.com/permissions e conecte de novo.")
    ch = yt.my_channel(tok["access_token"])
    if ch is None:
        raise Blocked("Esta conta Google não tem um canal do YouTube.")
    c.channel_id, c.channel_title = ch["id"], ch["title"]
    c.refresh_token_enc, c.access_token_enc = crypto.encrypt(tok["refresh_token"]), crypto.encrypt(tok["access_token"])
    c.expires_at = now() + timedelta(seconds=int(tok.get("expires_in", 3600)))
    c.scopes, c.status, c.status_message, c.connected_at = " ".join(sorted(granted)), "connected", None, now()
    db.commit()
    return c


def access_token(db: Session, c: YouTubeConnection) -> str:
    """Token de acesso válido; renova com o refresh token. Revogação marca a conexão como `revoked`."""
    if c.status != "connected" or not c.refresh_token_enc:
        raise yt.YTError("Canal do YouTube não conectado.", "auth")
    if c.access_token_enc and c.expires_at and aware(c.expires_at) - now() > timedelta(seconds=60):
        return crypto.decrypt(c.access_token_enc)
    try:
        tok = yt.refresh(crypto.decrypt(c.refresh_token_enc))
    except yt.YTError as exc:
        if exc.kind == "auth":
            c.status, c.status_message = "revoked", exc.message
            db.commit()
        raise
    c.access_token_enc = crypto.encrypt(tok["access_token"])
    c.expires_at = now() + timedelta(seconds=int(tok.get("expires_in", 3600)))
    db.commit()
    return tok["access_token"]


def disconnect(db: Session) -> None:
    c = connection(db)
    if db.scalar(select(YouTubePublication.id).where(YouTubePublication.status.in_(("preparing", "uploading", "uncertain")))):
        raise Conflict("há um envio em andamento; aguarde terminar antes de desconectar")
    for enc in (c.refresh_token_enc, c.access_token_enc):
        if enc:
            try:
                yt.revoke(crypto.decrypt(enc))
                break  # revogar o refresh token invalida o acesso
            except RuntimeError:
                pass
    c.channel_id = c.channel_title = c.refresh_token_enc = c.access_token_enc = c.expires_at = None
    c.scopes, c.status, c.status_message, c.connected_at = "", "pending", None, None
    c.pending_state = c.pending_verifier_enc = c.pending_at = None
    db.commit()


# ---------- envio ----------
def create_publication(db: Session, run_id: str, meta: dict) -> YouTubePublication:
    run = reviewable_run(db, run_id)
    if run.status != "succeeded":
        raise Blocked("a produção não foi concluída")
    st = review_status(db, run_id)
    if st != "approved":
        raise Blocked({"pending": "a produção ainda não foi aprovada", "changes_requested": "há alterações solicitadas; aprove a produção antes de publicar",
                       "rejected": "a produção foi rejeitada"}[st])
    c = connection(db)
    if c.status != "connected":
        raise Blocked("conecte um canal do YouTube em Configurações antes de publicar")
    if not any(a.filename == "video.mp4" for a in run.artifacts):
        raise Blocked("arquivo de vídeo não encontrado")
    pub = YouTubePublication(run_id=run_id, status="preparing", privacy="private", channel_id=c.channel_id,
                             channel_title=c.channel_title, **meta)
    db.add(pub)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("já existe um envio deste vídeo em andamento ou concluído") from None
    event(db, run_id, "youtube", f"Envio privado solicitado para o canal “{c.channel_title}”")
    db.commit()
    return pub
