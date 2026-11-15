from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.runs.models import new_id, now


class Experiment(Base):
    __tablename__ = "lab_experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(8))  # image|text
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)  # ex.: categoria do benchmark
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    prompt: Mapped[str] = mapped_column(Text)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

    results: Mapped[list["LabResult"]] = relationship(back_populates="experiment", order_by="LabResult.created_at",
                                                      cascade="all, delete-orphan")


class LabResult(Base):
    __tablename__ = "lab_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("lab_experiments.id", ondelete="CASCADE"), index=True)
    provider_id: Mapped[str] = mapped_column(String(36))
    model: Mapped[str] = mapped_column(String(120))
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    experiment: Mapped[Experiment] = relationship(back_populates="results")


class BenchmarkPrompt(Base):
    __tablename__ = "benchmark_prompts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    category: Mapped[str] = mapped_column(String(120), unique=True)
    prompt: Mapped[str] = mapped_column(Text)
    negative_prompt: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
