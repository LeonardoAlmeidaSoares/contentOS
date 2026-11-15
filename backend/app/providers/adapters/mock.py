"""Provedor simulado: custo zero real. Usado em testes e para validar o Laboratório sem gastar."""
import hashlib
import struct
import zlib
from decimal import Decimal

from .base import AIResult, Adapter, Estimate, ImageOut, ImageRequest, ProviderError, TextRequest, D


def png_lineart(w: int, h: int, seed: int) -> bytes:
    """PNG branco com linhas pretas (moldura + círculo) — lembra uma página de colorir."""
    cx, cy, r = w // 2, h // 2, min(w, h) // 3 + seed % 20
    rows = []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            on_frame = min(x, y, w - 1 - x, h - 1 - y) < 6
            d = abs(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 - r)
            row.append(0 if on_frame or d < 3 else 255)
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows))

    def chunk(t: bytes, d: bytes) -> bytes:
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


class MockAdapter(Adapter):
    service = "mock"
    label = "Simulado (sem custo real)"
    needs_key = False
    capabilities = ("text", "image")
    pricing_source = "valores fictícios para testar orçamento/reservas"
    known_models = [
        {"id": "mock-text", "capabilities": ["text"], "active": True,
         "pricing": {"input_per_mtok": 1.0, "output_per_mtok": 2.0}},
        {"id": "mock-image-free", "capabilities": ["image"], "active": True,
         "supports": {"aspect_ratios": ["1:1", "3:4", "4:3"], "qualities": ["standard"], "resolutions": ["1K"],
                      "max_n": 4, "negative_prompt": True, "reference_images": True},
         "pricing": {"per_image": {"default": 0}}},
        {"id": "mock-image-paid", "capabilities": ["image"], "active": True,
         "supports": {"aspect_ratios": ["1:1", "3:4", "4:3"], "qualities": ["standard"], "resolutions": ["1K"],
                      "max_n": 4, "negative_prompt": True, "reference_images": False},
         "pricing": {"per_image": {"default": 0.25}}, "note": "custo FICTÍCIO (só para testar orçamento)"},
        {"id": "mock-image-nopricing", "capabilities": ["image"], "active": True,
         "supports": {"aspect_ratios": ["1:1"], "qualities": ["standard"], "resolutions": ["1K"], "max_n": 1,
                      "negative_prompt": False, "reference_images": False}, "pricing": {}},
    ]

    def test(self, conn):
        return "provedor simulado disponível"

    def estimate(self, capability, mcfg, req):
        if capability == "text":
            p = mcfg.get("pricing", {})
            return Estimate(D(p.get("output_per_mtok", 0)) * req.max_tokens / D(1_000_000), "simulado")
        sup = mcfg.get("supports", {})
        if req.aspect_ratio not in sup.get("aspect_ratios", []):
            return Estimate(None, "", f"proporção não suportada: {req.aspect_ratio}")
        if req.n > sup.get("max_n", 1):
            return Estimate(None, "", f"n máximo é {sup.get('max_n', 1)}")
        per = (mcfg.get("pricing", {}).get("per_image") or {}).get("default")
        if per is None:
            return Estimate(None, "preço por imagem não configurado")
        return Estimate(D(per) * req.n, f"{req.n} × US$ {per} (simulado)")

    def _check(self, prompt: str):
        if "[fail]" in prompt:
            raise ProviderError("falha simulada", status=500)
        if "[timeout]" in prompt:
            raise ProviderError("timeout simulado após envio", uncertain=True)

    def text(self, conn, model, req: TextRequest, mcfg):
        self._check(req.prompt)
        out = f"[simulado] eco: {req.prompt[:200]}"
        return AIResult(model, text=out, input_tokens=len(req.prompt) // 4 + 1, output_tokens=len(out) // 4 + 1,
                        request_id=f"mock-{hashlib.md5(req.prompt.encode()).hexdigest()[:8]}", cost_source="estimate")

    def image(self, conn, model, req: ImageRequest, mcfg):
        self._check(req.prompt)
        w, h = {"1:1": (256, 256), "3:4": (192, 256), "4:3": (256, 192)}.get(req.aspect_ratio, (256, 256))
        seed = int(hashlib.md5((req.prompt + model).encode()).hexdigest()[:4], 16)
        return AIResult(model, images=[ImageOut(png_lineart(w, h, seed + i), "image/png") for i in range(req.n)],
                        request_id=f"mock-{seed:x}")
