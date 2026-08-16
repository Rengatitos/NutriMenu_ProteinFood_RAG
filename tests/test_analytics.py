import rag.analytics as analytics
import rag.memory as memory


def test_conversation_feedback_and_dashboard_use_real_data(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "cx.db")
    memory.init_db()
    room = memory.create_room()
    memory.save_message(room["id"], "user", "Necesito una recomendación")
    memory.save_message(room["id"], "assistant", "Indica tus kcal disponibles.")
    analytics.save_conversation_feedback(room["id"], 5, 10, "Muy útil", True)
    data = analytics.dashboard_metrics(30)
    assert data["kpis"]["conversations"] == 1
    assert data["kpis"]["messages"] == 2
    assert data["kpis"]["satisfaction"] == 5
    assert data["kpis"]["nps"] is None  # requiere al menos cinco respuestas
    assert data["feedback"][0]["comment"] == "Muy útil"


def test_greetings_are_natural_instead_of_forbidden():
    from config import SYSTEM_RULES
    assert "Saluda solo cuando resulte natural" in SYSTEM_RULES
    assert "No repitas saludos" in SYSTEM_RULES
    assert "marcadores sin completar" in SYSTEM_RULES


def test_only_repeated_turn_opening_greeting_is_removed():
    from rag.engine import NutriMenuRAG
    response = NutriMenuRAG._strip_repeated_greeting(
        "¡Hola! Estas son las opciones con menos calorías."
    )
    assert response == "Estas son las opciones con menos calorías."
    assert NutriMenuRAG._strip_repeated_greeting("Estas son tus opciones.") == "Estas son tus opciones."


def test_lowest_calorie_answer_compares_real_ranges():
    from rag.engine import NutriMenuRAG
    products = [
        {"producto": "A", "kcal_min_est": 110, "kcal_max_est": 170, "kcal_ref_est": 140},
        {"producto": "B", "kcal_min_est": 110, "kcal_max_est": 160, "kcal_ref_est": 140},
    ]
    answer = NutriMenuRAG._lowest_calorie_answer(products)
    assert "A (110–170 kcal" in answer
    assert "B queda en primer lugar con hasta 160 kcal" in answer
