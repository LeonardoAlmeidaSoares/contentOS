import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.storage import get_storage
from app.lab.models import BenchmarkPrompt, Experiment, LabResult
from app.providers.adapters.base import ImageRequest, TextRequest, D
from app.providers.gateway import Unsupported, estimate_for
from app.providers.ledger import ledger_sum
from app.providers.models import AIUsage, Provider
from app.runs import service, tasks
from app.runs.models import Artifact, Run, now
from app.runs.service import month_start

router = APIRouter(prefix="/api/lab", tags=["lab"])
MAX_REF = 10 * 1024 * 1024


class Target(BaseModel):
    provider_id: str
    model: str


class Params(BaseModel):
    targets: list[Target] = Field(min_length=1, max_length=12)
    aspect_ratio: str = "1:1"
    resolution: str = "1K"
    quality: str = "medium"
    n: int = Field(1, ge=1, le=10)
    system: str | None = None
    max_tokens: int = Field(1024, ge=16, le=16000)
    references: list[str] = []
    allow_unknown_cost: bool = False


class ExperimentIn(Params):
    kind: str = Field(pattern="^(image|text)$")
    prompt: str = Field(min_length=1, max_length=32000)
    negative_prompt: str | None = None
    label: str | None = None


def _request(kind: str, prompt: str, negative: str | None, p: Params):
    if kind == "text":
        return TextRequest(prompt, p.system, p.max_tokens)
    return ImageRequest(prompt, negative, p.aspect_ratio, p.resolution, p.quality, p.n,
                        references=[("image/png", b"")] * len(p.references))  # só a contagem importa p/ estimativa


def plan(db: Session, kind: str, prompt: str, negative: str | None, p: Params) -> list[dict]:
    """Estimativa por alvo, antes de qualquer execução."""
    rows = []
    for t in p.targets:
        prov = db.get(Provider, t.provider_id)
        row = {"provider_id": t.provider_id, "provider_name": prov.name if prov else "?", "model": t.model,
               "cost": None, "basis": "", "error": None}
        if not prov or not prov.active:
            row["error"] = "provedor inexistente ou inativo"
        else:
            try:
                est, mcfg = estimate_for(prov, t.model, kind, _request(kind, prompt, negative, p))
                row.update(cost=float(est.cost) if est.cost is not None else None, basis=est.basis, error=est.error)
                if kind == "image" and p.references and not mcfg.get("supports", {}).get("reference_images"):
                    row["error"] = "modelo não suporta imagens de referência"
            except Unsupported as exc:
                row["error"] = str(exc)
        rows.append(row)
    return rows


def _budget(db: Session) -> dict:
    spent = ledger_sum(db, scope="lab", since=month_start(now()))
    return {"lab_month_spent": float(spent), "lab_month_limit": settings.lab_month_limit_usd}


def _summary(rows: list[dict]) -> dict:
    return {"total_known": sum(r["cost"] or 0 for r in rows), "has_unknown": any(r["cost"] is None and not r["error"] for r in rows),
            "has_error": any(r["error"] for r in rows)}


@router.post("/estimate")
def estimate(body: ExperimentIn, db: Session = Depends(get_db)):
    rows = plan(db, body.kind, body.prompt, body.negative_prompt, body)
    return {"targets": rows, **_summary(rows), **_budget(db)}


def _launch(db: Session, kind, prompt, negative, label, batch_id, p: Params) -> Experiment:
    exp = Experiment(kind=kind, label=label, batch_id=batch_id, prompt=prompt, negative_prompt=negative,
                     params=p.model_dump(mode="json", exclude={"targets", "confirm_total_usd"}))
    db.add(exp)
    runs = []
    for t in p.targets:
        res = LabResult(experiment=exp, provider_id=t.provider_id, model=t.model)
        db.add(res)
        db.flush()
        cfg = {"kind": kind, "provider_id": t.provider_id, "model": t.model, "prompt": prompt, "negative_prompt": negative,
               "system": p.system, "max_tokens": p.max_tokens, "aspect_ratio": p.aspect_ratio, "resolution": p.resolution,
               "quality": p.quality, "n": p.n, "references": p.references, "allow_unknown_cost": p.allow_unknown_cost,
               "result_id": res.id}
        run = service.create_lab_run(db, cfg)
        res.run_id = run.id
        runs.append(run.id)
    db.commit()
    for rid in runs:
        tasks.enqueue(rid)
    return exp


def _check_plan(rows: list[dict], allow_unknown: bool) -> None:
    errs = [f"{r['provider_name']}/{r['model']}: {r['error']}" for r in rows if r["error"]]
    if errs:
        raise HTTPException(422, "; ".join(errs))
    unknown = [f"{r['provider_name']}/{r['model']}" for r in rows if r["cost"] is None]
    if unknown and not allow_unknown:
        raise HTTPException(409, f"custo não determinável previamente para: {', '.join(unknown)}. "
                                 "Confirme explicitamente (allow_unknown_cost) para executar.")


@router.post("/experiments", status_code=201)
def create_experiment(body: ExperimentIn, db: Session = Depends(get_db)):
    rows = plan(db, body.kind, body.prompt, body.negative_prompt, body)
    _check_plan(rows, body.allow_unknown_cost)
    exp = _launch(db, body.kind, body.prompt, body.negative_prompt, body.label, None, body)
    return experiment_out(db, exp)


# ---------- leitura ----------
def result_out(db: Session, r: LabResult, prov_names: dict) -> dict:
    run = db.get(Run, r.run_id) if r.run_id else None
    u = db.scalar(select(AIUsage).where(AIUsage.idempotency_key == f"lab:{r.id}").order_by(AIUsage.created_at.desc()).limit(1))
    arts = db.scalars(select(Artifact).where(Artifact.run_id == r.run_id)).all() if r.run_id else []
    step_out = (run.steps[0].output or {}) if run and run.steps else {}
    text = ((u.result or {}).get("text") if u else None) or step_out.get("text")
    return {"id": r.id, "provider_id": r.provider_id, "provider_name": prov_names.get(r.provider_id, "?"), "model": r.model,
            "run_id": r.run_id, "status": run.status if run else "unknown",
            "error": (u.error if u and u.error else None) or (run.error if run else None),
            "text": text, "rating": r.rating, "notes": r.notes,
            "images": [{"artifact_id": a.id, "filename": a.filename, "width": (a.meta or {}).get("width"),
                        "height": (a.meta or {}).get("height"), "size": a.size} for a in arts],
            "duration_ms": u.duration_ms if u else None,
            "cost_estimated": float(u.cost_estimated) if u else None,
            "cost_effective": float(u.cost_effective) if u else None, "cost_source": u.cost_source if u else None,
            "cost_unknown": u.cost_unknown if u else False,
            "input_tokens": u.input_tokens if u else None, "output_tokens": u.output_tokens if u else None}


def experiment_out(db: Session, e: Experiment) -> dict:
    names = {p.id: p.name for p in db.scalars(select(Provider))}
    results = [result_out(db, r, names) for r in e.results]
    return {"id": e.id, "kind": e.kind, "label": e.label, "batch_id": e.batch_id, "prompt": e.prompt,
            "negative_prompt": e.negative_prompt, "params": e.params, "created_at": e.created_at, "results": results,
            "total_cost": sum(r["cost_effective"] or 0 for r in results)}


@router.get("/experiments")
def list_experiments(kind: str | None = None, batch_id: str | None = None, limit: int = 60, db: Session = Depends(get_db)):
    q = select(Experiment).order_by(Experiment.created_at.desc()).limit(min(limit, 200))
    if kind:
        q = q.where(Experiment.kind == kind)
    if batch_id:
        q = q.where(Experiment.batch_id == batch_id)
    out = []
    for e in db.scalars(q):
        full = experiment_out(db, e)
        full["results"] = [{k: r[k] for k in ("id", "provider_name", "model", "status", "rating", "cost_effective")} for r in full["results"]]
        out.append(full)
    return out


@router.get("/experiments/{eid}")
def get_experiment(eid: str, db: Session = Depends(get_db)):
    e = db.get(Experiment, eid)
    if not e:
        raise HTTPException(404, "experimento não encontrado")
    return experiment_out(db, e)


class Rating(BaseModel):
    rating: int | None = Field(None, ge=1, le=5)
    notes: str | None = None


@router.patch("/results/{rid}")
def rate(rid: str, body: Rating, db: Session = Depends(get_db)):
    r = db.get(LabResult, rid)
    if not r:
        raise HTTPException(404, "resultado não encontrado")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    db.commit()
    return result_out(db, r, {p.id: p.name for p in db.scalars(select(Provider))})


@router.get("/budget")
def budget(db: Session = Depends(get_db)):
    return _budget(db)


@router.post("/references", status_code=201)
async def upload_reference(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_REF:
        raise HTTPException(413, "imagem de referência acima de 10 MB")
    head = data[:12]
    if not (head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8") or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")):
        raise HTTPException(422, "apenas PNG, JPEG ou WEBP")
    ext = "png" if head.startswith(b"\x89PNG") else ("webp" if head[:4] == b"RIFF" else "jpg")
    key = f"lab/refs/{uuid.uuid4()}.{ext}"
    get_storage().put(key, data, f"image/{'jpeg' if ext == 'jpg' else ext}")
    return {"key": key, "size": len(data)}


# ---------- benchmark ----------
class BenchmarkIn(Params):
    confirm_total_usd: Decimal | None = None  # autorização explícita do gasto estimado total


def _bench_plan(db: Session, p: Params):
    prompts = db.scalars(select(BenchmarkPrompt).where(BenchmarkPrompt.active.is_(True)).order_by(BenchmarkPrompt.position)).all()
    per_prompt = [(bp, plan(db, "image", bp.prompt, bp.negative_prompt, p)) for bp in prompts]
    rows = [r for _, rs in per_prompt for r in rs]
    return prompts, per_prompt, rows


@router.get("/benchmark")
def benchmark_prompts(db: Session = Depends(get_db)):
    return [{"id": b.id, "category": b.category, "prompt": b.prompt, "negative_prompt": b.negative_prompt}
            for b in db.scalars(select(BenchmarkPrompt).where(BenchmarkPrompt.active.is_(True)).order_by(BenchmarkPrompt.position))]


@router.post("/benchmark/estimate")
def benchmark_estimate(body: BenchmarkIn, db: Session = Depends(get_db)):
    prompts, per_prompt, rows = _bench_plan(db, body)
    by_target: dict = {}
    for r in rows:
        k = (r["provider_name"], r["model"])
        t = by_target.setdefault(k, {"provider_name": k[0], "model": k[1], "cost": 0.0, "unknown": False, "error": None})
        t["cost"] += r["cost"] or 0
        t["unknown"] |= r["cost"] is None and not r["error"]
        t["error"] = t["error"] or r["error"]
    return {"prompts": len(prompts), "generations": len(rows), "targets": list(by_target.values()), **_summary(rows), **_budget(db)}


@router.post("/benchmark/run", status_code=201)
def benchmark_run(body: BenchmarkIn, db: Session = Depends(get_db)):
    """Executa o benchmark (5 categorias × modelos). Exige confirmação explícita do gasto estimado."""
    prompts, _, rows = _bench_plan(db, body)
    _check_plan(rows, body.allow_unknown_cost)
    total = D(sum(r["cost"] or 0 for r in rows))
    if body.confirm_total_usd is None or body.confirm_total_usd < total:
        raise HTTPException(409, f"confirme o gasto estimado total (US$ {total:.4f}) em confirm_total_usd para executar")
    batch = str(uuid.uuid4())
    exps = [_launch(db, "image", bp.prompt, bp.negative_prompt, bp.category, batch, body) for bp in prompts]
    return {"batch_id": batch, "experiments": [e.id for e in exps], "estimated_total": float(total)}
