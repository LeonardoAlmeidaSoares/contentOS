from fastapi import FastAPI

from app.health.router import router as health_router
from app.runs.router import router as runs_router

app = FastAPI(title="ContentOS", version="0.1.0")
app.include_router(health_router)
app.include_router(health_router, prefix="/api")  # acessível também via proxy do frontend
app.include_router(runs_router)
