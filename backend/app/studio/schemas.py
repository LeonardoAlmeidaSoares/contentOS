"""Identidade criativa de uma fábrica de vídeos. Gerada pelo assistente e validada aqui; o usuário nunca edita JSON."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PER_RUN = {"topic", "script_text", "format", "standard_id", "standard_version", "pilot"}


class Voice(BaseModel):
    """Identidade vocal. `engine` é o campo legado (fábricas antigas); `provider`/`voice_id` o substituem quando presentes."""
    engine: Literal["piper", "espeak"] = "piper"
    speed: float = Field(1.0, ge=0.6, le=1.5)
    pitch: int = Field(40, ge=0, le=99)  # só eSpeak
    description: str = "Narrador masculino, tom neutro"
    provider: Literal["piper", "kokoro", "gemini", "espeak"] | None = None  # None = fábrica antiga (usa `engine`)
    voice_id: str | None = None  # None = voz padrão do provedor
    language: str = "pt-BR"
    style: str = Field("", max_length=300)  # instrução de entrega (só provedores com controle de estilo)
    instructions: str = Field("", max_length=500)  # pedido original em linguagem natural (registro)
    params: dict = Field(default_factory=dict)  # parâmetros específicos do provedor
    fallback: bool = True  # indisponibilidade do provedor => Piper (registrado); falha em execução NÃO usa fallback


class Editing(BaseModel):
    subtitles: bool = True
    ken_burns: bool = True  # movimento lento nas imagens
    resolution: Literal["720p", "1080p"] = "720p"
    credits: bool = True


ASPECTS = {"horizontal": (16, 9), "vertical": (9, 16)}  # vertical = Shorts/Reels
FORMAT_LABELS = {"horizontal": "Horizontal 16:9", "vertical": "Vertical 9:16 (Shorts/Reels)"}


class Format(BaseModel):
    """Formato de vídeo habilitado no canal, com proporção e faixa de duração próprias."""
    id: Literal["horizontal", "vertical"]
    enabled: bool = True
    min_seconds: int = Field(60, ge=10, le=3600)
    max_seconds: int = Field(180, ge=10, le=3600)

    @model_validator(mode="after")
    def _range(self):
        if self.min_seconds > self.max_seconds:
            raise ValueError("duração mínima maior que a máxima")
        return self


def dimensions(fmt: str, resolution: str) -> tuple[int, int]:
    """Largura x altura finais (a menor dimensão é 720 ou 1080)."""
    short = 720 if resolution == "720p" else 1080
    w, h = ASPECTS[fmt]
    k = short / min(w, h)
    return int(round(w * k)), int(round(h * k))


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
    # Canal (aditivo: fábricas antigas não têm estes campos e seguem funcionando sem padrão versionado)
    channel_name: str = Field("", max_length=100)
    niche: str = Field("", max_length=200)
    description: str = Field("", max_length=1000)
    platform: Literal["youtube"] = "youtube"
    external_channel_id: str | None = None  # canal externo vinculado (YouTube), quando existir
    formats: list[Format] = Field(default_factory=list)  # vazio = fábrica antiga (16:9, duração `video_minutes`)
    tone: str = Field("", max_length=300)
    editing_rhythm: Literal["lento", "medio", "rapido"] = "medio"
    references: str = Field("", max_length=1000)
    restrictions: str = Field("", max_length=1000)  # regras editoriais em texto (orientam o roteiro)
    forbidden_terms: list[str] = Field(default_factory=list, max_length=40)  # termos proibidos: verificados no roteiro
    # por produção (não fazem parte da identidade): preenchidos ao produzir
    topic: str = Field("", max_length=300)
    script_text: str = Field("", max_length=40000)  # roteiro próprio (pula a geração por IA)
    format: str = ""  # formato desta produção (um dos `formats` habilitados)
    standard_id: str | None = None
    standard_version: int | None = None
    pilot: bool = False

    @field_validator("name", "theme", "audience", "narrative_style", "visual_style", mode="before")
    @classmethod
    def _strip(cls, v):
        return (v or "").strip() if isinstance(v, str) or v is None else str(v)

    def identity(self) -> dict:
        return self.model_dump(exclude=PER_RUN)

    def target(self) -> Format | None:
        """Formato desta produção (None = fábrica antiga, sem regras de formato/duração)."""
        if not self.formats:
            return None
        enabled = [f for f in self.formats if f.enabled]
        return next((f for f in enabled if f.id == self.format), None)

    def minutes(self) -> float:
        t = self.target()
        return (t.min_seconds + t.max_seconds) / 120 if t else self.video_minutes

    def dims(self) -> tuple[int, int]:
        t = self.target()
        return dimensions(t.id if t else "horizontal", self.editing.resolution)


LABELS = {
    "name": "Nome da fábrica", "theme": "Tema", "audience": "Público", "video_minutes": "Duração do vídeo",
    "frequency_per_week": "Frequência", "narrative_style": "Estilo narrativo", "visual_style": "Estilo visual",
    "voice": "Voz", "editing": "Edição",
}


def voice_label(v: Voice) -> str:
    names = {"piper": "Piper", "espeak": "eSpeak", "kokoro": "Kokoro", "gemini": "Gemini TTS"}
    p = v.provider or v.engine
    return names.get(p, p) + (f" · {v.voice_id}" if v.voice_id else "")


def preview(c: FactoryConfig) -> list[dict]:
    freq = "Somente sob demanda" if not c.frequency_per_week else (
        f"{c.frequency_per_week:g} vez(es) por semana")
    edit = ["legendas" if c.editing.subtitles else "sem legendas", "movimento nas imagens" if c.editing.ken_burns else "imagens fixas",
            c.editing.resolution]
    rows = [("Nome da fábrica", c.name), ("Tema", c.theme), ("Público", c.audience or "Geral"),
            ("Duração do vídeo", "; ".join(f"{FORMAT_LABELS[f.id]}: {f.min_seconds}–{f.max_seconds}s" for f in c.formats if f.enabled)
             if c.formats else f"cerca de {c.video_minutes:g} minuto(s)"), ("Frequência", freq),
            ("Estilo narrativo", c.narrative_style or "Natural"), ("Estilo visual", c.visual_style or "Imagens reais relacionadas ao tema"),
            ("Voz", f"{c.voice.description} ({voice_label(c.voice)})"),
            ("Edição", ", ".join(edit))]
    if c.formats:
        rows = [("Canal", c.channel_name or c.name), ("Nicho", c.niche or c.theme), ("Idioma", c.language),
                ("Tom", c.tone or "Conforme o estilo narrativo"), ("Ritmo de edição", c.editing_rhythm)] + rows
        if c.restrictions or c.forbidden_terms:
            rows.append(("Restrições", " ".join(x for x in (c.restrictions, "Proibido: " + ", ".join(c.forbidden_terms) if c.forbidden_terms else "") if x)))
    return [{"label": a, "value": b} for a, b in rows]
