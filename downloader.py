import logging
import os

import yt_dlp

import config

logger = logging.getLogger(__name__)


def ensure_temp_dir():
    os.makedirs(config.TEMP_DIR, exist_ok=True)


def extract_post_from_url(url: str) -> dict | None:
    """Extract video metadata from a Reddit URL using yt-dlp (no Reddit API needed)."""
    ensure_temp_dir()
    try:
        ydl_opts = {"quiet": True, "no_warnings": True, "socket_timeout": 30}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            logger.error("yt-dlp returned no info for URL: %s", url)
            return None

        post_id = info.get("id", "unknown")
        title = info.get("title") or info.get("fulltitle") or "Untitled"
        # Try to extract subreddit from the URL or metadata
        subreddit = "unknown"
        webpage_url = info.get("webpage_url", url)
        if "/r/" in webpage_url:
            parts = webpage_url.split("/r/")
            if len(parts) > 1:
                subreddit = parts[1].split("/")[0]

        return {
            "id": post_id,
            "title": title,
            "url": webpage_url,
            "video_url": webpage_url,
            "duration": info.get("duration", 0),
            "subreddit": subreddit,
            "score": 0,
            "author": info.get("uploader") or "[unknown]",
        }
    except Exception:
        logger.exception("Failed to extract info from URL: %s", url)
        return None


def download_video(post: dict) -> str | None:
    """Download a Reddit video using yt-dlp. Returns the path to the downloaded file, or None on failure."""
    ensure_temp_dir()
    output_path = os.path.join(config.TEMP_DIR, f"{post['id']}.mp4")

    if os.path.exists(output_path):
        logger.info("Video already downloaded: %s", output_path)
        return output_path

    # Use the Reddit post URL so yt-dlp can find both video and audio streams
    download_url = post["url"]

    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": output_path,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
    }

    try:
        logger.info("Downloading video for post %s: %s", post["id"], post["title"][:60])
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([download_url])

        if os.path.exists(output_path):
            logger.info("Downloaded successfully: %s", output_path)
            return output_path

        logger.error("Download finished but file not found: %s", output_path)
        return None
    except Exception:
        logger.exception("Failed to download video for post %s", post["id"])
        # Clean up partial downloads
        if os.path.exists(output_path):
            os.remove(output_path)
        part_file = output_path + ".part"
        if os.path.exists(part_file):
            os.remove(part_file)
        return None
