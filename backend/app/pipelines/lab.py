"""Pipeline interno do Laboratório: uma geração (texto ou imagem) por execução, via motor + gateway de IA."""
from app.pipelines.registry import Pipeline, Step, StepContext, StepResult, register
from app.providers.adapters.base import ImageRequest, TextRequest


def generate(ctx: StepContext) -> StepResult:
    c = ctx.config
    key = f"lab:{c['result_id']}"
    allow = bool(c.get("allow_unknown_cost"))
    if c["kind"] == "text":
        out = ctx.ai.text(c["provider_id"], c["model"],
                          TextRequest(c["prompt"], c.get("system") or None, int(c.get("max_tokens", 1024))), key, allow)
        ctx.log(f"texto gerado ({out.output_tokens or '?'} tokens de saída)")
        return StepResult({"text": out.text, "usage_id": out.usage_id, "cached": out.cached}, message="texto gerado")
    req = ImageRequest(c["prompt"], c.get("negative_prompt") or None, c.get("aspect_ratio", "1:1"),
                       c.get("resolution", "1K"), c.get("quality", "medium"), int(c.get("n", 1)))
    out = ctx.ai.image(c["provider_id"], c["model"], req, key, allow, reference_keys=c.get("references") or None)
    ctx.log(f"{len(out.files)} imagem(ns) gerada(s)")
    return StepResult({"usage_id": out.usage_id, "cached": out.cached, "images": len(out.files)}, files=out.files,
                      message=f"{len(out.files)} imagem(ns)")


register(Pipeline("lab", "Laboratório", "Geração avulsa (interno).", {}, [Step("generate", generate)], internal=True))
