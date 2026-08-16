from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from rag.memory import _connect, _now


def save_conversation_feedback(room_id: str, satisfaction: int | None, nps: int | None,
                               comment: str = "", resolved: bool | None = None) -> dict[str, Any]:
    if satisfaction is not None and not 1 <= satisfaction <= 5:
        raise ValueError("La satisfacción debe estar entre 1 y 5.")
    if nps is not None and not 0 <= nps <= 10:
        raise ValueError("El NPS debe estar entre 0 y 10.")
    now = _now()
    with _connect() as con:
        if not con.execute("SELECT 1 FROM chat_rooms WHERE id=?", (room_id,)).fetchone():
            raise LookupError("La conversación no existe.")
        con.execute("""INSERT INTO conversation_feedback(room_id,satisfaction,nps,comment,resolved,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?) ON CONFLICT(room_id) DO UPDATE SET
                       satisfaction=excluded.satisfaction,nps=excluded.nps,comment=excluded.comment,
                       resolved=excluded.resolved,updated_at=excluded.updated_at""",
                    (room_id, satisfaction, nps, comment.strip()[:2000],
                     None if resolved is None else int(resolved), now, now))
    return {"room_id": room_id, "satisfaction": satisfaction, "nps": nps,
            "comment": comment.strip(), "resolved": resolved}


def dashboard_metrics(days: int = 30) -> dict[str, Any]:
    days = max(1, min(int(days), 365))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _connect() as con:
        counts = con.execute("""SELECT COUNT(*) conversations,
            COALESCE(SUM((SELECT COUNT(*) FROM messages m WHERE m.room_id=r.id)),0) messages
            FROM chat_rooms r WHERE created_at>=?""", (since,)).fetchone()
        message_fb = con.execute("""SELECT COUNT(*) total,
            SUM(CASE WHEN rating='useful' THEN 1 ELSE 0 END) positive
            FROM message_feedback WHERE created_at>=?""", (since,)).fetchone()
        conv = con.execute("""SELECT COUNT(satisfaction) csat_count, AVG(satisfaction) satisfaction,
            SUM(CASE WHEN satisfaction>=4 THEN 1 ELSE 0 END) positive,
            SUM(CASE WHEN satisfaction<=2 THEN 1 ELSE 0 END) negative,
            COUNT(nps) nps_count, SUM(CASE WHEN nps>=9 THEN 1 ELSE 0 END) promoters,
            SUM(CASE WHEN nps BETWEEN 7 AND 8 THEN 1 ELSE 0 END) passives,
            SUM(CASE WHEN nps<=6 THEN 1 ELSE 0 END) detractors,
            COUNT(resolved) resolution_count, AVG(resolved)*100 resolution_rate
            FROM conversation_feedback WHERE created_at>=?""", (since,)).fetchone()
        timeline = con.execute("""SELECT substr(created_at,1,10) day, COUNT(*) conversations
            FROM chat_rooms WHERE created_at>=? GROUP BY day ORDER BY day""", (since,)).fetchall()
        satisfaction_timeline = con.execute("""SELECT substr(created_at,1,10) day,
            ROUND(AVG(satisfaction),2) satisfaction FROM conversation_feedback
            WHERE created_at>=? AND satisfaction IS NOT NULL GROUP BY day ORDER BY day""", (since,)).fetchall()
        feedback = con.execute("""SELECT c.room_id,c.satisfaction,c.nps,c.comment,c.resolved,c.updated_at
            FROM conversation_feedback c WHERE c.created_at>=? AND COALESCE(c.comment,'')<>''
            ORDER BY c.updated_at DESC LIMIT 20""", (since,)).fetchall()
        durations = con.execute("""SELECT AVG((julianday(max_at)-julianday(min_at))*86400.0) avg_seconds,
            AVG(cnt) avg_messages FROM (SELECT room_id,MIN(created_at) min_at,MAX(created_at) max_at,
            COUNT(*) cnt FROM messages WHERE created_at>=? GROUP BY room_id)""", (since,)).fetchone()
    total_fb = message_fb["total"] or 0
    nps_count = conv["nps_count"] or 0
    nps = None if nps_count < 5 else round(100 * ((conv["promoters"] or 0) - (conv["detractors"] or 0)) / nps_count, 1)
    csat_count = conv["csat_count"] or 0
    return {"period_days": days, "kpis": {
        "satisfaction": round(conv["satisfaction"], 2) if conv["satisfaction"] is not None else None,
        "csat": round(100 * (conv["positive"] or 0) / csat_count, 1) if csat_count else None,
        "nps": nps, "nps_responses": nps_count, "promoters": conv["promoters"] or 0,
        "passives": conv["passives"] or 0, "detractors": conv["detractors"] or 0,
        "message_positive_rate": round(100 * (message_fb["positive"] or 0) / total_fb, 1) if total_fb else None,
        "message_negative_rate": round(100 * (total_fb-(message_fb["positive"] or 0)) / total_fb, 1) if total_fb else None,
        "conversations": counts["conversations"], "messages": counts["messages"], "clients": None,
        "resolution_rate": round(conv["resolution_rate"], 1) if conv["resolution_rate"] is not None else None,
        "avg_messages": round(durations["avg_messages"], 1) if durations["avg_messages"] is not None else None,
        "avg_response_seconds": None,
        "avg_conversation_seconds": round(durations["avg_seconds"]) if durations["avg_seconds"] is not None else None,
    }, "timeline": [dict(x) for x in timeline],
       "satisfaction_timeline": [dict(x) for x in satisfaction_timeline],
       "feedback": [dict(x) for x in feedback]}
