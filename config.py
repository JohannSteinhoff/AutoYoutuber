from settings_db import get_setting, migrate_from_dotenv

# Seed database from .env on first import
migrate_from_dotenv()

# Module-level settings — all other modules read these as config.ATTRIBUTE
REDDIT_CLIENT_ID = ""
REDDIT_CLIENT_SECRET = ""
REDDIT_USER_AGENT = ""
SUBREDDITS = []
TIME_FILTER = ""
POST_LIMIT = 20
YOUTUBE_CLIENT_SECRETS_FILE = ""
YOUTUBE_TOKEN_FILE = ""
VIDEOS_PER_DAY = 3
TEMP_DIR = ""
DB_PATH = ""
LOG_FILE = ""
MAX_DURATION_SECONDS = 59
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920


def reload():
    """Re-read all settings from the database into module-level variables."""
    global REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
    global SUBREDDITS, TIME_FILTER, POST_LIMIT
    global YOUTUBE_CLIENT_SECRETS_FILE, YOUTUBE_TOKEN_FILE
    global VIDEOS_PER_DAY, TEMP_DIR, DB_PATH, LOG_FILE, MAX_DURATION_SECONDS

    REDDIT_CLIENT_ID = get_setting("REDDIT_CLIENT_ID")
    REDDIT_CLIENT_SECRET = get_setting("REDDIT_CLIENT_SECRET")
    REDDIT_USER_AGENT = get_setting("REDDIT_USER_AGENT")
    SUBREDDITS = [s.strip() for s in get_setting("SUBREDDITS").split(",") if s.strip()]
    TIME_FILTER = get_setting("TIME_FILTER")
    POST_LIMIT = int(get_setting("POST_LIMIT") or "20")
    YOUTUBE_CLIENT_SECRETS_FILE = get_setting("YOUTUBE_CLIENT_SECRETS_FILE")
    YOUTUBE_TOKEN_FILE = get_setting("YOUTUBE_TOKEN_FILE")
    VIDEOS_PER_DAY = int(get_setting("VIDEOS_PER_DAY") or "3")
    TEMP_DIR = get_setting("TEMP_DIR") or "temp"
    DB_PATH = get_setting("DB_PATH") or "processed_posts.db"
    LOG_FILE = get_setting("LOG_FILE") or "auto_youtuber.log"
    MAX_DURATION_SECONDS = int(get_setting("MAX_DURATION_SECONDS") or "59")


# Load on first import
reload()
