# Auto Youtuber

Automated pipeline that scrapes top video posts from Reddit, reformats them for YouTube Shorts (9:16 vertical), and uploads them to your channel. Includes a web dashboard to manage everything from the browser.

---

## Prerequisites

Before you start, make sure you have these installed:

### Python 3.11+

Check if you have it:

    python --version

If not, download from https://www.python.org/downloads/

### FFmpeg

This is used to reformat videos. Check if you have it:

    ffmpeg -version

Windows (easiest method):
1. Open PowerShell as Administrator
2. Run: winget install FFmpeg
3. Close and reopen your terminal so it picks up the new PATH

Or manually: Download from https://ffmpeg.org/download.html, extract it, and add the bin folder to your system PATH.

### yt-dlp

This is installed automatically with pip install below, but if you run into issues downloading Reddit videos, update it:

    pip install --upgrade yt-dlp

---

## Setup (Step by Step)

### Step 1: Install Python packages

Open a terminal in the project folder and run:

    pip install -r requirements.txt

### Step 2: Set up Google Cloud (for YouTube uploads)

This is the most involved step. You need to create a Google Cloud project and get OAuth credentials so the app can upload to your YouTube channel.

#### 2a. Create a Google Cloud project

1. Go to https://console.cloud.google.com/
2. Sign in with the SAME Google account that owns your YouTube channel
3. At the top left, click the project dropdown then click New Project
4. Name it AutoYoutuber (or anything you want)
5. Click Create
6. Make sure it is selected as the active project in the dropdown

#### 2b. Enable the YouTube API

1. In the left sidebar, go to APIs and Services then Library
2. Search for YouTube Data API v3
3. Click on it then click Enable

#### 2c. Set up the OAuth consent screen

1. In the left sidebar, go to APIs and Services then OAuth consent screen
2. Select External then click Create
3. Fill in:
   - App name: AutoYoutuber
   - User support email: your email
   - Developer contact email: your email
4. Click Save and Continue
5. On the Scopes page, just click Save and Continue (skip it)
6. On the Test users page:
   - Click + Add Users
   - Enter your Gmail address (the one with the YouTube channel)
   - Click Add
7. Click Save and Continue then Back to Dashboard

#### 2d. Create OAuth credentials

1. Go to APIs and Services then Credentials
2. Click + Create Credentials then OAuth client ID
3. For Application type, select Web application
4. Name it AutoYoutuber Web
5. Under Authorized redirect URIs, click + Add URI and enter:
   http://127.0.0.1:5000/oauth/callback
6. Click Create
7. On the popup, click Download JSON
8. Rename the downloaded file to client_secrets.json
9. Move it into the project folder (same folder as main.py)

### Step 3: (Optional) Set up Reddit API for auto-scraping

This is only needed if you want the scheduler to automatically find and post videos from Reddit. If you just want to manually paste Reddit links, you can skip this.

1. Go to https://www.reddit.com/prefs/apps/
2. Scroll down and click create another app
3. Fill in:
   - Name: AutoYoutuber
   - Type: select script
   - Redirect URI: http://localhost:8080
4. Click Create app
5. Note the client ID (the short string right below the app name) and the secret

You will enter these in the web dashboard Settings page later.

Having trouble creating a Reddit app? Reddit now requires accepting their developer terms first. Try https://old.reddit.com/prefs/apps/ (the old UI). If it still blocks you, you can skip this step entirely and just use the manual URL submit feature.

### Step 4: Launch the app

    python main.py

This starts the web dashboard. Open your browser to:

    http://127.0.0.1:5000

### Step 5: Connect your YouTube account

1. On the dashboard, click Connect YouTube
2. A Google sign-in page will open
3. You will see a warning: This app is not verified -- this is normal for personal projects
   - Click Advanced
   - Click Go to AutoYoutuber (unsafe)
4. Grant the YouTube upload permission
5. You will be redirected back to the dashboard with a green Connected badge

That is it! The token is saved so you will not need to do this again (unless it expires).

### Step 6: Test it

1. Find a video post on Reddit and copy its URL (e.g. from the share button)
2. On the dashboard, paste the URL in the Quick Submit box and click Process
3. Watch the status update: Downloading then Processing then Uploading
4. Check the Logs page for detailed output
5. Once done, the Recent Activity table shows a link to the uploaded Short

---

## Using the Web Dashboard

### Dashboard (/)
- Pipeline status (idle, downloading, processing, uploading)
- Scheduler controls (start/stop, run now)
- YouTube connection status
- Quick submit form
- Recent activity table with links to uploaded videos

### Submit (/submit)
- Paste any Reddit video URL to process and upload immediately
- Supports full Reddit URLs, share links, and redd.it short links
- No Reddit API credentials needed for this -- it uses yt-dlp to extract the video directly

### Settings (/settings)
- Reddit API: Client ID, Secret, User Agent (only needed for auto-scraping)
- Scraping: Which subreddits to scrape, time filter (day/week/etc), post limit
- YouTube: Client secrets file path, token file path
- Scheduling: Videos per day (determines how often the scheduler runs)
- Video: Max duration in seconds (59 for Shorts compliance)
- Paths: Temp directory, database file, log file

All settings are saved to a local SQLite database and persist across restarts.

### Logs (/logs)
- Live-updating log viewer (polls every 2 seconds)
- Auto-scroll toggle
- Clear button (clears the in-memory buffer, not the log file)

---

## Running Modes

    # Web dashboard (default)
    python main.py

    # Web dashboard on a custom port
    python main.py --port 8080

    # Process a single URL from the command line (no web UI)
    python main.py --url "https://www.reddit.com/r/funny/comments/abc123/some_post/"

    # Headless scheduler mode (no web UI, runs in terminal)
    python main.py --cli

---

## How the Pipeline Works

1. Extract/Scrape: Gets video metadata from a Reddit URL (via yt-dlp) or scrapes subreddits (via PRAW)
2. Deduplicate: Checks against a local SQLite database to skip already-processed posts
3. Download: Uses yt-dlp to download and merge Reddit split video+audio streams into an MP4
4. Process: Uses FFmpeg to reformat to 1080x1920 (9:16 vertical), add a blurred background if the source is landscape, burn the Reddit post title as a subtitle overlay at the top, trim to 59 seconds max, and encode as H.264 MP4
5. Upload: Uses YouTube Data API v3 to upload with title, description, tags, and #Shorts
6. Schedule: APScheduler spaces uploads evenly across 24 hours (e.g. 3 videos/day = every 8 hours)

---

## Troubleshooting

### OAuth error or client_secrets.json not found
- Make sure client_secrets.json is in the project root folder (same folder as main.py)
- Make sure you selected Web application (not Desktop) when creating the OAuth client
- Make sure http://127.0.0.1:5000/oauth/callback is listed as an authorized redirect URI in Google Cloud Console

### This app is not verified warning during YouTube sign-in
This is normal. Since the app is in Testing mode and only you are using it, click Advanced then Go to AutoYoutuber (unsafe) to proceed.

### YouTube upload fails
- Check that your YouTube channel is in good standing and not restricted
- The YouTube Data API has a daily quota (10,000 units). Each upload costs 1,600 units, so you can do about 6 uploads per day on the free tier.
- Check the Logs page for the specific error message

### FFmpeg errors during processing
- Make sure FFmpeg is installed: ffmpeg -version
- Some Reddit videos have unusual formats. Check the logs for the specific FFmpeg error.

### Video does not appear as a Short
- Must be 60 seconds or less (the app trims to 59s by default)
- Must be vertical (9:16) -- the app handles this
- #Shorts must be in the title or description -- the app adds it to the description

### Reddit download fails
- Reddit sometimes rate-limits downloads. Try again in a few minutes.
- Make sure yt-dlp is up to date: pip install --upgrade yt-dlp
- Some Reddit posts link to external video hosts -- only Reddit-hosted videos (v.redd.it) are supported

---

## Project Structure

    Auto_youtuber/
      main.py              Entry point (--web, --url, --cli modes)
      app.py               Flask web dashboard + routes
      config.py            Settings loaded from SQLite (auto-migrates .env)
      settings_db.py       SQLite settings storage
      pipeline_runner.py   Thread-safe pipeline runner with status tracking
      scraper.py           Reddit scraping via PRAW
      downloader.py        Video downloading via yt-dlp
      processor.py         FFmpeg video reformatting
      uploader.py          YouTube upload via Google API
      templates/           HTML templates (Bootstrap 5 dark theme)
      static/              Static assets
      requirements.txt     Python dependencies
      .env.example         Example environment variables
      client_secrets.json  YouTube OAuth credentials (you create this)
