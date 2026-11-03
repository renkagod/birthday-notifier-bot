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


def test_records_word():
    assert screens.records_word(23) == "23 записи"
    assert screens.records_word(25) == "25 записей"
    assert screens.records_word(21) == "21 запись"


def test_when_phrase():
    assert screens.when_phrase(0) == "сегодня"
    assert screens.when_phrase(1) == "завтра"
    assert screens.when_phrase(5) == "через 5 дней"
    assert screens.when_phrase(7) == "через неделю"
    assert screens.when_phrase(22) == "через 22 дня"


def test_brief_names_are_never_declined():
    rows = [(1, "A|B", "17.10.1990", None), (2, "Маша", "16.10.1004", "@masha")]
    text = screens.render_brief(rows, NOW)
    assert "## 16 октября, пятница" in text
    assert 'Сегодня день рождения — **<tg-button type="callback_data" style="link" data="view:2">Маша' in text
    assert 'data="view:1">A\\|B</tg-button>, исполнится 36' in text
    assert 'url="https://t.me/masha"' in text
    assert " у " not in text


def test_brief_without_anything_soon_names_the_next_one():
    text = screens.render_brief([(5, "Игорь", "09.01.1985", None)], NOW)
    assert "В ближайший месяц дней рождения нет" in text
    assert "9 января" in text


def test_brief_caps_long_month():
    rows = [(i, f"P{i}", f"{17 + i:02d}.10.1990", None) for i in range(12)]
    text = screens.render_brief(rows, NOW)
    assert "И ещё 4 в ближайший месяц." in text


def test_empty_brief_is_onboarding():
    text = screens.render_brief([], NOW)
    assert "`Маша 3 августа`" in text
    assert 'data="add_tg"' in text


def test_list_one_line_per_month_from_current():
    rows = [(1, "Янв", "05.01.1990", None), (2, "Окт", "20.10.1990", None), (3, "Ранний", "01.10.1990", None)]
    text = screens.render_list(rows, NOW)
    assert text.index("**Октябрь**") < text.index("**Январь 2027**") < text.index("**Октябрь 2027**")


def test_list_pages_edit_in_place():
    rows = [(i, f"P{i}", "20.10.1990", None) for i in range(45)]
    text = screens.render_list(rows, NOW)
    assert 'data="page:1"' in text
    assert "1 из 2" in text


def test_search_without_matches_offers_add():
    text = screens.render_search("Петя", [], NOW)
    assert 'data="add_pending"' in text


def test_person_yearless_has_no_age_and_explains_reply():
    text = screens.render_person(7, "Маша", "03.08.1004", None, NOW)
    assert "исполнится" not in text
    assert "3 августа, год не указан" in text
    assert "ответьте на это сообщение" in text
    assert 'data="edit_date:7"' in text
    assert 'data="del:7"' in text


def test_person_shows_note_as_quote():
    text = screens.render_person(7, "Маша", "03.08.1004", None, NOW, note="Книга *про* горы\n\n- носки")
    assert "> Книга \\*про\\* горы\n>\n> - носки" in text
    assert 'data="note:7">Изменить заметку' in text


def test_person_without_note_offers_one():
    text = screens.render_person(7, "Маша", "03.08.1004", None, NOW)
    assert 'data="note:7">Добавить заметку' in text
    assert "\n> " not in text


def test_note_prompt_can_delete_existing():
    assert 'data="note_del:7"' in screens.render_note_prompt(7, "Маша", "идея")
    assert "note_del" not in screens.render_note_prompt(7, "Маша", None)


def test_added_person_can_be_undone():
    text = screens.render_added(7, "Маша", "03.08.1004", "@masha", NOW)
    assert 'data="undo:7"' in text
    assert 'url="https://t.me/masha"' in text


def test_deleted_can_be_restored():
    assert 'data="restore:4"' in screens.render_deleted(4, "Дима")


def test_settings_lists_custom_days_and_plain_labels():
    text = screens.render_settings("09:00", [14.0, 7.0, 1.0, -1.0])
    assert "## Напоминания в 09:00" in text
    assert "- [x] " in text and 'data="int:14">За 14 дней' in text
    assert 'data="int:1">За день' in text
    assert "Накануне" not in text
    assert 'data="int:30">За месяц' in text and "- [ ] " in text
    assert text.index("За 14 дней") < text.index("За неделю")


@pytest.mark.parametrize(
    ("value", "label"),
    [(30.0, "За месяц"), (14.0, "За 14 дней"), (2.0, "За 2 дня"), (21.0, "За 21 день"),
     (1.0, "За день"), (0.0, "В день рождения"), (-1.0, "Ровно в полночь")],
)
def test_interval_label(value, label):
    assert screens.interval_label(value) == label


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("9:00", "09:00"), ("09.30", "09:30"), ("2115", "21:15"), ("24:00", None), ("abc", None)],
)
def test_normalize_notify_time(raw, expected):
    assert normalize_notify_time(raw) == expected
