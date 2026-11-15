"""Proteção administrativa mínima: token único (ADMIN_TOKEN) -> cookie de sessão assinado.

Tudo sob a API exige sessão, exceto healthchecks e login. Sem ADMIN_TOKEN válido a API falha fechada (503).
"""
import hashlib
import hmac
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings

COOKIE = "contentos_session"
TTL = 12 * 3600
PUBLIC_PREFIXES = ("/health", "/api/health", "/api/auth/login")
_failures: list[float] = []


def _sign(exp: int) -> str:
    return hmac.new(settings.admin_token.encode(), f"session:{exp}".encode(), hashlib.sha256).hexdigest()


def make_cookie() -> str:
    exp = int(time.time()) + TTL
    return f"{exp}.{_sign(exp)}"


def _valid_cookie(value: str | None) -> bool:
    try:
        exp_s, sig = (value or "").split(".", 1)
        return int(exp_s) > time.time() and hmac.compare_digest(sig, _sign(int(exp_s)))
    except ValueError:
        return False


def _valid_bearer(header: str | None) -> bool:
    return bool(header and header.startswith("Bearer ") and hmac.compare_digest(header[7:], settings.admin_token))


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)
        if len(settings.admin_token) < 12:
            return JSONResponse({"detail": "ADMIN_TOKEN não configurado no servidor"}, status_code=503)
        if _valid_cookie(request.cookies.get(COOKIE)) or _valid_bearer(request.headers.get("authorization")):
            return await call_next(request)
        return JSONResponse({"detail": "não autenticado"}, status_code=401)


router = APIRouter(prefix="/api/auth", tags=["auth"])


class Login(BaseModel):
    token: str


@router.post("/login")
def login(body: Login, response: Response):
    now = time.time()
    _failures[:] = [t for t in _failures if now - t < 60]
    if len(_failures) >= 10:
        raise HTTPException(429, "muitas tentativas; aguarde 1 minuto")
    if len(settings.admin_token) < 12:
        raise HTTPException(503, "ADMIN_TOKEN não configurado no servidor")
    if not hmac.compare_digest(body.token, settings.admin_token):
        _failures.append(now)
        time.sleep(1)
        raise HTTPException(401, "token inválido")
    response.set_cookie(COOKIE, make_cookie(), max_age=TTL, httponly=True, samesite="strict", path="/")
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me():
    return {"ok": True}  # chega aqui apenas autenticado (middleware)
