"""SQLite persistence for the pipeline queue so items survive restarts."""

import json
import sqlite3

from settings_db import DB_FILE


def _connect():
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS queue ("
        "  uid TEXT PRIMARY KEY,"
        "  post_json TEXT NOT NULL,"
        "  status TEXT DEFAULT 'queued',"
        "  progress TEXT DEFAULT '',"
        "  youtube_id TEXT,"
        "  error TEXT,"
        "  added_at TEXT"
        ")"
    )
    conn.commit()
    return conn


def save_queue(items: list[dict]):
    """Replace the entire persisted queue with the given items."""
    conn = _connect()
    conn.execute("DELETE FROM queue")
    for item in items:
        conn.execute(
            "INSERT INTO queue (uid, post_json, status, progress, youtube_id, error, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                item["uid"],
                json.dumps(item["post"]),
                item["status"],
                item.get("progress", ""),
                item.get("youtube_id"),
                item.get("error"),
                item.get("added_at", ""),
            ),
        )
    conn.commit()
    conn.close()


def load_queue() -> list[dict]:
    """Load persisted queue items. Returns list of dicts with post, uid, status, etc."""
    conn = _connect()
    cursor = conn.execute(
        "SELECT uid, post_json, status, progress, youtube_id, error, added_at FROM queue ORDER BY rowid"
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "uid": r[0],
            "post": json.loads(r[1]),
            "status": r[2],
            "progress": r[3] or "",
            "youtube_id": r[4],
            "error": r[5],
            "added_at": r[6] or "",
        }
        for r in rows
    ]


def clear_queue():
    conn = _connect()
    conn.execute("DELETE FROM queue")
    conn.commit()
    conn.close()
