"""Dados iniciais idempotentes: provedor simulado e prompts de referência do benchmark."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lab.models import BenchmarkPrompt
from app.providers.adapters import ADAPTERS
from app.providers.models import Provider

STYLE = ("Coloring book page. Clean, bold, uniform black outlines on a pure white background. No shading, no gray tones, "
         "no filled black areas, no textures. Large open spaces suitable for coloring. Single centered composition with "
         "comfortable margins for printing. No text, no letters, no watermark, no signature, no border frame.")
NEGATIVE = ("shading, gradients, gray tones, grayscale, color, filled black areas, texture, hatching, text, letters, numbers, "
            "watermark, signature, border, frame, blurry, cropped, low contrast")

BENCHMARK = [
    ("Animais fofos — Bold & Easy",
     "A cute chubby baby panda sitting and hugging a big heart-shaped balloon. Bold & Easy style for toddlers: very thick "
     "outlines, only a few large simple shapes, minimal details."),
    ("Fantasia medieval",
     "A friendly young knight in simple armor holding a shield, standing in front of a small stone castle with two towers, "
     "with a gentle dragon flying above. Medieval fantasy scene with moderate detail."),
    ("Dinossauros infantis",
     "A cheerful baby triceratops and a small stegosaurus friend walking among big tropical leaves, with a little volcano "
     "and a smiling sun in the background. Cute, child-friendly cartoon style."),
    ("Jardins e flores",
     "A beautiful garden path bordered by large daisies, tulips and roses, with a butterfly, a ladybug and a watering can. "
     "Balanced detail with well-separated petals and leaves."),
    ("Arquitetura e vilarejos encantados",
     "An enchanted village street with cozy cottages with round doors and curved roofs, a tall clock tower, a stone bridge, "
     "hanging lanterns and flower boxes. Whimsical architecture, clear separated shapes."),
]


def seed(db: Session) -> None:
    if not db.scalar(select(Provider).where(Provider.service == "mock")):
        db.add(Provider(name="Simulado (sem custo real)", service="mock", models=[dict(m) for m in ADAPTERS["mock"].known_models],
                        active=True, status="ok", status_message="provedor simulado"))
    existing = {b.category for b in db.scalars(select(BenchmarkPrompt))}
    for i, (cat, subject) in enumerate(BENCHMARK, start=1):
        if cat not in existing:
            db.add(BenchmarkPrompt(category=cat, prompt=f"{subject} {STYLE}", negative_prompt=NEGATIVE, position=i))
    db.commit()
