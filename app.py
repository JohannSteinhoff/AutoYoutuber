import csv
import io
import json
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from flask import (
    Flask, Response, flash, jsonify, redirect, render_template,
    request, send_file, session, url_for,
)

import config
from history import get_history, get_history_count
from pipeline_runner import runner
from quota import get_quota_info
from settings_db import DEFAULTS, get_all_settings, set_many_settings

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)

scheduler = BackgroundScheduler()
_scheduler_running = False


# ── Scheduler helpers ──────────────────────────────────────────────

def start_scheduler():
    global _scheduler_running
    if _scheduler_running:
        return

    def scheduled_run():
        runner.load_queue()

    scheduler.add_job(
        scheduled_run,
        "interval",
        hours=24,
        id="pipeline_job",
        max_instances=1,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    _scheduler_running = True
    logger.info("Scheduler started: loads queue every 24 hours")


def stop_scheduler():
    global _scheduler_running
    if not _scheduler_running:
        return
    try:
        scheduler.remove_job("pipeline_job")
    except Exception:
        pass
    _scheduler_running = False
    logger.info("Scheduler stopped")


def get_next_run_time() -> str | None:
    if not _scheduler_running:
        return None
    job = scheduler.get_job("pipeline_job")
    if job and job.next_run_time:
        return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
    return None


def is_youtube_connected() -> bool:
    token_file = config.YOUTUBE_TOKEN_FILE
    return os.path.exists(token_file) and os.path.getsize(token_file) > 0


# ── Page Routes ───────────────────────────────────────────────────

@app.route("/")
def dashboard():
    return render_template(
        "dashboard.html",
        status=runner.get_status(),
        scheduler_running=_scheduler_running,
        pipeline_running=runner.is_running(),
        videos_per_day=config.VIDEOS_PER_DAY,
        next_run=get_next_run_time(),
        youtube_connected=is_youtube_connected(),
        quota=get_quota_info(),
        history=get_history(limit=20),
        history_total=get_history_count(),
    )


@app.route("/settings", methods=["GET"])
def settings_page():
    return render_template("settings.html", settings=get_all_settings())


@app.route("/settings", methods=["POST"])
def settings_save():
    fields = [
        "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT",
        "SUBREDDITS", "TIME_FILTER", "POST_LIMIT",
        "YOUTUBE_CLIENT_SECRETS_FILE", "YOUTUBE_TOKEN_FILE",
        "VIDEOS_PER_DAY", "MAX_DURATION_SECONDS",
        "TEMP_DIR", "DB_PATH", "LOG_FILE",
    ]
    updates = {}
    for field in fields:
        value = request.form.get(field, "").strip()
        if value:
            updates[field] = value

    set_many_settings(updates)
    config.reload()

    # If this is an AJAX request, return JSON
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "message": "Settings saved!"})

    flash("Settings saved!", "success")
    return redirect(url_for("settings_page"))


@app.route("/submit", methods=["GET"])
def submit():
    return render_template("submit.html", pipeline_running=runner.is_running())


@app.route("/submit", methods=["POST"])
def submit_url():
    url = request.form.get("url", "").strip()
    if not url:
        flash("Please enter a URL.", "error")
        return redirect(url_for("submit"))

    if runner.is_running():
        flash("Pipeline is busy. Please wait.", "error")
        return redirect(url_for("dashboard"))

    started = runner.add_single_to_queue(url)
    if started:
        flash("Video added to queue!", "success")
    else:
        flash("Could not add to queue.", "error")

    return redirect(url_for("dashboard"))


@app.route("/submit/batch", methods=["POST"])
def submit_batch():
    """Accept multiple URLs, one per line."""
    urls_raw = request.form.get("urls", "").strip()
    if not urls_raw:
        flash("Please enter at least one URL.", "error")
        return redirect(url_for("submit"))

    if runner.is_running():
        flash("Pipeline is busy. Please wait.", "error")
        return redirect(url_for("dashboard"))

    urls = [u.strip() for u in urls_raw.splitlines() if u.strip()]
    added = 0
    for url in urls:
        if runner.add_single_to_queue(url):
            added += 1
            # Small delay to let the thread kick off extraction
            import time
            time.sleep(0.5)

    if added:
        flash(f"Added {added} video(s) to queue!", "success")
    else:
        flash("Could not add any URLs to queue.", "error")

    return redirect(url_for("dashboard"))


@app.route("/history")
def history_page():
    return render_template(
        "history.html",
        uploads=get_history(limit=500),
        total=get_history_count(),
    )


@app.route("/logs")
def logs_page():
    return render_template("logs.html", log_lines=runner.log_buffer.get_lines())


# ── Queue & Pipeline controls ─────────────────────────────────────

@app.route("/queue/burn", methods=["POST"])
def queue_burn():
    """Scrape top viral videos and add to queue."""
    if runner.is_running():
        flash("Pipeline is busy.", "error")
        return redirect(url_for("dashboard"))

    try:
        count = int(request.form.get("count", 6))
        count = max(1, min(count, 50))
    except (TypeError, ValueError):
        count = 6

    started = runner.load_queue(count=count)
    if started:
        flash(f"Searching for {count} viral videos...", "success")
    else:
        flash("Could not start scraping.", "error")
    return redirect(url_for("dashboard"))


@app.route("/queue/arm", methods=["POST"])
def queue_arm():
    runner.arm()
    flash("Pipeline armed! Click Start to begin processing.", "success")
    return redirect(url_for("dashboard"))


@app.route("/queue/disarm", methods=["POST"])
def queue_disarm():
    runner.disarm()
    flash("Pipeline disarmed.", "info")
    return redirect(url_for("dashboard"))


@app.route("/queue/start", methods=["POST"])
def queue_start():
    # Auto-arm if not already armed (new simplified flow)
    if not runner.armed:
        runner.arm()

    started = runner.start_processing()
    if started:
        flash("Processing started!", "success")
    else:
        flash("Could not start — is the pipeline already running or the queue empty?", "error")
    return redirect(url_for("dashboard"))


@app.route("/queue/clear", methods=["POST"])
def queue_clear():
    runner.clear_queue()
    flash("Queue cleared.", "info")
    return redirect(url_for("dashboard"))


@app.route("/queue/remove/<uid>", methods=["POST"])
def queue_remove(uid):
    runner.remove_from_queue(uid)
    return redirect(url_for("dashboard"))


@app.route("/queue/cancel", methods=["POST"])
def queue_cancel():
    """Cancel the running pipeline by disarming it."""
    runner.disarm()
    flash("Pipeline cancelled. Current video will finish, remaining will be skipped.", "info")
    return redirect(url_for("dashboard"))


@app.route("/queue/reorder", methods=["POST"])
def queue_reorder():
    """Reorder queue items. Expects JSON body with {uids: [uid1, uid2, ...]}."""
    data = request.get_json(silent=True)
    if not data or "uids" not in data:
        return jsonify({"ok": False, "error": "Missing uids"}), 400

    uid_order = data["uids"]
    runner.reorder_queue(uid_order)
    return jsonify({"ok": True})


@app.route("/queue/retry/<uid>", methods=["POST"])
def queue_retry(uid):
    """Re-queue a failed item."""
    success = runner.retry_item(uid)
    if success:
        flash("Item re-queued!", "success")
    else:
        flash("Could not retry this item.", "error")
    return redirect(url_for("dashboard"))


# ── Scheduler controls ─────────────────────────────────────────────

@app.route("/scheduler/start", methods=["POST"])
def scheduler_start():
    start_scheduler()
    flash("Scheduler started.", "success")
    return redirect(url_for("dashboard"))


@app.route("/scheduler/stop", methods=["POST"])
def scheduler_stop():
    stop_scheduler()
    flash("Scheduler stopped.", "success")
    return redirect(url_for("dashboard"))


# ── YouTube OAuth ──────────────────────────────────────────────────

@app.route("/oauth/start")
def oauth_start():
    try:
        from google_auth_oauthlib.flow import Flow

        secrets_file = config.YOUTUBE_CLIENT_SECRETS_FILE
        if not os.path.exists(secrets_file):
            flash(f"Client secrets file not found: {secrets_file}. Upload it first via Settings.", "error")
            return redirect(url_for("dashboard"))

        flow = Flow.from_client_secrets_file(
            secrets_file,
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
            redirect_uri=url_for("oauth_callback", _external=True),
        )
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        session["oauth_state"] = state
        session["oauth_code_verifier"] = flow.code_verifier
        return redirect(authorization_url)

    except Exception as e:
        logger.exception("OAuth start failed")
        flash(f"OAuth error: {e}", "error")
        return redirect(url_for("dashboard"))


@app.route("/oauth/callback")
def oauth_callback():
    try:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_secrets_file(
            config.YOUTUBE_CLIENT_SECRETS_FILE,
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
            redirect_uri=url_for("oauth_callback", _external=True),
            state=session.get("oauth_state"),
        )
        flow.code_verifier = session.get("oauth_code_verifier")
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials

        with open(config.YOUTUBE_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

        flash("YouTube account connected successfully!", "success")
        logger.info("YouTube OAuth completed, token saved")

    except Exception as e:
        logger.exception("OAuth callback failed")
        flash(f"OAuth failed: {e}", "error")

    return redirect(url_for("dashboard"))


# ── API endpoints (JSON) ───────────────────────────────────────────

@app.route("/api/status")
def api_status():
    return jsonify(runner.get_status())


@app.route("/api/quota")
def api_quota():
    return jsonify(get_quota_info())


@app.route("/api/history")
def api_history():
    limit = request.args.get("limit", 20, type=int)
    return jsonify({"uploads": get_history(limit=limit), "total": get_history_count()})


@app.route("/api/logs")
def api_logs():
    return jsonify({"lines": runner.log_buffer.get_lines()})


@app.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    runner.log_buffer.clear()
    return jsonify({"ok": True})


@app.route("/api/logs/download")
def api_logs_download():
    """Download the full log file."""
    log_file = config.LOG_FILE
    if os.path.exists(log_file):
        return send_file(
            os.path.abspath(log_file),
            mimetype="text/plain",
            as_attachment=True,
            download_name="auto_youtuber.log",
        )
    # Fall back to in-memory buffer
    content = "\n".join(runner.log_buffer.get_lines())
    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=auto_youtuber.log"},
    )


@app.route("/api/test-reddit", methods=["POST"])
def api_test_reddit():
    """Test Reddit API connection with current credentials."""
    try:
        import requests as req

        cid = config.REDDIT_CLIENT_ID
        secret = config.REDDIT_CLIENT_SECRET
        ua = config.REDDIT_USER_AGENT or "AutoYoutuber/1.0"

        if not cid or not secret:
            return jsonify({"ok": False, "message": "Reddit credentials not configured"})

        # Try fetching r/funny top post as a connectivity test
        headers = {"User-Agent": ua}
        resp = req.get(
            "https://www.reddit.com/r/funny/top.json?limit=1&t=day",
            headers=headers,
            timeout=10,
        )

        if resp.status_code == 200:
            return jsonify({"ok": True, "message": "Reddit API connection successful!"})
        else:
            return jsonify({"ok": False, "message": f"Reddit returned HTTP {resp.status_code}"})

    except Exception as e:
        return jsonify({"ok": False, "message": f"Connection failed: {e}"})


@app.route("/api/test-youtube", methods=["POST"])
def api_test_youtube():
    """Test YouTube connection by checking if token is valid."""
    try:
        token_file = config.YOUTUBE_TOKEN_FILE
        if not os.path.exists(token_file):
            return jsonify({"ok": False, "message": "No YouTube token found. Connect your account first."})

        with open(token_file) as f:
            token_data = json.load(f)

        if token_data.get("token"):
            return jsonify({"ok": True, "message": "YouTube token found and appears valid!"})
        else:
            return jsonify({"ok": False, "message": "YouTube token file exists but appears empty or invalid"})

    except Exception as e:
        return jsonify({"ok": False, "message": f"Error checking token: {e}"})


@app.route("/api/history/export")
def api_history_export():
    """Export upload history as CSV."""
    uploads = get_history(limit=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Title", "Subreddit", "Author", "Score", "Duration", "Status", "YouTube URL", "Reddit URL", "Error"])

    for u in uploads:
        yt_url = f"https://www.youtube.com/shorts/{u['youtube_id']}" if u.get("youtube_id") else ""
        writer.writerow([
            u.get("uploaded_at", ""),
            u.get("title", ""),
            u.get("subreddit", ""),
            u.get("author", ""),
            u.get("score", 0),
            u.get("duration", 0),
            u.get("status", ""),
            yt_url,
            u.get("reddit_url", ""),
            u.get("error", ""),
        ])

    csv_content = output.getvalue()
    output.close()

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=auto_youtuber_history.csv"},
    )


@app.route("/api/dashboard")
def api_dashboard():
    """Consolidated dashboard endpoint — reduces polling from 3 requests to 1."""
    return jsonify({
        "status": runner.get_status(),
        "quota": get_quota_info(),
        "history": {"uploads": get_history(limit=20), "total": get_history_count()},
        "scheduler_running": _scheduler_running,
        "next_run": get_next_run_time(),
        "youtube_connected": is_youtube_connected(),
    })
