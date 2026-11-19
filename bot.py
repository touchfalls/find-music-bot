import asyncio
import logging
import os
import re
import secrets
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import music

PAGE_SIZE = 10
DB_PATH = Path(__file__).with_name("cache.db")

db: sqlite3.Connection
invite_code: str
allowed: set[int] = set()  # кто вошёл по ссылке-приглашению; грузится из БД в main()
# shortcut: результаты поиска живут в памяти и пропадают при рестарте; для семьи хватает, иначе хранить в SQLite
results: dict[tuple[int, int], list[dict]] = {}

public = Router()
auth = Router()  # всё, кроме /start, только для вошедших; чужим бот молчит
auth.message.filter(F.from_user.id.in_(allowed))
auth.callback_query.filter(F.from_user.id.in_(allowed))


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
    sent = await m.answer(f"🔎 {m.text}", reply_markup=build_keyboard(items, 0))
    results[(sent.chat.id, sent.message_id)] = items


@auth.callback_query(F.data.startswith("pg:"))
async def on_page(c: CallbackQuery):
    items = results.get((c.message.chat.id, c.message.message_id))
    if items is None:
        return await c.answer("Поиск устарел, повтори запрос", show_alert=True)
    await c.message.edit_reply_markup(reply_markup=build_keyboard(items, int(c.data[3:])))
    await c.answer()


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
    allowed.update(uid for (uid,) in db.execute("SELECT user_id FROM users"))

    bot = Bot(os.environ["BOT_TOKEN"])
    me = await bot.get_me()
    logging.info("Ссылка-приглашение: https://t.me/%s?start=%s", me.username, invite_code)
    dp = Dispatcher()
    dp.include_routers(public, auth)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
