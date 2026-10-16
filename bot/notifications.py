"""Build birthday notification messages (pure logic, testable without Telegram)."""

from __future__ import annotations

from datetime import datetime, time

from bot.dates import (
    YEARLESS_YEAR,
    age_turning,
    days_until,
    minutes_until,
    next_birthday_datetime,
    parse_birth_date,
)
from bot.screens import cb, md, row, tag_url, url_button, years_word


def display_name(name: str, tg_username: str | None) -> str:
    label = f"**{md(name)}**"
    if tg_username:
        label += f" ({md(tg_username)})"
    return label


def _message(title: str, label: str, details: str = "") -> str:
    body = f"У {label} день рождения{details}."
    return f"### {title}\n\n{body}"


def build_birthday_notification(
    *,
    name: str,
    bday_str: str,
    tg_username: str | None,
    now: datetime,
    notify_time: time,
    intervals: list[float],
) -> str | None:
    """Rich Markdown notification due right now (with its buttons), or None."""
    text = _notification_text(
        name=name, bday_str=bday_str, tg_username=tg_username,
        now=now, notify_time=notify_time, intervals=intervals,
    )
    if text is None:
        return None
    buttons = [cb("🏠 Главная", "home")]
    if tg_username:
        buttons.insert(0, url_button("💬 Поздравить", tag_url(tg_username), "success"))
    return f"{text}\n\n{row(*buttons)}"


def _notification_text(
    *,
    name: str,
    bday_str: str,
    tg_username: str | None,
    now: datetime,
    notify_time: time,
    intervals: list[float],
) -> str | None:
    bday_dt = parse_birth_date(bday_str)
    target_date = next_birthday_datetime(bday_dt, now)
    is_yearless = bday_dt.year == YEARLESS_YEAR
    age = age_turning(bday_dt, target_date) if not is_yearless else None
    label = display_name(name, tg_username)

    diff_minutes = minutes_until(target_date, now)
    diff_days = days_until(target_date, now)

    turns = f": исполнится {years_word(age)}" if age is not None else ""
    turns_today = f": исполняется {years_word(age)}" if age is not None else ""
    on_date = f" ({target_date:%d.%m})"

    if diff_minutes == 30 and 0.5 in intervals:
        return _message("⏳ Через 30 минут", label, turns)
    if diff_minutes == 5 and 0.08 in intervals:
        return _message("🔥 Через 5 минут", label, turns)
    if diff_minutes == 0 and -1.0 in intervals:
        return _message("🌙 С днем рождения!", label, f" сегодня{turns_today}") + (
            "\n\n> 🎉 Самое время поздравить первым!"
        )

    if now.time() != notify_time:
        return None

    if diff_days == 0 and 0.0 in intervals:
        return _message("☀️ Сегодня праздник", label, f" сегодня{turns_today}") + (
            "\n\n> 🎁 Не забудьте поздравить!"
        )
    if diff_days == 1 and 1.0 in intervals:
        return _message("🔔 Завтра", label, f" завтра{on_date}{turns}")
    if diff_days == 3 and 3.0 in intervals:
        return _message("🔔 Через 3 дня", label, f"{on_date}{turns}")
    if diff_days == 7 and 7.0 in intervals:
        return _message("🔔 Через неделю", label, f"{on_date}{turns}")
    if diff_days == 30 and 30.0 in intervals:
        return _message("📅 Через месяц", label, f"{on_date}{turns}") + (
            "\n\n> 💡 Есть время спокойно выбрать подарок."
        )

    return None
