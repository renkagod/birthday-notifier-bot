"""Rich Markdown screens (Bot API 10.1+ rich messages), pure and testable without Telegram."""

from __future__ import annotations

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


def _tag_text(tag: str | None) -> str:
    return md(tag) if tag else "не указан"


def _notice(lines: list[str], notice: str | None) -> None:
    if notice:
        lines += [f"> {notice}", ""]


# --- Home / help ---

def render_home(
    rows: list[tuple],
    now: datetime,
    notify_time: str,
    notice: str | None = None,
    reminders_on: bool = True,
) -> str:
    lines = ["# 🎂 Birthday Notifier", ""]
    _notice(lines, notice)
    if not reminders_on:
        lines += ["> 🔕 Все напоминания выключены. Включить их можно в **⚙️ Настройках**.", ""]
    if not rows:
        lines += [
            "Я напомню о днях рождения друзей и близких: заранее и точно в срок.",
            "",
            "Список пока пуст. Нажмите **➕ Добавить** или просто напишите мне, "
            "например `Маша 3 августа`.",
        ]
        return "\n".join(lines)

    upcoming = sort_by_upcoming(rows, now)
    today = []
    soon = []
    for _id, name, date_str, _tag in upcoming[:3]:
        facts = birthday_facts(date_str, now)
        if not facts:
            continue
        target, days, age = facts
        if days == 0:
            today.append(name)
        age_part = f" · исполнится {years_word(age)}" if age is not None else ""
        soon.append(f"- **{md(name)}**: {when_phrase(days)}, {target:%d.%m}{age_part}")

    if today:
        names = ", ".join(f"**{md(n)}**" for n in today)
        lines += [f"> 🎉 Сегодня празднует {names}. Самое время поздравить!", ""]
    lines += ["### 🔥 Скоро", *soon, ""]
    lines.append(f"_Всего в списке: {len(rows)} · напоминаю в {notify_time}_")
    lines += ["", "💡 Чтобы добавить человека, можно просто написать мне `Имя дата`."]
    return "\n".join(lines)


def render_help() -> str:
    return "\n".join([
        "## ❓ Как пользоваться",
        "",
        "**Быстрое добавление.** Напишите мне в любой момент `Имя @тег дата`, "
        "например `Иван Иванов @ivan 12.05.1990`. Тег и год не обязательны.",
        "",
        "**Список.** В «📅 Мой список» нажмите на имя, чтобы открыть карточку: "
        "там можно изменить имя, дату или удалить запись.",
        "",
        "**Напоминания.** В «⚙️ Настройках» выберите время и когда напоминать: "
        "за месяц, за неделю, в сам день или ровно в полночь.",
        "",
        DATE_FORMATS_HELP,
        "",
        "<details><summary>Команды</summary>\n\n"
        "- /start: главное меню\n"
        "- /add: добавить день рождения\n"
        "- /list: весь список\n"
        "- /upcoming: ближайшие дни рождения\n"
        "- /settings: настройки уведомлений\n"
        "- /cancel: отменить текущее действие\n"
        "</details>",
    ])


# --- List / card ---

def render_list(
    page_rows: list[tuple],
    *,
    now: datetime,
    sort_by: str,
    page: int,
    total_pages: int,
    total: int,
) -> str:
    title = "## 🔥 Ближайшие дни рождения" if sort_by == "date" else "## 📅 Мой список"
    order = "по дате" if sort_by == "date" else "по имени"
    pages = f" · стр. {page + 1} из {total_pages}" if total_pages > 1 else ""
    lines = [title, f"_Сортировка {order}{pages} · всего {total}_", ""]
    lines += ["| Имя | Дата | Когда |", "|:--|:--:|--:|"]
    for _id, name, date_str, _tag in page_rows:
        facts = birthday_facts(date_str, now)
        if facts:
            days = facts[1]
            when = "**сегодня** 🎉" if days == 0 else when_phrase(days)
        else:
            when = "?"
        lines.append(f"| **{md(name)}** | {md(format_bday(date_str))} | {when} |")
    lines += ["", "Нажмите на имя, чтобы открыть карточку."]
    return "\n".join(lines)


def render_empty_list() -> str:
    return "\n".join([
        "## 📅 Мой список",
        "",
        "Здесь пока никого нет. Добавьте первый день рождения: "
        "нажмите **➕ Добавить** или напишите мне `Маша 3 августа`.",
    ])


def render_card(
    name: str,
    date_str: str,
    tag: str | None,
    now: datetime,
    notice: str | None = None,
) -> str:
    lines = [f"## 👤 {md(name)}", ""]
    _notice(lines, notice)
    lines.append(f"- 📅 **Дата рождения:** {md(format_bday(date_str))}")
    facts = birthday_facts(date_str, now)
    if facts:
        target, days, age = facts
        if age is not None:
            lines.append(f"- 🎈 **Исполнится:** {years_word(age)}")
        lines.append(
            f"- ⏳ **Следующий:** {when_phrase(days)}, {target:%d.%m} ({WEEKDAYS[target.weekday()]})"
        )
    lines.append(f"- 🔗 **Telegram:** {_tag_text(tag)}")
    if facts and facts[1] == 0:
        lines += ["", "> 🎉 День рождения сегодня! Не забудьте поздравить."]
    return "\n".join(lines)


def render_delete_confirm(name: str) -> str:
    return "\n".join([
        "## 🗑 Удалить запись?",
        "",
        f"Запись **{md(name)}** пропадёт из списка вместе с напоминаниями. "
        "Отменить удаление нельзя.",
    ])


def render_edit_info_prompt(name: str, tag: str | None) -> str:
    return "\n".join([
        f"## ✏️ Имя и тег: {md(name)}",
        "",
        f"- Сейчас: **{md(name)}**, тег {_tag_text(tag)}",
        "",
        "Пришлите новое имя и, если нужно, @тег, например `Иван @ivan`. "
        "Если тег не указать, он будет удалён.",
    ])


def render_edit_date_prompt(name: str, date_str: str) -> str:
    return "\n".join([
        f"## 📅 Дата рождения: {md(name)}",
        "",
        f"Сейчас: **{md(format_bday(date_str))}**",
        "",
        "Пришлите новую дату, например `15.08.1990`, `22.10` или `3 августа`, "
        "или выберите её в календаре.",
        "",
        DATE_FORMATS_HELP,
    ])


# --- Add flow ---

def render_add_menu() -> str:
    return "\n".join([
        "## ➕ Новый день рождения",
        "",
        "- **Ввести вручную**: имя, @тег и дату одним сообщением",
        "- **Из контактов Telegram**: выберите человека, имя и тег подставлю сам",
        "",
        "💡 Меню не обязательно: можно просто написать мне `Маша 3 августа`.",
    ])


def render_name_prompt(prefilled_tag: str | None = None) -> str:
    lines = ["## 📝 Кого добавим?", ""]
    if prefilled_tag:
        lines += [f"Тег {md(prefilled_tag)} уже запомнил. Осталось имя и дата.", ""]
    lines += [
        "Напишите имя и, если хотите, @тег и дату. Всё одним сообщением:",
        "",
        "- `Иван Иванов @ivan 12.05.1990`",
        "- `Маша 3 августа`",
        "- `Петя`, а дату выберем в календаре",
        "",
        DATE_FORMATS_HELP,
    ]
    return "\n".join(lines)


def render_contact_date_prompt(name: str, tag: str | None) -> str:
    return "\n".join([
        f"## 📅 Дата рождения: {md(name)}",
        "",
        f"- 🔗 **Telegram:** {_tag_text(tag)}",
        "",
        "Пришлите дату, например `15.08.1990` или `3 августа`, или откройте календарь.",
        "",
        DATE_FORMATS_HELP,
    ])


def render_confirm_add(
    name: str,
    tag: str | None,
    day: int,
    month: int,
    year: int | None,
    now: datetime,
    exists: bool,
) -> str:
    stored_year = year if year is not None else YEARLESS_YEAR
    date_str = f"{day:02d}.{month:02d}.{stored_year}"
    lines = ["## 🔍 Всё верно?", ""]
    lines.append(f"- 👤 **Имя:** {md(name)}")
    lines.append(f"- 📅 **Дата:** {format_date(day, month, year)}")
    facts = birthday_facts(date_str, now)
    if facts:
        _target, days, age = facts
        age_part = f", исполнится {years_word(age)}" if age is not None else ""
        lines.append(f"- ⏳ **Следующий:** {when_phrase(days)}{age_part}")
    lines.append(f"- 🔗 **Telegram:** {_tag_text(tag)}")
    if exists:
        lines += ["", f"> ⚠️ **{md(name)}** уже есть в списке. Сохранение заменит старую запись."]
    return "\n".join(lines)


def render_picker(name: str | None, step: str, year: int | None = None, month: int | None = None) -> str:
    """Calendar wizard header; shows what is already chosen."""
    title = f"## 📅 Дата рождения: {md(name)}" if name else "## 📅 Дата рождения"
    chosen = []
    if year == YEARLESS_YEAR:
        chosen.append("год: без года")
    elif year:
        chosen.append(f"год: **{year}**")
    if month:
        chosen.append(f"месяц: **{MONTHS_NOMINATIVE[month - 1].lower()}**")
    lines = [title, ""]
    if chosen:
        lines += ["Выбрано: " + ", ".join(chosen), ""]
    lines.append(f"**{step}**")
    return "\n".join(lines)


# --- Settings ---

def render_settings(notify_time: str, intervals: list[float], notice: str | None = None) -> str:
    active = [label for value, label in TIMED_INTERVALS + EXACT_INTERVALS if value in intervals]
    lines = ["## ⚙️ Настройки уведомлений", ""]
    _notice(lines, notice)
    lines += [
        f"- ⏰ **Время напоминаний:** {notify_time}",
        f"- 🔔 **Когда напоминать:** {', '.join(a.lower() for a in active) if active else 'выключено'}",
        "",
        "> Напоминания «за N дней» и «в день рождения» приходят в выбранное время, "
        "а полуночные ровно к началу дня.",
    ]
    return "\n".join(lines)


def render_time_prompt(notify_time: str) -> str:
    return "\n".join([
        "## ⏰ Время напоминаний",
        "",
        f"Сейчас: **{notify_time}**",
        "",
        "Выберите вариант ниже или пришлите своё время, например `08:30` или `21:15`.",
    ])


def render_intervals(intervals: list[float], notify_time: str) -> str:
    def task(value: float, label: str) -> str:
        return f"- [{'x' if value in intervals else ' '}] {label}"

    return "\n".join([
        "## 🔔 Когда напоминать",
        "",
        f"**В {notify_time}:**",
        "",
        *(task(v, label) for v, label in TIMED_INTERVALS),
        "",
        "**Ровно к началу дня:**",
        "",
        *(task(v, label) for v, label in EXACT_INTERVALS),
        "",
        "_Нажмите на пункт ниже, чтобы включить или выключить его._",
    ])


# --- Backup ---

def render_backup(total: int) -> str:
    return "\n".join([
        "## 💾 Резервная копия",
        "",
        f"- **Экспорт**: пришлю JSON-файл со всеми записями ({total})",
        "- **Импорт**: пришлите такой файл, и я добавлю записи. "
        "Записи с совпадающим именем обновятся.",
    ])


def render_import_prompt() -> str:
    return "\n".join([
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
    ])


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
    return "\n".join(lines)
