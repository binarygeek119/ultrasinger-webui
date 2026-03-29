from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# list/index/start_radio: avoid yt-dlp downloading a whole mix/playlist for one video.
# si: share-id tracking on youtu.be / watch URLs; not needed for resolution and safe to drop.
_STRIP_QUERY_KEYS = frozenset({"list", "index", "start_radio", "si"})


def normalize_youtube_url_for_single_video(url: str) -> str:
    """
    Remove playlist/mix and share-tracking query parameters from YouTube URLs so
    downstream yt-dlp gets a canonical single-video link (--no-playlist style for watch URLs).
    """
    s = (url or "").strip()
    if not s:
        return s
    try:
        p = urlparse(s)
    except ValueError:
        return s
    netloc = (p.netloc or "").lower()
    if "youtube.com" not in netloc and "youtu.be" not in netloc:
        return s
    q = parse_qs(p.query, keep_blank_values=True)
    removed = [k for k in list(q.keys()) if k.lower() in _STRIP_QUERY_KEYS]
    if not removed:
        return s
    for k in removed:
        del q[k]
    pairs: list[tuple[str, str]] = []
    for k, vals in q.items():
        for v in vals:
            pairs.append((k, v))
    new_query = urlencode(pairs)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, p.fragment))
