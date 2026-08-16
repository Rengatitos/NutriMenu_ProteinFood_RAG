import json
from pathlib import Path

from rag.filters import select_candidates

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "data" / "catalogo_rag.json").read_text(encoding="utf-8"))


def test_strict_160_protein_never_exceeds():
    products, meta = select_candidates(CATALOG, {
        "meal_kcal": 160, "kcal_mode": "strict", "wants_protein": True,
        "exclusions": [], "flavor": None, "consumption_type": None, "price_max": None,
    })
    assert products
    assert all(p["kcal_max_est"] <= 160 for p in products)
    assert products[0]["producto"] == "Simple 16 Oz"


def test_strict_250_sweet_snack():
    products, _ = select_candidates(CATALOG, {
        "meal_kcal": 250, "kcal_mode": "strict", "wants_protein": False,
        "exclusions": [], "flavor": "Dulce", "consumption_type": "Snack/Postre", "price_max": None,
    })
    assert products
    assert all(p["kcal_max_est"] <= 250 for p in products)
    assert all(p["preferencia_sabor"] == "Dulce" for p in products)


def test_strict_lunch_500_prioritizes_fitting_meal():
    products, _ = select_candidates(CATALOG, {
        "meal_kcal": 500, "kcal_mode": "strict", "wants_protein": True,
        "exclusions": [], "flavor": "Salado", "consumption_type": "Comida", "price_max": None,
    })
    assert products
    assert all(p["tipo_consumo"] == "Comida" for p in products)
    assert all(p["kcal_max_est"] <= 500 for p in products)


def test_gluten_request_only_declared_products():
    products, _ = select_candidates(CATALOG, {
        "meal_kcal": 500, "kcal_mode": "around", "wants_protein": False,
        "exclusions": ["gluten"], "flavor": None, "consumption_type": "Snack/Postre", "price_max": None,
    })
    assert all(p["sin_gluten_declarado"] for p in products)
