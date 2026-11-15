from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core import auth
from app.core.db import SessionLocal
from app.health.router import router as health_router
from app.lab import models as _lab_models  # noqa: F401
from app.lab.router import router as lab_router
from app.lab.seed import seed
from app.providers import models as _prov_models  # noqa: F401
from app.providers.router import router as providers_router
from app.runs.router import router as runs_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="ContentOS", version="0.3.0", lifespan=lifespan)
app.add_middleware(auth.AuthMiddleware)
app.include_router(health_router)
app.include_router(health_router, prefix="/api")  # acessível também via proxy do frontend
app.include_router(auth.router)
app.include_router(runs_router)
app.include_router(providers_router)
app.include_router(lab_router)
