from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Float, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.runs.models import new_id, now


class VoiceSample(Base):
    """Amostra real gerada no Laboratório de Vozes (áudio no storage; nunca simulada)."""
    __tablename__ = "voice_samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(20))
    voice: Mapped[str] = mapped_column(String(80))
    text: Mapped[str] = mapped_column(Text)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    storage_key: Mapped[str] = mapped_column(String(200))
    seconds: Mapped[float] = mapped_column(Float)
    gen_ms: Mapped[int] = mapped_column(default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
