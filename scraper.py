import logging
import sqlite3
import time

import requests

import config

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": config.REDDIT_USER_AGENT or "AutoYoutuber/1.0"}


def init_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS processed_posts "
        "(post_id TEXT PRIMARY KEY, processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()


def is_processed(post_id: str) -> bool:
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.execute(
        "SELECT 1 FROM processed_posts WHERE post_id = ?", (post_id,)
    )
    result = cursor.fetchone() is not None
    conn.close()
    return result


def mark_processed(post_id: str):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO processed_posts (post_id) VALUES (?)", (post_id,)
    )
    conn.commit()
    conn.close()


def fetch_video_posts(count: int = 6) -> list[dict]:
    """Fetch the top `count` most viral video posts from yesterday across all configured subreddits.

    Filters for Reddit-hosted videos that are <= MAX_DURATION_SECONDS (Shorts-eligible).
    Sorted by score descending, deduped against already-processed posts.
    """
    init_db()
    video_posts = []
    max_dur = config.MAX_DURATION_SECONDS

    # Top of all time for maximum viral potential
    time_filter = "all"
    limit = min(config.POST_LIMIT, 100)

    for subreddit_name in config.SUBREDDITS:
        url = f"https://www.reddit.com/r/{subreddit_name}/top.json?t={time_filter}&limit={limit}"
        logger.info("Scraping r/%s (top/%s, limit=%d)", subreddit_name, time_filter, limit)

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 429:
                logger.warning("Rate limited on r/%s, waiting 10s...", subreddit_name)
                time.sleep(10)
                resp = requests.get(url, headers=HEADERS, timeout=15)

            if resp.status_code != 200:
                logger.error("Failed to fetch r/%s: HTTP %d", subreddit_name, resp.status_code)
                continue

            data = resp.json()
            posts = data.get("data", {}).get("children", [])

            for item in posts:
                post = item.get("data", {})
                post_id = post.get("id", "")

                if is_processed(post_id):
                    continue

                # Check for Reddit-hosted video
                is_video = post.get("is_video", False)
                media = post.get("media") or {}
                reddit_video = media.get("reddit_video", {})
                video_url = reddit_video.get("fallback_url", "")
                duration = reddit_video.get("duration", 0)

                # Also check for v.redd.it links
                post_url = post.get("url", "")
                if not is_video and "v.redd.it" not in post_url:
                    continue
                if not video_url and "v.redd.it" not in post_url:
                    continue

                # Filter: only Shorts-eligible duration (skip long videos)
                # duration=0 means unknown, we'll let those through and trim later
                if duration > max_dur and duration > 0:
                    logger.debug("Skipping %s: too long (%ds > %ds)", post_id, duration, max_dur)
                    continue

                permalink = post.get("permalink", "")
                title = post.get("title", "Untitled")
                score = post.get("score", 0)
                author = post.get("author", "[deleted]")

                video_posts.append({
                    "id": post_id,
                    "title": title,
                    "url": f"https://www.reddit.com{permalink}",
                    "video_url": video_url or post_url,
                    "duration": duration,
                    "subreddit": subreddit_name,
                    "score": score,
                    "author": author,
                })

            time.sleep(2)

        except Exception:
            logger.exception("Error scraping r/%s", subreddit_name)

    # Sort by score descending — most viral first
    video_posts.sort(key=lambda p: p["score"], reverse=True)

    # Take only the top `count`
    top_posts = video_posts[:count]

    logger.info(
        "Found %d video posts total, selected top %d (scores: %s)",
        len(video_posts),
        len(top_posts),
        ", ".join(str(p["score"]) for p in top_posts),
    )

    for p in top_posts:
        logger.info(
            "  #%d r/%s — %s (score: %d, %ds)",
            top_posts.index(p) + 1, p["subreddit"], p["title"][:50], p["score"], p["duration"],
        )

    return top_posts
