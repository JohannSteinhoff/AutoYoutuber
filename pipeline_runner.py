import logging
import os
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

import config
from downloader import download_video, extract_post_from_url
from processor import process_video
from scraper import fetch_video_posts, mark_processed
from uploader import upload_video

logger = logging.getLogger(__name__)


class LogBuffer(logging.Handler):
    """Ring-buffer logging handler for the web UI."""

    def __init__(self, capacity=500):
        super().__init__()
        self.buffer = deque(maxlen=capacity)

    def emit(self, record):
        self.buffer.append(self.format(record))

    def get_lines(self) -> list[str]:
        return list(self.buffer)

    def clear(self):
        self.buffer.clear()


@dataclass
class RunRecord:
    timestamp: str
    post_title: str
    post_id: str
    subreddit: str
    success: bool
    video_id: str | None = None
    error: str | None = None


@dataclass
class PipelineStatus:
    state: str = "idle"  # idle, scraping, downloading, processing, uploading, error
    current_post: dict | None = None
    message: str = ""
    last_run: str | None = None
    last_error: str | None = None
    history: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "current_post": self.current_post,
            "message": self.message,
            "last_run": self.last_run,
            "last_error": self.last_error,
            "history": [
                {
                    "timestamp": r.timestamp,
                    "post_title": r.post_title,
                    "post_id": r.post_id,
                    "subreddit": r.subreddit,
                    "success": r.success,
                    "video_id": r.video_id,
                    "error": r.error,
                }
                for r in self.history[-20:]  # keep last 20
            ],
        }


class PipelineRunner:
    def __init__(self):
        self.status = PipelineStatus()
        self.log_buffer = LogBuffer(capacity=500)
        self._thread: threading.Thread | None = None

        # Attach log buffer to root logger
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.log_buffer.setFormatter(formatter)
        logging.getLogger().addHandler(self.log_buffer)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def run_single(self, url: str) -> bool:
        """Start processing a single URL in a background thread. Returns False if already running."""
        if self.is_running():
            return False
        self._thread = threading.Thread(target=self._execute_single, args=(url,), daemon=True)
        self._thread.start()
        return True

    def run_pipeline(self):
        """Run the automated scrape pipeline. Called by the scheduler or manually."""
        if self.is_running():
            logger.warning("Pipeline already running, skipping")
            return
        self._thread = threading.Thread(target=self._execute_pipeline, daemon=True)
        self._thread.start()

    def _execute_single(self, url: str):
        """Process a single Reddit URL: extract -> download -> process -> upload."""
        self.status.state = "downloading"
        self.status.message = "Extracting video info..."
        self.status.last_error = None

        try:
            os.makedirs(config.TEMP_DIR, exist_ok=True)

            post = extract_post_from_url(url)
            if not post:
                self.status.state = "error"
                self.status.message = "Could not extract video from URL"
                self.status.last_error = "Extraction failed — is this a Reddit video post?"
                return

            self.status.current_post = {"title": post["title"], "subreddit": post["subreddit"], "id": post["id"]}
            self._download_process_upload(post)

        except Exception as e:
            logger.exception("Single video pipeline failed")
            self.status.state = "error"
            self.status.message = str(e)
            self.status.last_error = str(e)
        finally:
            if self.status.state != "error":
                self.status.state = "idle"
                self.status.message = ""
            self.status.current_post = None
            self.status.last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _execute_pipeline(self):
        """Run the full scrape -> download -> process -> upload pipeline."""
        self.status.state = "scraping"
        self.status.message = "Fetching video posts from Reddit..."
        self.status.last_error = None

        try:
            os.makedirs(config.TEMP_DIR, exist_ok=True)
            posts = fetch_video_posts()

            if not posts:
                logger.warning("No new video posts found")
                self.status.message = "No new posts found"
                self.status.state = "idle"
                return

            for post in posts:
                self.status.current_post = {"title": post["title"], "subreddit": post["subreddit"], "id": post["id"]}
                self._download_process_upload(post)
                # Only process one per scheduled run
                return

        except Exception as e:
            logger.exception("Pipeline failed")
            self.status.state = "error"
            self.status.message = str(e)
            self.status.last_error = str(e)
        finally:
            if self.status.state != "error":
                self.status.state = "idle"
                self.status.message = ""
            self.status.current_post = None
            self.status.last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _download_process_upload(self, post: dict):
        """Shared download -> process -> upload logic."""
        raw_path = None
        processed_path = None

        try:
            # Download
            self.status.state = "downloading"
            self.status.message = f"Downloading: {post['title'][:50]}"
            raw_path = download_video(post)
            if not raw_path:
                self._record(post, success=False, error="Download failed")
                mark_processed(post["id"])
                return

            # Process
            self.status.state = "processing"
            self.status.message = f"Processing: {post['title'][:50]}"
            processed_path = process_video(raw_path, post)
            if not processed_path:
                self._record(post, success=False, error="Processing failed")
                mark_processed(post["id"])
                return

            # Upload
            self.status.state = "uploading"
            self.status.message = f"Uploading: {post['title'][:50]}"
            video_id = upload_video(processed_path, post)
            if video_id:
                self._record(post, success=True, video_id=video_id)
                logger.info("Done! https://www.youtube.com/shorts/%s", video_id)
            else:
                self._record(post, success=False, error="Upload failed")

            mark_processed(post["id"])

        finally:
            # Clean up temp files
            for path in [raw_path, processed_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    def _record(self, post: dict, success: bool, video_id: str | None = None, error: str | None = None):
        record = RunRecord(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            post_title=post["title"],
            post_id=post["id"],
            subreddit=post["subreddit"],
            success=success,
            video_id=video_id,
            error=error,
        )
        self.status.history.append(record)
        if error:
            self.status.last_error = error
            logger.warning("Failed: %s — %s", post["title"][:50], error)
        else:
            logger.info("Success: %s -> %s", post["title"][:50], video_id)


# Module-level singleton
runner = PipelineRunner()
