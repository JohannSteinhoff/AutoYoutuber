import sqlite3

from settings_db import DB_FILE


def _connect():
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS upload_history ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  post_id TEXT,"
        "  title TEXT,"
        "  subreddit TEXT,"
        "  reddit_url TEXT,"
        "  youtube_id TEXT,"
        "  score INTEGER DEFAULT 0,"
        "  duration INTEGER DEFAULT 0,"
        "  status TEXT DEFAULT 'uploaded',"
        "  error TEXT,"
        "  uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        "  author TEXT DEFAULT ''"
        ")"
    )
    # Migrate: add author column if missing
    try:
        conn.execute("ALTER TABLE upload_history ADD COLUMN author TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    return conn


def save_upload(post: dict, youtube_id: str | None, success: bool, error: str | None = None):
    conn = _connect()
    conn.execute(
        "INSERT INTO upload_history (post_id, title, subreddit, reddit_url, youtube_id, score, duration, status, error, author) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            post.get("id", ""),
            post.get("title", ""),
            post.get("subreddit", ""),
            post.get("url", ""),
            youtube_id,
            post.get("score", 0),
            post.get("duration", 0),
            "uploaded" if success else "failed",
            error,
            post.get("author", ""),
        ),
    )
    conn.commit()
    conn.close()


def get_history(limit: int = 50) -> list[dict]:
    conn = _connect()
    cursor = conn.execute(
        "SELECT post_id, title, subreddit, reddit_url, youtube_id, score, duration, status, error, uploaded_at, author "
        "FROM upload_history ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "post_id": r[0],
            "title": r[1],
            "subreddit": r[2],
            "reddit_url": r[3],
            "youtube_id": r[4],
            "score": r[5],
            "duration": r[6],
            "status": r[7],
            "error": r[8],
            "uploaded_at": r[9],
            "author": r[10] or "",
        }
        for r in rows
    ]


def get_history_count() -> int:
    conn = _connect()
    cursor = conn.execute("SELECT COUNT(*) FROM upload_history WHERE status = 'uploaded'")
    count = cursor.fetchone()[0]
    conn.close()
    return count
