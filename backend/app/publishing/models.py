from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.runs.models import new_id, now

LIVE_PUB = ("preparing", "uploading", "succeeded", "uncertain")  # estados que bloqueiam novo envio do mesmo vídeo


class VideoReview(Base):
    """Decisão humana sobre uma produção. Sem registro = aguardando aprovação."""
    __tablename__ = "video_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(20))  # approved|changes_requested|rejected
    note: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class YouTubeConnection(Base):
    """Canal conectado (no máximo um). Tokens só criptografados (Fernet)."""
    __tablename__ = "youtube_connection"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|connected|revoked
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pending_verifier_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class YouTubePublication(Base):
    __tablename__ = "youtube_publications"
    __table_args__ = (
        # no máximo um envio "vivo" por produção: protege contra clique duplo, retries e tarefas repetidas
        Index("uq_ytpub_one_live_per_run", "run_id", unique=True,
              postgresql_where=text("status in ('preparing','uploading','succeeded','uncertain')"),
              sqlite_where=text("status in ('preparing','uploading','succeeded','uncertain')")),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="preparing")  # preparing|uploading|succeeded|failed|uncertain
    privacy: Mapped[str] = mapped_column(String(10), default="private")
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    made_for_kids: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    session_url_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # sessão de upload retomável (sensível)
    bytes_sent: Mapped[int] = mapped_column(Integer, default=0)
    video_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    url: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
