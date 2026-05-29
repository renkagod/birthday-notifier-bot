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
