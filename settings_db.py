import os
import sqlite3

DB_FILE = "auto_youtuber.db"

DEFAULTS = {
    "REDDIT_CLIENT_ID": "",
    "REDDIT_CLIENT_SECRET": "",
    "REDDIT_USER_AGENT": "AutoYoutuber/1.0",
    "SUBREDDITS": "funny,videos,Unexpected",
    "TIME_FILTER": "day",
    "POST_LIMIT": "20",
    "YOUTUBE_CLIENT_SECRETS_FILE": "client_secrets.json",
    "YOUTUBE_TOKEN_FILE": "youtube_token.json",
    "VIDEOS_PER_DAY": "6",
    "TEMP_DIR": "temp",
    "DB_PATH": "processed_posts.db",
    "LOG_FILE": "auto_youtuber.log",
    "MAX_DURATION_SECONDS": "59",
}


def _connect():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    return conn


def migrate_from_dotenv():
    """Seed settings from .env file if it exists, then fill remaining defaults."""
    env_values = {}
    if os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key in DEFAULTS:
                    env_values[key] = value

    conn = _connect()
    for key, default in DEFAULTS.items():
        value = env_values.get(key, default)
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.commit()
    conn.close()


def get_setting(key: str) -> str:
    conn = _connect()
    cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row is not None:
        return row[0]
    return DEFAULTS.get(key, "")


def set_setting(key: str, value: str):
    conn = _connect()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_all_settings() -> dict:
    conn = _connect()
    cursor = conn.execute("SELECT key, value FROM settings")
    settings = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    # Fill in any missing defaults
    for key, default in DEFAULTS.items():
        if key not in settings:
            settings[key] = default
    return settings


def set_many_settings(updates: dict):
    conn = _connect()
    for key, value in updates.items():
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()
