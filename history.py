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


def get_stats() -> dict:
    """Return aggregate stats for the stats bar."""
    conn = _connect()
    total = conn.execute("SELECT COUNT(*) FROM upload_history").fetchone()[0]
    uploaded = conn.execute("SELECT COUNT(*) FROM upload_history WHERE status = 'uploaded'").fetchone()[0]
    failed = conn.execute("SELECT COUNT(*) FROM upload_history WHERE status = 'failed'").fetchone()[0]
    today = conn.execute(
        "SELECT COUNT(*) FROM upload_history WHERE status = 'uploaded' AND date(uploaded_at) = date('now')"
    ).fetchone()[0]
    conn.close()
    success_rate = round((uploaded / total * 100) if total > 0 else 0, 1)
    return {
        "total": total,
        "uploaded": uploaded,
        "failed": failed,
        "today": today,
        "success_rate": success_rate,
    }


def get_distinct_subreddits() -> list[str]:
    """Return list of distinct subreddits from history."""
    conn = _connect()
    cursor = conn.execute("SELECT DISTINCT subreddit FROM upload_history WHERE subreddit != '' ORDER BY subreddit")
    subs = [r[0] for r in cursor.fetchall()]
    conn.close()
    return subs


def search_history(q: str = "", subreddit: str = "", status: str = "",
                   page: int = 1, per_page: int = 25) -> dict:
    """Search and filter history with pagination."""
    conn = _connect()
    conditions = []
    params = []

    if q:
        conditions.append("title LIKE ?")
        params.append(f"%{q}%")
    if subreddit:
        conditions.append("subreddit = ?")
        params.append(subreddit)
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    # Total count
    count_cursor = conn.execute(f"SELECT COUNT(*) FROM upload_history{where}", params)
    total = count_cursor.fetchone()[0]

    # Paginated results
    offset = (page - 1) * per_page
    cursor = conn.execute(
        f"SELECT post_id, title, subreddit, reddit_url, youtube_id, score, duration, status, error, uploaded_at, author "
        f"FROM upload_history{where} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    )
    rows = cursor.fetchall()
    conn.close()

    return {
        "uploads": [
            {
                "post_id": r[0], "title": r[1], "subreddit": r[2], "reddit_url": r[3],
                "youtube_id": r[4], "score": r[5], "duration": r[6], "status": r[7],
                "error": r[8], "uploaded_at": r[9], "author": r[10] or "",
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }
