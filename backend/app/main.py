from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core import auth
from app.core.config import settings
from app.core.db import SessionLocal
from app.health.router import router as health_router
from app.lab import models as _lab_models  # noqa: F401
from app.lab.router import router as lab_router
from app.lab.seed import seed
from app.providers import models as _prov_models  # noqa: F401
from app.publishing import models as _pub_models  # noqa: F401
from app.publishing.router import router as publishing_router
from app.providers.router import router as providers_router
from app.runs.router import router as runs_router
from app.voices import models as _voice_models  # noqa: F401
from app.voices.router import router as voices_router
from app.studio import assistant as studio_assistant
from app.studio.router import router as studio_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        seed(db)
        if settings.gemini_api_key:
            studio_assistant.ensure_provider(db)
    yield


app = FastAPI(title="ContentOS", version="0.5.0", lifespan=lifespan)
app.add_middleware(auth.AuthMiddleware)
app.include_router(health_router)
app.include_router(health_router, prefix="/api")  # acessível também via proxy do frontend
app.include_router(auth.router)
app.include_router(runs_router)
app.include_router(providers_router)
app.include_router(lab_router)
app.include_router(studio_router)
app.include_router(publishing_router)
app.include_router(voices_router)
