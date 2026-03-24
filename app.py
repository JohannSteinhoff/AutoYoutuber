import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

import config
from pipeline_runner import runner
from settings_db import get_all_settings, set_many_settings

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
    interval_hours = 24 / max(config.VIDEOS_PER_DAY, 1)
    scheduler.add_job(
        runner.run_pipeline,
        "interval",
        hours=interval_hours,
        id="pipeline_job",
        max_instances=1,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    _scheduler_running = True
    logger.info("Scheduler started: every %.1f hours", interval_hours)


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


def reschedule():
    if not _scheduler_running:
        return
    interval_hours = 24 / max(config.VIDEOS_PER_DAY, 1)
    scheduler.reschedule_job("pipeline_job", trigger="interval", hours=interval_hours)
    logger.info("Scheduler rescheduled: every %.1f hours", interval_hours)


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


# ── Routes ─────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    return render_template(
        "dashboard.html",
        status=runner.status,
        scheduler_running=_scheduler_running,
        pipeline_running=runner.is_running(),
        interval_hours=round(24 / max(config.VIDEOS_PER_DAY, 1), 1),
        videos_per_day=config.VIDEOS_PER_DAY,
        next_run=get_next_run_time(),
        youtube_connected=is_youtube_connected(),
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

    # Reschedule if videos per day changed
    if _scheduler_running:
        reschedule()

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
        flash("Pipeline is already running. Please wait.", "error")
        return redirect(url_for("dashboard"))

    started = runner.run_single(url)
    if started:
        flash("Processing started! Check the dashboard for progress.", "success")
    else:
        flash("Could not start pipeline.", "error")

    return redirect(url_for("dashboard"))


@app.route("/logs")
def logs_page():
    return render_template("logs.html", log_lines=runner.log_buffer.get_lines())


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


@app.route("/scheduler/run-now", methods=["POST"])
def scheduler_run_now():
    if runner.is_running():
        flash("Pipeline is already running.", "error")
    else:
        runner.run_pipeline()
        flash("Pipeline run started.", "success")
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
    return jsonify(runner.status.to_dict())


@app.route("/api/logs")
def api_logs():
    return jsonify({"lines": runner.log_buffer.get_lines()})


@app.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    runner.log_buffer.clear()
    return jsonify({"ok": True})
