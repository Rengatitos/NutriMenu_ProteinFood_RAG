import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
catalog = json.loads((ROOT / "data" / "catalogo_rag.json").read_text(encoding="utf-8"))
assert len(catalog) == 59
for p in catalog:
    assert p["imagen_png"].endswith(".png")
    assert (ROOT / "static" / "products" / p["imagen_png"]).exists(), p["imagen_png"]
print("OK: 59 productos y 59 imágenes PNG referenciadas.")
