from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text.lower()).strip()


def _find_number(patterns: list[str], text: str) -> float | None:
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except ValueError:
                pass
    return None


def extract_state_updates(message: str, previous: dict[str, Any]) -> dict[str, Any]:
    t = normalize(message)
    updates: dict[str, Any] = {}

    weight = _find_number([r"(?:peso|peso es|peso de)\s*(?:de\s*)?(\d{2,3}(?:[.,]\d+)?)\s*(?:kg|kilos?)"], t)
    height = _find_number([r"(?:mido|estatura|altura)\s*(?:de\s*)?(\d{2,3}(?:[.,]\d+)?)\s*cm"], t)
    if height is None:
        height_m = _find_number([r"(?:mido|estatura|altura)\s*(?:de\s*)?(1[.,]\d{1,2})\s*(?:m|metros?)?\b"], t)
        height = height_m * 100 if height_m is not None else None
    age = _find_number([r"(?:tengo|edad|edad de)\s*(\d{1,3})\s*(?:anos?)"], t)
    if previous.get("last_intent") == "daily_calorie_calculation":
        weight = weight if weight is not None else _find_number([r"\b(\d{2,3}(?:[.,]\d+)?)\s*(?:kg|kilos?)\b"], t)
        height = height if height is not None else _find_number([r"\b(1[.,]\d{1,2})\s*(?:m|metros?)\b"], t)
        if height is not None and height < 3:
            height *= 100
        age = age if age is not None else _find_number([r"\b(\d{2})\s*(?:anos?)\b"], t)
    if weight is not None:
        updates["weight_kg"] = weight
    if height is not None:
        updates["height_cm"] = height
    if age is not None:
        updates["age"] = int(age)
    if any(x in t for x in ["sexo masculino", "soy hombre", "masculino"]):
        updates["formula_sex"] = "masculino"
    elif any(x in t for x in ["sexo femenino", "soy mujer", "femenino"]):
        updates["formula_sex"] = "femenino"
    activity_terms = {"muy_alto": ["muy alta", "muy alto"], "alto": ["actividad alta", "actividad alto"],
                      "moderado": ["moderada", "moderado"], "ligero": ["ligera", "ligero"],
                      "sedentario": ["sedentaria", "sedentario"]}
    for level, terms in activity_terms.items():
        if any(term in t for term in terms):
            updates["activity_level"] = level
            break

    # Calorías: distinguir meta diaria del presupuesto de esta ocasión.
    kcal = _find_number([
        r"(\d{2,4})\s*(?:kcal|calorias?)",
        r"(?:maximo|hasta|alrededor de|unas?|aprox(?:imadamente)?)\s*(\d{2,4})",
    ], t)
    if kcal is not None:
        if any(x in t for x in ["al dia", "diarias", "meta diaria", "diario", "por dia"]):
            updates["daily_kcal"] = kcal
        else:
            updates["meal_kcal"] = kcal

        if any(x in t for x in ["alrededor", "aprox", "unas ", "cerca de", "mas o menos"]):
            updates["kcal_mode"] = "around"
        elif any(x in t for x in ["maximo", "no pasar", "no exced", "hasta ", "menos de", "como tope", "me quedan"]):
            updates["kcal_mode"] = "strict"

    if "dulce" in t:
        updates["flavor"] = "Dulce"
    elif "salado" in t:
        updates["flavor"] = "Salado"

    if any(x in t for x in ["postre", "snack", "galleta", "alfajor", "mousse", "pastel", "helado"]):
        updates["consumption_type"] = "Snack/Postre"
        if "salado" not in t:
            updates.setdefault("flavor", "Dulce")
    elif any(x in t for x in ["bebida", "shake", "frappe", "jugo"]):
        updates["consumption_type"] = "Bebida"
    elif any(x in t for x in ["almuerzo", "cena", "desayuno", "comida", "wrap", "ensalada", "sandwich", "sándwich"]):
        updates["consumption_type"] = "Comida"

    if any(x in t for x in ["proteina", "proteico", "alta proteina", "mas proteina", "protein"]):
        updates["wants_protein"] = True
    if any(x in t for x in ["no importa la proteina", "sin priorizar proteina"]):
        updates["wants_protein"] = False

    price = _find_number([
        r"(?:s/\.?|soles?)\s*(\d{1,3}(?:[.,]\d{1,2})?)",
        r"(?:maximo|hasta|tope)\s*(\d{1,3}(?:[.,]\d{1,2})?)\s*soles?",
    ], t)
    if price is not None:
        updates["price_max"] = price

    exclusions = set(previous.get("exclusions") or [])
    exclusion_terms = {
        "lacteos": ["sin lactosa", "sin lacteos", "alergia a la leche", "evitar leche", "intolerante a la lactosa"],
        "huevo": ["sin huevo", "alergia al huevo", "evitar huevo"],
        "frutos secos/mani": ["sin mani", "sin maní", "sin frutos secos", "alergia al mani", "alergia al maní", "alergia a frutos secos"],
        "gluten": ["sin gluten", "celiaco", "celiaca", "celiaquia"],
    }
    for key, phrases in exclusion_terms.items():
        if any(normalize(p) in t for p in phrases):
            exclusions.add(key)
    if exclusions != set(previous.get("exclusions") or []):
        updates["exclusions"] = sorted(exclusions)

    if any(x in t for x in ["postre", "almuerzo", "cena", "desayuno", "snack", "bebida", "comida"]):
        updates["last_intent"] = message.strip()[:160]

    return updates


PROTEIN_SCORE = {"Baja": 0, "Baja-Media": 1, "Media": 2, "Media-Alta": 3, "Alta": 4}


def _passes_exclusions(product: dict, exclusions: list[str]) -> bool:
    alerts = normalize(product.get("ingredientes_alerta") or "")
    desc = normalize(product.get("descripcion_fuente") or "")
    for ex in exclusions:
        if ex == "gluten":
            if not product.get("sin_gluten_declarado"):
                return False
        elif ex == "lacteos" and any(k in alerts + " " + desc for k in ["lacteo", "leche", "queso", "yogurt", "whey", "suero"]):
            return False
        elif ex == "huevo" and "huevo" in alerts + " " + desc:
            return False
        elif ex == "frutos secos/mani" and any(k in alerts + " " + desc for k in ["mani", "frutos secos", "pistacho", "pecana", "almendra", "castana"]):
            return False
    return True


def select_candidates(catalog: list[dict], state: dict[str, Any], semantic_rank: dict[str, int] | None = None,
                      max_products: int = 3) -> tuple[list[dict], dict[str, Any]]:
    semantic_rank = semantic_rank or {}
    budget = state.get("meal_kcal")
    mode = state.get("kcal_mode") or "strict"
    flavor = state.get("flavor")
    consumption = state.get("consumption_type")
    price_max = state.get("price_max")
    exclusions = state.get("exclusions") or []
    wants_protein = bool(state.get("wants_protein"))

    rows = [p for p in catalog if _passes_exclusions(p, exclusions)]
    if price_max is not None:
        rows = [p for p in rows if float(p.get("precio_pen") or 0) <= float(price_max)]
    if flavor:
        rows = [p for p in rows if p.get("preferencia_sabor") == flavor]
    if consumption:
        rows = [p for p in rows if p.get("tipo_consumo") == consumption]

    flexible_used = False
    if budget is not None:
        if mode == "strict":
            strict = [p for p in rows if float(p.get("kcal_max_est") or 10**9) <= float(budget)]
            if strict:
                rows = strict
            else:
                # No se inventa un encaje: se permite mostrar alternativas flexibles,
                # pero la capa de respuesta las marcará explícitamente.
                rows = [p for p in rows if float(p.get("kcal_ref_est") or 10**9) <= float(budget)]
                flexible_used = bool(rows)
        else:
            # "Alrededor de" permite rangos que crucen el objetivo; se ordena por kcal de referencia.
            rows = [p for p in rows if float(p.get("kcal_min_est") or 0) <= float(budget) + 120]
            flexible_used = True

    def score(p: dict) -> tuple:
        pid = p.get("id", "")
        sem = semantic_rank.get(pid, 999)
        if budget is None:
            kcal_distance = float(p.get("kcal_ref_est") or 0)
        elif mode == "strict" and not flexible_used:
            kcal_distance = max(0.0, float(budget) - float(p.get("kcal_max_est") or 0))
        else:
            kcal_distance = abs(float(p.get("kcal_ref_est") or 0) - float(budget))
        protein = -PROTEIN_SCORE.get(str(p.get("nivel_proteico")), 0) if wants_protein else 0
        return (sem, kcal_distance, protein, float(p.get("precio_pen") or 0), str(p.get("producto")))

    rows.sort(key=score)
    return rows[:max_products], {
        "budget": budget,
        "mode": mode,
        "flexible_used": flexible_used,
        "filtered_count": len(rows),
        "exclusions": exclusions,
    }
