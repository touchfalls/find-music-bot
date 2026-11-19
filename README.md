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
Боты друг другу не мешают: у каждого свой токен, папка, пользователь и systemd-сервис; порты не нужны (long polling).
Ниже Ubuntu 24.04, команды от root.

```bash
# 1. Зависимости: ffmpeg и git из apt, uv; JS-runtime (deno) ставится сам вместе с yt-dlp
apt update && apt install -y ffmpeg git
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# 2. Отдельный пользователь и код
useradd --system --create-home --home-dir /var/lib/musicbot --shell /usr/sbin/nologin musicbot
git clone https://github.com/touchfalls/find-music-bot.git /opt/find-music-bot
chown -R musicbot:musicbot /opt/find-music-bot
cd /opt/find-music-bot && sudo -u musicbot uv sync --no-dev
# .env (BOT_TOKEN=...) и, если есть, cache.db копируем с мака:
#   scp .env cache.db root@VPS:/opt/find-music-bot/
chown musicbot:musicbot .env cache.db; chmod 600 .env

# 3. Сервис
cp deploy/find-music-bot.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now find-music-bot
journalctl -u find-music-bot -f   # логи
```

- **Перед запуском на VPS останови бота на маке**: два процесса с одним токеном конфликтуют (`TelegramConflictError`).
- Сервис ограничен 450 МБ памяти (`MemoryMax`), чтобы не мешать соседям. На VPS с 1 ГБ без swap стоит добавить swap:
  `fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab`
- Обновление: `cd /opt/find-music-bot && sudo -u musicbot git pull && sudo -u musicbot uv sync --no-dev && systemctl restart find-music-bot`.
- YouTube иногда блокирует IP дата-центров («Sign in to confirm you're not a bot»). Тогда положи рядом с `bot.py` файл `cookies.txt` (см. ниже) и перезапусти сервис.

## Cookies YouTube (на случай блокировки)
Если рядом с `bot.py` лежит `cookies.txt`, yt-dlp качает от имени этого аккаунта. Файла нет — качает анонимно. `cookies.txt` в `.gitignore`: это доступ к аккаунту, никому его не показывай.

1. Заведи **отдельный** Google-аккаунт: YouTube может забанить аккаунт, через который массово качают.
2. Открой **приватное окно** браузера, войди в этот аккаунт на youtube.com.
3. В том же окне на `youtube.com/robots.txt` выгрузи cookies расширением «Get cookies.txt LOCALLY» (формат Netscape) в `cookies.txt`.
4. **Закрой приватное окно, не выходя из аккаунта**: иначе YouTube обновит cookies и выгруженные перестанут работать.
5. `scp cookies.txt root@VPS:/opt/find-music-bot/ && ssh root@VPS 'cd /opt/find-music-bot && chown musicbot:musicbot cookies.txt && chmod 600 cookies.txt && systemctl restart find-music-bot'`

Cookies со временем протухают; если блокировка вернулась, повтори шаги 2–5.

Если YouTube перестал отдавать треки, обнови yt-dlp: `uv lock --upgrade-package yt-dlp && uv sync`.
