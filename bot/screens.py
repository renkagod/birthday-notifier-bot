"""Rich Markdown screens (Bot API 10.1+ rich messages), pure and testable without Telegram.

Controls live inside the message itself (Bot API 10.3): <tg-button> inline in text and
table cells, <tg-button-row> as button blocks. Presses arrive as ordinary callback queries.
"""

from __future__ import annotations

import calendar
import html
from datetime import datetime

from bot.dates import (
    YEARLESS_YEAR,
    age_turning,
    days_until,
    next_birthday_datetime,
    parse_birth_date,
    sort_by_upcoming,
)

# Characters with a meaning in Rich Markdown (emphasis, spoilers, marks, tables, links,
# inline HTML, math, footnotes, entities). Escaping any ASCII punctuation is valid GFM.
_MD_SPECIAL = set("\\`*_~=|[]()<>#!$^&{}")

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS_NOMINATIVE = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
MONTHS_SHORT = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
TIME_PRESETS = ["07:00", "08:00", "09:00", "10:00", "12:00", "18:00", "20:00", "21:00"]

# (value stored in settings, label). Day-based ones fire at notify_time, the rest at midnight.
TIMED_INTERVALS = [
    (30.0, "За месяц"),
    (7.0, "За неделю"),
    (3.0, "За 3 дня"),
    (1.0, "За день"),
    (0.0, "В день рождения"),
]
EXACT_INTERVALS = [
    (0.5, "За 30 минут до 00:00"),
    (0.08, "За 5 минут до 00:00"),
    (-1.0, "Ровно в 00:00"),
]
INTERVAL_LABELS = dict(TIMED_INTERVALS + EXACT_INTERVALS)
ALL_INTERVALS = [value for value, _ in TIMED_INTERVALS + EXACT_INTERVALS]
STANDARD_INTERVALS = [1.0, 0.0, -1.0]

MAX_NAME_LENGTH = 64
HOME_UPCOMING = 5
LIST_PAGE_SIZE = 40

DATE_FORMATS_HELP = (
    "<details><summary>Какие форматы даты я понимаю</summary>\n\n"
    "- `15.08.1990`, `15/08/90`, `15-08`\n"
    "- `3 августа`, `3 авг 1995`, `3 aug`\n"
    "- Год можно не указывать: тогда я не буду считать возраст\n"
    "</details>"
)


def md(text: object) -> str:
    """Escape user-provided text for Rich Markdown and keep it on one line."""
    flat = " ".join(str(text).split())
    return "".join("\\" + ch if ch in _MD_SPECIAL else ch for ch in flat)


# --- Buttons ---
# Markdown is parsed inside inline tags but not inside <tg-button-row> blocks, so button
# text is Markdown-escaped in text/table buttons and HTML-escaped in button rows.

def _attr(value: str) -> str:
    return html.escape(value, quote=True)


def _style(style: str | None) -> str:
    return f' style="{style}"' if style else ""


def cb(text: str, data: str, style: str | None = None) -> str:
    """Callback button for a button row."""
    return f'<tg-button type="callback_data"{_style(style)} data="{_attr(data)}">{html.escape(text)}</tg-button>'


def url_button(text: str, url: str, style: str | None = None) -> str:
    return f'<tg-button type="url"{_style(style)} url="{_attr(url)}">{html.escape(text)}</tg-button>'


def off(text: str) -> str:
    """Disabled button: a caption or a blank cell inside a row."""
    return f'<tg-button type="disabled">{html.escape(text)}</tg-button>'


def link(text: str, data: str) -> str:
    """Callback button shown as a link, for use inside text and table cells."""
    return f'<tg-button type="callback_data" style="link" data="{_attr(data)}">{md(text)}</tg-button>'


def inline_url(text: str, url: str) -> str:
    """URL button for use inside text."""
    return f'<tg-button type="url" url="{_attr(url)}">{md(text)}</tg-button>'


def row(*buttons: str, align: str | None = None) -> str:
    align_attr = f' align="{align}"' if align else ""
    inner = "\n".join(f"  {b}" for b in buttons if b)
    return f"<tg-button-row{align_attr}>\n{inner}\n</tg-button-row>"


def screen(body: str | list[str], *rows: str) -> str:
    text = body if isinstance(body, str) else "\n".join(body)
    controls = "\n".join(r for r in rows if r)
    return f"{text}\n\n{controls}" if controls else text


def home_row() -> str:
    return row(cb("🏠 Главная", "home"))


def cancel_row(data: str = "home") -> str:
    return row(cb("❌ Отмена", data))


def tag_url(tag: str) -> str:
    return f"https://t.me/{tag.lstrip('@')}"


# --- Formatting helpers ---

def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def years_word(n: int) -> str:
    return f"{n} {plural(n, 'год', 'года', 'лет')}"


def when_phrase(days: int) -> str:
    if days == 0:
        return "сегодня"
    if days == 1:
        return "завтра"
    if days == 2:
        return "послезавтра"
    return f"через {days} {plural(days, 'день', 'дня', 'дней')}"


def format_date(day: int, month: int, year: int | None) -> str:
    text = f"{day:02d}.{month:02d}"
    return text if year in (None, YEARLESS_YEAR) else f"{text}.{year}"


def format_bday(date_str: str) -> str:
    try:
        dt = parse_birth_date(date_str)
    except ValueError:
        return date_str
    return format_date(dt.day, dt.month, dt.year)


def birthday_facts(date_str: str, now: datetime) -> tuple[datetime, int, int | None] | None:
    """(next occurrence, days left, age turning or None) for a stored date."""
    try:
        bday = parse_birth_date(date_str)
    except ValueError:
        return None
    target = next_birthday_datetime(bday, now)
    age = None if bday.year == YEARLESS_YEAR else age_turning(bday, target)
    return target, days_until(target, now), age


def _notice(lines: list[str], notice: str | None) -> None:
    if notice:
        lines += [f"> {notice}", ""]


# --- Home ---

def render_home(
    rows: list[tuple],
    now: datetime,
    notify_time: str,
    notice: str | None = None,
    reminders_on: bool = True,
) -> str:
    lines = ["# 🎂 Дни рождения", ""]
    _notice(lines, notice)

    if not rows:
        lines += [
            "Привет! Я напомню о днях рождения близких: заранее и в удобное время.",
            "",
            "**Чтобы добавить человека, просто напишите мне имя и дату:**",
            "",
            "- `Маша 3 августа`",
            "- `Иван Иванов @ivan 12.05.1990`",
            "",
            "Или выберите человека из Telegram: имя и тег я подставлю сам.",
        ]
        return screen(
            lines,
            row(cb("👤 Выбрать из Telegram", "add_tg", "primary"), cb("➕ Добавить", "add")),
            row(cb("⚙️ Настройки", "settings"), cb("❓ Помощь", "help")),
        )

    if not reminders_on:
        lines += [f"> 🔕 Напоминания выключены. {link('Включить', 'settings')}", ""]

    upcoming = []
    for b_id, name, date_str, tag in sort_by_upcoming(rows, now):
        facts = birthday_facts(date_str, now)
        if facts:
            upcoming.append((b_id, name, tag, *facts))

    for b_id, name, tag, _target, days, age in upcoming:
        if days != 0:
            break
        age_part = f": исполняется {years_word(age)}" if age is not None else ""
        greet = f" {inline_url('💬 Поздравить', tag_url(tag))}" if tag else ""
        lines += [f"> 🎉 Сегодня праздник у {link(name, f'view:{b_id}')}{age_part}.{greet}", ""]

    lines += ["### 🗓 Ближайшие", "", "| Когда | Кто | Лет |", "|:--|:--|:--:|"]
    for b_id, name, _tag, target, days, age in upcoming[:HOME_UPCOMING]:
        when = f"**{when_phrase(days)}**" if days <= 1 else when_phrase(days)
        date_part = "" if days == 0 else f", {WEEKDAYS_SHORT[target.weekday()]} {target:%d.%m}"
        lines.append(f"| {when}{date_part} | {link(name, f'view:{b_id}')} | {age if age is not None else '—'} |")

    lines += [
        "",
        f"_Всего {len(rows)} · напоминаю в {notify_time}_",
        "",
        "💡 Напишите `Имя дата`, и я добавлю человека. Напишите только имя, и я его найду.",
    ]
    return screen(
        lines,
        row(cb("➕ Добавить", "add", "primary"), cb(f"📋 Все ({len(rows)})", "list:0"),
            cb("⚙️", "settings")),
    )


def render_help() -> str:
    return screen([
        "## ❓ Как пользоваться",
        "",
        "**Добавить.** Напишите мне `Имя @тег дата`, например `Иван Иванов @ivan 12.05.1990`. "
        "Тег и год не обязательны. Ошиблись? Нажмите «Отменить» под сохранённой записью.",
        "",
        "**Найти.** Напишите имя или его часть, и я покажу карточку.",
        "",
        "**Изменить.** В карточке нажмите «изменить» рядом с датой или тегом.",
        "",
        "**Напоминания.** В «⚙️ Настройках» выберите время и когда напоминать: "
        "за месяц, за неделю, в сам день или ровно в полночь.",
        "",
        DATE_FORMATS_HELP,
        "",
        "<details><summary>Команды</summary>\n\n"
        "- /start: главная\n"
        "- /add: добавить день рождения\n"
        "- /list: весь список\n"
        "- /settings: настройки\n"
        "- /cancel: отменить текущее действие\n"
        "</details>",
    ], home_row())


# --- List / search ---

def _entry(b_id: int, name: str, target: datetime, days: int, age: int | None) -> str:
    age_part = f" · {years_word(age)}" if age is not None else ""
    today = " · 🎉 **сегодня**" if days == 0 else ""
    return f"- **{target.day}** {WEEKDAYS_SHORT[target.weekday()]} · {link(name, f'view:{b_id}')}{age_part}{today}"


def render_list(rows: list[tuple], now: datetime, page: int = 0) -> str:
    """Everyone, in order of the next birthday, grouped by month."""
    if not rows:
        return screen([
            "## 📋 Все дни рождения",
            "",
            "Здесь пока никого нет. Напишите мне `Маша 3 августа`, чтобы добавить первую запись.",
        ], row(cb("➕ Добавить", "add", "primary"), cb("🏠 Главная", "home")))

    entries = []
    for b_id, name, date_str, _tag in sort_by_upcoming(rows, now):
        facts = birthday_facts(date_str, now)
        if facts:
            entries.append((b_id, name, *facts))

    total_pages = max(1, (len(entries) + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = entries[page * LIST_PAGE_SIZE:(page + 1) * LIST_PAGE_SIZE]

    lines = [f"## 📋 Все дни рождения · {len(rows)}"]
    current = None
    for b_id, name, target, days, age in chunk:
        month = (target.year, target.month)
        if month != current:
            current = month
            year = f" {target.year}" if target.year != now.year else ""
            lines += ["", f"### {MONTHS_NOMINATIVE[target.month - 1]}{year}", ""]
        lines.append(_entry(b_id, name, target, days, age))

    rows_out = []
    if total_pages > 1:
        rows_out.append(row(
            cb("◀️", f"list:{page - 1}") if page > 0 else off("·"),
            off(f"{page + 1} / {total_pages}"),
            cb("▶️", f"list:{page + 1}") if page < total_pages - 1 else off("·"),
            align="center",
        ))
    rows_out.append(row(cb("➕ Добавить", "add"), cb("🏠 Главная", "home")))
    return screen(lines, *rows_out)


def render_search(query: str, matches: list[tuple], now: datetime) -> str:
    if not matches:
        return screen([
            f"## 🔎 «{md(query)}»",
            "",
            "Никого с таким именем нет в списке. Добавить нового человека?",
        ], row(cb(f"➕ Добавить «{query[:24]}»", "add_pending", "primary"), cb("🏠 Главная", "home")))

    lines = [f"## 🔎 «{md(query)}»", ""]
    for b_id, name, date_str, _tag in sort_by_upcoming(matches, now):
        facts = birthday_facts(date_str, now)
        if facts:
            target, days, age = facts
            lines.append(f"- {link(name, f'view:{b_id}')}: {md(format_bday(date_str))}, {when_phrase(days)}")
    return screen(lines, row(cb(f"➕ Добавить «{query[:24]}»", "add_pending"), cb("🏠 Главная", "home")))


# --- Card ---

def render_card(
    b_id: int,
    name: str,
    date_str: str,
    tag: str | None,
    now: datetime,
    *,
    notice: str | None = None,
    undo: bool = False,
) -> str:
    lines = [f"## 👤 {md(name)}", ""]
    _notice(lines, notice)
    lines.append(f"- 📅 **{md(format_bday(date_str))}** · {link('изменить', f'edit_date:{b_id}')}")
    facts = birthday_facts(date_str, now)
    if facts:
        target, days, age = facts
        lines.append(f"- ⏳ **{when_phrase(days)}** · {WEEKDAYS[target.weekday()]}, {target:%d.%m}")
        if age is not None:
            lines.append(f"- 🎈 исполнится **{years_word(age)}**")
    tag_part = md(tag) if tag else "тег не указан"
    lines.append(f"- 🔗 {tag_part} · {link('изменить имя и тег', f'edit_name:{b_id}')}")
    if facts and facts[1] == 0:
        lines += ["", "> 🎉 День рождения сегодня! Не забудьте поздравить."]

    rows = []
    if tag:
        rows.append(row(url_button("💬 Написать", tag_url(tag), "success")))
    if undo:
        rows.append(row(cb("↩️ Отменить добавление", f"undo:{b_id}"), cb("➕ Ещё", "add", "primary")))
    rows.append(row(
        cb("🗑 Удалить", f"del:{b_id}", "danger"),
        cb("📋 Все", "list:0"),
        cb("🏠 Главная", "home"),
    ))
    return screen(lines, *rows)


def render_delete_confirm(b_id: int, name: str) -> str:
    return screen([
        "## 🗑 Удалить запись?",
        "",
        f"Запись **{md(name)}** пропадёт из списка вместе с напоминаниями. "
        "Отменить удаление нельзя.",
    ], row(cb("🗑 Да, удалить", f"del_yes:{b_id}", "danger"), cb("Оставить", f"view:{b_id}")))


def render_edit_name_prompt(b_id: int, name: str, tag: str | None) -> str:
    tag_part = md(tag) if tag else "не указан"
    return screen([
        f"## ✏️ {md(name)}",
        "",
        f"Сейчас: **{md(name)}**, тег {tag_part}",
        "",
        "Пришлите новое имя и, если нужно, @тег, например `Иван @ivan`. "
        "Без тега в сообщении тег будет удалён.",
    ], cancel_row(f"view:{b_id}"))


def edit_date_rows(b_id: int) -> list[str]:
    return [row(cb("📅 Календарь", "cal", "primary"), cb("❌ Отмена", f"view:{b_id}"))]


def render_edit_date_prompt(b_id: int, name: str, date_str: str) -> str:
    return screen([
        f"## 📅 {md(name)}",
        "",
        f"Сейчас: **{md(format_bday(date_str))}**",
        "",
        "Пришлите новую дату, например `15.08.1990`, `22.10` или `3 августа`, "
        "или выберите её в календаре.",
        "",
        DATE_FORMATS_HELP,
    ], *edit_date_rows(b_id))


# --- Add flow ---

def render_add_prompt(prefilled_tag: str | None = None) -> str:
    lines = ["## ➕ Кого добавим?", ""]
    if prefilled_tag:
        lines += [f"Тег {md(prefilled_tag)} уже запомнил. Осталось имя и дата.", ""]
    lines += [
        "Напишите имя и дату одним сообщением, @тег по желанию:",
        "",
        "- `Маша 3 августа`",
        "- `Иван Иванов @ivan 12.05.1990`",
        "- `Петя`, а дату выберем в календаре",
        "",
        DATE_FORMATS_HELP,
    ]
    return screen(lines, row(cb("👤 Выбрать из Telegram", "add_tg"), cb("❌ Отмена", "home")))


def date_prompt_rows() -> list[str]:
    return [row(cb("📅 Календарь", "cal", "primary"), cb("❌ Отмена", "home"))]


def render_date_prompt(name: str, tag: str | None) -> str:
    who = f"**{md(name)}**" + (f" ({md(tag)})" if tag else "")
    return screen([
        "## 📅 Когда день рождения?",
        "",
        f"👤 {who}",
        "",
        "Пришлите дату, например `15.08.1990` или `3 августа`, или выберите её в календаре.",
        "",
        DATE_FORMATS_HELP,
    ], *date_prompt_rows())


def render_replace_confirm(
    name: str,
    tag: str | None,
    day: int,
    month: int,
    year: int | None,
    old_date: str,
) -> str:
    return screen([
        "## ⚠️ Такое имя уже есть",
        "",
        f"**{md(name)}** уже в списке с датой **{md(format_bday(old_date))}**.",
        "",
        f"Заменить на **{format_date(day, month, year)}**"
        + (f" и тег {md(tag)}" if tag else "") + "?",
    ], row(cb("✅ Заменить", "confirm_yes", "primary"), cb("❌ Отмена", "home")))


# --- Calendar picker ---

def _picker(name: str | None, step: str, rows: list[str], year: int | None = None,
            month: int | None = None) -> str:
    title = f"## 📅 {md(name)}" if name else "## 📅 Дата рождения"
    chosen = []
    if year == YEARLESS_YEAR:
        chosen.append("без года")
    elif year:
        chosen.append(f"**{year}**")
    if month:
        chosen.append(f"**{MONTHS_NOMINATIVE[month - 1].lower()}**")
    lines = [title, ""]
    if chosen:
        lines += ["Выбрано: " + ", ".join(chosen), ""]
    lines.append(step)
    return screen(lines, *rows)


def render_decade_picker(name: str | None, this_year: int) -> str:
    start = (this_year // 10) * 10
    decades = [cb(f"{d}-е", f"dec:{d}") for d in range(start, start - 80, -10)]
    rows = [row(*decades[i:i + 4]) for i in range(0, len(decades), 4)]
    rows.append(row(cb("🤷 Год не знаю", "noyear"), cb("❌ Отмена", "picker_cancel")))
    return _picker(name, "Выберите десятилетие рождения:", rows)


def render_year_picker(name: str | None, decade: int, this_year: int) -> str:
    years = [cb(str(y), f"year:{y}") for y in range(decade + 9, decade - 1, -1) if y <= this_year]
    rows = [row(*years[i:i + 5]) for i in range(0, len(years), 5)]
    rows.append(row(cb("🔙 Назад", "back_dec")))
    return _picker(name, "Выберите год:", rows)


def render_month_picker(name: str | None, year: int) -> str:
    months = [cb(MONTHS_SHORT[m], f"month:{m + 1}") for m in range(12)]
    rows = [row(*months[i:i + 4]) for i in range(0, 12, 4)]
    rows.append(row(cb("🔙 Назад", "back_dec" if year == YEARLESS_YEAR else "back_year")))
    return _picker(name, "Выберите месяц:", rows, year=year)


def render_day_picker(name: str | None, year: int, month: int) -> str:
    rows = [row(*(off(d) for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]))]
    for week in calendar.monthcalendar(year, month):
        rows.append(row(*(cb(str(day), f"day:{day}") if day else off("·") for day in week)))
    rows.append(row(cb("🔙 Назад", "back_month")))
    return _picker(name, "Выберите число:", rows, year=year, month=month)


# --- Settings ---

def render_settings(
    notify_time: str,
    intervals: list[float],
    total: int,
    notice: str | None = None,
) -> str:
    def task(value: float, label: str) -> str:
        on = value in intervals
        toggle = link("выключить" if on else "включить", f"int:{value}")
        return f"- [{'x' if on else ' '}] {label} · {toggle}"

    presets = [cb(t, f"time:{t}", "primary" if t == notify_time else None) for t in TIME_PRESETS]
    lines = ["## ⚙️ Настройки", ""]
    _notice(lines, notice)
    lines += [
        f"### ⏰ Напоминаю в {notify_time}",
        "",
        row(*presets[:4]),
        row(*presets[4:]),
        "",
        "Другое время пришлите сообщением, например `08:30`.",
        "",
        "### 🔔 Когда напоминать",
        "",
        f"**В {notify_time}:**",
        "",
        *(task(v, label) for v, label in TIMED_INTERVALS),
        "",
        "**Ровно к началу дня:**",
        "",
        *(task(v, label) for v, label in EXACT_INTERVALS),
        "",
        row(cb("🔔 Всё", "ints:all"), cb("⭐ Стандарт", "ints:default"), cb("🔕 Ничего", "ints:none")),
        "",
        "### 💾 Резервная копия",
        "",
        f"JSON-файл со всеми записями ({total}). При импорте совпадающие имена обновятся.",
        "",
        row(cb("📤 Экспорт", "export"), cb("📥 Импорт", "import")),
    ]
    return screen(lines, home_row())


def render_import_prompt() -> str:
    return screen([
        "## 📥 Импорт",
        "",
        "Пришлите JSON-файл, который я выгружал при экспорте.",
        "",
        "<details><summary>Формат файла</summary>\n\n"
        "```json\n"
        '[{"name": "Иван", "date": "15.08.1990", "tag": "@ivan"},\n'
        ' {"name": "Маша", "date": "03.08"}]\n'
        "```\n"
        "</details>",
    ], cancel_row("settings"))


def render_import_result(added: int, updated: int, skipped: int) -> str:
    lines = [
        "## ✅ Импорт завершён",
        "",
        "| Добавлено | Обновлено | Пропущено |",
        "|:--:|:--:|:--:|",
        f"| {added} | {updated} | {skipped} |",
    ]
    if skipped:
        lines += ["", "_Пропущены записи без имени или с неверной датой._"]
    return screen(lines, row(cb("📋 Все", "list:0"), cb("🏠 Главная", "home")))
