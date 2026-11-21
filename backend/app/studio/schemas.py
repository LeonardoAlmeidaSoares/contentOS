"""Identidade criativa de uma fábrica de vídeos. Gerada pelo assistente e validada aqui; o usuário nunca edita JSON."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Voice(BaseModel):
    engine: Literal["piper", "espeak"] = "piper"
    speed: float = Field(1.0, ge=0.6, le=1.5)
    pitch: int = Field(40, ge=0, le=99)  # só eSpeak
    description: str = "Narrador masculino, tom neutro"


class Editing(BaseModel):
    subtitles: bool = True
    ken_burns: bool = True  # movimento lento nas imagens
    resolution: Literal["720p", "1080p"] = "720p"
    credits: bool = True


class FactoryConfig(BaseModel):
    name: str = Field("", max_length=80)
    theme: str = Field("", max_length=300)  # tema/nicho do canal
    audience: str = Field("", max_length=200)
    language: str = "pt-BR"
    video_minutes: float = Field(5, ge=0.5, le=20)
    frequency_per_week: float = Field(0, ge=0, le=14)  # 0 = só manual
    narrative_style: str = Field("", max_length=300)
    visual_style: str = Field("", max_length=300)
    voice: Voice = Voice()
    editing: Editing = Editing()
    image_sources: Literal["auto", "pexels", "wikimedia"] = "auto"
    # por produção (não fazem parte da identidade): preenchidos ao produzir
    topic: str = Field("", max_length=300)
    script_text: str = Field("", max_length=40000)  # roteiro próprio (pula a geração por IA)

    @field_validator("name", "theme", "audience", "narrative_style", "visual_style", mode="before")
    @classmethod
    def _strip(cls, v):
        return (v or "").strip() if isinstance(v, str) or v is None else str(v)

    def identity(self) -> dict:
        return self.model_dump(exclude={"topic", "script_text"})


LABELS = {
    "name": "Nome da fábrica", "theme": "Tema", "audience": "Público", "video_minutes": "Duração do vídeo",
    "frequency_per_week": "Frequência", "narrative_style": "Estilo narrativo", "visual_style": "Estilo visual",
    "voice": "Voz", "editing": "Edição",
}


def preview(c: FactoryConfig) -> list[dict]:
    freq = "Somente sob demanda" if not c.frequency_per_week else (
        f"{c.frequency_per_week:g} vez(es) por semana")
    edit = ["legendas" if c.editing.subtitles else "sem legendas", "movimento nas imagens" if c.editing.ken_burns else "imagens fixas",
            c.editing.resolution]
    rows = [("Nome da fábrica", c.name), ("Tema", c.theme), ("Público", c.audience or "Geral"),
            ("Duração do vídeo", f"cerca de {c.video_minutes:g} minuto(s)"), ("Frequência", freq),
            ("Estilo narrativo", c.narrative_style or "Natural"), ("Estilo visual", c.visual_style or "Imagens reais relacionadas ao tema"),
            ("Voz", f"{c.voice.description} ({'Piper' if c.voice.engine == 'piper' else 'eSpeak'})"),
            ("Edição", ", ".join(edit))]
    return [{"label": a, "value": b} for a, b in rows]
