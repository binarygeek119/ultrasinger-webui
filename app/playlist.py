from __future__ import annotations

import logging
import subprocess
from urllib.parse import urlparse

log = logging.getLogger(__name__)


def looks_like_playlist_url(url: str) -> bool:
    u = url.lower().strip()
    if "list=" in u:
        return True
    if "playlist" in urlparse(url).path.lower():
        return True
    return False


def expand_playlist(url: str, timeout: int = 600) -> list[str]:
    """
    Use yt-dlp to expand a playlist into individual watch URLs.
    Falls back to [url] on any failure.
    """
    try:
        proc = subprocess.run(
            [
                "yt-dlp",
                "--flat-playlist",
                "--ignore-errors",
                "--no-warnings",
                "--print",
                "url",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        log.warning("yt-dlp not found; playlist treated as single URL")
        return [url]
    except subprocess.TimeoutExpired:
        log.warning("yt-dlp playlist timeout; treating as single URL")
        return [url]

    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if proc.returncode != 0 or not lines:
        log.warning("yt-dlp playlist parse failed (%s); single job", proc.stderr[:200] if proc.stderr else proc.returncode)
        return [url]
    return lines
