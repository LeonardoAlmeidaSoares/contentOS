"""API do Laboratório de Vozes (aditiva): catálogo, amostras reais, interpretação de pedidos e identidade vocal da fábrica."""
import time

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, get_db
from app.core.storage import get_storage
from app.providers.gateway import AIGateway
from app.runs.models import ProductionLine, new_id
from app.studio import assistant
from app.studio.schemas import FactoryConfig, Voice as VoiceCfg
from app.voices import service
from app.voices.engines import Unavailable, VoiceError
from app.voices.models import VoiceSample

router = APIRouter(prefix="/api/voices", tags=["voices"])
PIPELINE = "video_youtube"
DEFAULT_TEXT = ("Era uma noite escura e silenciosa, quando a velha porta rangeu sozinha. "
                "Ninguém ouviu o sussurro que veio do fim do corredor.")


class SampleIn(BaseModel):
    provider: str
    voice: str
    text: str = Field(min_length=3, max_length=service.MAX_SAMPLE_CHARS)
    speed: float | None = Field(None, ge=0.6, le=1.5)
    pitch: int | None = Field(None, ge=0, le=99)
    style: str = Field("", max_length=300)


class InterpretIn(BaseModel):
    instruction: str = Field(min_length=3, max_length=500)


class IdentityIn(BaseModel):
    provider: str
    voice_id: str
    speed: float = Field(1.0, ge=0.6, le=1.5)
    pitch: int = Field(40, ge=0, le=99)
    style: str = Field("", max_length=300)
    instructions: str = Field("", max_length=500)
    fallback: bool = True


def _sample(s: VoiceSample) -> dict:
    return {"id": s.id, "provider": s.provider, "voice": s.voice, "text": s.text, "params": s.params, "seconds": round(s.seconds, 2),
            "gen_ms": s.gen_ms, "cost": float(s.cost), "created_at": s.created_at, "audio_url": f"/api/voices/samples/{s.id}/audio"}


@router.get("/providers")
def providers():
    return {"providers": service.catalog(), "default_text": DEFAULT_TEXT, "max_chars": service.MAX_SAMPLE_CHARS}


@router.post("/samples", status_code=201)
def create_sample(body: SampleIn, db: Session = Depends(get_db)):
    try:
        e = service.check(body.provider, body.voice)
    except VoiceError as exc:
        raise HTTPException(422, str(exc)) from None
    params = {}
    if body.speed is not None and e.controls.get("speed"):
        params["speed"] = body.speed
    if body.pitch is not None and e.controls.get("pitch"):
        params["pitch"] = body.pitch
    if body.style.strip() and e.controls.get("style"):
        params["style"] = body.style.strip()
    gw = AIGateway(SessionLocal, get_storage(), scope="lab")
    t0 = time.monotonic()
    try:
        r = service.synthesize(body.provider, body.voice, body.text, params, gateway=gw, key=f"voice-sample:{time.time_ns()}")
    except Unavailable as exc:
        raise HTTPException(412, f"{e.label} indisponível: {exc}") from None
    except VoiceError as exc:
        raise HTTPException(502, f"falha ao gerar a amostra: {exc}") from None
    sid = new_id()  # o id do ORM só existe após o flush: usá-lo na chave sobrescreveria todas as amostras
    s = VoiceSample(id=sid, provider=r.provider, voice=r.voice, text=body.text, params=params, storage_key="", seconds=r.seconds,
                    gen_ms=int((time.monotonic() - t0) * 1000), cost=r.cost)
    s.storage_key = f"voices/samples/{sid}.wav"
    get_storage().put(s.storage_key, r.wav, "audio/wav")
    db.add(s)
    db.commit()
    return _sample(s)


@router.get("/samples")
def list_samples(limit: int = 30, db: Session = Depends(get_db)):
    rows = db.scalars(select(VoiceSample).order_by(VoiceSample.created_at.desc()).limit(min(limit, 100))).all()
    return [_sample(s) for s in rows]


@router.get("/samples/{sid}/audio")
def sample_audio(sid: str, db: Session = Depends(get_db)):
    s = db.get(VoiceSample, sid)
    if not s:
        raise HTTPException(404, "amostra não encontrada")
    return Response(get_storage().get(s.storage_key), media_type="audio/wav", headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/samples/{sid}", status_code=204)
def delete_sample(sid: str, db: Session = Depends(get_db)):
    s = db.get(VoiceSample, sid)
    if s:
        db.delete(s)
        db.commit()


# ---------------------------------------------------------------- interpretação de pedidos em linguagem natural
INTERPRET_SYSTEM = """Você escolhe a voz de narração de um canal de vídeos em pt-BR a partir de um pedido em linguagem natural.
Receberá o catálogo REAL de provedores/vozes disponíveis agora (com o que cada um controla). Responda SOMENTE JSON:
{"provider": id, "voice": id exato do catálogo, "speed": número 0.6-1.5 ou null, "style": texto curto em português com a instrução
de entrega ou "", "explanation": 1-2 frases, "unsupported": [partes do pedido que nenhum provedor disponível consegue controlar]}.
Regras: escolha o provedor que melhor atende ao pedido — se o pedido fala de tom/emoção/estilo/mistério e algum provedor tem controle de
estilo, prefira-o e preencha "style"; use apenas ids do catálogo; só use "speed" se o provedor tiver controle de velocidade; só preencha "style" se o provedor
tiver controle de estilo; NUNCA prometa controles inexistentes — liste-os em "unsupported" (ex.: "grave" em Piper). Gênero só quando
o catálogo informar; se o catálogo não informa o gênero, não afirme."""


@router.post("/interpret")
def interpret(body: InterpretIn):
    cat = [{"provider": p["id"], "controls": p["controls"], "quality_note": p["quality_note"],
            "voices": [{"id": v["id"], "gender": v["gender"], "note": v["note"]} for v in p["voices"]]}
           for p in service.catalog() if p["available"]]
    if not cat:
        raise HTTPException(412, "nenhum provedor de voz disponível")
    try:
        import json
        data, _ = assistant.call_json(INTERPRET_SYSTEM, f"Catálogo: {json.dumps(cat, ensure_ascii=False)}\nPedido: {body.instruction}",
                                      max_tokens=1024, scope="lab")
    except assistant.NotConfigured as exc:
        raise HTTPException(412, str(exc)) from None
    except assistant.AssistantError as exc:
        raise HTTPException(502, str(exc)) from None
    prov, voice = str(data.get("provider", "")), str(data.get("voice", ""))
    try:
        e = service.check(prov, voice)
    except VoiceError:
        raise HTTPException(502, "A IA sugeriu uma voz que não existe no catálogo. Reformule o pedido.") from None
    unsupported = [str(u)[:150] for u in (data.get("unsupported") or [])][:6]
    speed = data.get("speed") if isinstance(data.get("speed"), (int, float)) and e.controls.get("speed") else None
    style = str(data.get("style") or "")[:300] if e.controls.get("style") else ""
    if data.get("style") and not style:
        unsupported.append("estilo narrativo (este provedor não oferece controle de estilo)")
    return {"provider": prov, "voice": voice, "speed": min(max(float(speed), .6), 1.5) if speed else None, "style": style,
            "explanation": str(data.get("explanation") or "")[:400], "unsupported": unsupported, "instruction": body.instruction}


# ---------------------------------------------------------------- identidade vocal da fábrica
def _line(db: Session, lid: str) -> ProductionLine:
    line = db.get(ProductionLine, lid)
    if not line or line.pipeline != PIPELINE:
        raise HTTPException(404, "fábrica não encontrada")
    return line


@router.get("/factories/{lid}")
def factory_voice(lid: str, db: Session = Depends(get_db)):
    v = FactoryConfig.model_validate(_line(db, lid).config).voice
    p, vid = service.effective(v)
    return {"voice": v.model_dump(), "provider": p, "voice_id": vid, "legacy": v.provider is None}


@router.put("/factories/{lid}")
def set_factory_voice(lid: str, body: IdentityIn, db: Session = Depends(get_db)):
    line = _line(db, lid)
    try:
        e = service.check(body.provider, body.voice_id)
    except VoiceError as exc:
        raise HTTPException(422, str(exc)) from None
    ok, why = e.available()
    if not ok:
        raise HTTPException(412, f"{e.label} indisponível: {why}")
    cfg = FactoryConfig.model_validate(line.config)
    v = cfg.voice
    v.provider, v.voice_id, v.speed, v.pitch, v.fallback = body.provider, body.voice_id, body.speed, body.pitch, body.fallback
    v.style = body.style.strip() if e.controls.get("style") else ""
    v.instructions = body.instructions.strip()
    v.engine = "espeak" if body.provider == "espeak" else "piper"  # campo legado
    label = next(x.label for x in e.voices() if x.id == body.voice_id)
    v.description = f"{label} ({e.label})"
    line.config = cfg.identity()
    db.commit()
    return factory_voice(lid, db)
