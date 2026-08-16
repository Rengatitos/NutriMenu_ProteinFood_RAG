from __future__ import annotations

import requests
from flask import Flask, jsonify, render_template, request

from config import OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL, OLLAMA_LLM_MODEL
from rag.engine import NutriMenuRAG
from rag.feedback import save_feedback
from rag.analytics import dashboard_metrics, save_conversation_feedback
from rag.memory import (
    create_room, delete_room, ensure_room, get_messages, init_db, list_rooms,
    maybe_title_room, reset_room, save_message,
)

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
init_db()
_engine: NutriMenuRAG | None = None


def engine() -> NutriMenuRAG:
    global _engine
    if _engine is None:
        _engine = NutriMenuRAG()
    return _engine


@app.get("/")
def index():
    return render_template("home.html")


@app.get("/chat")
def chat_page():
    return render_template("index.html")


@app.get("/api/health")
def health():
    ollama_ok = False
    models = []
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        r.raise_for_status()
        models = sorted(m.get("name", "") for m in r.json().get("models", []))
        ollama_ok = True
    except Exception:
        pass
    return jsonify({
        "ok": True,
        "ollama_ok": ollama_ok,
        "llm_model": OLLAMA_LLM_MODEL,
        "embedding_model": OLLAMA_EMBED_MODEL,
        "models": models,
    })


@app.get("/api/cx/metrics")
def cx_metrics():
    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        return jsonify({"error": "El período no es válido."}), 400
    return jsonify(dashboard_metrics(days))


@app.post("/api/conversation-feedback")
def conversation_feedback():
    data = request.get_json(silent=True) or {}
    try:
        saved = save_conversation_feedback(
            str(data.get("room_id") or ""),
            int(data["satisfaction"]) if data.get("satisfaction") is not None else None,
            int(data["nps"]) if data.get("nps") is not None else None,
            str(data.get("comment") or ""), data.get("resolved"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"ok": True, "feedback": saved})


@app.get("/api/rooms")
def rooms_list():
    return jsonify({"rooms": list_rooms()})


@app.post("/api/rooms")
def rooms_create():
    data = request.get_json(silent=True) or {}
    return jsonify({"room": create_room(data.get("title") or "Nueva conversación")}), 201


@app.delete("/api/rooms/<room_id>")
def rooms_delete(room_id: str):
    delete_room(room_id)
    return jsonify({"ok": True})


@app.post("/api/rooms/<room_id>/reset")
def rooms_reset(room_id: str):
    reset_room(room_id)
    return jsonify({"ok": True})


@app.get("/api/rooms/<room_id>/messages")
def room_messages(room_id: str):
    room = ensure_room(room_id)
    return jsonify({"room": room, "messages": get_messages(room["id"], limit=200)})


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    text = str(data.get("message") or "").strip()
    room_id = data.get("room_id")
    if not text:
        return jsonify({"error": "El mensaje está vacío."}), 400

    room = ensure_room(room_id)
    room_id = room["id"]
    save_message(room_id, "user", text)
    maybe_title_room(room_id, text)
    result = engine().answer(room_id, text)
    return jsonify({"room_id": room_id, **result})


@app.post("/api/feedback")
def feedback():
    data = request.get_json(silent=True) or {}
    room_id = str(data.get("room_id") or "").strip()
    rating = str(data.get("rating") or "").strip()
    try:
        message_id = int(data.get("message_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "message_id inválido."}), 400
    if not room_id:
        return jsonify({"error": "room_id es obligatorio."}), 400
    try:
        saved = save_feedback(room_id, message_id, rating)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except PermissionError:
        return jsonify({"error": "Cierra el archivo Excel para poder actualizarlo."}), 409
    return jsonify({"ok": True, "feedback": saved})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
