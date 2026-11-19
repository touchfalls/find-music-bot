import bot
import music


def track(i, dur=200):
    return {"video_id": f"id{i}", "title": f"t{i}", "artist": "a", "duration_s": dur, "thumb": ""}


def test_fmt_duration():
    assert bot.fmt_duration(205) == "3:25"
    assert bot.fmt_duration(59) == "0:59"


def test_keyboard_pages():
    items = [track(i) for i in range(25)]

    def nav(page):
        return [b.callback_data for b in bot.build_keyboard(items, page).inline_keyboard[-1]]

    first = bot.build_keyboard(items, 0).inline_keyboard
    assert len(first) == 11 and first[0][0].callback_data == "dl:id0"
    assert first[0][0].text == "a — t0 (3:20)"
    assert nav(0) == ["noop", "pg:1"]
    assert nav(1) == ["pg:0", "noop", "pg:2"]
    assert nav(2) == ["pg:1", "noop"]
    assert len(bot.build_keyboard(items, 99).inline_keyboard) == 6  # последняя страница: 5 + навигация


def test_keyboard_single_page_has_no_nav():
    assert len(bot.build_keyboard([track(1)], 0).inline_keyboard) == 1


def test_search_filters(monkeypatch):
    raw = [
        {"videoId": "a", "title": "Song", "artists": [{"name": "X"}, {"name": "Y"}], "duration_seconds": 200,
         "thumbnails": [{"url": "https://x/img=w60-h60-l90-rj"}, {"url": "https://x/img=w120-h120-l90-rj"}]},
        {"videoId": "a", "title": "Dup", "duration_seconds": 200},
        {"videoId": "b", "title": "Mix", "duration_seconds": 3600},
        {"videoId": None, "title": "Broken"},
    ]
    monkeypatch.setattr(music._yt, "search", lambda *a, **k: raw)
    assert music.search("q") == [
        {"video_id": "a", "title": "Song", "artist": "X, Y", "duration_s": 200,
         "thumb": "https://x/img=w320-h320-l90-rj"},
    ]
