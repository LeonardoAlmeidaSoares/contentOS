"""Google Gemini — docs: aistudio.google.com/docs (Interactions API, image-generation, pricing)."""
import base64

from .base import (AIResult, Adapter, Conn, Estimate, ImageOut, ImageRequest, ProviderError, TextRequest, D, b64, request,
                   token_text_actual, token_text_estimate)

API_REVISION = "2026-05-20"
RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9"]


def _headers(conn: Conn) -> dict:
    if conn.config.get("api") == "generate_content":  # API estável v1beta (generateContent)
        return {"x-goog-api-key": conn.api_key or ""}
    return {"x-goog-api-key": conn.api_key or "", "Api-Revision": API_REVISION}


def free_text_models() -> list[dict]:
    """Modelos com camada gratuita (custo 0 enquanto a chave não tiver faturamento ativo)."""
    return [{"id": m, "capabilities": ["text"], "active": True, "note": "camada gratuita (US$ 0 sem faturamento)",
             "pricing": {"input_per_mtok": 0, "output_per_mtok": 0}} for m in ("gemini-2.5-flash", "gemini-2.5-flash-lite")]


def _img(sizes: dict, refs: int, extra=None) -> dict:
    return {"supports": {"aspect_ratios": RATIOS, "qualities": ["standard"], "resolutions": list(sizes), "max_n": 1,
                         "negative_prompt": False, "reference_images": True, "max_references": refs},
            "pricing": {"per_image": sizes, **(extra or {})}}


class GeminiAdapter(Adapter):
    service = "gemini"
    label = "Google Gemini"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"
    capabilities = ("text", "image")
    pricing_source = "aistudio.google.com/docs/pricing (conferido em 2026-11-15, camada paga padrão)"
    known_models = [
        {"id": "gemini-3.1-flash-lite", "capabilities": ["text"], "active": True,
         "pricing": {"input_per_mtok": 0.25, "output_per_mtok": 1.50}},
        {"id": "gemini-2.5-flash-lite", "capabilities": ["text"], "active": True,
         "pricing": {"input_per_mtok": 0.10, "output_per_mtok": 0.40}},
        {"id": "gemini-3-flash-preview", "capabilities": ["text"], "active": True,
         "pricing": {"input_per_mtok": 0.50, "output_per_mtok": 3.00}},
        {"id": "gemini-nano-banana-2.1", "capabilities": ["image"], "active": True,
         **_img({"1K": 0.0336, "2K": 0.0504, "4K": 0.113}, 10)},
        {"id": "gemini-3.1-flash-lite-image", "capabilities": ["image"], "active": True,
         **_img({"1K": 0.0336}, 10)},
        {"id": "gemini-3.1-flash-image", "capabilities": ["image"], "active": True,
         **_img({"0.5K": 0.045, "1K": 0.067, "2K": 0.101, "4K": 0.151}, 10)},
        {"id": "gemini-3-pro-image", "capabilities": ["image"], "active": True,
         **_img({"1K": 0.134, "2K": 0.134, "4K": 0.24}, 6, {"ref_image": 0.0011})},
    ]

    def test(self, conn):
        # models.list: endpoint estável da Gemini API (não reconfirmado na doc atual — o resultado indica o erro real)
        j = request("GET", f"{conn.base_url}/models", headers=_headers(conn)).json()
        return f"{len(j.get('models', []))} modelos visíveis"

    def estimate(self, capability, mcfg, req):
        if capability == "text":
            return token_text_estimate(mcfg, req)
        sup, p = mcfg.get("supports", {}), mcfg.get("pricing", {})
        if req.aspect_ratio not in sup.get("aspect_ratios", []) or req.resolution not in sup.get("resolutions", []):
            return Estimate(None, "", f"combinação não suportada ({req.aspect_ratio}, {req.resolution})")
        if req.n > 1:
            return Estimate(None, "", "este modelo gera 1 imagem por requisição")
        if len(req.references) > sup.get("max_references", 0):
            return Estimate(None, "", "excede o máximo de imagens de referência")
        per = p.get("per_image", {}).get(req.resolution)
        if per is None:
            return Estimate(None, f"preço para {req.resolution} não configurado")
        ref = p.get("ref_image")
        if req.references and ref is None:
            return Estimate(None, "custo das imagens de referência (tokens de entrada) não é estimável previamente")
        total = D(per) + (D(ref) * len(req.references) if req.references else 0)
        return Estimate(total, f"US$ {per} ({req.resolution})" + (f" + {len(req.references)} ref. × {ref}" if req.references else ""))

    @staticmethod
    def _blocks(j: dict, kind: str) -> list[dict]:
        return [c for s in j.get("steps", []) if s.get("type") == "model_output"
                for c in s.get("content", []) if c.get("type") == kind]

    def _text_generate_content(self, conn, model, req: TextRequest, mcfg):
        gen = {"maxOutputTokens": req.max_tokens}
        if model.startswith("gemini-2.5") and "pro" not in model:
            gen["thinkingConfig"] = {"thinkingBudget": 0}  # evita gastar o teto de saída (e tokens) com raciocínio interno
        if req.json_mode:
            gen["responseMimeType"] = "application/json"
        body = {"contents": [{"role": "user", "parts": [{"text": req.prompt}]}], "generationConfig": gen}
        if req.system:
            body["systemInstruction"] = {"parts": [{"text": req.system}]}
        j = request("POST", f"{conn.base_url}/models/{model}:generateContent", headers=_headers(conn), json=body).json()
        cands = j.get("candidates") or []
        if not cands:
            reason = (j.get("promptFeedback") or {}).get("blockReason", "sem candidatos")
            raise ProviderError(f"resposta bloqueada ou vazia ({reason})")
        c = cands[0]
        text = "".join(p.get("text", "") for p in (c.get("content") or {}).get("parts", []))
        if not text:
            raise ProviderError(f"resposta vazia (finishReason={c.get('finishReason')})")
        if c.get("finishReason") == "MAX_TOKENS":
            raise ProviderError("resposta truncada (limite de tokens); reduza o tamanho pedido")
        u = j.get("usageMetadata") or {}
        in_t, out_t = u.get("promptTokenCount"), (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)
        cost = token_text_actual(mcfg, in_t, out_t)
        return AIResult(model, text=text, input_tokens=in_t, output_tokens=out_t, cost_actual=cost,
                        cost_source="computed", request_id=j.get("responseId"), usage_raw=u or None)

    def text(self, conn, model, req: TextRequest, mcfg):
        if conn.config.get("api") == "generate_content":
            return self._text_generate_content(conn, model, req, mcfg)
        body = {"model": model, "input": req.prompt, "store": False,
                "generation_config": {"max_output_tokens": req.max_tokens}}  # temperature é ignorado nos modelos novos
        if req.system:
            body["system_instruction"] = req.system
        j = request("POST", f"{conn.base_url}/interactions", headers=_headers(conn), json=body).json()
        text = "".join(c.get("text", "") for c in self._blocks(j, "text")) or j.get("output_text") or ""
        usage = j.get("usage") or {}
        return AIResult(model, text=text, request_id=j.get("id"), usage_raw=usage or None)  # campos de uso não documentados: custo = estimativa

    def image(self, conn, model, req: ImageRequest, mcfg):
        content = [{"type": "text", "text": req.prompt}] + [
            {"type": "image", "mime_type": m, "data": base64.b64encode(d).decode()} for m, d in req.references]
        body = {"model": model, "input": content if req.references else req.prompt, "store": False,
                "response_format": {"type": "image", "mime_type": conn.config.get("mime_type", "image/jpeg"),
                                    "aspect_ratio": req.aspect_ratio, "image_size": req.resolution}}
        j = request("POST", f"{conn.base_url}/interactions", headers=_headers(conn), json=body).json()
        blocks = self._blocks(j, "image")
        imgs = [ImageOut(b64(c["data"]), c.get("mime_type", "image/jpeg")) for c in blocks if c.get("data")]
        if not imgs and (j.get("output_image") or {}).get("data"):
            imgs = [ImageOut(b64(j["output_image"]["data"]), "image/jpeg")]
        if not imgs:
            raise ProviderError("resposta sem imagens")
        return AIResult(model, images=imgs, request_id=j.get("id"), usage_raw=j.get("usage") or None)
