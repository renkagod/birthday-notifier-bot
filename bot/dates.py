"""Pure date and interval helpers (no Telegram / DB dependencies)."""

from __future__ import annotations

import re
from datetime import datetime

BIRTH_DATE_FMT = "%d.%m.%Y"
DEFAULT_INTERVALS = [30.0, 7.0, 3.0, 1.0, 0.0, -1.0, 0.5, 0.08]
DEFAULT_NOTIFY_TIME = "09:00"
NOTIFY_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def parse_birth_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, BIRTH_DATE_FMT)


def parse_intervals(intervals_str: str) -> list[float]:
    return [float(i) for i in intervals_str.split(",") if i.strip()]


def format_intervals(intervals: list[float]) -> str:
    return ",".join(str(i) for i in intervals)


def is_valid_notify_time(value: str) -> bool:
    return bool(NOTIFY_TIME_RE.match(value))


def next_birthday_datetime(bday_dt: datetime, now: datetime) -> datetime:
    """Midnight (local) of the next calendar occurrence of the birthday."""
    target = bday_dt.replace(year=now.year, hour=0, minute=0, second=0, microsecond=0)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if target < today:
        target = target.replace(year=now.year + 1)
    return target


def age_turning(bday_dt: datetime, target_date: datetime) -> int:
    return target_date.year - bday_dt.year


def days_until(target_date: datetime, now: datetime) -> int:
    now_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return (target_date - now_date).days


def minutes_until(target_date: datetime, now: datetime) -> int:
    now_aligned = now.replace(second=0, microsecond=0)
    return int((target_date - now_aligned).total_seconds() / 60)


def sort_by_name(birthdays: list[tuple]) -> list[tuple]:
    return sorted(birthdays, key=lambda x: x[1].lower())


def sort_by_upcoming(birthdays: list[tuple], now: datetime) -> list[tuple]:
    def sort_key(row: tuple) -> tuple:
        try:
            bday_dt = parse_birth_date(row[2])
            upcoming = next_birthday_datetime(bday_dt, now)
            return (upcoming, row[1].lower())
        except (ValueError, IndexError):
            return (datetime.max, "")

    return sorted(birthdays, key=sort_key)
