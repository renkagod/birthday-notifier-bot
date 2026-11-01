from datetime import datetime, time

from bot.notifications import build_digest

NINE = time(9, 0)


def digest(people, now, intervals, notify_time=NINE):
    return build_digest(people, now=now, notify_time=notify_time, intervals=intervals)


def test_week_ahead_mentions_age_and_date():
    msg = digest([(1, "Anna", "20.06.1990", None)], datetime(2026, 6, 13, 9, 0), [7.0])
    assert msg is not None
    assert "**Через неделю**, 20 июня" in msg
    assert "исполнится 36" in msg


def test_custom_days_interval():
    msg = digest([(1, "Anna", "27.06.1990", None)], datetime(2026, 6, 13, 9, 0), [14.0])
    assert msg is not None
    assert "Через 14 дней" in msg


def test_several_people_arrive_in_one_message():
    people = [(1, "Anna", "13.06.1990", "@anna"), (2, "Bob", "14.06.1985", None), (3, "Eve", "01.01.1990", None)]
    msg = digest(people, datetime(2026, 6, 13, 9, 0), [7.0, 1.0, 0.0])
    assert msg.count("## ") == 1
    assert "Сегодня день рождения — **" in msg and 'url="https://t.me/anna"' in msg
    assert "**Завтра** — " in msg
    assert "Eve" not in msg


def test_midnight_notification():
    msg = digest([(1, "Anna", "20.06.1990", None)], datetime(2026, 6, 20, 0, 0), [-1.0])
    assert msg is not None
    assert "Наступил день рождения" in msg
    assert "исполняется 36" in msg


def test_thirty_minutes_before():
    msg = digest([(1, "Anna", "20.06.1990", None)], datetime(2026, 6, 19, 23, 30), [0.5])
    assert msg is not None
    assert "Через 30 минут" in msg


def test_scheduled_tomorrow_at_notify_time():
    msg = digest([(1, "Anna", "20.06.1990", None)], datetime(2026, 6, 19, 10, 0), [1.0], time(10, 0))
    assert msg is not None
    assert "Завтра" in msg


def test_no_notification_wrong_time():
    assert digest([(1, "Anna", "20.06.1990", None)], datetime(2026, 6, 19, 15, 0), [1.0], time(10, 0)) is None


def test_name_is_escaped():
    msg = digest([(1, "<Bob> *&*", "20.06.1990", None)], datetime(2026, 6, 19, 9, 0), [1.0])
    assert r"\<Bob\> \*\&\*" in msg


def test_long_digest_is_cut():
    people = [(i, f"P{i}", "13.06.1990", None) for i in range(50)]
    msg = digest(people, datetime(2026, 6, 13, 9, 0), [0.0])
    assert msg.count("Сегодня день рождения") == 20
    assert "И ещё 30" in msg
