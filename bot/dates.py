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
    try:
        target = bday_dt.replace(year=now.year, hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        # For February 29 on non-leap years, notify on March 1st.
        target = datetime(year=now.year, month=3, day=1, hour=0, minute=0, second=0, microsecond=0)
        
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if target < today:
        try:
            target = target.replace(year=now.year + 1)
        except ValueError:
            target = datetime(year=now.year + 1, month=3, day=1, hour=0, minute=0, second=0, microsecond=0)
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


def get_month_from_word(word: str) -> int | None:
    word = word.lower()
    if word.startswith("янв") or word.startswith("jan"):
        return 1
    if word.startswith("фев") or word.startswith("feb"):
        return 2
    if word.startswith("мар") or word.startswith("mar"):
        return 3
    if word.startswith("апр") or word.startswith("apr"):
        return 4
    if word.startswith("май") or word.startswith("мая") or word.startswith("may"):
        return 5
    if word.startswith("июн") or word.startswith("jun"):
        return 6
    if word.startswith("июл") or word.startswith("jul"):
        return 7
    if word.startswith("авг") or word.startswith("aug"):
        return 8
    if word.startswith("сен") or word.startswith("sep"):
        return 9
    if word.startswith("окт") or word.startswith("oct"):
        return 10
    if word.startswith("ноя") or word.startswith("nov"):
        return 11
    if word.startswith("дек") or word.startswith("dec"):
        return 12
    return None


def is_valid_calendar_date(day: int, month: int, year: int | None) -> bool:
    try:
        test_year = year if year is not None else 2000
        datetime(test_year, month, day)
        return True
    except (ValueError, OverflowError):
        return False


def parse_natural_date(text: str) -> tuple[int, int, int | None] | None:
    text = text.strip().lower()
    
    # 1. Delimiter format: DD.MM.YYYY or DD.MM.YY or DD.MM
    match = re.search(r'\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b', text)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year_str = match.group(3)
        year = None
        if year_str:
            year = int(year_str)
            if len(year_str) == 2:
                year += 2000 if year < 50 else 1900
        if is_valid_calendar_date(day, month, year):
            return day, month, year

    # 2. Text month format: 12 мая 1990 or 3 августа
    match = re.search(r'\b(\d{1,2})\s+([а-яa-z]+)(?:\s+(\d{2,4}))?\b', text)
    if match:
        day = int(match.group(1))
        month_word = match.group(2)
        year_str = match.group(3)
        month = get_month_from_word(month_word)
        if month:
            year = None
            if year_str:
                year = int(year_str)
                if len(year_str) == 2:
                    year += 2000 if year < 50 else 1900
            if is_valid_calendar_date(day, month, year):
                return day, month, year
                
    return None


def extract_name_and_date(text: str) -> tuple[str, str | None, tuple[int, int, int | None] | None]:
    # Extract @username if present
    username_match = re.search(r'(@\w+)', text)
    username = username_match.group(1) if username_match else None
    
    text_clean = re.sub(r'(@\w+)', '', text).strip()
    
    # Try delimiters first
    date_tuple = None
    date_match = re.search(r'\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b', text_clean)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year_str = date_match.group(3)
        year = None
        if year_str:
            year = int(year_str)
            if len(year_str) == 2:
                year += 2000 if year < 50 else 1900
        if is_valid_calendar_date(day, month, year):
            date_tuple = (day, month, year)
            text_clean = text_clean.replace(date_match.group(0), "").strip()
    else:
        # Try text month
        date_match = re.search(r'\b(\d{1,2})\s+([а-яa-z]+)(?:\s+(\d{2,4}))?\b', text_clean, re.IGNORECASE)
        if date_match:
            day = int(date_match.group(1))
            month_word = date_match.group(2)
            year_str = date_match.group(3)
            month = get_month_from_word(month_word)
            if month:
                year = None
                if year_str:
                    year = int(year_str)
                    if len(year_str) == 2:
                        year += 2000 if year < 50 else 1900
                if is_valid_calendar_date(day, month, year):
                    date_tuple = (day, month, year)
                    text_clean = text_clean.replace(date_match.group(0), "").strip()
                    
    name = re.sub(r'\s+', ' ', text_clean).strip()
    return name, username, date_tuple

