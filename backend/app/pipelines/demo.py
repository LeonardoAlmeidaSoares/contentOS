"""Pipeline técnico de demonstração: valida fila, worker, banco, MinIO, retry e custos sem APIs pagas."""
import json
import time

from app.pipelines.registry import OutFile, Pipeline, Step, StepContext, StepResult, register

DEFAULT_CONFIG = {
    "items": 5,             # quantidade de itens gerados
    "step_delay": 2.0,      # segundos simulados por etapa
    "cost_per_step": 0.0,   # custo simulado (USD) por etapa — para testar orçamento
    "fail_step": None,      # nome da etapa que deve falhar (teste de retry/retomada)
    "fail_attempts": 0,     # quantas tentativas totais dessa etapa falham antes de ter sucesso
}


def _common(ctx: StepContext, name: str) -> float:
    cfg = {**DEFAULT_CONFIG, **ctx.config}
    time.sleep(float(cfg["step_delay"]))
    if cfg["fail_step"] == name and ctx.attempt <= int(cfg["fail_attempts"]):
        raise RuntimeError(f"falha simulada em '{name}' (tentativa {ctx.attempt})")
    return float(cfg["cost_per_step"])


def prepare(ctx: StepContext) -> StepResult:
    cost = _common(ctx, "prepare")
    n = int({**DEFAULT_CONFIG, **ctx.config}["items"])
    items = [f"item-{i}" for i in range(1, n + 1)]
    return StepResult({"items": items}, cost, message=f"{n} itens preparados")


def process(ctx: StepContext) -> StepResult:
    cost = _common(ctx, "process")
    processed = [i.upper() for i in ctx.previous["prepare"]["items"]]
    return StepResult({"processed": processed}, cost, message=f"{len(processed)} itens processados")


def package(ctx: StepContext) -> StepResult:
    cost = _common(ctx, "package")
    body = json.dumps({"run_id": ctx.run_id, "pipeline": "demo", "items": ctx.previous["process"]["processed"]},
                      indent=2, ensure_ascii=False).encode()
    return StepResult({"filename": "demo-output.json", "bytes": len(body)}, cost,
                      [OutFile("demo-output.json", "application/json", body)],
                      f"arquivo gerado ({len(body)} bytes)")


register(Pipeline(
    name="demo", label="Demonstração técnica",
    description="3 etapas simuladas que geram um JSON. Sem custo real; parâmetros de falha/custo para testes.",
    default_config=DEFAULT_CONFIG,
    steps=[Step("prepare", prepare), Step("process", process), Step("package", package)],
))
