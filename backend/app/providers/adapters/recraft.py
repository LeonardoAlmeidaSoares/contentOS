"""Recraft — docs: recraft.ai/docs/api-reference (endpoints, pricing, appendix)."""
from .base import AIResult, Adapter, Conn, Estimate, ImageOut, ImageRequest, ProviderError, D, b64, request

RATIOS = ["1:1", "2:1", "1:2", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5", "6:10", "14:10", "10:14", "16:9", "9:16"]


def _headers(conn: Conn) -> dict:
    return {"Authorization": f"Bearer {conn.api_key}"}


def _sup(neg: bool) -> dict:
    return {"aspect_ratios": RATIOS, "qualities": ["standard"], "resolutions": ["1K"], "max_n": 6,
            "negative_prompt": neg, "reference_images": False}


class RecraftAdapter(Adapter):
    service = "recraft"
    label = "Recraft"
    default_base_url = "https://external.api.recraft.ai/v1"
    capabilities = ("image",)
    pricing_source = "recraft.ai/docs/api-reference/pricing (conferido em 2026-11-15); US$1 = 1000 unidades"
    known_models = [
        {"id": "recraftv4_1", "capabilities": ["image"], "active": True, "supports": _sup(False),
         "pricing": {"per_image": {"default": 0.035}}, "note": "V4.1 raster (modelo padrão da API)"},
        {"id": "recraftv4_1_flash_v2", "capabilities": ["image"], "active": True, "supports": _sup(False),
         "pricing": {"per_image": {"default": 0.007}}, "note": "V4.1 Flash V2 raster; não aceita style"},
        {"id": "recraftv3", "capabilities": ["image"], "active": True, "supports": _sup(True),
         "pricing": {"per_image": {"default": 0.04}}, "note": "V3 raster — confirme o id na sua conta"},
        {"id": "recraftv3_vector", "capabilities": ["image"], "active": True, "supports": _sup(True),
         "pricing": {"per_image": {"default": 0.08}}, "note": "V3 vetorial (SVG)"},
    ]

    def test(self, conn):
        j = request("GET", f"{conn.base_url}/users/me", headers=_headers(conn)).json()
        return f"credenciais válidas; saldo: {j.get('credits', '?')} unidades"

    def estimate(self, capability, mcfg, req: ImageRequest):
        sup = mcfg.get("supports", {})
        if req.aspect_ratio not in sup.get("aspect_ratios", []):
            return Estimate(None, "", f"proporção não suportada: {req.aspect_ratio}")
        if req.n > sup.get("max_n", 1):
            return Estimate(None, "", f"n máximo é {sup.get('max_n', 1)}")
        if req.references:
            return Estimate(None, "", "imagens de referência não suportadas nesta integração")
        per = (mcfg.get("pricing", {}).get("per_image") or {}).get("default")
        if per is None:
            return Estimate(None, "preço por imagem não configurado")
        return Estimate(D(per) * req.n, f"{req.n} × US$ {per}")

    def image(self, conn, model, req: ImageRequest, mcfg):
        body = {"prompt": req.prompt, "model": model, "size": req.aspect_ratio, "n": req.n,
                "response_format": "b64_json", "image_format": "png"}
        if req.negative_prompt:
            body["negative_prompt"] = req.negative_prompt
        j = request("POST", f"{conn.base_url}/images/generations", headers=_headers(conn), json=body).json()
        mime = "image/svg+xml" if model.endswith("_vector") else "image/png"
        imgs = [ImageOut(b64(d["b64_json"]), mime) for d in j.get("data", []) if d.get("b64_json")]
        if not imgs:
            raise ProviderError("resposta sem imagens")
        credits = j.get("credits")  # 1 unidade = US$ 0,001 (docs)
        actual = D(credits) / D(1000) if credits is not None else None
        return AIResult(model, images=imgs, cost_actual=actual, cost_source="provider" if actual is not None else "estimate",
                        request_id=j.get("id"), usage_raw={"credits": credits} if credits is not None else None)
