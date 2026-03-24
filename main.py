import argparse
import logging
import os
import shutil
from logging.handlers import RotatingFileHandler

import config


def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler: 5 MB per file, keep 3 backups
    file_handler = RotatingFileHandler(
        config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)


logger = logging.getLogger(__name__)


def run_cli_url(url: str):
    """CLI mode: process a single URL and exit."""
    from downloader import download_video, extract_post_from_url
    from processor import process_video
    from scraper import mark_processed
    from uploader import upload_video

    logger.info("--- Single video mode: %s ---", url)
    os.makedirs(config.TEMP_DIR, exist_ok=True)

    post = extract_post_from_url(url)
    if not post:
        logger.error("Could not fetch post from URL. Is it a Reddit video post?")
        return

    logger.info("Post: %s (r/%s)", post["title"], post["subreddit"])

    raw_path = download_video(post)
    if not raw_path:
        logger.error("Download failed")
        return

    processed_path = process_video(raw_path, post)
    if not processed_path:
        logger.error("Processing failed")
        return

    video_id = upload_video(processed_path, post)
    if video_id:
        logger.info("Done! https://www.youtube.com/shorts/%s", video_id)
        mark_processed(post["id"])
    else:
        logger.error("Upload failed")

    for path in [raw_path, processed_path]:
        if path and os.path.exists(path):
            os.remove(path)


def run_cli_scheduler():
    """CLI mode: run the old headless scheduler."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    from downloader import download_video
    from processor import process_video
    from scraper import fetch_video_posts, mark_processed
    from uploader import upload_video

    def pipeline():
        logger.info("--- Pipeline run starting ---")
        posts = fetch_video_posts()
        if not posts:
            logger.warning("No new video posts found")
            return
        for post in posts:
            raw_path = download_video(post)
            if not raw_path:
                mark_processed(post["id"])
                continue
            processed_path = process_video(raw_path, post)
            if not processed_path:
                mark_processed(post["id"])
                continue
            video_id = upload_video(processed_path, post)
            if video_id:
                logger.info("Uploaded post %s as %s", post["id"], video_id)
            mark_processed(post["id"])
            for path in [raw_path, processed_path]:
                if path and os.path.exists(path):
                    os.remove(path)
            return

    os.makedirs(config.TEMP_DIR, exist_ok=True)
    interval_hours = 24 / config.VIDEOS_PER_DAY
    logger.info("Scheduling pipeline every %.1f hours", interval_hours)
    pipeline()

    scheduler = BlockingScheduler()
    scheduler.add_job(pipeline, "interval", hours=interval_hours, id="pipeline_job", max_instances=1, misfire_grace_time=3600)
    try:
        logger.info("Scheduler started. Press Ctrl+C to exit.")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
    finally:
        if os.path.exists(config.TEMP_DIR):
            shutil.rmtree(config.TEMP_DIR, ignore_errors=True)


def run_web(host: str, port: int):
    """Launch the web dashboard."""
    # Allow OAuth over HTTP for localhost development
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    from app import app

    logger.info("Starting web dashboard at http://%s:%d", host, port)
    app.run(host=host, port=port, debug=False)


def main():
    parser = argparse.ArgumentParser(description="Auto Youtuber — Reddit to YouTube Shorts pipeline")
    parser.add_argument("--url", help="Process a single Reddit video URL (CLI mode)")
    parser.add_argument("--web", action="store_true", help="Launch the web dashboard (default)")
    parser.add_argument("--cli", action="store_true", help="Run the headless CLI scheduler")
    parser.add_argument("--host", default="127.0.0.1", help="Web server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Web server port (default: 5000)")
    args = parser.parse_args()

    setup_logging()

    if args.url:
        run_cli_url(args.url)
    elif args.cli:
        run_cli_scheduler()
    else:
        # Default to web mode
        run_web(args.host, args.port)


if __name__ == "__main__":
    main()
