"""Assistente conversacional: interpreta linguagem natural em uma configuração de fábrica via Gemini (real).

Sem chave configurada, nada é simulado: levanta `NotConfigured` e a interface mostra a instrução.
"""
import json
import re
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.storage import get_storage
from app.providers.adapters import ADAPTERS
from app.providers.adapters.base import ProviderError, TextRequest
from app.providers.adapters.gemini import free_text_models
from app.providers.gateway import AIError, AIGateway
from app.providers.models import Provider
from app.studio.schemas import FactoryConfig, preview


class NotConfigured(Exception):
    pass


class AssistantError(Exception):
    """Erro apresentável ao usuário (limite, indisponibilidade, resposta inválida)."""


GEMINI_ENV_NAME = "Google Gemini (chave por variável de ambiente)"


def ensure_provider(db) -> Provider:
    """Provedor Gemini cuja chave vem só de GEMINI_API_KEY; idempotente. Modelos gratuitos (preço 0)."""
    p = db.scalar(select(Provider).where(Provider.service == "gemini", Provider.name == GEMINI_ENV_NAME))
    models = free_text_models()
    if settings.gemini_text_model not in [m["id"] for m in models]:
        models.insert(0, {**models[0], "id": settings.gemini_text_model})
    if p is None:
        p = Provider(name=GEMINI_ENV_NAME, service="gemini", config={"api": "generate_content", "key_source": "env"},
                     models=models, active=True, status="unknown", limit_month_usd=Decimal(1))  # teto de segurança
        db.add(p)
    else:
        p.models, p.active = models, True
    db.commit()
    return p


def provider_id() -> str:
    if not settings.gemini_api_key:
        raise NotConfigured("Defina GEMINI_API_KEY no arquivo .env (chave gratuita em aistudio.google.com/apikey) e reinicie com "
                            "'docker compose up -d'.")
    with SessionLocal() as db:
        return ensure_provider(db).id


def friendly(exc: Exception) -> str:
    s = str(exc)
    if isinstance(exc, ProviderError):
        if exc.status == 429:
            return "Limite de uso da Gemini atingido (camada gratuita). Aguarde alguns minutos e tente de novo."
        if exc.status in (400, 403) and ("API key" in s or "API_KEY" in s or "PERMISSION" in s):
            return "A chave do Gemini foi recusada. Confira o valor de GEMINI_API_KEY."
        if exc.status and exc.status >= 500:
            return "O Gemini está indisponível no momento. Tente novamente em instantes."
        if exc.status == 404:
            return "O modelo configurado não está disponível para esta chave (ajuste GEMINI_TEXT_MODEL)."
    return s


def call_json(system: str, prompt: str, *, max_tokens=4096, key: str | None = None, scope="studio") -> tuple[dict, object]:
    pid = provider_id()
    gw = AIGateway(SessionLocal, get_storage(), scope=scope)
    try:
        out = gw.text(pid, settings.gemini_text_model, TextRequest(prompt, system, max_tokens, json_mode=True),
                      key or f"studio:{uuid.uuid4()}")
    except (ProviderError, AIError) as exc:
        raise AssistantError(friendly(exc)) from None
    return parse_json(out.text or ""), out


def parse_json(text: str) -> dict:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        v = json.loads(t)
    except json.JSONDecodeError:
        raise AssistantError("A IA devolveu uma resposta fora do formato esperado. Tente reformular o pedido.") from None
    if isinstance(v, list) and v and isinstance(v[0], dict):
        v = v[0]
    if not isinstance(v, dict):
        raise AssistantError("A IA devolveu uma resposta fora do formato esperado. Tente reformular o pedido.")
    return v


SYSTEM = """Você é o assistente do ContentOS Studio, que cria "fábricas" de vídeos para YouTube a partir de uma conversa.
Interprete o pedido do usuário (em português) e devolva SOMENTE um JSON com:
{"status": "need_info" | "ready", "message": "texto curto e amigável em pt-BR", "questions": ["..."],
 "config": {"name": str, "theme": str, "audience": str, "video_minutes": number, "frequency_per_week": number,
 "narrative_style": str, "visual_style": str,
 "voice": {"engine": "piper", "speed": 0.6-1.5, "pitch": 0-99, "description": str},
 "editing": {"subtitles": bool, "ken_burns": bool, "resolution": "720p"|"1080p", "credits": bool}}}
Regras:
- Pergunte (status need_info) SOMENTE se faltar o essencial: o tema/nicho do canal. Nunca pergunte o que dá para inferir ou
  que tenha um bom padrão (duração 5 min, frequência 0 = sob demanda, legendas ligadas, resolução 720p).
- No máximo 2 perguntas, simples, sem jargão técnico.
- Quando status ready, preencha TODOS os campos de config com valores coerentes com o pedido. "name" deve ser um nome
  curto e atraente para a fábrica. frequency_per_week é número de vídeos por semana.
- Voz: "speed" menor (0.85-0.95) para narração sombria/calma; maior para energética. Só existe voz masculina neutra em pt-BR.
- Imagens vêm de bancos de imagens livres (fotos reais), não de IA: reflita isso em visual_style de modo realista.
- Não invente funcionalidades como publicar no YouTube."""


def _history(messages: list[dict]) -> str:
    lines = []
    for m in messages[-12:]:
        who = "Usuário" if m.get("role") == "user" else "Assistente"
        lines.append(f"{who}: {str(m.get('content', ''))[:2000]}")
    return "\n".join(lines)


def interpret(messages: list[dict]) -> dict:
    data, out = call_json(SYSTEM, "Conversa até agora:\n" + _history(messages))
    return _build(data, out)


ADJUST_SYSTEM = SYSTEM + """
Você receberá a configuração ATUAL da fábrica e um pedido de ajuste em linguagem natural. Devolva status "ready" e a
configuração COMPLETA atualizada (altere só o que o pedido exige; mantenha o restante igual). Em "message" resuma o que mudou."""


def adjust(current: dict, instruction: str) -> dict:
    prompt = f"Configuração atual: {json.dumps(current, ensure_ascii=False)}\nPedido de ajuste: {instruction[:1500]}"
    data, out = call_json(ADJUST_SYSTEM, prompt)
    r = _build(data, out)
    if r["status"] != "ready":
        return r
    return r


def _build(data: dict, out) -> dict:
    status = data.get("status") if data.get("status") in ("need_info", "ready") else "need_info"
    msg = str(data.get("message") or "")[:1500]
    questions = [str(q)[:300] for q in (data.get("questions") or [])][:2]
    usage = {"input_tokens": out.input_tokens, "output_tokens": out.output_tokens, "cost": float(out.cost)}
    if status == "ready":
        try:
            cfg = FactoryConfig.model_validate(data.get("config") or {})
        except Exception:  # noqa: BLE001
            cfg = None
        if cfg is None or not cfg.theme:
            return {"status": "need_info", "message": msg or "Sobre qual tema será a fábrica?",
                    "questions": questions or ["Sobre qual tema ou nicho será o canal?"], "proposal": None, "usage": usage}
        cfg.voice.engine = "piper"
        if not cfg.name:
            cfg.name = cfg.theme[:60]
        return {"status": "ready", "message": msg, "questions": [], "usage": usage,
                "proposal": {"config": cfg.identity(), "preview": preview(cfg)}}
    return {"status": "need_info", "message": msg, "questions": questions or ["Sobre qual tema será a fábrica?"],
            "proposal": None, "usage": usage}
