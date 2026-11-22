"""Contrato comum dos adaptadores de provedores de IA (texto e imagem nesta fase)."""
import base64
import math
from dataclasses import dataclass, field
from decimal import Decimal

import httpx

TIMEOUT = httpx.Timeout(180.0, connect=10.0)
_client_factory = lambda: httpx.Client(timeout=TIMEOUT)  # noqa: E731  (testes substituem por MockTransport)


def http() -> httpx.Client:
    return _client_factory()


def set_client_factory(fn) -> None:
    global _client_factory
    _client_factory = fn


def D(x) -> Decimal:
    return Decimal(str(x))


def approx_tokens(text: str) -> int:
    """Estimativa conservadora (≈3 caracteres/token) — só para limitar custo previamente."""
    return math.ceil(len(text) / 3) + 1


@dataclass
class Conn:
    service: str
    base_url: str
    api_key: str | None
    config: dict = field(default_factory=dict)


@dataclass
class TextRequest:
    prompt: str
    system: str | None = None
    max_tokens: int = 1024
    json_mode: bool = False


@dataclass
class ImageRequest:
    prompt: str
    negative_prompt: str | None = None
    aspect_ratio: str = "1:1"
    resolution: str = "1K"
    quality: str = "medium"
    n: int = 1
    references: list[tuple[str, bytes]] = field(default_factory=list)  # (mime, bytes)


@dataclass
class SpeechRequest:
    text: str
    voice: str
    style: str | None = None  # instrução de entrega em linguagem natural (só provedores que suportam)
    language: str = "pt-BR"


@dataclass
class Estimate:
    cost: Decimal | None  # None = não é possível determinar/limitar previamente
    basis: str
    error: str | None = None  # combinação não suportada pelo modelo


@dataclass
class ImageOut:
    data: bytes
    mime: str = "image/png"


@dataclass
class AIResult:
    model: str
    text: str | None = None
    audio: bytes | None = None  # WAV completo (capacidade "speech")
    images: list[ImageOut] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_actual: Decimal | None = None
    cost_source: str = "estimate"  # provider|computed|estimate
    request_id: str | None = None
    usage_raw: dict | None = None


class ProviderError(Exception):
    """Falha de integração. `uncertain`=a requisição pode ter sido processada/cobrada (não reexecutar sozinho)."""

    def __init__(self, message: str, status: int | None = None, uncertain: bool = False):
        super().__init__(message)
        self.status, self.uncertain = status, uncertain
        # 4xx (exceto 408/429) não melhora com retry
        self.retryable = not (status and 400 <= status < 500 and status not in (408, 429))


def b64(data: str) -> bytes:
    return base64.b64decode(data)


def request(method: str, url: str, **kw) -> httpx.Response:
    """Executa HTTP traduzindo falhas; sem log de headers/corpo (credenciais)."""
    try:
        with http() as c:
            resp = c.request(method, url, **kw)
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ProviderError(f"não foi possível conectar: {exc.__class__.__name__}") from None
    except httpx.HTTPError as exc:  # timeouts de leitura / conexão caída após o envio
        raise ProviderError(f"falha de rede após envio: {exc.__class__.__name__}", uncertain=True) from None
    if resp.status_code >= 400:
        detail = resp.text[:300].replace("\n", " ")
        raise ProviderError(f"HTTP {resp.status_code}: {detail}", status=resp.status_code)
    return resp


class Adapter:
    service = ""
    label = ""
    default_base_url: str | None = None
    needs_key = True
    capabilities: tuple[str, ...] = ()
    known_models: list[dict] = []
    pricing_source = ""  # URL + data da conferência dos preços semeados

    def test(self, conn: Conn) -> str:
        """Verificação gratuita de conectividade/credencial. Devolve mensagem curta."""
        raise NotImplementedError

    def estimate(self, capability: str, mcfg: dict, req) -> Estimate:
        raise NotImplementedError

    def text(self, conn: Conn, model: str, req: TextRequest, mcfg: dict) -> AIResult:
        raise ProviderError("geração de texto não suportada por este provedor")

    def image(self, conn: Conn, model: str, req: ImageRequest, mcfg: dict) -> AIResult:
        raise ProviderError("geração de imagem não suportada por este provedor")

    def speech(self, conn: Conn, model: str, req: SpeechRequest, mcfg: dict) -> AIResult:
        raise ProviderError("síntese de voz não suportada por este provedor")


def token_text_estimate(mcfg: dict, req: TextRequest) -> Estimate:
    """Limite superior: tokens de entrada estimados + max_tokens de saída (a API recebe esse teto)."""
    p = (mcfg.get("pricing") or {})
    if "input_per_mtok" not in p or "output_per_mtok" not in p:
        return Estimate(None, "preço do modelo não configurado")
    tin = approx_tokens((req.system or "") + req.prompt)
    cost = (D(tin) * D(p["input_per_mtok"]) + D(req.max_tokens) * D(p["output_per_mtok"])) / D(1_000_000)
    return Estimate(cost, f"≤ {tin} tokens de entrada + {req.max_tokens} de saída (teto)")


def token_text_actual(mcfg: dict, in_tok: int | None, out_tok: int | None) -> Decimal | None:
    p = (mcfg.get("pricing") or {})
    if in_tok is None or out_tok is None or "input_per_mtok" not in p or "output_per_mtok" not in p:
        return None
    return (D(in_tok) * D(p["input_per_mtok"]) + D(out_tok) * D(p["output_per_mtok"])) / D(1_000_000)
