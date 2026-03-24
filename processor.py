import json
import logging
import os
import subprocess
import textwrap

import config

logger = logging.getLogger(__name__)

# Use Windows Arial font directly to avoid fontconfig issues on WSL
FONT_FILE = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf")
if not os.path.exists(FONT_FILE):
    # Fallback: try common locations
    for candidate in [r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(candidate):
            FONT_FILE = candidate
            break


def get_video_info(input_path: str) -> dict:
    """Get video dimensions and duration using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    probe = json.loads(result.stdout)

    video_stream = next(
        (s for s in probe.get("streams", []) if s["codec_type"] == "video"), None
    )
    if not video_stream:
        raise ValueError(f"No video stream found in {input_path}")

    duration = float(probe.get("format", {}).get("duration", 0))
    width = int(video_stream["width"])
    height = int(video_stream["height"])
    return {"width": width, "height": height, "duration": duration}


def process_video(input_path: str, post: dict) -> str | None:
    """Reformat video for YouTube Shorts (1080x1920) with title overlay. Returns output path or None."""
    output_path = os.path.join(config.TEMP_DIR, f"{post['id']}_shorts.mp4")

    if os.path.exists(output_path):
        logger.info("Processed video already exists: %s", output_path)
        return output_path

    try:
        info = get_video_info(input_path)
        src_w, src_h = info["width"], info["height"]
        duration = info["duration"]
        logger.info(
            "Source video: %dx%d, %.1fs", src_w, src_h, duration
        )

        out_w = config.OUTPUT_WIDTH
        out_h = config.OUTPUT_HEIGHT

        # Wrap long titles across multiple lines
        title_text = post["title"].replace("'", "'\\''").replace(":", "\\:")
        wrapped = textwrap.fill(title_text, width=35)
        # Escape characters that FFmpeg drawtext treats specially
        escaped_title = wrapped.replace("\\", "\\\\").replace("%", "%%")

        # Escape the font path for FFmpeg (backslashes and colons)
        font_escaped = FONT_FILE.replace("\\", "/").replace(":", "\\:")

        # Build filter graph
        is_landscape = src_w / src_h > (out_w / out_h)

        drawtext = (
            f"drawtext=fontfile='{font_escaped}':"
            f"text='{escaped_title}':"
            f"fontsize=42:fontcolor=white:borderw=3:bordercolor=black:"
            f"x=(w-text_w)/2:y=80:line_spacing=10"
        )

        if is_landscape:
            # Landscape source: create blurred background + centered sharp overlay
            filter_complex = (
                f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                f"crop={out_w}:{out_h},boxblur=20:5[bg];"
                f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
                f"{drawtext}"
            )
        else:
            # Portrait/square source: scale to fit and pad
            filter_complex = (
                f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
                f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"{drawtext}"
            )

        # Build ffmpeg command
        cmd = ["ffmpeg", "-y", "-i", input_path]

        # Trim to max duration
        max_dur = config.MAX_DURATION_SECONDS
        if duration > max_dur:
            cmd.extend(["-t", str(max_dur)])
            logger.info("Trimming video from %.1fs to %ds", duration, max_dur)

        cmd.extend([
            "-filter_complex", filter_complex,
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            "-r", "30",
            output_path,
        ])

        logger.info("Processing video for post %s", post["id"])
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )

        if result.returncode != 0:
            logger.error("FFmpeg failed:\n%s", result.stderr[-2000:])
            return None

        if os.path.exists(output_path):
            logger.info("Processed successfully: %s", output_path)
            return output_path

        logger.error("FFmpeg finished but output file missing: %s", output_path)
        return None

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timed out processing %s", input_path)
        return None
    except Exception:
        logger.exception("Failed to process video for post %s", post["id"])
        return None
