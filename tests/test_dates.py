from datetime import datetime

import pytest
from bot.dates import (
    age_turning,
    days_until,
    is_valid_notify_time,
    minutes_until,
    next_birthday_datetime,
    parse_birth_date,
    parse_intervals,
    sort_by_name,
    sort_by_upcoming,
)


def test_parse_birth_date():
    dt = parse_birth_date("15.03.1990")
    assert dt.day == 15 and dt.month == 3 and dt.year == 1990


def test_next_birthday_same_year():
    now = datetime(2026, 5, 10, 12, 0)
    bday = parse_birth_date("20.06.1985")
    target = next_birthday_datetime(bday, now)
    assert target == datetime(2026, 6, 20)


def test_next_birthday_rolls_to_next_year():
    now = datetime(2026, 8, 1, 12, 0)
    bday = parse_birth_date("20.06.1985")
    target = next_birthday_datetime(bday, now)
    assert target == datetime(2027, 6, 20)


def test_age_turning():
    bday = parse_birth_date("20.06.1985")
    target = datetime(2026, 6, 20)
    assert age_turning(bday, target) == 41


def test_days_until():
    now = datetime(2026, 6, 18, 15, 0)
    target = datetime(2026, 6, 20)
    assert days_until(target, now) == 2


def test_minutes_until_midnight_birthday():
    now = datetime(2026, 6, 19, 23, 30)
    target = datetime(2026, 6, 20)
    assert minutes_until(target, now) == 30


@pytest.mark.parametrize(
    "value,expected",
    [
        ("09:00", True),
        ("23:59", True),
        ("24:00", False),
        ("9:00", False),
        ("invalid", False),
    ],
)
def test_is_valid_notify_time(value, expected):
    assert is_valid_notify_time(value) is expected


def test_parse_intervals():
    assert parse_intervals("30,7,3,1,0,-1,0.5,0.08") == [30.0, 7.0, 3.0, 1.0, 0.0, -1.0, 0.5, 0.08]


def test_sort_by_name():
    rows = [(1, "Bob", "01.01.2000", None), (1, "alice", "02.02.2000", None)]
    assert [r[1] for r in sort_by_name(rows)] == ["alice", "Bob"]


def test_sort_by_upcoming():
    now = datetime(2026, 6, 1)
    rows = [
        (1, "Later", "01.12.1990", None),
        (1, "Soon", "15.06.1990", None),
    ]
    sorted_rows = sort_by_upcoming(rows, now)
    assert sorted_rows[0][1] == "Soon"


def test_get_month_from_word():
    from bot.dates import get_month_from_word
    assert get_month_from_word("января") == 1
    assert get_month_from_word("Марта") == 3
    assert get_month_from_word("may") == 5
    assert get_month_from_word("unknown") is None


def test_parse_natural_date():
    from bot.dates import parse_natural_date
    assert parse_natural_date("12.05.1990") == (12, 5, 1990)
    assert parse_natural_date("12/05/90") == (12, 5, 1990)
    assert parse_natural_date("12-05") == (12, 5, None)
    assert parse_natural_date("3 августа 2001") == (3, 8, 2001)
    assert parse_natural_date("22 октября") == (22, 10, None)
    assert parse_natural_date("not a date") is None


def test_extract_name_and_date():
    from bot.dates import extract_name_and_date
    assert extract_name_and_date("Иван Иванов @ivan 12.05.1990") == ("Иван Иванов", "@ivan", (12, 5, 1990))
    assert extract_name_and_date("Маша 3 августа") == ("Маша", None, (3, 8, None))
    assert extract_name_and_date("Коля @kolya 23.11") == ("Коля", "@kolya", (23, 11, None))
    assert extract_name_and_date("Просто Имя") == ("Просто Имя", None, None)


def test_leap_year_birthday_handling():
    # February 29 on leap year (2020) -> check next occurrence in non-leap year (2026)
    bday = datetime(2020, 2, 29)
    now = datetime(2026, 2, 1, 12, 0)
    target = next_birthday_datetime(bday, now)
    # Target should fall back to March 1st (or February 28th, depending on choice)
    # We implemented March 1st fallback.
    assert target == datetime(2026, 3, 1)


def test_invalid_calendar_dates():
    from bot.dates import parse_natural_date
    assert parse_natural_date("31.02.2024") is None
    assert parse_natural_date("31.04.2024") is None
    assert parse_natural_date("29.02.2023") is None
    assert parse_natural_date("29.02.2024") == (29, 2, 2024)
    assert parse_natural_date("29.02") == (29, 2, None)
    assert parse_natural_date("31 февраля") is None


