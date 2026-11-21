"""Cliente mínimo e oficial do YouTube Data API v3 + OAuth 2.0 (HTTP direto, sem SDK).

Segurança: nenhum token, código ou corpo de resposta é logado; mensagens de erro são montadas só com campos seguros
(`reason`/`message` do erro) e passam por `scrub`.
"""
import base64
import hashlib
import logging
import re
import time
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from app.core.config import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
# Escopos mínimos: enviar vídeos + ler o próprio canal (identificar qual canal está conectado).
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
CHUNK = 8 * 1024 * 1024  # múltiplo de 256 KiB, exigido pelo upload retomável
RETRY_SLEEP = 2.0  # testes zeram

for _n in ("httpx", "httpcore"):  # o httpx loga URLs (a sessão de upload é uma URL-capacidade): silenciar
    logging.getLogger(_n).setLevel(logging.WARNING)

_factory = lambda: httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0))  # noqa: E731


def set_client_factory(fn) -> None:
    global _factory
    _factory = fn


class YTError(Exception):
    """kind: auth (reconectar) | quota | network | api. `message` é seguro para a interface."""

    def __init__(self, message: str, kind: str = "api", status: int | None = None):
        super().__init__(message)
        self.message, self.kind, self.status = message, kind, status


def scrub(msg: str) -> str:
    for secret in (settings.youtube_client_secret,):
        if secret:
            msg = msg.replace(secret, "***")
    return msg


def _safe_error(resp: httpx.Response) -> YTError:
    reason, text = "", ""
    try:
        j = resp.json()
        err = j.get("error")
        if isinstance(err, dict):
            reason = ((err.get("errors") or [{}])[0] or {}).get("reason", "") or err.get("status", "")
            text = str(err.get("message", ""))[:200]
        elif isinstance(err, str):  # erros OAuth: {"error": "invalid_grant", "error_description": ...}
            reason, text = err, str(j.get("error_description", ""))[:200]
    except ValueError:
        pass
    s = resp.status_code
    if reason in ("invalid_grant", "invalid_token", "unauthorized_client") or s == 401:
        return YTError("Autorização do Google expirada ou revogada. Reconecte o canal em Configurações.", "auth", s)
    if reason in ("quotaExceeded", "uploadLimitExceeded", "rateLimitExceeded", "dailyLimitExceeded") or s == 429:
        return YTError("Limite de uso da API do YouTube atingido. Tente novamente mais tarde (a cota diária reinicia à meia-noite, horário do Pacífico).", "quota", s)
    if reason in ("youtubeSignupRequired", "channelNotFound"):
        return YTError("Esta conta Google não tem um canal do YouTube.", "api", s)
    return YTError(scrub(f"YouTube respondeu HTTP {s}" + (f" ({reason})" if reason else "") + (f": {text}" if text else "")),
                   "network" if s >= 500 else "api", s)


def _send(client, method, url, **kw) -> httpx.Response:
    try:
        return client.request(method, url, **kw)
    except httpx.HTTPError as exc:
        raise YTError(f"falha de rede ({exc.__class__.__name__})", "network") from None


# ---------- OAuth ----------
def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def auth_url(state: str, verifier: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": settings.youtube_client_id, "redirect_uri": settings.youtube_redirect_uri, "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": pkce_challenge(verifier), "code_challenge_method": "S256", "include_granted_scopes": "false"})


def parse_redirect(url: str) -> tuple[str | None, str | None, str | None]:
    """Aceita a URL pura ou o texto inteiro da página de erro do navegador (extrai a primeira URL de loopback)."""
    m = re.search(r"https?://[^\s\"“”'<>]+", url)
    q = parse_qs(urlparse((m.group(0) if m else url).strip()).query)
    return (q.get("code", [None])[0], q.get("state", [None])[0], q.get("error", [None])[0])


def _token_call(data: dict) -> dict:
    with _factory() as c:
        r = _send(c, "POST", TOKEN_URL, data={**data, "client_id": settings.youtube_client_id,
                                              "client_secret": settings.youtube_client_secret})
    if r.status_code >= 400:
        raise _safe_error(r)
    return r.json()


def exchange_code(code: str, verifier: str) -> dict:
    return _token_call({"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
                        "redirect_uri": settings.youtube_redirect_uri})


def refresh(refresh_token: str) -> dict:
    return _token_call({"grant_type": "refresh_token", "refresh_token": refresh_token})


def revoke(token: str) -> None:
    try:
        with _factory() as c:
            c.post(REVOKE_URL, data={"token": token})
    except httpx.HTTPError:
        pass  # melhor esforço: os tokens locais são apagados de qualquer forma


# ---------- API ----------
def my_channel(access: str) -> dict | None:
    with _factory() as c:
        r = _send(c, "GET", f"{API}/channels", params={"part": "snippet", "mine": "true"},
                  headers={"Authorization": f"Bearer {access}"})
    if r.status_code >= 400:
        raise _safe_error(r)
    items = r.json().get("items") or []
    return {"id": items[0]["id"], "title": items[0]["snippet"]["title"]} if items else None


def init_upload(access: str, meta: dict, size: int) -> str:
    body = {"snippet": {"title": meta["title"], "description": meta["description"], "tags": meta["tags"], "categoryId": "22"},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": bool(meta["made_for_kids"])}}
    with _factory() as c:
        r = _send(c, "POST", UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"}, json=body,
                  headers={"Authorization": f"Bearer {access}", "X-Upload-Content-Type": "video/mp4",
                           "X-Upload-Content-Length": str(size)})
    if r.status_code >= 400:
        raise _safe_error(r)
    loc = r.headers.get("location")
    if not loc:
        raise YTError("o YouTube não devolveu a sessão de upload", "api")
    return loc


def _next_offset(resp: httpx.Response) -> int:
    rng = resp.headers.get("range")  # "bytes=0-1234"
    return int(rng.split("-")[-1]) + 1 if rng else 0


def upload(session_url: str, data: bytes, start: int, on_progress) -> dict:
    """Envia em blocos; em falha de rede consulta a sessão e retoma do ponto confirmado (sem reenviar o que já chegou).
    Devolve o recurso `video` quando concluído. Levanta YTError(kind='network') se não conseguir confirmar o estado."""
    total, pos, fails = len(data), start, 0
    with _factory() as c:
        while True:
            end = min(pos + CHUNK, total)
            try:
                r = _send(c, "PUT", session_url, content=data[pos:end],
                          headers={"Content-Length": str(end - pos), "Content-Type": "video/mp4",
                                   "Content-Range": f"bytes {pos}-{end - 1}/{total}"})
                if r.status_code >= 500:
                    raise YTError("erro do servidor", "network", r.status_code)
            except YTError as exc:
                if exc.kind != "network" or fails >= 5:
                    raise
                fails += 1
                time.sleep(RETRY_SLEEP * fails)
                try:  # consulta o que o servidor já recebeu
                    q = _send(c, "PUT", session_url, content=b"", headers={"Content-Length": "0", "Content-Range": f"bytes */{total}"})
                except YTError:
                    continue
                if q.status_code in (200, 201):
                    return q.json()
                if q.status_code == 308:
                    pos = _next_offset(q)
                    on_progress(pos)
                    continue
                if q.status_code in (404, 410):
                    raise YTError("sessão de upload expirou antes da conclusão", "api", q.status_code)
                if q.status_code >= 400 and q.status_code < 500:
                    raise _safe_error(q)
                continue
            if r.status_code in (200, 201):
                return r.json()
            if r.status_code == 308:
                pos = _next_offset(r)
                on_progress(pos)
                fails = 0
                continue
            raise _safe_error(r)


def query_session(session_url: str, total: int) -> tuple[str, object]:
    """Pergunta ao YouTube o estado de um upload retomável: ("done", recurso) | ("offset", bytes_recebidos)."""
    with _factory() as c:
        q = _send(c, "PUT", session_url, content=b"", headers={"Content-Length": "0", "Content-Range": f"bytes */{total}"})
    if q.status_code in (200, 201):
        return "done", q.json()
    if q.status_code == 308:
        return "offset", _next_offset(q)
    if q.status_code in (404, 410):
        raise YTError("a sessão de upload expirou antes da conclusão; nenhum vídeo foi criado", "api", q.status_code)
    raise _safe_error(q)
