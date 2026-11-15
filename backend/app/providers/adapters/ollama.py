"""Ollama (local) — somente texto. Docs: github.com/ollama/ollama docs/api.md."""
from decimal import Decimal

from .base import AIResult, Adapter, Conn, Estimate, TextRequest, request


class OllamaAdapter(Adapter):
    service = "ollama"
    label = "Ollama (local)"
    default_base_url = "http://host.docker.internal:11434"
    needs_key = False
    capabilities = ("text",)
    pricing_source = "execução local: sem custo de API"
    known_models: list[dict] = []  # descobertos via /api/tags no teste de conexão

    def test(self, conn):
        j = request("GET", f"{conn.base_url}/api/tags").json()
        names = [m.get("name") for m in j.get("models", [])]
        return f"{len(names)} modelos locais: {', '.join(n for n in names[:5] if n)}"

    def discover(self, conn: Conn) -> list[dict]:
        j = request("GET", f"{conn.base_url}/api/tags").json()
        return [{"id": m["name"], "capabilities": ["text"], "active": True, "pricing": {"local": True}}
                for m in j.get("models", []) if m.get("name")]

    def estimate(self, capability, mcfg, req):
        return Estimate(Decimal(0), "local: sem custo de API")

    def text(self, conn, model, req: TextRequest, mcfg):
        body = {"model": model, "prompt": req.prompt, "stream": False, "options": {"num_predict": req.max_tokens}}
        if req.system:
            body["system"] = req.system
        j = request("POST", f"{conn.base_url}/api/generate", json=body).json()
        return AIResult(model, text=j.get("response", ""), input_tokens=j.get("prompt_eval_count"),
                        output_tokens=j.get("eval_count"), cost_actual=Decimal(0), cost_source="computed",
                        usage_raw={k: j.get(k) for k in ("total_duration", "eval_duration") if k in j} or None)
