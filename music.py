"""Поиск песен на YouTube Music и скачивание MP3. Без Telegram."""
import re
from pathlib import Path

import yt_dlp
from ytmusicapi import YTMusic

# cookies YouTube-аккаунта (формат Netscape): нужны, если YouTube блокирует IP сервера. Нет файла — качаем без них
COOKIES = Path(__file__).with_name("cookies.txt")
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


def download(video_id: str, dest_dir: str) -> Path:
    """M4A (оригинальный AAC с YouTube, без перекодирования) с тегами и квадратной обложкой. Блокирующая: из бота звать через asyncio.to_thread."""
    if not re.fullmatch(r"[\w-]{11}", video_id):  # id приходит из callback_data, её клиент может подделать
        raise ValueError(f"bad video id: {video_id!r}")
    opts = {
        # m4a (AAC) идёт без перекодирования: на 1 CPU это экономит ~20 с на трек; Telegram играет его как аудио
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": f"{dest_dir}/%(id)s.%(ext)s",
        "writethumbnail": True,
        "quiet": True,
        "noprogress": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"},  # AAC копируется как есть, иначе перекодируется
            {"key": "FFmpegMetadata"},
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg"},
            {"key": "EmbedThumbnail"},
        ],
        # превью YouTube 16:9 с обложкой по центру, режем до квадрата
        "postprocessor_args": {"thumbnailsconvertor": ["-vf", "crop=ih:ih"]},
    }
    if COOKIES.exists():
        opts["cookiefile"] = str(COOKIES)
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([f"https://music.youtube.com/watch?v={video_id}"])
    return Path(dest_dir, f"{video_id}.m4a")
