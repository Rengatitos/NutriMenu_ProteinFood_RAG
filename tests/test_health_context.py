from config import SYSTEM_RULES
from rag.engine import NutriMenuRAG


def test_health_calculation_is_not_treated_as_product_request():
    assert not NutriMenuRAG._wants_products_now("¿Cuál es mi IMC?")
    assert not NutriMenuRAG._wants_products_now("¿Cuántas calorías debo consumir al día?")


def test_health_context_contains_required_guardrails():
    assert "IMC = peso_kg / (talla_m ** 2)" in SYSTEM_RULES
    assert "Mifflin–St Jeor" in SYSTEM_RULES
    assert "El IMC por sí solo NO permite calcular" in SYSTEM_RULES
    assert "SOLO ADULTOS DE 20 AÑOS O MÁS" in SYSTEM_RULES
