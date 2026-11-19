# find-music-bot

Telegram-бот: пишешь название песни или исполнителя, выбираешь трек из списка, получаешь MP3 320 с тегами и обложкой.
Поиск идёт по YouTube Music (только песни, без клипов), скачивание через yt-dlp.

## Запуск
Нужны [uv](https://docs.astral.sh/uv/) и ffmpeg (`brew install ffmpeg`).

1. Создай бота у @BotFather (`/newbot`) и возьми токен.
2. `cp .env.example .env` и впиши `BOT_TOKEN`.
3. Чтобы отправлять треки прямо в чат с другом (`@бот название`), включи у @BotFather:
   `/setinline` (подсказка, например «Название песни…») и `/setinlinefeedback` → Enabled.
4. `uv run --env-file .env bot.py`

В inline-режиме трек, которого ещё нет в кэше, сначала уходит заглушкой «⏳ Загружаю…», и через несколько секунд бот подменяет её на MP3.
Уже скачанные треки уходят сразу.

Тесты: `uv run pytest`

## На VPS (рядом с другим ботом)
Боты друг другу не мешают: у каждого свой токен, своя папка и свой systemd-сервис, порты не нужны (long polling).
Ниже Ubuntu/Debian; `USER` — твой пользователь на VPS.

```bash
# 1. Зависимости: ffmpeg из apt, uv; JS-runtime (deno) ставится сам вместе с yt-dlp
sudo apt update && sudo apt install -y ffmpeg git
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Код
git clone https://github.com/touchfalls/find-music-bot.git ~/find-music-bot
cd ~/find-music-bot && uv sync --no-dev
echo 'BOT_TOKEN=...' > .env && chmod 600 .env

# 3. Сервис
sed "s/USER/$USER/g" deploy/find-music-bot.service | sudo tee /etc/systemd/system/find-music-bot.service
sudo systemctl daemon-reload && sudo systemctl enable --now find-music-bot
journalctl -u find-music-bot -f   # логи
```

- **Перед запуском на VPS останови бота на маке**: два процесса с одним токеном конфликтуют (`TelegramConflictError`).
- Кэш можно перенести, чтобы скачанные треки уходили сразу: `scp cache.db USER@VPS:~/find-music-bot/` (до `systemctl start`).
- Обновление: `cd ~/find-music-bot && git pull && uv sync --no-dev && sudo systemctl restart find-music-bot`.
- YouTube иногда блокирует IP дата-центров («Sign in to confirm you're not a bot»). Тогда положи рядом с `bot.py` файл `cookies.txt` (см. ниже) и перезапусти сервис.

## Cookies YouTube (на случай блокировки)
Если рядом с `bot.py` лежит `cookies.txt`, yt-dlp качает от имени этого аккаунта. Файла нет — качает анонимно. `cookies.txt` в `.gitignore`: это доступ к аккаунту, никому его не показывай.

1. Заведи **отдельный** Google-аккаунт: YouTube может забанить аккаунт, через который массово качают.
2. Открой **приватное окно** браузера, войди в этот аккаунт на youtube.com.
3. В том же окне на `youtube.com/robots.txt` выгрузи cookies расширением «Get cookies.txt LOCALLY» (формат Netscape) в `cookies.txt`.
4. **Закрой приватное окно, не выходя из аккаунта**: иначе YouTube обновит cookies и выгруженные перестанут работать.
5. `scp cookies.txt USER@VPS:~/find-music-bot/ && ssh USER@VPS 'chmod 600 ~/find-music-bot/cookies.txt && sudo systemctl restart find-music-bot'`

Cookies со временем протухают; если блокировка вернулась, повтори шаги 2–5.

Если YouTube перестал отдавать треки, обнови yt-dlp: `uv lock --upgrade-package yt-dlp && uv sync`.
