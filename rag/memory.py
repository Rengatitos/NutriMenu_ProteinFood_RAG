from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def init_db() -> None:
    with _connect() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_rooms (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
                content TEXT NOT NULL,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(room_id) REFERENCES chat_rooms(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS room_state (
                room_id TEXT PRIMARY KEY,
                meal_kcal REAL,
                daily_kcal REAL,
                kcal_mode TEXT,
                flavor TEXT,
                consumption_type TEXT,
                wants_protein INTEGER,
                price_max REAL,
                exclusions_json TEXT,
                last_intent TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(room_id) REFERENCES chat_rooms(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS message_feedback (
                message_id INTEGER PRIMARY KEY,
                room_id TEXT NOT NULL,
                rating TEXT NOT NULL CHECK(rating IN ('useful','not_useful')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE,
                FOREIGN KEY(room_id) REFERENCES chat_rooms(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS conversation_feedback (
                room_id TEXT PRIMARY KEY,
                satisfaction INTEGER CHECK(satisfaction BETWEEN 1 AND 5),
                nps INTEGER CHECK(nps BETWEEN 0 AND 10),
                comment TEXT,
                resolved INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(room_id) REFERENCES chat_rooms(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_room_created
                ON messages(room_id, id);
            CREATE INDEX IF NOT EXISTS idx_rooms_updated
                ON chat_rooms(updated_at DESC);
            """
        )
        existing = {row[1] for row in con.execute("PRAGMA table_info(room_state)")}
        for column, sql_type in {"weight_kg": "REAL", "height_cm": "REAL", "age": "INTEGER",
                                 "formula_sex": "TEXT", "activity_level": "TEXT"}.items():
            if column not in existing:
                con.execute(f"ALTER TABLE room_state ADD COLUMN {column} {sql_type}")


def create_room(title: str = "Nueva conversación") -> dict[str, Any]:
    init_db()
    room_id = str(uuid.uuid4())
    now = _now()
    with _connect() as con:
        con.execute(
            "INSERT INTO chat_rooms(id,title,created_at,updated_at) VALUES(?,?,?,?)",
            (room_id, title.strip() or "Nueva conversación", now, now),
        )
        con.execute(
            "INSERT INTO room_state(room_id,kcal_mode,wants_protein,exclusions_json,updated_at) "
            "VALUES(?,?,?,?,?)",
            (room_id, "strict", 0, "[]", now),
        )
    return get_room(room_id)


def get_room(room_id: str) -> dict[str, Any] | None:
    with _connect() as con:
        row = con.execute("SELECT * FROM chat_rooms WHERE id=?", (room_id,)).fetchone()
    return dict(row) if row else None


def ensure_room(room_id: str | None) -> dict[str, Any]:
    if room_id:
        room = get_room(room_id)
        if room:
            return room
    return create_room()


def list_rooms(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with _connect() as con:
        rows = con.execute(
            """
            SELECT r.*,
                   (SELECT content FROM messages m WHERE m.room_id=r.id AND m.role='user'
                    ORDER BY m.id DESC LIMIT 1) AS preview
            FROM chat_rooms r
            ORDER BY r.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_room(room_id: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM chat_rooms WHERE id=?", (room_id,))


def reset_room(room_id: str) -> None:
    now = _now()
    with _connect() as con:
        con.execute("DELETE FROM messages WHERE room_id=?", (room_id,))
        con.execute(
            """UPDATE room_state SET meal_kcal=NULL,daily_kcal=NULL,kcal_mode='strict',
               flavor=NULL,consumption_type=NULL,wants_protein=0,price_max=NULL,
               exclusions_json='[]',last_intent=NULL,weight_kg=NULL,height_cm=NULL,age=NULL,
               formula_sex=NULL,activity_level=NULL,updated_at=? WHERE room_id=?""",
            (now, room_id),
        )
        con.execute(
            "UPDATE chat_rooms SET title='Nueva conversación',updated_at=? WHERE id=?",
            (now, room_id),
        )


def save_message(room_id: str, role: str, content: str, payload: dict | None = None) -> int:
    now = _now()
    payload_json = json.dumps(payload, ensure_ascii=False) if payload is not None else None
    with _connect() as con:
        cur = con.execute(
            "INSERT INTO messages(room_id,role,content,payload_json,created_at) VALUES(?,?,?,?,?)",
            (room_id, role, content, payload_json, now),
        )
        con.execute("UPDATE chat_rooms SET updated_at=? WHERE id=?", (now, room_id))
        msg_id = int(cur.lastrowid)
    return msg_id


def get_messages(room_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as con:
        rows = con.execute(
            """SELECT * FROM (
                   SELECT id,room_id,role,content,payload_json,created_at,
                          (SELECT rating FROM message_feedback f WHERE f.message_id=messages.id) AS feedback
                   FROM messages WHERE room_id=? ORDER BY id DESC LIMIT ?
               ) ORDER BY id ASC""",
            (room_id, limit),
        ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["payload"] = json.loads(d.pop("payload_json")) if d.get("payload_json") else None
        out.append(d)
    return out


def maybe_title_room(room_id: str, first_user_text: str) -> None:
    room = get_room(room_id)
    if not room or room["title"] != "Nueva conversación":
        return
    title = " ".join(first_user_text.strip().split())[:54]
    if len(first_user_text.strip()) > 54:
        title += "…"
    with _connect() as con:
        con.execute(
            "UPDATE chat_rooms SET title=?,updated_at=? WHERE id=?",
            (title or "Nueva conversación", _now(), room_id),
        )


def get_state(room_id: str) -> dict[str, Any]:
    init_db()
    with _connect() as con:
        row = con.execute("SELECT * FROM room_state WHERE room_id=?", (room_id,)).fetchone()
        if not row:
            con.execute(
                "INSERT INTO room_state(room_id,kcal_mode,wants_protein,exclusions_json,updated_at) "
                "VALUES(?,?,?,?,?)",
                (room_id, "strict", 0, "[]", _now()),
            )
            row = con.execute("SELECT * FROM room_state WHERE room_id=?", (room_id,)).fetchone()
    d = dict(row)
    d["wants_protein"] = bool(d.get("wants_protein"))
    d["exclusions"] = json.loads(d.pop("exclusions_json") or "[]")
    return d


def update_state(room_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "meal_kcal", "daily_kcal", "kcal_mode", "flavor", "consumption_type",
        "wants_protein", "price_max", "last_intent", "weight_kg", "height_cm", "age",
        "formula_sex", "activity_level",
    }
    current = get_state(room_id)
    exclusions = updates.pop("exclusions", None)
    fields, values = [], []
    for key, value in updates.items():
        if key not in allowed:
            continue
        fields.append(f"{key}=?")
        if key == "wants_protein":
            value = int(bool(value))
        values.append(value)
    if exclusions is not None:
        fields.append("exclusions_json=?")
        values.append(json.dumps(sorted(set(exclusions)), ensure_ascii=False))
    fields.append("updated_at=?")
    values.append(_now())
    values.append(room_id)
    with _connect() as con:
        con.execute(f"UPDATE room_state SET {', '.join(fields)} WHERE room_id=?", values)
    return get_state(room_id)
