"""OpenAI — docs: developers.openai.com/api (Responses, Images)."""
from decimal import Decimal

from .base import (AIResult, Adapter, Conn, Estimate, ImageOut, ImageRequest, ProviderError, TextRequest, D, approx_tokens,
                   b64, request, token_text_actual, token_text_estimate)

# aspecto -> tamanhos documentados (1024x1024, 1024x1536, 1536x1024)
def _size(aspect: str) -> str:
    w, h = (int(x) for x in aspect.split(":"))
    return "1024x1024" if w == h else ("1536x1024" if w > h else "1024x1536")


def _headers(conn: Conn) -> dict:
    return {"Authorization": f"Bearer {conn.api_key}"}


class OpenAIAdapter(Adapter):
    service = "openai"
    label = "OpenAI"
    default_base_url = "https://api.openai.com/v1"
    capabilities = ("text", "image")
    pricing_source = "developers.openai.com/api/docs/pricing e /guides/image-generation (conferido em 2026-11-15)"
    known_models = [
        {"id": "gpt-5-mini", "capabilities": ["text"], "active": True,
         "pricing": {"input_per_mtok": 0.25, "output_per_mtok": 2.00}},
        {"id": "gpt-5-nano", "capabilities": ["text"], "active": True,
         "pricing": {"input_per_mtok": 0.05, "output_per_mtok": 0.40}},
        {"id": "gpt-4.1-mini", "capabilities": ["text"], "active": True,
         "pricing": {"input_per_mtok": 0.40, "output_per_mtok": 1.60}},
        {"id": "gpt-image-2", "capabilities": ["image"], "active": True,
         "supports": {"aspect_ratios": ["1:1", "2:3", "3:2"], "qualities": ["low", "medium", "high"],
                      "resolutions": ["1K"], "max_n": 10, "negative_prompt": False, "reference_images": True},
         "pricing": {"tokens": {"text_in": 5.0, "image_in": 8.0, "image_out": 30.0},
                     "per_image": {"low:1024x1024": 0.006, "low:1024x1536": 0.005, "low:1536x1024": 0.005,
                                   "medium:1024x1024": 0.053, "medium:1024x1536": 0.041, "medium:1536x1024": 0.041,
                                   "high:1024x1024": 0.211, "high:1024x1536": 0.165, "high:1536x1024": 0.165}}},
        {"id": "gpt-image-1.5", "capabilities": ["image"], "active": True,
         "supports": {"aspect_ratios": ["1:1", "2:3", "3:2"], "qualities": ["low", "medium", "high"],
                      "resolutions": ["1K"], "max_n": 10, "negative_prompt": False, "reference_images": True},
         "pricing": {"tokens": {"text_in": 5.0, "image_in": 8.0, "image_out": 32.0},
                     "per_image": {"low:1024x1024": 0.009, "low:1024x1536": 0.013, "low:1536x1024": 0.013,
                                   "medium:1024x1024": 0.034, "medium:1024x1536": 0.05, "medium:1536x1024": 0.05,
                                   "high:1024x1024": 0.133, "high:1024x1536": 0.2, "high:1536x1024": 0.2}}},
        {"id": "gpt-image-1-mini", "capabilities": ["image"], "active": True,
         "supports": {"aspect_ratios": ["1:1", "2:3", "3:2"], "qualities": ["low", "medium", "high"],
                      "resolutions": ["1K"], "max_n": 10, "negative_prompt": False, "reference_images": True},
         "pricing": {"tokens": {"text_in": 2.0, "image_in": 2.5, "image_out": 8.0},
                     "per_image": {"low:1024x1024": 0.005, "low:1024x1536": 0.006, "low:1536x1024": 0.006,
                                   "medium:1024x1024": 0.011, "medium:1024x1536": 0.015, "medium:1536x1024": 0.015,
                                   "high:1024x1024": 0.036, "high:1024x1536": 0.052, "high:1536x1024": 0.052}}},
    ]

    def test(self, conn: Conn) -> str:
        r = request("GET", f"{conn.base_url}/models", headers=_headers(conn))
        return f"{len(r.json().get('data', []))} modelos visíveis"

    def estimate(self, capability, mcfg, req):
        if capability == "text":
            return token_text_estimate(mcfg, req)
        sup, p = mcfg.get("supports", {}), mcfg.get("pricing", {})
        if req.aspect_ratio not in sup.get("aspect_ratios", []) or req.quality not in sup.get("qualities", []):
            return Estimate(None, "", f"combinação não suportada ({req.aspect_ratio}, {req.quality})")
        if req.n > sup.get("max_n", 1):
            return Estimate(None, "", f"n máximo é {sup.get('max_n', 1)}")
        key = f"{req.quality}:{_size(req.aspect_ratio)}"
        per = p.get("per_image", {}).get(key)
        if per is None:
            return Estimate(None, f"preço por imagem '{key}' não configurado")
        if req.references:
            return Estimate(None, "custo das imagens de referência (tokens de entrada) não é estimável previamente")
        tin = approx_tokens(req.prompt)
        text_cost = D(tin) * D(p.get("tokens", {}).get("text_in", 0)) / D(1_000_000)
        return Estimate((D(per) + text_cost) * req.n, f"{req.n} × US$ {per} ({key}) + ≤{tin} tokens de prompt")

    def text(self, conn, model, req: TextRequest, mcfg):
        body = {"model": model, "input": req.prompt, "max_output_tokens": max(16, req.max_tokens), "store": False}
        if req.system:
            body["instructions"] = req.system
        r = request("POST", f"{conn.base_url}/responses", headers=_headers(conn), json=body)
        j = r.json()
        parts = [c.get("text", "") for item in j.get("output", []) if item.get("type") == "message"
                 for c in item.get("content", []) if c.get("type") == "output_text"]
        usage = j.get("usage") or {}
        cost = token_text_actual(mcfg, usage.get("input_tokens"), usage.get("output_tokens"))
        return AIResult(model, text="".join(parts), input_tokens=usage.get("input_tokens"),
                        output_tokens=usage.get("output_tokens"), cost_actual=cost,
                        cost_source="computed" if cost is not None else "estimate", request_id=j.get("id"),
                        usage_raw=usage or None)

    def image(self, conn, model, req: ImageRequest, mcfg):
        fields = {"model": model, "prompt": req.prompt, "size": _size(req.aspect_ratio), "quality": req.quality,
                  "n": req.n, "output_format": "png"}
        if req.references:  # /v1/images/edits aceita várias imagens como image[] (multipart)
            files = [("image[]", (f"ref{i}", data, mime)) for i, (mime, data) in enumerate(req.references)]
            r = request("POST", f"{conn.base_url}/images/edits", headers=_headers(conn),
                        data={k: str(v) for k, v in fields.items()}, files=files)
        else:
            r = request("POST", f"{conn.base_url}/images/generations", headers=_headers(conn), json=fields)
        j = r.json()
        imgs = [ImageOut(b64(d["b64_json"]), "image/png") for d in j.get("data", []) if d.get("b64_json")]
        if not imgs:
            raise ProviderError("resposta sem imagens")
        usage = j.get("usage") or {}
        cost = None
        tok = (mcfg.get("pricing") or {}).get("tokens") or {}
        det = usage.get("input_tokens_details") or {}
        if tok and usage.get("output_tokens") is not None and det:
            cost = (D(det.get("text_tokens", 0)) * D(tok["text_in"]) + D(det.get("image_tokens", 0)) * D(tok["image_in"])
                    + D(usage["output_tokens"]) * D(tok["image_out"])) / D(1_000_000)
        return AIResult(model, images=imgs, input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                        cost_actual=cost, cost_source="computed" if cost is not None else "estimate",
                        usage_raw=usage or None)
