"""Porta única para chamadas pagas de IA: estimativa -> reserva de orçamento -> chamada -> conciliação.

Garantias:
- Nada é chamado sem estimativa (ou autorização explícita `allow_unknown_cost`).
- Reservas são contadas por chamadas concorrentes (advisory lock + livro-razão `ai_usage`).
- Chave de idempotência: retry de chamada já concluída devolve o resultado salvo (sem nova cobrança);
  chamada de resultado incerto (timeout após envio) nunca é repetida automaticamente.
"""
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import settings
from app.core.storage import Storage
from app.pipelines.registry import OutFile
from app.providers.adapters import ADAPTERS
from app.providers.adapters.base import AIResult, Conn, ImageRequest, ProviderError, SpeechRequest, TextRequest, D
from app.providers.ledger import ledger_sum
from app.providers.models import COUNTED, AIUsage, Provider
from app.runs.models import Run, now
from app.runs.service import month_start, run_spent


class AIError(Exception):
    retryable = False


class CostUnknown(AIError):
    pass


class BudgetExceeded(AIError):
    pass


class UncertainDuplicate(AIError):
    pass


class Unsupported(AIError):
    pass


@dataclass
class Outcome:
    text: str | None = None
    files: list[OutFile] = field(default_factory=list)
    cost: Decimal = Decimal(0)
    cost_source: str = "estimate"
    usage_id: str = ""
    cached: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_id: str | None = None
    duration_ms: int | None = None


def find_model(prov: Provider, model: str) -> dict | None:
    return next((m for m in prov.models if m.get("id") == model), None)


def scrub(msg: str, secret: str | None) -> str:
    return msg.replace(secret, "***") if secret else msg


def estimate_for(prov: Provider, model: str, capability: str, req):
    mcfg = find_model(prov, model)
    if not mcfg or capability not in mcfg.get("capabilities", []) or not mcfg.get("active", True):
        raise Unsupported(f"modelo '{model}' indisponível para {capability} em {prov.name}")
    return ADAPTERS[prov.service].estimate(capability, mcfg, req), mcfg


def _lock(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("select pg_advisory_xact_lock(7421)"))  # serializa reservas concorrentes


def check_budgets(db: Session, prov: Provider, cost: Decimal, *, run_id: str | None, scope: str) -> None:
    ms = month_start(now())
    if prov.limit_month_usd is not None:
        spent = ledger_sum(db, provider_id=prov.id, since=ms)
        if spent + cost > prov.limit_month_usd:
            raise BudgetExceeded(f"limite mensal do provedor {prov.name} excedido ({spent} + {cost} > {prov.limit_month_usd})")
    if scope == "lab":
        spent = ledger_sum(db, scope="lab", since=ms)
        if spent + cost > D(settings.lab_month_limit_usd):
            raise BudgetExceeded(f"limite mensal do Laboratório excedido ({spent} + {cost} > {settings.lab_month_limit_usd})")
    run = db.get(Run, run_id) if run_id else None
    line = run.line if run else None
    if run and line:
        spent_run = run_spent(db, run)
        if line.cost_limit_run is not None and spent_run + cost > line.cost_limit_run:
            raise BudgetExceeded(f"limite por execução excedido ({spent_run} + {cost} > {line.cost_limit_run})")
        if line.cost_limit_month is not None:
            others = sum((r.cost for r in line.runs if r.id != run.id and r.created_at >= ms), Decimal(0))
            if others + spent_run + cost > line.cost_limit_month:
                raise BudgetExceeded(f"limite mensal da linha excedido ({others + spent_run} + {cost} > {line.cost_limit_month})")


class AIGateway:
    def __init__(self, session_factory, storage: Storage, *, run_id=None, step_name=None, line_id=None, scope="line"):
        self.sf, self.storage = session_factory, storage
        self.run_id, self.step_name, self.line_id, self.scope = run_id, step_name, line_id, scope

    # -- API pública ---------------------------------------------------------
    def text(self, provider_id: str, model: str, req: TextRequest, key: str, allow_unknown_cost=False) -> Outcome:
        return self._call(provider_id, model, "text", req, key, allow_unknown_cost)

    def image(self, provider_id: str, model: str, req: ImageRequest, key: str, allow_unknown_cost=False,
              reference_keys: list[str] | None = None) -> Outcome:
        if reference_keys:
            req.references = [(sniff_mime(d), d) for d in (self.storage.get(k) for k in reference_keys)]
        return self._call(provider_id, model, "image", req, key, allow_unknown_cost)

    def speech(self, provider_id: str, model: str, req: SpeechRequest, key: str, allow_unknown_cost=False) -> Outcome:
        return self._call(provider_id, model, "speech", req, key, allow_unknown_cost)

    # -- núcleo --------------------------------------------------------------
    def _call(self, provider_id, model, capability, req, key, allow_unknown) -> Outcome:
        with self.sf() as db:
            prov = db.get(Provider, provider_id)
            if prov is None or not prov.active:
                raise Unsupported("provedor inexistente ou inativo")
            est, mcfg = estimate_for(prov, model, capability, req)
            if est.error:
                raise Unsupported(est.error)
            live = db.scalar(select(AIUsage).where(AIUsage.idempotency_key == key, AIUsage.status.in_(COUNTED)))
            if live is not None:
                if live.status == "succeeded":
                    return self._cached(live)
                raise UncertainDuplicate("chamada anterior com a mesma chave está em andamento ou teve resultado incerto; "
                                         "não será repetida automaticamente (evita cobrança duplicada)")
            if est.cost is None and not allow_unknown:
                raise CostUnknown(f"custo não determinável previamente ({est.basis}); requer autorização explícita")
            reserve = est.cost if est.cost is not None else Decimal(0)
            _lock(db)
            check_budgets(db, prov, reserve, run_id=self.run_id, scope=self.scope)
            usage = AIUsage(provider_id=prov.id, model=model, capability=capability, scope=self.scope,
                            line_id=self.line_id, run_id=self.run_id, step_name=self.step_name, idempotency_key=key,
                            status="reserved", cost_estimated=reserve, cost_effective=reserve, cost_source="estimate",
                            cost_unknown=est.cost is None)
            db.add(usage)
            try:
                db.commit()  # a reserva fica visível para chamadas concorrentes antes da requisição externa
            except IntegrityError:
                db.rollback()
                raise UncertainDuplicate("chamada duplicada com a mesma chave de idempotência") from None
            usage_id = usage.id
            if prov.credentials_enc:
                secret = crypto.decrypt(prov.credentials_enc)
            elif prov.service == "gemini" and (prov.config or {}).get("key_source") == "env":
                secret = settings.gemini_api_key or None  # chave só em variável de ambiente
            else:
                secret = None
            if secret is None and ADAPTERS[prov.service].needs_key:
                raise Unsupported("chave de API não configurada para este provedor")
            conn = Conn(prov.service, (prov.base_url or ADAPTERS[prov.service].default_base_url or "").rstrip("/"),
                        secret, dict(prov.config or {}))
            prov_name = prov.name

        import time
        t0 = time.monotonic()
        adapter = ADAPTERS[conn.service]
        try:
            res: AIResult = (adapter.text if capability == "text" else adapter.speech if capability == "speech"
                             else adapter.image)(conn, model, req, mcfg)
        except ProviderError as exc:
            self._fail(usage_id, provider_id, scrub(str(exc), secret), exc.uncertain, int((time.monotonic() - t0) * 1000))
            err = ProviderError(scrub(str(exc), secret), exc.status, exc.uncertain)
            err.retryable = exc.retryable and not exc.uncertain
            raise err from None
        except Exception as exc:  # noqa: BLE001  (bug do adaptador/parse): tratar como incerto, não repetir
            self._fail(usage_id, provider_id, scrub(f"erro inesperado: {exc.__class__.__name__}", secret), True, 0)
            raise ProviderError(f"erro inesperado no adaptador: {exc.__class__.__name__}", uncertain=True) from None
        dur = int((time.monotonic() - t0) * 1000)

        files, stored = [], []
        for i, img in enumerate(res.images):
            ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/svg+xml": "svg"}.get(img.mime, "bin")
            skey = f"ai/{usage_id}/{i + 1}.{ext}"
            self.storage.put(skey, img.data, img.mime)
            dims = image_size(img.data)
            meta = {"size": len(img.data), **({"width": dims[0], "height": dims[1]} if dims else {})}
            files.append(OutFile(f"{model}-{usage_id[:8]}-{i + 1}.{ext}", img.mime, storage_key=skey,
                                 provider=prov_name, model=model, meta=meta))
            stored.append({"key": skey, "filename": files[-1].filename, "mime": img.mime, "meta": meta})

        if res.audio:
            skey = f"ai/{usage_id}/1.wav"
            self.storage.put(skey, res.audio, "audio/wav")
            files.append(OutFile(f"{model}-{usage_id[:8]}.wav", "audio/wav", storage_key=skey, provider=prov_name, model=model,
                                 meta={"size": len(res.audio)}))
            stored.append({"key": skey, "filename": files[-1].filename, "mime": "audio/wav", "meta": files[-1].meta})

        with self.sf() as db:
            u = db.get(AIUsage, usage_id)
            u.status, u.finished_at, u.duration_ms, u.request_id = "succeeded", now(), dur, res.request_id
            u.input_tokens, u.output_tokens, u.images = res.input_tokens, res.output_tokens, len(res.images)
            u.cost_actual = res.cost_actual
            u.cost_source = res.cost_source if res.cost_actual is not None else "estimate"
            u.cost_effective = res.cost_actual if res.cost_actual is not None else u.cost_estimated
            u.result = {"text": res.text, "files": stored, "usage": res.usage_raw, "provider": prov_name}
            if capability == "speech":  # trilha de auditoria: voz/idioma/estilo realmente enviados ao provedor
                u.result["request"] = {"voice": req.voice, "language": req.language, "style": req.style, "chars": len(req.text)}
            p = db.get(Provider, provider_id)
            p.status, p.status_message, p.status_checked_at = "ok", None, now()
            db.commit()
            return Outcome(res.text, files, u.cost_effective, u.cost_source, u.id, False, res.input_tokens,
                           res.output_tokens, res.request_id, dur)

    def _fail(self, usage_id, provider_id, error, uncertain, dur) -> None:
        with self.sf() as db:
            u = db.get(AIUsage, usage_id)
            u.status = "uncertain" if uncertain else "failed"  # incerto continua contando custo (conservador)
            u.error, u.finished_at, u.duration_ms = error[:1000], now(), dur
            if not uncertain:
                u.cost_effective = Decimal(0)  # falha confirmada: reserva liberada
            p = db.get(Provider, provider_id)
            p.status, p.status_message, p.status_checked_at = "error", error[:300], now()
            db.commit()

    def _cached(self, u: AIUsage) -> Outcome:
        r = u.result or {}
        files = [OutFile(f["filename"], f["mime"], storage_key=f["key"], provider=r.get("provider"), model=u.model, meta=f.get("meta"))
                 for f in r.get("files", [])]
        return Outcome(r.get("text"), files, u.cost_effective, u.cost_source, u.id, True, u.input_tokens,
                       u.output_tokens, u.request_id, u.duration_ms)


def sniff_mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def image_size(data: bytes) -> tuple[int, int] | None:
    """Dimensões de PNG/JPEG sem dependências."""
    import struct
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                break
            marker, ln = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + ln
    return None
