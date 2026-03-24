import logging
import sqlite3

import praw

import config

logger = logging.getLogger(__name__)


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


def get_reddit_instance() -> praw.Reddit:
    return praw.Reddit(
        client_id=config.REDDIT_CLIENT_ID,
        client_secret=config.REDDIT_CLIENT_SECRET,
        user_agent=config.REDDIT_USER_AGENT,
    )


def fetch_post_by_url(url: str) -> dict | None:
    """Fetch a single Reddit post by URL and return its metadata."""
    reddit = get_reddit_instance()
    try:
        submission = reddit.submission(url=url)
        # Force-load the submission data
        _ = submission.title

        video_url = None
        duration = 0

        if submission.is_video and hasattr(submission, "media") and submission.media:
            reddit_video = submission.media.get("reddit_video", {})
            video_url = reddit_video.get("fallback_url")
            duration = reddit_video.get("duration", 0)
        elif hasattr(submission, "url") and "v.redd.it" in submission.url:
            video_url = submission.url

        if not video_url:
            logger.error("Post does not contain a Reddit-hosted video: %s", url)
            return None

        subreddit_name = str(submission.subreddit)
        post = {
            "id": submission.id,
            "title": submission.title,
            "url": f"https://www.reddit.com{submission.permalink}",
            "video_url": video_url,
            "duration": duration,
            "subreddit": subreddit_name,
            "score": submission.score,
            "author": str(submission.author) if submission.author else "[deleted]",
        }
        logger.info("Fetched post: %s (r/%s, score: %d)", post["title"][:60], subreddit_name, post["score"])
        return post

    except Exception:
        logger.exception("Failed to fetch post from URL: %s", url)
        return None


def fetch_video_posts() -> list[dict]:
    """Fetch top video posts from configured subreddits, skipping already-processed ones."""
    init_db()
    reddit = get_reddit_instance()
    video_posts = []

    for subreddit_name in config.SUBREDDITS:
        logger.info("Scraping r/%s (top/%s, limit=%d)", subreddit_name, config.TIME_FILTER, config.POST_LIMIT)
        try:
            subreddit = reddit.subreddit(subreddit_name)
            for post in subreddit.top(time_filter=config.TIME_FILTER, limit=config.POST_LIMIT):
                if is_processed(post.id):
                    logger.debug("Skipping already-processed post %s", post.id)
                    continue

                # Check for Reddit-hosted video
                if post.is_video and hasattr(post, "media") and post.media:
                    reddit_video = post.media.get("reddit_video", {})
                    video_url = reddit_video.get("fallback_url")
                    if not video_url:
                        continue
                    duration = reddit_video.get("duration", 0)
                    video_posts.append({
                        "id": post.id,
                        "title": post.title,
                        "url": f"https://www.reddit.com{post.permalink}",
                        "video_url": video_url,
                        "duration": duration,
                        "subreddit": subreddit_name,
                        "score": post.score,
                        "author": str(post.author) if post.author else "[deleted]",
                    })
                    logger.info("Found video: %s (score: %d, duration: %ds)", post.title[:60], post.score, duration)

                # Check for v.redd.it links in non is_video posts
                elif hasattr(post, "url") and "v.redd.it" in post.url:
                    video_posts.append({
                        "id": post.id,
                        "title": post.title,
                        "url": f"https://www.reddit.com{post.permalink}",
                        "video_url": post.url,
                        "duration": 0,  # unknown
                        "subreddit": subreddit_name,
                        "score": post.score,
                        "author": str(post.author) if post.author else "[deleted]",
                    })
                    logger.info("Found v.redd.it link: %s (score: %d)", post.title[:60], post.score)

        except Exception:
            logger.exception("Error scraping r/%s", subreddit_name)

    # Sort by score descending so we process the best content first
    video_posts.sort(key=lambda p: p["score"], reverse=True)
    logger.info("Total video posts found: %d", len(video_posts))
    return video_posts
