from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.runs.models import Money, new_id, now

COUNTED = ("reserved", "succeeded", "uncertain")  # estados que consomem orçamento


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    service: Mapped[str] = mapped_column(String(32))  # openai|recraft|gemini|ollama|mock
    base_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    credentials_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # Fernet; nunca exposto
    credentials_hint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    models: Mapped[list] = mapped_column(JSON, default=list)  # catálogo editável: ids, capacidades, preços
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="unknown")  # unknown|ok|error
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    limit_month_usd: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AIUsage(Base):
    """Livro-razão de consumo: reserva -> conciliação. Fonte de verdade de custos de IA."""
    __tablename__ = "ai_usage"
    __table_args__ = (
        # uma única chamada "viva" por chave de idempotência (protege contra cobrança duplicada em retries)
        Index("uq_ai_usage_live_key", "idempotency_key", unique=True,
              postgresql_where=text("status in ('reserved','succeeded','uncertain')"),
              sqlite_where=text("status in ('reserved','succeeded','uncertain')")),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True)
    model: Mapped[str] = mapped_column(String(120))
    capability: Mapped[str] = mapped_column(String(16))  # text|image|speech
    scope: Mapped[str] = mapped_column(String(8), default="line")  # line|lab
    line_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    step_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12), default="reserved")  # reserved|succeeded|failed|uncertain
    cost_estimated: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    cost_actual: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    cost_effective: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))  # actual se houver, senão estimado
    cost_source: Mapped[str] = mapped_column(String(12), default="estimate")  # provider|computed|estimate
    cost_unknown: Mapped[bool] = mapped_column(Boolean, default=False)  # executada com autorização explícita
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    images: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # texto/artefatos para reuso idempotente
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
