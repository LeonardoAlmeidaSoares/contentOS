from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.runs.models import new_id, now

STANDARD_STATES = ("proposed", "approved", "rejected", "superseded")


class ChannelStandard(Base):
    """Versão do Padrão do Canal. Imutável depois de criada (só o estado muda); somente `approved` orienta produções."""
    __tablename__ = "channel_standards"
    __table_args__ = (
        UniqueConstraint("line_id", "version", name="uq_standard_version"),
        # no máximo uma versão aprovada (vigente) por fábrica
        Index("uq_standard_one_approved", "line_id", unique=True,
              postgresql_where=text("status = 'approved'"), sqlite_where=text("status = 'approved'")),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    line_id: Mapped[str] = mapped_column(ForeignKey("production_lines.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="proposed")  # proposed|approved|rejected|superseded
    config: Mapped[dict] = mapped_column(JSON)  # FactoryConfig.identity() desta versão
    changelog: Mapped[list] = mapped_column(JSON, default=list)  # [{field,label,from,to}] versus a versão anterior
    pending: Mapped[list] = mapped_column(JSON, default=list)  # campos sugeridos pela IA, não informados pelo usuário
    note: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(12), default="manual")  # chat|manual|legacy
    preview: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # prévia conceitual (roteiro, visual, narração)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
