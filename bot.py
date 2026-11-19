import asyncio
import logging
import os
import re
import secrets
import sqlite3
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import (BufferedInputFile, CallbackQuery, ChosenInlineResult, FSInputFile, InlineKeyboardButton,
                           InlineKeyboardMarkup, InlineQuery, InlineQueryResultCachedAudio,
                           InlineQueryResultCachedDocument, InputMediaAudio, Message, URLInputFile)
from aiogram.utils.chat_action import ChatActionSender

import music

PAGE_SIZE = 10
MAX_UPLOAD = 50 * 1024 * 1024  # лимит Bot API на отправку файла
DB_PATH = Path(__file__).with_name("cache.db")

db: sqlite3.Connection
invite_code: str
allowed: set[int] = set()  # кто вошёл по ссылке-приглашению; грузится из БД в main()
# shortcut: результаты поиска живут в памяти и пропадают при рестарте; для семьи хватает, иначе хранить в SQLite
results: dict[tuple[int, int], list[dict]] = {}
known: dict[str, dict] = {}  # video_id -> название/артист/обложка из последних поисков

public = Router()
auth = Router()  # всё, кроме /start, только для вошедших; чужим бот молчит
auth.message.filter(F.from_user.id.in_(allowed))
auth.callback_query.filter(F.from_user.id.in_(allowed))
auth.inline_query.filter(F.from_user.id.in_(allowed))
auth.chosen_inline_result.filter(F.from_user.id.in_(allowed))

# кнопка нужна, иначе Telegram не даст inline_message_id и заглушку нельзя будет заменить на трек
LOADING_KB = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏳ Загружаю…", callback_data="noop")]])


def fmt_duration(s: int) -> str:
    return f"{s // 60}:{s % 60:02d}"


def build_keyboard(items: list[dict], page: int) -> InlineKeyboardMarkup:
    pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, pages - 1))
    rows = [
        [InlineKeyboardButton(
            text=f"{t['artist']} — {t['title']} ({fmt_duration(t['duration_s'])})",
            callback_data=f"dl:{t['video_id']}",
        )]
        for t in items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    ]
    if pages > 1:
        nav = [InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop")]
        if page > 0:
            nav.insert(0, InlineKeyboardButton(text="←", callback_data=f"pg:{page - 1}"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(text="→", callback_data=f"pg:{page + 1}"))
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@public.message(CommandStart())
async def on_start(m: Message, command: CommandObject):
    uid = m.from_user.id
    if uid not in allowed:
        if not command.args or not secrets.compare_digest(command.args.encode(), invite_code.encode()):
            return
        allowed.add(uid)
        db.execute("INSERT OR IGNORE INTO users VALUES (?)", (uid,))
        db.commit()
    await m.answer("Привет! Напиши название песни или исполнителя 🎵")


@auth.message(F.text)
async def on_search(m: Message):
    try:
        items = await asyncio.to_thread(music.search, m.text)
    except Exception:
        logging.exception("search failed")
        return await m.answer("Поиск сейчас не работает, попробуй позже")
    if not items:
        return await m.answer("Ничего не нашёл 😔")
    known.update((t["video_id"], t) for t in items)
    sent = await m.answer(f"🔎 {m.text}", reply_markup=build_keyboard(items, 0))
    results[(sent.chat.id, sent.message_id)] = items


@auth.callback_query(F.data.startswith("pg:"))
async def on_page(c: CallbackQuery):
    items = results.get((c.message.chat.id, c.message.message_id))
    if items is None:
        return await c.answer("Поиск устарел, повтори запрос", show_alert=True)
    await c.message.edit_reply_markup(reply_markup=build_keyboard(items, int(c.data[3:])))
    await c.answer()


class TooBig(Exception):
    pass


async def send_track(bot: Bot, chat_id: int, video_id: str, info: dict | None) -> Message:
    """Отправить трек в chat_id: из кэша file_id мгновенно, иначе скачать и запомнить file_id."""
    if fid := cached_file_id(video_id):
        return await bot.send_audio(chat_id, fid)
    async with ChatActionSender.upload_document(bot=bot, chat_id=chat_id):
        with tempfile.TemporaryDirectory() as tmp:
            path = await asyncio.to_thread(music.download, video_id, tmp)
            if path.stat().st_size > MAX_UPLOAD:
                raise TooBig
            extra = {}
            if info:  # без info (после рестарта) Telegram возьмёт название и артиста из ID3-тегов
                extra = dict(title=info["title"], performer=info["artist"], duration=info["duration_s"],
                             thumbnail=URLInputFile(info["thumb"]) if info["thumb"] else None)
            msg = await bot.send_audio(chat_id, FSInputFile(path), request_timeout=300, **extra)
    db.execute("INSERT OR REPLACE INTO tracks VALUES (?, ?)", (video_id, msg.audio.file_id))
    db.commit()
    return msg


@auth.callback_query(F.data.startswith("dl:"))
async def on_download(c: CallbackQuery):
    await c.answer()
    vid = c.data[3:]
    try:
        await send_track(c.bot, c.message.chat.id, vid, known.get(vid))
    except TooBig:
        await c.message.answer("Файл больше 50 МБ, Telegram не даст его отправить")
    except Exception:
        logging.exception("download failed: %s", vid)
        await c.message.answer("Не получилось скачать этот трек 😔")


def cached_file_id(video_id: str) -> str | None:
    row = db.execute("SELECT file_id FROM tracks WHERE video_id = ?", (video_id,)).fetchone()
    return row[0] if row else None


async def placeholder_id(bot: Bot, user_id: int) -> str:
    """file_id документа-заглушки для inline. Загружается один раз через личку пользователя и сразу удаляется."""
    row = db.execute("SELECT value FROM meta WHERE key = 'placeholder'").fetchone()
    if row:
        return row[0]
    msg = await bot.send_document(user_id, BufferedInputFile("Загружаю трек…".encode(), "loading.txt"))
    await msg.delete()
    db.execute("INSERT OR REPLACE INTO meta VALUES ('placeholder', ?)", (msg.document.file_id,))
    db.commit()
    return msg.document.file_id


@auth.inline_query()
async def on_inline(q: InlineQuery, bot: Bot):
    if not q.query.strip():
        return await q.answer([], cache_time=0)
    try:
        items = (await asyncio.to_thread(music.search, q.query))[:50]  # больше 50 Telegram не принимает
        known.update((t["video_id"], t) for t in items)
        answer = []
        for t in items:
            if fid := cached_file_id(t["video_id"]):
                answer.append(InlineQueryResultCachedAudio(id=t["video_id"], audio_file_id=fid))
            else:
                answer.append(InlineQueryResultCachedDocument(
                    id=t["video_id"], title=f"{t['artist']} — {t['title']}",
                    description=fmt_duration(t["duration_s"]),
                    document_file_id=await placeholder_id(bot, q.from_user.id), reply_markup=LOADING_KB,
                ))
    except Exception:
        logging.exception("inline search failed")
        answer = []
    await q.answer(answer, is_personal=True, cache_time=10)


@auth.chosen_inline_result()
async def on_chosen(r: ChosenInlineResult, bot: Bot):
    if not r.inline_message_id:  # трек был в кэше и ушёл сразу аудио
        return
    try:
        # send_track шлёт в личку пользователю: Telegram не даёт загружать файл прямо в inline-сообщение
        msg = await send_track(bot, r.from_user.id, r.result_id, known.get(r.result_id))
        await msg.delete()
        await bot.edit_message_media(inline_message_id=r.inline_message_id,
                                     media=InputMediaAudio(media=msg.audio.file_id))
    except Exception:
        logging.exception("inline download failed: %s", r.result_id)
        await bot.edit_message_caption(inline_message_id=r.inline_message_id,
                                       caption="Не получилось загрузить трек 😔")


@auth.callback_query(F.data == "noop")
async def on_noop(c: CallbackQuery):
    await c.answer()


async def main():
    global db, invite_code
    logging.basicConfig(level=logging.INFO)
    invite_code = os.environ["INVITE_CODE"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", invite_code):
        raise SystemExit("INVITE_CODE: 8-64 символа A-Za-z0-9_- (см. README)")
    db = sqlite3.connect(DB_PATH)
    db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS tracks (video_id TEXT PRIMARY KEY, file_id TEXT NOT NULL)")
    allowed.update(uid for (uid,) in db.execute("SELECT user_id FROM users"))

    bot = Bot(os.environ["BOT_TOKEN"])
    me = await bot.get_me()
    logging.info("Ссылка-приглашение: https://t.me/%s?start=%s", me.username, invite_code)
    dp = Dispatcher()
    dp.include_routers(public, auth)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
