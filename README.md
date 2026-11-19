# find-music-bot

Семейный Telegram-бот: пишешь название песни или исполнителя, выбираешь трек из списка, получаешь MP3 320 с тегами и обложкой.
Поиск идёт по YouTube Music (только песни, без клипов), скачивание через yt-dlp.

## Доступ
Бот отвечает только тем, кто открыл ссылку-приглашение `https://t.me/<бот>?start=<INVITE_CODE>`.
Бот печатает её в лог при запуске. Если ссылка утекла, поменяй `INVITE_CODE` и перезапусти бота: старая ссылка перестанет работать (кто уже вошёл, останется).
Чтобы убрать человека, удали его строку: `sqlite3 cache.db "DELETE FROM users WHERE user_id=…"`.

## Запуск
Нужны [uv](https://docs.astral.sh/uv/) и ffmpeg (`brew install ffmpeg`).

1. Создай бота у @BotFather (`/newbot`) и возьми токен.
2. `cp .env.example .env`, впиши `BOT_TOKEN`, а в `INVITE_CODE` сгенерированный секрет:
   `python3 -c "import secrets; print(secrets.token_urlsafe(16))"`
3. Чтобы отправлять треки прямо в чат с другом (`@бот название`), включи у @BotFather:
   `/setinline` (подсказка, например «Название песни…») и `/setinlinefeedback` → Enabled.
4. `uv run --env-file .env bot.py`

В inline-режиме трек, которого ещё нет в кэше, сначала уходит заглушкой «⏳ Загружаю…», и через несколько секунд бот подменяет её на MP3.
Уже скачанные треки уходят сразу.

Тесты: `uv run pytest`

Если YouTube перестал отдавать треки, обнови yt-dlp: `uv lock --upgrade-package yt-dlp && uv sync`.
