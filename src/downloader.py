"""Video downloader utility for AutoShorts.

Enables downloading videos from YouTube, Twitch, and other web sources
directly into the processing queue using yt-dlp.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

# Supported video formats by AutoShorts
SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}

# Standard URL pattern matching web video providers
URL_REGEX = re.compile(
    r"^(https?://)?"
    r"([a-zA-Z0-9_-]+\.)+[a-zA-Z]{2,}"
    r"(/[-a-zA-Z0-9@:%_\+.~#?&//=]*)?$"
)

COMMON_VIDEO_DOMAINS = {
    "youtube.com",
    "youtu.be",
    "m.youtube.com",
    "twitch.tv",
    "vimeo.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "instagram.com",
}


def is_url(candidate: str | Path | None) -> bool:
    """Check if candidate represents a web URL (e.g. YouTube video or stream).

    Args:
        candidate: String or Path to inspect.

    Returns:
        True if the candidate is an HTTP/HTTPS URL or known video domain.
    """
    if candidate is None:
        return False

    candidate_str = str(candidate).strip().replace("\\", "/")
    if not candidate_str:
        return False

    # Normalize cases where Path collapsed // into a single / (e.g. on Windows)
    candidate_str = re.sub(r"^(https?):/+", r"\1://", candidate_str)

    if candidate_str.startswith(("http://", "https://")):
        try:
            parsed = urlparse(candidate_str)
            return bool(parsed.netloc and parsed.scheme in ("http", "https"))
        except Exception:
            return False

    # Check for shorthand domains like youtu.be/xxx or youtube.com/watch?v=xxx
    lowered = candidate_str.lower()
    for domain in COMMON_VIDEO_DOMAINS:
        if lowered.startswith(domain + "/") or lowered.startswith("www." + domain + "/"):
            return True

    return False


def get_video_title(url: str) -> Optional[str]:
    """Retrieve the video title without downloading.

    Args:
        url: The web video URL.

    Returns:
        The video title, or None if extraction fails.
    """
    try:
        import yt_dlp
    except ImportError:
        logging.warning("yt-dlp is not installed. Cannot query video metadata.")
        return None

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return info.get("title")
    except Exception as e:
        logging.debug(f"Failed to extract title for {url}: {e}")

    return None


def download_video(
    url: str,
    output_dir: Path | str = "gameplay",
    max_height: int = 1080,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> Path:
    """Download a video or livestream VOD from YouTube or other supported sites.

    Args:
        url: Video URL to download.
        output_dir: Target directory where the video will be saved (default: gameplay).
        max_height: Maximum resolution height (e.g. 1080 for 1080p).
        progress_callback: Optional hook called with yt-dlp progress status.

    Returns:
        The Path to the downloaded .mp4 video file.

    Raises:
        ImportError: If yt-dlp is not installed.
        RuntimeError: If download fails or output file is not created.
    """
    try:
        import yt_dlp
    except ImportError as e:
        raise ImportError(
            "yt-dlp is required to download web/YouTube videos.\n"
            "Install it via: pip install yt-dlp"
        ) from e

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize URL if scheme is missing or contains Windows path slashes
    clean_url = str(url).strip().replace("\\", "/")
    clean_url = re.sub(r"^(https?):/+", r"\1://", clean_url)
    if not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url

    # Restrict resolution to max_height, prefer MP4 containers compatible with Decord/FFmpeg
    format_selector = (
        f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={max_height}]+bestaudio/"
        f"best[height<={max_height}][ext=mp4]/"
        f"best[ext=mp4]/best"
    )

    out_template = str(target_dir / "%(title).90B [%(id)s].%(ext)s")

    downloaded_files: list[str] = []

    def _ytdl_hook(d: dict) -> None:
        if d.get("status") == "finished":
            filename = d.get("filename")
            if filename:
                downloaded_files.append(filename)
        if progress_callback:
            try:
                progress_callback(d)
            except Exception:
                pass

    ydl_opts = {
        "format": format_selector,
        "outtmpl": out_template,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": False,
        "no_warnings": True,
        "progress_hooks": [_ytdl_hook],
        # Re-encode to standard h264/aac if needed for maximum compatibility
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }
        ],
    }

    logging.info(f"Downloading video from {clean_url} to '{target_dir}'...")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            retcode = ydl.download([clean_url])
            if retcode != 0:
                raise RuntimeError(f"yt-dlp failed with return code {retcode}")
    except Exception as e:
        if isinstance(e, RuntimeError):
            raise
        raise RuntimeError(f"Failed to download video from {clean_url}: {e}") from e

    # Find the downloaded file
    # Check hooked filenames first
    for f in downloaded_files:
        p = Path(f)
        # Check if the merged mp4 exists
        mp4_cand = p.with_suffix(".mp4")
        if mp4_cand.exists():
            return mp4_cand.resolve()
        if p.exists():
            return p.resolve()

    # Fallback: find the most recently modified video file in target_dir
    candidates = [
        f for f in target_dir.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    if candidates:
        latest = max(candidates, key=lambda f: f.stat().st_mtime)
        return latest.resolve()

    raise RuntimeError(
        f"Download succeeded but no output video file was found in '{target_dir}'."
    )
