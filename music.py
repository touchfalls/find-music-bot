"""Поиск песен на YouTube Music и скачивание MP3. Без Telegram."""
import re

from ytmusicapi import YTMusic

MAX_DURATION_S = 15 * 60  # длиннее не влезет в лимит бота 50 МБ при 320 kbps

_yt = YTMusic()


def search(query: str) -> list[dict]:
    """Только песни (filter="songs"), без клипов; дубли по videoId убраны."""
    found = {}
    for r in _yt.search(query, filter="songs", limit=50):
        vid, dur = r.get("videoId"), r.get("duration_seconds") or 0
        if not vid or vid in found or dur > MAX_DURATION_S:
            continue
        thumbs = r.get("thumbnails") or [{}]
        found[vid] = {
            "video_id": vid,
            "title": r.get("title") or "?",
            "artist": ", ".join(a["name"] for a in r.get("artists") or []) or "?",
            "duration_s": dur,
            # w60-h60 → 320x320: максимум для thumbnail в Telegram
            "thumb": re.sub(r"w\d+-h\d+", "w320-h320", thumbs[-1].get("url", "")),
        }
    return list(found.values())
