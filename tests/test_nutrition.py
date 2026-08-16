import pytest

from rag.filters import extract_state_updates
from rag.nutrition import calculate_daily_calories


def test_daily_calories_mifflin_male_moderate():
    result = calculate_daily_calories(
        weight_kg=70, height_cm=175, age=30, sex="masculino", activity_level="moderado"
    )
    assert result["resting_kcal"] == 1649
    assert result["maintenance_kcal"] == 2560


def test_daily_calories_defaults_to_sedentary_reference():
    result = calculate_daily_calories(weight_kg=60, height_cm=165, age=25, sex="femenino")
    assert result["activity_factor"] == 1.2
    assert result["activity_assumed"] is True


def test_rejects_people_under_20():
    with pytest.raises(ValueError, match="adultos"):
        calculate_daily_calories(weight_kg=60, height_cm=165, age=19, sex="femenino")


def test_extracts_all_calculation_inputs():
    updates = extract_state_updates(
        "Cuántas calorías necesito: tengo 30 años, peso 70 kg, mido 1.75 m, soy hombre y actividad moderada", {}
    )
    assert updates["weight_kg"] == 70
    assert updates["height_cm"] == 175
    assert updates["age"] == 30
    assert updates["formula_sex"] == "masculino"
    assert updates["activity_level"] == "moderado"


def test_extracts_short_follow_up_using_calculation_context():
    updates = extract_state_updates("70 kg y 30 años", {"last_intent": "daily_calorie_calculation"})
    assert updates["weight_kg"] == 70
    assert updates["age"] == 30
