from __future__ import annotations

from typing import Any

ACTIVITY_FACTORS = {"sedentario": 1.2, "ligero": 1.375, "moderado": 1.55, "alto": 1.725, "muy_alto": 1.9}


def calculate_daily_calories(*, weight_kg: float, height_cm: float, age: int, sex: str,
                             activity_level: str = "sedentario") -> dict[str, Any]:
    """Estimate adult resting energy and maintenance kcal with Mifflin-St Jeor."""
    if not 20 <= int(age) <= 100:
        raise ValueError("La fórmula está habilitada solo para adultos de 20 a 100 años.")
    if not 30 <= float(weight_kg) <= 350:
        raise ValueError("El peso debe estar entre 30 y 350 kg.")
    if not 120 <= float(height_cm) <= 230:
        raise ValueError("La estatura debe estar entre 120 y 230 cm.")
    sex = str(sex).lower()
    if sex not in {"masculino", "femenino"}:
        raise ValueError("El sexo de la fórmula debe ser masculino o femenino.")
    if activity_level not in ACTIVITY_FACTORS:
        raise ValueError("El nivel de actividad no es válido.")
    ree = 10 * float(weight_kg) + 6.25 * float(height_cm) - 5 * int(age) + (5 if sex == "masculino" else -161)
    factor = ACTIVITY_FACTORS[activity_level]
    return {"weight_kg": float(weight_kg), "height_cm": float(height_cm), "age": int(age),
            "sex": sex, "activity_level": activity_level, "activity_factor": factor,
            "resting_kcal": round(ree), "maintenance_kcal": int(round(ree * factor / 10.0) * 10),
            "activity_assumed": activity_level == "sedentario"}


def format_daily_calorie_result(result: dict[str, Any]) -> str:
    assumption = (" Como no indicaste tu actividad, usé el nivel sedentario como referencia; puedes decirme si "
                  "tu actividad es ligera, moderada, alta o muy alta para ajustarla."
                  if result.get("activity_assumed") else "")
    constant = "+ 5" if result["sex"] == "masculino" else "− 161"
    return (f"Tu gasto energético en reposo estimado es de {result['resting_kcal']} kcal/día. "
            f"Cálculo Mifflin–St Jeor: 10×{result['weight_kg']:g} + 6.25×{result['height_cm']:g} "
            f"− 5×{result['age']} {constant}. Con actividad {result['activity_level'].replace('_', ' ')} "
            f"(factor {result['activity_factor']:g}), tus calorías de mantenimiento estimadas son "
            f"aproximadamente {result['maintenance_kcal']} kcal/día.{assumption} "
            "Es una orientación para adultos, no una prescripción médica.")
