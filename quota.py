import logging
import sqlite3
from datetime import datetime, timezone, timedelta

from settings_db import DB_FILE

logger = logging.getLogger(__name__)

DAILY_QUOTA = 10000
UPLOAD_COST = 1600

# YouTube quota resets at midnight Pacific Time (UTC-8, or UTC-7 during DST)
PACIFIC_OFFSET = timedelta(hours=-7)  # PDT; change to -8 for PST if needed


def _connect():
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS quota_log "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
        " action TEXT, units INTEGER, "
        " timestamp TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    return conn


def _get_pacific_today() -> str:
    """Get today's date in Pacific time as YYYY-MM-DD."""
    utc_now = datetime.now(timezone.utc)
    pacific_now = utc_now + PACIFIC_OFFSET
    return pacific_now.strftime("%Y-%m-%d")


def record_upload():
    """Record that an upload was made (1600 units)."""
    conn = _connect()
    conn.execute(
        "INSERT INTO quota_log (action, units, timestamp) VALUES (?, ?, ?)",
        ("upload", UPLOAD_COST, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    logger.info("Quota: recorded upload (%d units)", UPLOAD_COST)


def get_units_used_today() -> int:
    """Get total API units used since the last Pacific midnight."""
    pacific_today = _get_pacific_today()
    # Convert Pacific midnight to UTC for comparison
    pacific_midnight = datetime.strptime(pacific_today, "%Y-%m-%d").replace(
        tzinfo=timezone(PACIFIC_OFFSET)
    )
    utc_cutoff = pacific_midnight.astimezone(timezone.utc).isoformat()

    conn = _connect()
    cursor = conn.execute(
        "SELECT COALESCE(SUM(units), 0) FROM quota_log WHERE timestamp >= ?",
        (utc_cutoff,),
    )
    used = cursor.fetchone()[0]
    conn.close()
    return used


def get_uploads_today() -> int:
    """Get number of uploads since the last Pacific midnight."""
    pacific_today = _get_pacific_today()
    pacific_midnight = datetime.strptime(pacific_today, "%Y-%m-%d").replace(
        tzinfo=timezone(PACIFIC_OFFSET)
    )
    utc_cutoff = pacific_midnight.astimezone(timezone.utc).isoformat()

    conn = _connect()
    cursor = conn.execute(
        "SELECT COUNT(*) FROM quota_log WHERE action = 'upload' AND timestamp >= ?",
        (utc_cutoff,),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_quota_info() -> dict:
    """Get full quota status for the dashboard."""
    used = get_units_used_today()
    remaining = max(DAILY_QUOTA - used, 0)
    uploads_today = get_uploads_today()
    max_uploads_remaining = remaining // UPLOAD_COST

    return {
        "daily_quota": DAILY_QUOTA,
        "used": used,
        "remaining": remaining,
        "uploads_today": uploads_today,
        "max_uploads_remaining": max_uploads_remaining,
        "upload_cost": UPLOAD_COST,
        "percent_used": round((used / DAILY_QUOTA) * 100, 1),
    }


def can_upload() -> bool:
    """Check if there's enough quota for another upload."""
    used = get_units_used_today()
    return (DAILY_QUOTA - used) >= UPLOAD_COST
