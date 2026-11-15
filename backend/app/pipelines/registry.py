"""Registro de pipelines reutilizáveis. Um pipeline = lista ordenada de etapas.

Uma etapa recebe um `StepContext` e devolve um `StepResult`; ela não toca no banco nem no
storage: o executor persiste saída, custo e arquivos (assim retries/retomadas não duplicam efeitos).
"""
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class OutFile:
    filename: str
    content_type: str
    data: bytes


@dataclass
class StepResult:
    output: dict
    cost: float = 0.0
    files: list[OutFile] = field(default_factory=list)
    message: str = ""


@dataclass
class StepContext:
    run_id: str
    config: dict
    previous: dict[str, dict]  # saídas das etapas já concluídas, por nome
    attempt: int  # tentativas totais desta etapa (1 = primeira)


@dataclass
class Step:
    name: str
    fn: Callable[[StepContext], StepResult]


@dataclass
class Pipeline:
    name: str
    label: str
    description: str
    default_config: dict
    steps: list[Step]


PIPELINES: dict[str, Pipeline] = {}


def register(p: Pipeline) -> Pipeline:
    PIPELINES[p.name] = p
    return p


def load_all() -> None:
    from app.pipelines import demo  # noqa: F401  (registra ao importar)
