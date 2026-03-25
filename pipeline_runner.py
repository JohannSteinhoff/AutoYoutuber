import logging
import os
import threading
import uuid
from collections import deque
from datetime import datetime

import config
from downloader import download_video, extract_post_from_url
from history import save_upload
from processor import process_video
from queue_db import load_queue as db_load_queue, save_queue as db_save_queue
from quota import can_upload, get_quota_info
from scraper import fetch_video_posts, mark_processed
from uploader import upload_video

logger = logging.getLogger(__name__)


class LogBuffer(logging.Handler):
    def __init__(self, capacity=500):
        super().__init__()
        self.buffer = deque(maxlen=capacity)

    def emit(self, record):
        self.buffer.append(self.format(record))

    def get_lines(self) -> list[str]:
        return list(self.buffer)

    def clear(self):
        self.buffer.clear()


class QueueItem:
    """A single video in the queue."""

    def __init__(self, post: dict):
        self.uid = uuid.uuid4().hex[:8]
        self.post = post
        self.status = "queued"  # queued, downloading, processing, uploading, done, failed, skipped
        self.progress = ""  # human-readable progress message
        self.youtube_id: str | None = None
        self.error: str | None = None
        self.added_at = datetime.now().strftime("%H:%M:%S")

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "title": self.post.get("title", ""),
            "url": self.post.get("url", ""),
            "subreddit": self.post.get("subreddit", ""),
            "score": self.post.get("score", 0),
            "duration": self.post.get("duration", 0),
            "author": self.post.get("author", ""),
            "status": self.status,
            "progress": self.progress,
            "youtube_id": self.youtube_id,
            "error": self.error,
            "added_at": self.added_at,
        }

    def to_persist(self) -> dict:
        """Dict for SQLite persistence."""
        return {
            "uid": self.uid,
            "post": self.post,
            "status": self.status,
            "progress": self.progress,
            "youtube_id": self.youtube_id,
            "error": self.error,
            "added_at": self.added_at,
        }

    @classmethod
    def from_persist(cls, data: dict) -> "QueueItem":
        """Restore a QueueItem from persisted data."""
        item = cls.__new__(cls)
        item.uid = data["uid"]
        item.post = data["post"]
        item.status = data["status"]
        item.progress = data.get("progress", "")
        item.youtube_id = data.get("youtube_id")
        item.error = data.get("error")
        item.added_at = data.get("added_at", "")
        return item


class PipelineRunner:
    def __init__(self):
        self.queue: list[QueueItem] = []
        self.armed = False
        self.state = "idle"  # idle, scraping, running
        self.message = ""
        self.last_run: str | None = None
        self.log_buffer = LogBuffer(capacity=500)
        self._thread: threading.Thread | None = None

        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.log_buffer.setFormatter(formatter)
        logging.getLogger().addHandler(self.log_buffer)

        # Restore persisted queue from SQLite
        self._load_persisted_queue()

    def _load_persisted_queue(self):
        try:
            rows = db_load_queue()
            for row in rows:
                self.queue.append(QueueItem.from_persist(row))
            if self.queue:
                logger.info("Restored %d items from persisted queue", len(self.queue))
        except Exception:
            logger.exception("Failed to load persisted queue")

    def _persist_queue(self):
        try:
            db_save_queue([item.to_persist() for item in self.queue])
        except Exception:
            logger.exception("Failed to persist queue")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Queue management ───────────────────────────────────────────

    def load_queue(self, count: int = 6) -> bool:
        """Scrape Reddit and fill the queue with top viral videos. Returns False if already busy."""
        if self.is_running():
            return False
        self._thread = threading.Thread(target=self._scrape_to_queue, args=(count,), daemon=True)
        self._thread.start()
        return True

    def add_single_to_queue(self, url: str) -> bool:
        """Extract a single URL and add it to the queue. Returns False if busy."""
        if self.is_running():
            return False
        self._thread = threading.Thread(target=self._extract_to_queue, args=(url,), daemon=True)
        self._thread.start()
        return True

    def clear_queue(self):
        """Remove all items from the queue."""
        self.queue.clear()
        self.armed = False
        self._persist_queue()

    def remove_from_queue(self, uid: str):
        """Remove a specific item by uid if it's still queued."""
        self.queue = [item for item in self.queue if not (item.uid == uid and item.status == "queued")]
        self._persist_queue()

    def arm(self):
        """Arm the pipeline so it starts processing the queue."""
        self.armed = True

    def disarm(self):
        """Disarm to prevent processing."""
        self.armed = False

    def reorder_queue(self, uid_order: list[str]):
        """Reorder queued items according to the given UID list."""
        uid_map = {item.uid: item for item in self.queue}
        reordered = []
        seen = set()

        # First, place items in the requested order
        for uid in uid_order:
            if uid in uid_map and uid not in seen:
                reordered.append(uid_map[uid])
                seen.add(uid)

        # Then append any items not in the order list (done/failed/active items)
        for item in self.queue:
            if item.uid not in seen:
                reordered.append(item)

        self.queue = reordered
        self._persist_queue()

    def retry_item(self, uid: str) -> bool:
        """Re-queue a failed item so it can be processed again."""
        for item in self.queue:
            if item.uid == uid and item.status in ("failed", "skipped"):
                item.status = "queued"
                item.error = None
                item.progress = ""
                item.youtube_id = None
                self._persist_queue()
                return True
        return False

    def start_processing(self) -> bool:
        """Begin processing the armed queue. Returns False if already running or not armed."""
        if self.is_running():
            return False
        if not self.armed:
            return False
        queued = [item for item in self.queue if item.status == "queued"]
        if not queued:
            return False
        self._thread = threading.Thread(target=self._process_queue, daemon=True)
        self._thread.start()
        return True

    # ── Status for API ─────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "state": self.state,
            "message": self.message,
            "armed": self.armed,
            "last_run": self.last_run,
            "queue": [item.to_dict() for item in self.queue],
            "queue_summary": {
                "total": len(self.queue),
                "queued": sum(1 for i in self.queue if i.status == "queued"),
                "done": sum(1 for i in self.queue if i.status == "done"),
                "failed": sum(1 for i in self.queue if i.status == "failed"),
                "active": sum(1 for i in self.queue if i.status in ("downloading", "processing", "uploading")),
            },
        }

    # ── Internal: scrape to queue ──────────────────────────────────

    def _scrape_to_queue(self, count: int = 6):
        self.state = "scraping"
        self.message = f"Finding top {count} viral videos..."
        try:
            os.makedirs(config.TEMP_DIR, exist_ok=True)

            posts = fetch_video_posts(count=count)

            if not posts:
                logger.warning("No new video posts found")
                self.message = "No viral videos found"
                self.state = "idle"
                return

            # Clear old queued items, keep done/failed for display
            self.queue = [item for item in self.queue if item.status not in ("queued",)]

            for post in posts:
                self.queue.append(QueueItem(post))

            logger.info("Queued %d videos for review", len(posts))
            self.message = f"{len(posts)} videos queued — review and arm to start"
            self.armed = False
            self._persist_queue()

        except Exception as e:
            logger.exception("Scraping failed")
            self.message = f"Scrape error: {e}"
        finally:
            self.state = "idle"

    def _extract_to_queue(self, url: str):
        self.state = "scraping"
        self.message = "Extracting video info..."
        try:
            os.makedirs(config.TEMP_DIR, exist_ok=True)
            post = extract_post_from_url(url)
            if not post:
                self.message = "Could not extract video from URL"
                logger.error("Failed to extract: %s", url)
                self.state = "idle"
                return

            self.queue.append(QueueItem(post))
            logger.info("Added to queue: %s", post["title"][:60])
            self.message = "Video added to queue"
            self._persist_queue()

        except Exception as e:
            logger.exception("Extraction failed")
            self.message = f"Error: {e}"
        finally:
            self.state = "idle"

    # ── Internal: process queue ────────────────────────────────────

    def _process_queue(self):
        self.state = "running"
        self.message = "Processing queue..."
        queued_items = [item for item in self.queue if item.status == "queued"]

        try:
            os.makedirs(config.TEMP_DIR, exist_ok=True)

            for i, item in enumerate(queued_items):
                if not self.armed:
                    logger.info("Pipeline disarmed, stopping after %d videos", i)
                    # Mark remaining as skipped
                    for remaining in queued_items[i:]:
                        if remaining.status == "queued":
                            remaining.status = "skipped"
                            remaining.progress = "Disarmed"
                    break

                if not can_upload():
                    logger.warning("Quota exhausted, stopping after %d uploads", i)
                    item.status = "failed"
                    item.error = "Quota exhausted"
                    item.progress = "No API quota remaining"
                    for remaining in queued_items[i + 1:]:
                        if remaining.status == "queued":
                            remaining.status = "skipped"
                            remaining.progress = "Quota exhausted"
                    break

                self.message = f"Video {i + 1}/{len(queued_items)}"
                self._process_item(item)
                self._persist_queue()

        except Exception as e:
            logger.exception("Queue processing failed")
            self.message = f"Error: {e}"
        finally:
            self.state = "idle"
            self.armed = False
            self.message = "Queue complete"
            self.last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._persist_queue()

    def _process_item(self, item: QueueItem):
        post = item.post
        raw_path = None
        processed_path = None

        try:
            # Download
            item.status = "downloading"
            item.progress = "Downloading video..."
            raw_path = download_video(post)
            if not raw_path:
                item.status = "failed"
                item.error = "Download failed"
                item.progress = "Download failed"
                save_upload(post, None, False, "Download failed")
                mark_processed(post["id"])
                return

            # Process
            item.status = "processing"
            item.progress = "Reformatting to 9:16..."
            processed_path = process_video(raw_path, post)
            if not processed_path:
                item.status = "failed"
                item.error = "FFmpeg processing failed"
                item.progress = "Processing failed"
                save_upload(post, None, False, "Processing failed")
                mark_processed(post["id"])
                return

            # Upload
            item.status = "uploading"
            item.progress = "Uploading to YouTube..."
            video_id = upload_video(processed_path, post)
            if video_id:
                item.status = "done"
                item.youtube_id = video_id
                item.progress = f"youtube.com/shorts/{video_id}"
                save_upload(post, video_id, True)
                logger.info("Uploaded: %s -> %s", post["title"][:50], video_id)
            else:
                item.status = "failed"
                item.error = "Upload failed"
                item.progress = "Upload to YouTube failed"
                save_upload(post, None, False, "Upload failed")

            mark_processed(post["id"])

        except Exception as e:
            logger.exception("Failed processing %s", post.get("title", "")[:50])
            item.status = "failed"
            item.error = str(e)
            item.progress = f"Error: {e}"
            save_upload(post, None, False, str(e))
        finally:
            for path in [raw_path, processed_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass


# Module-level singleton
runner = PipelineRunner()
