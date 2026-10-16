from datetime import datetime

import pytest
from bot import screens
from bot.dates import normalize_notify_time

NOW = datetime(2026, 10, 16)


def test_md_escapes_markup_and_flattens_lines():
    assert screens.md("a*b_c|d\n[x](y)") == r"a\*b\_c\|d \[x\]\(y\)"
    assert screens.md("Иван-Петров. @ivan") == "Иван-Петров. @ivan"


def test_link_escapes_markdown_text_and_attribute():
    assert screens.link("A*B", 'x"y') == (
        '<tg-button type="callback_data" style="link" data="x&quot;y">A\\*B</tg-button>'
    )


def test_row_button_escapes_html_text():
    assert screens.cb("<b>", "home") == '<tg-button type="callback_data" data="home">&lt;b&gt;</tg-button>'
    assert screens.row(screens.cb("1", "a")).splitlines()[0] == "<tg-button-row>"


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


def test_home_upcoming_table_links_names():
    rows = [(1, "A|B", "17.10.1990", None), (2, "Маша", "16.10.1004", "@masha")]
    text = screens.render_home(rows, NOW, "09:00")
    assert 'data="view:1">A\\|B</tg-button> | 36 |' in text
    assert "Сегодня праздник у" in text
    assert 'url="https://t.me/masha"' in text


def test_empty_home_is_onboarding():
    text = screens.render_home([], NOW, "09:00")
    assert "`Маша 3 августа`" in text
    assert 'data="add_tg"' in text


def test_list_groups_by_month_from_current():
    rows = [(1, "Янв", "05.01.1990", None), (2, "Окт", "20.10.1990", None), (3, "Ранний", "01.10.1990", None)]
    text = screens.render_list(rows, NOW)
    assert text.index("### Октябрь\n") < text.index("### Январь 2027") < text.index("### Октябрь 2027")


def test_search_without_matches_offers_add():
    text = screens.render_search("Петя", [], NOW)
    assert 'data="add_pending"' in text


def test_card_yearless_has_no_age():
    text = screens.render_card(7, "Маша", "03.08.1004", None, NOW, undo=True)
    assert "исполнится" not in text
    assert "03.08" in text
    assert 'data="undo:7"' in text
    assert 'data="edit_date:7"' in text


def test_settings_marks_current_time_and_intervals():
    text = screens.render_settings("09:00", [7.0, -1.0], total=3)
    assert 'style="primary" data="time:09:00"' in text
    assert "- [x] За неделю" in text
    assert "- [ ] За месяц" in text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("9:00", "09:00"), ("09.30", "09:30"), ("2115", "21:15"), ("24:00", None), ("abc", None)],
)
def test_normalize_notify_time(raw, expected):
    assert normalize_notify_time(raw) == expected
