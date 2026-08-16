from __future__ import annotations

import json
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any

from langchain_community.vectorstores import LanceDB
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama, OllamaEmbeddings
from rank_bm25 import BM25Okapi

from config import (
    BRAND_CONTEXT, CATALOG_PATH, CHUNKS_PATH, CONTEXT_K, DENSE_K, LANCEDB_DIR,
    LEXICAL_K, MAX_HISTORY_MESSAGES, MAX_PRODUCTS, OLLAMA_BASE_URL,
    OLLAMA_EMBED_MODEL, OLLAMA_LLM_MODEL, OLLAMA_TEMPERATURE, SYSTEM_RULES,
)
from rag.filters import extract_state_updates, normalize, select_candidates
from rag.ingest import build_index, load_documents
from rag.memory import get_messages, get_state, save_message, update_state
from rag.nutrition import calculate_daily_calories, format_daily_calorie_result


class NutriMenuRAG:
    def __init__(self) -> None:
        self.catalog = json.loads(Path(CATALOG_PATH).read_text(encoding="utf-8"))
        self.by_id = {p["id"]: p for p in self.catalog}
        self.by_product = {str(p["producto"]).strip().lower(): p for p in self.catalog}
        self.chunk_rows = json.loads(Path(CHUNKS_PATH).read_text(encoding="utf-8"))
        self._documents = load_documents()
        self._tokens = [self._tokenize(d.page_content) for d in self._documents]
        self._bm25 = BM25Okapi(self._tokens)
        self._vectorstore: LanceDB | None = None
        self._lock = threading.Lock()
        self.llm = ChatOllama(
            model=OLLAMA_LLM_MODEL,
            temperature=OLLAMA_TEMPERATURE,
            base_url=OLLAMA_BASE_URL,
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
        return re.findall(r"[a-z0-9]+", t.lower())

    def _get_vectorstore(self) -> LanceDB:
        if self._vectorstore is not None:
            return self._vectorstore
        with self._lock:
            if self._vectorstore is None:
                # Para un corpus pequeño (119 chunks), reconstruir si no se pudo reabrir es barato
                # y evita depender de detalles de serialización entre versiones de LanceDB.
                self._vectorstore = build_index(force=True)
        return self._vectorstore

    def hybrid_retrieve(self, query: str, k: int = CONTEXT_K) -> list[Any]:
        dense_docs = self._get_vectorstore().similarity_search(query, k=DENSE_K)
        scores = self._bm25.get_scores(self._tokenize(query))
        lexical_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:LEXICAL_K]
        lexical_docs = [self._documents[i] for i in lexical_idx]

        # Reciprocal Rank Fusion: estable, simple y alineada a la práctica de búsqueda híbrida.
        fused: dict[str, dict[str, Any]] = {}
        for source_docs in (dense_docs, lexical_docs):
            for rank, doc in enumerate(source_docs, start=1):
                key = str(doc.metadata.get("chunk_id") or doc.page_content[:80])
                if key not in fused:
                    fused[key] = {"doc": doc, "score": 0.0}
                fused[key]["score"] += 1.0 / (60 + rank)
        ordered = sorted(fused.values(), key=lambda x: x["score"], reverse=True)
        return [x["doc"] for x in ordered[:k]]

    def _semantic_product_rank(self, docs: list[Any]) -> dict[str, int]:
        rank: dict[str, int] = {}
        pos = 0
        for d in docs:
            pid = d.metadata.get("product_id")
            if pid and pid not in rank:
                pos += 1
                rank[pid] = pos
        return rank


    def _mentioned_products(self, message: str) -> list[dict]:
        q = normalize(message)
        found = []
        for p in self.catalog:
            name = normalize(str(p.get("producto") or ""))
            if name and (name in q or q in name) and len(q) >= 4:
                found.append(p)
        return found[:3]

    @staticmethod
    def _wants_products_now(message: str) -> bool:
        q = normalize(message)
        health_calculation_terms = [
            "imc", "indice de masa corporal", "calorias debo consumir",
            "cuantas calorias necesito", "calorias de mantenimiento",
            "gasto calorico", "metabolismo basal", "mifflin",
        ]
        if any(term in q for term in health_calculation_terms):
            return False
        words = [
            "kcal", "caloria", "quiero", "recomienda", "recomiendame", "opcion", "otra",
            "comer", "postre", "snack", "almuerzo", "cena", "desayuno", "comida", "bebida",
            "dulce", "salado", "proteina", "proteico", "barato", "precio", "menu", "carta",
            "menos calorias", "mas ligero", "mas proteina"
        ]
        return any(w in q for w in words)

    def _history_text(self, room_id: str) -> str:
        messages = get_messages(room_id, limit=MAX_HISTORY_MESSAGES)
        lines = []
        for m in messages:
            role = "Usuario" if m["role"] == "user" else "Clara"
            content = m["content"]
            if content.strip():
                lines.append(f"{role}: {content.strip()}")
        return "\n".join(lines)

    @staticmethod
    def _strip_repeated_greeting(text: str) -> str:
        """Remove only a turn-opening greeting; preserve the useful response that follows."""
        return re.sub(
            r"^\s*¡?(?:hola|buenos días|buenas tardes|buenas noches)[!,.¿?\s]*",
            "", text or "", count=1, flags=re.IGNORECASE,
        ).strip()

    @staticmethod
    def _product_context(products: list[dict], meta: dict[str, Any]) -> str:
        if not products:
            return "No hay productos candidatos que cumplan los filtros actuales."
        blocks = []
        for p in products:
            blocks.append(
                " | ".join([
                    f"ID={p['id']}", f"Producto={p['producto']}", f"Categoría={p['categoria']}",
                    f"Precio=S/ {float(p['precio_pen']):.2f}",
                    f"kcal estimadas={p['kcal_min_est']}–{p['kcal_max_est']}",
                    f"kcal ref={p['kcal_ref_est']}", f"Proteína={p['nivel_proteico']}",
                    f"Etiquetas={p['etiquetas']}", f"Alertas={p['ingredientes_alerta']}",
                    f"Descripción={p['descripcion_fuente']}", f"imagen_png={p['imagen_png']}",
                ])
            )
        if meta.get("flexible_used"):
            blocks.append("NOTA: las opciones se están tratando como FLEXIBLES; no afirmar que cumplen un límite estricto.")
        return "\n".join(blocks)

    @staticmethod
    def _lowest_calorie_answer(products: list[dict]) -> str:
        if not products:
            return "No encontré opciones comparables con los filtros actuales."
        details = [
            f"{p['producto']} ({p['kcal_min_est']}–{p['kcal_max_est']} kcal, referencia {p['kcal_ref_est']})"
            for p in products
        ]
        first = min(products, key=lambda p: (float(p["kcal_max_est"]), float(p["kcal_ref_est"])))
        return (
            "Las opciones con menos calorías de la carta son "
            + "; ".join(details)
            + f". Si buscas la alternativa más conservadora por su límite máximo, {first['producto']} "
              f"queda en primer lugar con hasta {first['kcal_max_est']} kcal. "
              "Son valores estimados y pueden variar según la preparación."
        )

    def _context_text(self, docs: list[Any]) -> str:
        return "\n\n".join(
            f"[{d.metadata.get('tipo')} · {d.metadata.get('titulo')}] {d.page_content}"
            for d in docs
        )

    def answer(self, room_id: str, message: str) -> dict[str, Any]:
        previous = get_state(room_id)
        updates = extract_state_updates(message, previous)
        state = update_state(room_id, updates) if updates else previous

        q = normalize(message)
        explicit_calorie_intent = any(term in q for term in [
            "calorias debo consumir", "cuantas calorias necesito", "calorias diarias",
            "calorias de mantenimiento", "gasto calorico", "metabolismo basal", "mifflin",
        ])
        supplied_calculation_data = any(key in updates for key in [
            "weight_kg", "height_cm", "age", "formula_sex", "activity_level",
        ])
        calorie_intent = explicit_calorie_intent or (
            previous.get("last_intent") == "daily_calorie_calculation" and supplied_calculation_data
        )
        if calorie_intent:
            state = update_state(room_id, {"last_intent": "daily_calorie_calculation"})
            required = {"peso en kg": state.get("weight_kg"), "estatura en cm": state.get("height_cm"),
                        "edad": state.get("age"), "sexo (masculino o femenino)": state.get("formula_sex")}
            missing = [label for label, value in required.items() if value is None]
            if missing:
                response = "Para calcularlo me falta: " + ", ".join(missing) + "."
                payload = {"products": [], "state": state, "filter_meta": {}, "retrieved_chunks": []}
                message_id = save_message(room_id, "assistant", response, payload=payload)
                return {"answer": response, "message_id": message_id, **payload}
            try:
                result = calculate_daily_calories(weight_kg=state["weight_kg"], height_cm=state["height_cm"],
                                                   age=state["age"], sex=state["formula_sex"],
                                                   activity_level=state.get("activity_level") or "sedentario")
                response = format_daily_calorie_result(result)
            except ValueError as exc:
                response, result = str(exc), None
            payload = {"products": [], "state": state, "filter_meta": {}, "retrieved_chunks": [],
                       "nutrition_calculation": result}
            message_id = save_message(room_id, "assistant", response, payload=payload)
            return {"answer": response, "message_id": message_id, **payload}

        retrieved = self.hybrid_retrieve(message)
        semantic_rank = self._semantic_product_rank(retrieved)
        mentioned = self._mentioned_products(message)
        products, filter_meta = select_candidates(
            self.catalog, state, semantic_rank=semantic_rank, max_products=MAX_PRODUCTS
        )

        q = normalize(message)
        wants_lowest_calorie = any(term in q for term in [
            "menos calorias", "menor calorias", "menor en calorias", "mas bajo en calorias",
            "pocas calorias", "poca calorias", "bajas en calorias", "baja en calorias",
            "bajos en calorias", "bajo en calorias", "pocas kcal", "bajas kcal",
            "menos kcal", "menor kcal", "alimento mas ligero", "producto mas ligero",
        ])
        if wants_lowest_calorie and not state.get("meal_kcal"):
            eligible = sorted(
                self.catalog,
                key=lambda p: (float(p.get("kcal_ref_est") or 10**9), float(p.get("precio_pen") or 10**9)),
            )
            products = eligible[:MAX_PRODUCTS]
            filter_meta.update({"lowest_calorie_query": True, "filtered_count": len(eligible)})

        # El presupuesto de la ocasión es el dato obligatorio para una recomendación.
        # Consultas informativas sobre un producto exacto sí pueden responderse sin presupuesto.
        needs_meal_budget = not state.get("meal_kcal") and not wants_lowest_calorie
        wants_products_now = self._wants_products_now(message)
        if mentioned:
            products = mentioned
            filter_meta["informational_product_query"] = True
        elif (needs_meal_budget and not wants_lowest_calorie) or not wants_products_now:
            products = []

        history = self._history_text(room_id)
        has_previous_assistant = any(m["role"] == "assistant" for m in get_messages(room_id, limit=MAX_HISTORY_MESSAGES))
        knowledge_context = self._context_text(retrieved)
        product_context = self._product_context(products, filter_meta)

        user_prompt = f"""
CONTEXTO DE MARCA
{BRAND_CONTEXT}

ESTADO RECORDADO DE ESTA SALA (room_id={room_id})
{json.dumps(state, ensure_ascii=False, default=str)}

HISTORIAL RECIENTE DE ESTA SALA
{history or '(sin historial previo)'}

FRAGMENTOS RAG RECUPERADOS
{knowledge_context}

PRODUCTOS CANDIDATOS DETERMINÍSTICOS
{product_context}

MENSAJE ACTUAL DEL USUARIO
{message}

BANDERAS DE CONTROL
needs_meal_budget={needs_meal_budget}
wants_products_now={wants_products_now}
lowest_calorie_query={wants_lowest_calorie}

INSTRUCCIÓN PARA ESTA RESPUESTA
- Responde al mensaje actual usando el historial y el estado de esta sala.
- Si needs_meal_budget=True y wants_products_now=True, pide cuántas kcal desea reservar para esta comida.
- Si lowest_calorie_query=True, responde directamente cuál tiene menos calorías y compáralo con
  las otras opciones candidatas; no pidas un presupuesto de kcal.
- Si hay productos candidatos, puedes recomendar solamente esos productos.
- No escribas JSON ni Markdown de tabla. Las tarjetas visuales se construyen aparte con datos estructurados.
- La respuesta debe seguir las reglas del sistema y recordar que Clara pertenece a Protein Food.
""".strip()

        if wants_lowest_calorie:
            response = self._lowest_calorie_answer(products)
        else:
            try:
                response = self.llm.invoke([
                    SystemMessage(content=SYSTEM_RULES),
                    HumanMessage(content=user_prompt),
                ]).content.strip()
                if has_previous_assistant:
                    response = self._strip_repeated_greeting(response)
            except Exception as exc:
                response = (
                    "No pude conectarme con Ollama en este momento. Verifica que Ollama esté ejecutándose "
                    f"y que el modelo {OLLAMA_LLM_MODEL} esté descargado. Detalle: {type(exc).__name__}."
                )
                products = []

        payload_products = []
        for p in products:
            payload_products.append({
                "id": p["id"],
                "producto": p["producto"],
                "categoria": p["categoria"],
                "precio_pen": p["precio_pen"],
                "kcal_min_est": p["kcal_min_est"],
                "kcal_max_est": p["kcal_max_est"],
                "kcal_ref_est": p["kcal_ref_est"],
                "nivel_proteico": p["nivel_proteico"],
                "descripcion": p["descripcion_fuente"],
                "ingredientes_alerta": p["ingredientes_alerta"],
                "imagen_png": p["imagen_png"],
                "image_url": f"/static/products/{p['imagen_png']}",
                "flexible": bool(filter_meta.get("flexible_used")),
            })

        payload = {
            "products": payload_products,
            "state": state,
            "filter_meta": filter_meta,
            "retrieved_chunks": [d.metadata.get("chunk_id") for d in retrieved],
        }
        message_id = save_message(room_id, "assistant", response, payload=payload)
        return {"answer": response, "message_id": message_id, **payload}
