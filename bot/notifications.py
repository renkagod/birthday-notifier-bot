"""Build birthday notification messages (pure logic, testable without Telegram)."""

from __future__ import annotations

from datetime import datetime, time

from bot.dates import (
    age_turning,
    days_until,
    minutes_until,
    next_birthday_datetime,
    parse_birth_date,
)


def display_name(name: str, tg_username: str | None) -> str:
    label = f"<b>{name}</b>"
    if tg_username:
        label += f" ({tg_username})"
    return label


def build_birthday_notification(
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
    is_yearless = bday_dt.year == 1004
    age = age_turning(bday_dt, target_date) if not is_yearless else None
    label = display_name(name, tg_username)

    diff_minutes = minutes_until(target_date, now)
    diff_days = days_until(target_date, now)

    age_suffix = f" (исполнится {age})" if age is not None else ""
    today_suffix = f" сегодня исполняется {age}! 🥳" if age is not None else " сегодня день рождения! 🥳"

    if diff_minutes == 30 and 0.5 in intervals:
        return f"⏳ <b>Через 30 минут</b> день рождения у {label}!{age_suffix}"
    if diff_minutes == 5 and 0.08 in intervals:
        return f"🔥 <b>Через 5 минут</b> день рождения у {label}!"
    if diff_minutes == 0 and -1.0 in intervals:
        return f"🌙 <b>С днем рождения!</b> Сегодня у {label}{today_suffix}"

    if now.time() != notify_time:
        return None

    if diff_days == 0 and 0.0 in intervals:
        today_msg = f" сегодня день рождения у {label}!{age_suffix} 🎉" if age is not None else f" сегодня день рождения у {label}! 🎉"
        return f"☀️ <b>Напоминание:</b>{today_msg}"
    if diff_days == 1 and 1.0 in intervals:
        return f"🔔 <b>Завтра</b> день рождения у {label}!"
    if diff_days == 3 and 3.0 in intervals:
        return f"🔔 <b>Через 3 дня</b> день рождения у {label}!"
    if diff_days == 7 and 7.0 in intervals:
        return f"🔔 <b>Через неделю</b> день рождения у {label}!"
    if diff_days == 30 and 30.0 in intervals:
        date_display = bday_dt.strftime("%d.%m") if is_yearless else bday_str
        return f"📅 <b>Через месяц</b> ({date_display}) день рождения у {label}!"

    return None
