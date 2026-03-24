import logging
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class NeedsOAuthError(Exception):
    """Raised when YouTube OAuth is required but no valid token exists."""
    pass


def get_authenticated_service():
    """Authenticate with YouTube Data API v3 using saved OAuth2 token."""
    creds = None

    if os.path.exists(config.YOUTUBE_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(config.YOUTUBE_TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired YouTube credentials")
            creds.refresh(Request())
            with open(config.YOUTUBE_TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            logger.info("YouTube credentials refreshed")
        else:
            raise NeedsOAuthError(
                "YouTube OAuth required. Please connect your YouTube account via the web dashboard."
            )

    return build("youtube", "v3", credentials=creds)


def upload_video(video_path: str, post: dict) -> str | None:
    """Upload a processed video to YouTube as a Short. Returns the video ID or None."""
    try:
        youtube = get_authenticated_service()

        title = post["title"][:100]  # YouTube title limit is 100 chars

        description = (
            f"{post['title']}\n\n"
            f"Originally from r/{post['subreddit']}\n"
            f"#Shorts"
        )

        tags = [
            "shorts", "reddit", post["subreddit"],
            "funny", "viral", "trending",
        ]

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "24",  # Entertainment
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024 * 5,  # 5 MB chunks
        )

        logger.info("Uploading video: %s", title[:60])
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info("Upload progress: %d%%", int(status.progress() * 100))

        video_id = response["id"]
        logger.info(
            "Upload complete: https://www.youtube.com/shorts/%s", video_id
        )
        return video_id

    except Exception:
        logger.exception("Failed to upload video for post %s", post["id"])
        return None
