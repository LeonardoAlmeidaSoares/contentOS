import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
                        text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

ACTIVE_STATUSES = ("queued", "running", "retrying")
Money = Numeric(14, 6)


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class ProductionLine(Base):
    __tablename__ = "production_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    pipeline: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_limit_run: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    cost_limit_month: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    backoff_seconds: Mapped[int] = mapped_column(Integer, default=5)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    runs: Mapped[list["Run"]] = relationship(back_populates="line")


class Run(Base):
    __tablename__ = "runs"
    # No máximo uma execução ativa por linha (garantia no banco contra duplicidade)
    __table_args__ = (
        Index("uq_runs_one_active_per_line", "line_id", unique=True,
              postgresql_where=text("status in ('queued','running','retrying')"),
              sqlite_where=text("status in ('queued','running','retrying')")),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    line_id: Mapped[str | None] = mapped_column(ForeignKey("production_lines.id"), nullable=True, index=True)
    pipeline: Mapped[str] = mapped_column(String(64))
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual|schedule|lab|pilot
    standard_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # padrão do canal usado (rastreabilidade)
    standard_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    format: Mapped[str | None] = mapped_column(String(16), nullable=True)  # horizontal|vertical
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # snapshot da config usada (idempotência em retomadas)
    # queued|running|retrying|succeeded|failed|cancelled
    status: Mapped[str] = mapped_column(String(16), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    line: Mapped[ProductionLine | None] = relationship(back_populates="runs")
    steps: Mapped[list["RunStep"]] = relationship(
        back_populates="run", order_by="RunStep.position", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="run", order_by="Artifact.created_at", cascade="all, delete-orphan"
    )

    @property
    def line_name(self) -> str | None:
        return self.line.name if self.line else None


class RunStep(Base):
    __tablename__ = "run_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(64))
    # pending|running|retrying|succeeded|failed|cancelled
    status: Mapped[str] = mapped_column(String(16), default="pending")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cost: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    attempts: Mapped[int] = mapped_column(Integer, default=0)  # tentativas do ciclo atual (zera ao retomar)
    total_attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[Run] = relationship(back_populates="steps")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    step_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(512))
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    run: Mapped[Run] = relationship(back_populates="artifacts")


class RunLog(Base):
    __tablename__ = "run_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    step_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    level: Mapped[str] = mapped_column(String(8), default="info")  # info|warn|error
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
