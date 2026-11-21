"""Fontes de imagem gratuitas e licenciadas (sem IA, sem custo): Pexels (opcional, chave grátis) e Wikimedia Commons.

Só são aceitas imagens com licença livre (domínio público, CC0, CC BY, CC BY-SA) ou a licença Pexels; a atribuição fica
registrada para os créditos do vídeo. Nenhum cabeçalho com credenciais é logado.
"""
import re
from dataclasses import dataclass

import httpx

from app.core.config import settings

_client_factory = lambda: httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)  # noqa: E731


def set_client_factory(fn) -> None:  # testes
    global _client_factory
    _client_factory = fn


@dataclass
class Image:
    data: bytes
    source: str
    url: str
    title: str
    author: str
    license: str


OK_LICENSE = re.compile(r"^(public domain|pd\b|cc0|cc[- ]by(-sa)?\b|attribution)", re.I)
BAD_LICENSE = re.compile(r"\b(nc|nd|fair use|non-?commercial)\b", re.I)


def _strip(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()[:160]


def _get(c: httpx.Client, url: str, **kw):
    r = c.get(url, headers={"User-Agent": settings.media_user_agent, **kw.pop("headers", {})}, **kw)
    r.raise_for_status()
    return r


def search_pexels(query: str, used: set[str]) -> Image | None:
    if not settings.pexels_api_key:
        return None
    with _client_factory() as c:
        r = _get(c, "https://api.pexels.com/v1/search", params={"query": query, "orientation": "landscape", "per_page": 15},
                 headers={"Authorization": settings.pexels_api_key})
        for p in r.json().get("photos", []):
            url = (p.get("src") or {}).get("large2x") or (p.get("src") or {}).get("large")
            if not url or url in used:
                continue
            data = _get(c, url).content
            return Image(data, "pexels", p.get("url", url), p.get("alt") or query, p.get("photographer", ""), "Pexels License")
    return None


def search_wikimedia(query: str, used: set[str]) -> Image | None:
    with _client_factory() as c:
        r = _get(c, "https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 20,
            "gsrsearch": f"{query} filetype:bitmap", "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": 1920})
        pages = sorted((r.json().get("query", {}).get("pages", {})).values(), key=lambda p: p.get("index", 0))
        for p in pages:
            info = (p.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            lic = _strip((meta.get("LicenseShortName") or {}).get("value", ""))
            if info.get("mime") not in ("image/jpeg", "image/png") or not lic:
                continue
            if BAD_LICENSE.search(lic) or not OK_LICENSE.search(lic):
                continue
            if (info.get("width") or 0) < 1000 or (info.get("height") or 0) < 600:
                continue
            url = info.get("thumburl") or info.get("url")
            if not url or url in used:
                continue
            data = _get(c, url).content
            return Image(data, "wikimedia", info.get("descriptionurl", url), _strip(p.get("title", "")).removeprefix("File:"),
                         _strip((meta.get("Artist") or {}).get("value", "")), lic)
    return None


def find_image(queries: list[str], used: set[str], sources: str = "auto") -> tuple[Image | None, list[str]]:
    """Tenta cada consulta em cada fonte; devolve (imagem|None, avisos)."""
    warns: list[str] = []
    order = [("pexels", search_pexels), ("wikimedia", search_wikimedia)]
    if sources in ("pexels", "wikimedia"):
        order = [o for o in order if o[0] == sources]
    for q in queries:
        for name, fn in order:
            try:
                img = fn(q, used)
            except httpx.HTTPError as exc:
                warns.append(f"{name}: {exc.__class__.__name__}")
                continue
            if img:
                used.add(img.url)
                return img, warns
    return None, warns
