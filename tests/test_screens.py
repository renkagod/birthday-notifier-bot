from datetime import datetime

import pytest
from bot import screens
from bot.dates import normalize_notify_time

NOW = datetime(2026, 10, 16)


def test_md_escapes_markup_and_flattens_lines():
    assert screens.md("a*b_c|d\n[x](y)") == r"a\*b\_c\|d \[x\]\(y\)"
    assert screens.md("Иван-Петров. @ivan") == "Иван-Петров. @ivan"


@pytest.mark.parametrize(
    ("n", "expected"),
    [(1, "1 год"), (2, "2 года"), (5, "5 лет"), (11, "11 лет"), (21, "21 год"), (34, "34 года")],
)
def test_years_word(n, expected):
    assert screens.years_word(n) == expected


def test_when_phrase():
    assert screens.when_phrase(0) == "сегодня"
    assert screens.when_phrase(1) == "завтра"
    assert screens.when_phrase(5) == "через 5 дней"
    assert screens.when_phrase(22) == "через 22 дня"


def test_list_table_escapes_names():
    rows = [(1, "A|B", "17.10.1990", None), (2, "Маша", "16.10.1004", "@masha")]
    text = screens.render_list(rows, now=NOW, sort_by="date", page=0, total_pages=1, total=2)
    assert "| **A\\|B** | 17.10.1990 | завтра |" in text
    assert "| **Маша** | 16.10 | **сегодня** 🎉 |" in text


def test_card_yearless_has_no_age():
    text = screens.render_card("Маша", "03.08.1004", None, NOW)
    assert "Исполнится" not in text
    assert "03.08" in text
    assert "не указан" in text


def test_home_highlights_today():
    rows = [(1, "Маша", "16.10.1990", None)]
    text = screens.render_home(rows, NOW, "09:00")
    assert "Сегодня празднует **Маша**" in text
    assert "исполнится 36 лет" in text


def test_intervals_task_list():
    text = screens.render_intervals([7.0, -1.0], "09:00")
    assert "- [x] За неделю" in text
    assert "- [ ] За месяц" in text
    assert "- [x] Ровно в 00:00" in text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("9:00", "09:00"), ("09.30", "09:30"), ("2115", "21:15"), ("24:00", None), ("abc", None)],
)
def test_normalize_notify_time(raw, expected):
    assert normalize_notify_time(raw) == expected
