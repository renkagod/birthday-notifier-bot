"""Rich Markdown messages (Bot API 10.1+ rich messages), pure and testable without Telegram.

The chat is the interface: every message is a short record that stays readable later. The
brief (/start and the morning digest) is the home, a person is a small card that is edited by
replying to it, and buttons are kept for actions. Controls live inside the message itself
(Bot API 10.3): <tg-button> inline in text, <tg-button-row> as button blocks.
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
MONTHS_NOMINATIVE = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
MONTHS_GENITIVE = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
MONTHS_SHORT = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]

# Stored interval values. Whole non-negative numbers are days before the birthday and fire at
# notify_time (any number of days can be added by the user); the rest fire around midnight.
DAY_INTERVALS = [30.0, 7.0, 3.0, 1.0, 0.0]
NIGHT_INTERVALS = [-1.0, 0.5, 0.08]
NIGHT_LABELS = {
    -1.0: "Ровно в полночь",
    0.5: "За 30 минут до полуночи",
    0.08: "За 5 минут до полуночи",
}
ALL_INTERVALS = DAY_INTERVALS + NIGHT_INTERVALS
MAX_REMIND_DAYS = 365

MAX_NAME_LENGTH = 64
BRIEF_LINES = 8
BRIEF_HORIZON = 31
LIST_PAGE_SIZE = 40

DATE_FORMATS_HELP = (
    "<details><summary>Какие даты я понимаю</summary>\n\n"
    "- `15.08.1990`, `15/08/90`, `15-08`\n"
    "- `3 августа`, `3 авг 1995`, `3 aug`\n"
    "- Без года тоже можно, тогда возраст не считаю\n"
    "</details>"
)


def md(text: object) -> str:
    """Escape user-provided text for Rich Markdown and keep it on one line."""
    flat = " ".join(str(text).split())
    return "".join("\\" + ch if ch in _MD_SPECIAL else ch for ch in flat)


# --- Buttons ---
# Markdown is parsed inside inline tags but not inside <tg-button-row> blocks, so button
# text is Markdown-escaped in text buttons and HTML-escaped in button rows.

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
    """Callback button shown as a link, for use inside text."""
    return f'<tg-button type="callback_data" style="link" data="{_attr(data)}">{md(text)}</tg-button>'


def inline_url(text: str, url: str) -> str:
    """URL button for use inside text."""
    return f'<tg-button type="url" url="{_attr(url)}">{md(text)}</tg-button>'


def row(*buttons: str, align: str | None = None) -> str:
    align_attr = f' align="{align}"' if align else ""
    inner = "\n".join(f"  {b}" for b in buttons if b)
    return f"<tg-button-row{align_attr}>\n{inner}\n</tg-button-row>"


def links(*buttons: str) -> str:
    """A quiet row of link-styled callback buttons, aligned with the text."""
    return row(*buttons, align="left")


def screen(body: str | list[str], *rows: str) -> str:
    text = body if isinstance(body, str) else "\n".join(body)
    controls = "\n".join(r for r in rows if r)
    return f"{text}\n\n{controls}" if controls else text


def footer(text: str) -> str:
    return f"<footer>{text}</footer>"


def tag_url(tag: str) -> str:
    return f"https://t.me/{tag.lstrip('@')}"


def nav_row(total: int) -> str:
    return links(
        cb(f"Все {total}" if total else "Все", "list:0", "link"),
        cb("Напоминания", "settings", "link"),
        cb("Помощь", "help", "link"),
    )


def back_row(data: str = "cancel", text: str = "Отмена") -> str:
    return links(cb(text, data, "link"))


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


def days_word(n: int) -> str:
    return f"{n} {plural(n, 'день', 'дня', 'дней')}"


def records_word(n: int) -> str:
    return f"{n} {plural(n, 'запись', 'записи', 'записей')}"


def when_phrase(days: int) -> str:
    if days == 0:
        return "сегодня"
    if days == 1:
        return "завтра"
    if days == 2:
        return "послезавтра"
    if days == 7:
        return "через неделю"
    return f"через {days_word(days)}"


def capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def day_month(dt: datetime) -> str:
    return f"{dt.day} {MONTHS_GENITIVE[dt.month - 1]}"


def format_date(day: int, month: int, year: int | None) -> str:
    text = f"{day:02d}.{month:02d}"
    return text if year in (None, YEARLESS_YEAR) else f"{text}.{year}"


def format_bday(date_str: str) -> str:
    try:
        dt = parse_birth_date(date_str)
    except ValueError:
        return date_str
    return format_date(dt.day, dt.month, dt.year)


def birth_phrase(date_str: str) -> str:
    """"12 ноября 1988" or "3 августа, год не указан"."""
    try:
        dt = parse_birth_date(date_str)
    except ValueError:
        return md(date_str)
    if dt.year == YEARLESS_YEAR:
        return f"{day_month(dt)}, год не указан"
    return f"{day_month(dt)} {dt.year}"


def birthday_facts(date_str: str, now: datetime) -> tuple[datetime, int, int | None] | None:
    """(next occurrence, days left, age turning or None) for a stored date."""
    try:
        bday = parse_birth_date(date_str)
    except ValueError:
        return None
    target = next_birthday_datetime(bday, now)
    age = None if bday.year == YEARLESS_YEAR else age_turning(bday, target)
    return target, days_until(target, now), age


def turns(age: int | None, days: int) -> str:
    """", исполнится 35" / ", исполняется 62" / ""."""
    if age is None:
        return ""
    return f", {'исполняется' if days == 0 else 'исполнится'} {age}"


def upcoming(rows: list[tuple], now: datetime) -> list[tuple]:
    """(id, name, tag, target, days, age) in order of the next birthday."""
    out = []
    for b_id, name, date_str, tag in sort_by_upcoming(rows, now):
        facts = birthday_facts(date_str, now)
        if facts:
            out.append((b_id, name, tag, *facts))
    return out


def interval_label(value: float) -> str:
    if value in NIGHT_LABELS:
        return NIGHT_LABELS[value]
    days = int(value)
    if days == 0:
        return "В день рождения"
    if days == 30:
        return "За месяц"
    if days == 7:
        return "За неделю"
    if days == 1:
        return "За день"
    return f"За {days_word(days)}"


def is_day_interval(value: float) -> bool:
    return value >= 0 and float(value).is_integer()


def _notice(lines: list[str], notice: str | None) -> None:
    if notice:
        lines += [f"> {notice}", ""]


def today_line(b_id: int, name: str, tag: str | None, age: int | None) -> str:
    greet = f" {inline_url('Написать', tag_url(tag))}" if tag else ""
    return f"Сегодня день рождения — **{link(name, f'view:{b_id}')}**{turns(age, 0)}.{greet}"


def soon_line(b_id: int, name: str, target: datetime, days: int, age: int | None) -> str:
    when = capitalize(when_phrase(days)) if days <= 7 else day_month(target)
    return f"**{when}** — {link(name, f'view:{b_id}')}{turns(age, days)}"


# --- Brief: /start, and what the morning digest looks like ---

def render_welcome(notice: str | None = None) -> str:
    lines = ["## Дни рождения", ""]
    _notice(lines, notice)
    lines += [
        "Напишите имя и дату — я запомню и напомню заранее: `Маша 3 августа` "
        "или `Иван @ivan 15.08.1990`.",
        "",
        "Напишите только имя — покажу этого человека.",
        "",
        DATE_FORMATS_HELP,
    ]
    return screen(lines, row(cb("Выбрать из контактов Telegram", "add_tg")), nav_row(0))


def render_brief(
    rows: list[tuple],
    now: datetime,
    notice: str | None = None,
    reminders_on: bool = True,
) -> str:
    if not rows:
        return render_welcome(notice)

    lines = [f"## {day_month(now)}, {WEEKDAYS[now.weekday()]}", ""]
    _notice(lines, notice)
    if not reminders_on:
        lines += [f"> Напоминания выключены. {link('Включить', 'settings')}", ""]

    people = upcoming(rows, now)
    for b_id, name, tag, _target, days, age in people:
        if days == 0:
            lines += [today_line(b_id, name, tag, age), ""]

    near = [p for p in people if 0 < p[4] <= BRIEF_HORIZON]
    for b_id, name, _tag, target, days, age in near[:BRIEF_LINES]:
        lines += [soon_line(b_id, name, target, days, age), ""]
    if len(near) > BRIEF_LINES:
        rest = len(near) - BRIEF_LINES
        lines += [f"И ещё {rest} в ближайший месяц.", ""]

    if not near and not any(p[4] == 0 for p in people):
        b_id, name, _tag, target, days, _age = people[0]
        lines += [
            f"В ближайший месяц дней рождения нет. Следующий — {link(name, f'view:{b_id}')}, "
            f"{day_month(target)}, {when_phrase(days)}.",
            "",
        ]
    return screen(lines, nav_row(len(rows)))


def render_help() -> str:
    return screen([
        "## Как пользоваться",
        "",
        "**Добавить.** Напишите имя и дату: `Маша 3 августа`, `Иван @ivan 15.08.1990`. "
        "Тег и год не обязательны.",
        "",
        "**Найти.** Напишите имя или его часть.",
        "",
        "**Исправить.** Ответьте на сообщение с человеком: датой `13.11.1988`, "
        "новым именем `Дмитрий` или тегом `@dima`. Чтобы убрать тег, ответьте `без тега`.",
        "",
        "**Напоминания.** Утром в выбранное время приходит одна сводка: кому сегодня, "
        "завтра, через неделю. Время и дни настраиваются в «Напоминаниях».",
        "",
        DATE_FORMATS_HELP,
        "",
        "<details><summary>Команды</summary>\n\n"
        "- /start — сводка\n"
        "- /add — добавить человека\n"
        "- /list — все записи\n"
        "- /settings — напоминания\n"
        "- /cancel — отменить текущее действие\n"
        "</details>",
    ], row(cb("Выбрать из контактов Telegram", "add_tg")))


# --- All / search ---

def render_list(rows: list[tuple], now: datetime, page: int = 0) -> str:
    """Everyone, in order of the next birthday, one line per month."""
    if not rows:
        return render_welcome()

    people = upcoming(rows, now)
    total_pages = max(1, (len(people) + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = people[page * LIST_PAGE_SIZE:(page + 1) * LIST_PAGE_SIZE]

    lines = [f"## Все, {len(rows)}", ""]
    month_key, month_items = None, []

    def flush():
        if month_items:
            target = month_key[2]
            year = f" {target.year}" if target.year != now.year else ""
            lines.extend([f"**{MONTHS_NOMINATIVE[target.month - 1]}{year}**  " + ", ".join(month_items), ""])
            month_items.clear()

    for b_id, name, _tag, target, _days, _age in chunk:
        key = (target.year, target.month, target)
        if month_key is None or key[:2] != month_key[:2]:
            flush()
            month_key = key
        month_items.append(f"{target.day} {link(name, f'view:{b_id}')}")
    flush()
    lines.append(footer("Отсчёт от сегодняшнего дня. Напишите имя, чтобы открыть человека."))

    controls = []
    if total_pages > 1:
        controls.append(links(
            cb("‹ Назад", f"page:{page - 1}", "link") if page > 0 else "",
            off(f"{page + 1} из {total_pages}"),
            cb("Дальше ›", f"page:{page + 1}", "link") if page < total_pages - 1 else "",
        ))
    return screen(lines, *controls)


def render_search(query: str, matches: list[tuple], now: datetime) -> str:
    short = query[:24]
    if not matches:
        return screen([
            f"Никого с именем «{md(query)}» нет.",
            "",
            footer(f"Можно сразу с датой: `{md(short)} 3 августа`."),
        ], row(cb(f"Добавить «{short}»", "add_pending")))

    lines = [f"## «{md(query)}»", ""]
    for b_id, name, _tag, target, days, _age in upcoming(matches, now):
        lines += [f"{link(name, f'view:{b_id}')} — {day_month(target)}, {when_phrase(days)}", ""]
    lines.append(footer(f"Нет нужного? {link(f'Добавить «{short}»', 'add_pending')}"))
    return screen(lines)


# --- Person ---

def render_person(
    b_id: int,
    name: str,
    date_str: str,
    tag: str | None,
    now: datetime,
    *,
    notice: str | None = None,
) -> str:
    lines = []
    _notice(lines, notice)
    lines += [f"**{md(name)}**" + (f"  {md(tag)}" if tag else ""), "", birth_phrase(date_str), ""]
    facts = birthday_facts(date_str, now)
    if facts:
        target, days, age = facts
        if days == 0:
            age_part = f", исполняется {years_word(age)}" if age is not None else ""
            lines += [f"**Сегодня**{age_part}", ""]
        else:
            age_part = f", исполнится {years_word(age)}" if age is not None else ""
            lines += [f"{capitalize(when_phrase(days))}, {WEEKDAYS[target.weekday()]}{age_part}", ""]

    buttons = []
    if tag:
        buttons.append(url_button("Написать", tag_url(tag)))
    buttons.append(cb("Удалить", f"del:{b_id}"))
    lines.append(footer(
        "Чтобы исправить, ответьте на это сообщение: `13.11.1988`, `Дмитрий` или `@dima`. "
        f"Дату можно {link('выбрать в календаре', f'edit_date:{b_id}')}."
    ))
    return screen(lines, row(*buttons))


def render_deleted(b_id: int, name: str) -> str:
    return screen(f"~~{md(name)}~~ удалён из списка. {link('Вернуть', f'restore:{b_id}')}")


def render_added(b_id: int, name: str, date_str: str, tag: str | None, now: datetime) -> str:
    return render_person(b_id, name, date_str, tag, now,
                         notice=f"Запомнил. {link('Отменить', f'undo:{b_id}')}")


def render_undone(name: str) -> str:
    return f"~~{md(name)}~~ не сохранён."


# --- Add flow ---

def render_add_prompt(prefilled_tag: str | None = None) -> str:
    lines = []
    if prefilled_tag:
        lines += [f"Тег {md(prefilled_tag)} запомнил. Напишите имя и дату.", ""]
    else:
        lines += ["Напишите имя и дату одним сообщением: `Маша 3 августа` или `Иван @ivan 15.08.1990`.", ""]
    lines += ["Можно только имя — дату тогда выберем в календаре.", "", DATE_FORMATS_HELP]
    return screen(lines, row(cb("Выбрать из контактов Telegram", "add_tg")), back_row())


def date_prompt_rows() -> list[str]:
    return [row(cb("Выбрать в календаре", "cal")), back_row()]


def render_date_prompt(name: str, tag: str | None) -> str:
    who = f"**{md(name)}**" + (f" {md(tag)}" if tag else "")
    return screen([
        f"{who} — когда день рождения?",
        "",
        "Напишите дату: `15.08.1990`, `22.10` или `3 августа`.",
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
    new = format_date(day, month, year) + (f" и тег {md(tag)}" if tag else "")
    return screen([
        f"**{md(name)}** уже есть в списке: {md(format_bday(old_date))}.",
        "",
        f"Заменить на {new}?",
    ], row(cb("Заменить", "confirm_yes"), cb("Оставить как было", "cancel")))


# --- Calendar picker ---

def _picker(name: str | None, step: str, rows: list[str], year: int | None = None,
            month: int | None = None) -> str:
    title = f"**{md(name)}** — дата рождения" if name else "**Дата рождения**"
    chosen = []
    if year == YEARLESS_YEAR:
        chosen.append("без года")
    elif year:
        chosen.append(str(year))
    if month:
        chosen.append(MONTHS_NOMINATIVE[month - 1].lower())
    lines = [title, ""]
    if chosen:
        lines += ["Выбрано: " + ", ".join(chosen), ""]
    lines.append(step)
    return screen(lines, *rows)


def render_decade_picker(name: str | None, this_year: int) -> str:
    start = (this_year // 10) * 10
    decades = [cb(f"{d}-е", f"dec:{d}") for d in range(start, start - 80, -10)]
    rows = [row(*decades[i:i + 4]) for i in range(0, len(decades), 4)]
    rows.append(row(cb("Год не знаю", "noyear")))
    rows.append(back_row("picker_cancel"))
    return _picker(name, "Выберите десятилетие:", rows)


def render_year_picker(name: str | None, decade: int, this_year: int) -> str:
    years = [cb(str(y), f"year:{y}") for y in range(decade + 9, decade - 1, -1) if y <= this_year]
    rows = [row(*years[i:i + 5]) for i in range(0, len(years), 5)]
    rows.append(back_row("back_dec", "‹ Назад"))
    return _picker(name, "Выберите год:", rows)


def render_month_picker(name: str | None, year: int) -> str:
    months = [cb(MONTHS_SHORT[m], f"month:{m + 1}") for m in range(12)]
    rows = [row(*months[i:i + 4]) for i in range(0, 12, 4)]
    rows.append(back_row("back_dec" if year == YEARLESS_YEAR else "back_year", "‹ Назад"))
    return _picker(name, "Выберите месяц:", rows, year=year)


def render_day_picker(name: str | None, year: int, month: int) -> str:
    rows = [row(*(off(d) for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]))]
    for week in calendar.monthcalendar(year, month):
        rows.append(row(*(cb(str(day), f"day:{day}") if day else off(" ") for day in week)))
    rows.append(back_row("back_month", "‹ Назад"))
    return _picker(name, "Выберите число:", rows, year=year, month=month)


# --- Reminders ---

def render_settings(notify_time: str, intervals: list[float], notice: str | None = None) -> str:
    def line(value: float) -> str:
        mark = "x" if value in intervals else " "
        return f"- [{mark}] {link(interval_label(value), f'int:{value:g}')}"

    days = sorted({*DAY_INTERVALS, *(v for v in intervals if is_day_interval(v))}, reverse=True)
    lines = []
    _notice(lines, notice)
    lines += [
        f"## Напоминания в {notify_time}",
        "",
        *(line(v) for v in days),
        "",
        "**Ночью**",
        "",
        *(line(v) for v in NIGHT_INTERVALS),
        "",
        footer(
            "Нажмите на строку, чтобы включить или выключить. Ответьте на это сообщение "
            "временем `08:30`, чтобы сменить время, или числом `14`, чтобы напоминать за 14 дней."
        ),
    ]
    return screen(lines, links(cb("Резервная копия", "backup", "link")))


def render_backup(total: int) -> str:
    return screen([
        "## Резервная копия",
        "",
        f"JSON-файл со всеми записями ({records_word(total)}). "
        "При загрузке записи с теми же именами обновятся.",
    ], row(cb("Скачать файл", "export"), cb("Загрузить файл", "import")), back_row("settings:here", "‹ Напоминания"))


def render_import_prompt() -> str:
    return screen([
        "Пришлите JSON-файл, который я выгружал раньше.",
        "",
        "<details><summary>Формат файла</summary>\n\n"
        "```json\n"
        '[{"name": "Иван", "date": "15.08.1990", "tag": "@ivan"},\n'
        ' {"name": "Маша", "date": "03.08"}]\n'
        "```\n"
        "</details>",
    ], back_row("backup"))


def render_import_result(added: int, updated: int, skipped: int) -> str:
    parts = [f"добавлено {added}", f"обновлено {updated}"]
    if skipped:
        parts.append(f"пропущено {skipped} — без имени или с неверной датой")
    return screen("Загрузил файл: " + ", ".join(parts) + ".", nav_row(0))
