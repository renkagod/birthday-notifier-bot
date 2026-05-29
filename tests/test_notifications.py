from datetime import datetime, time

from bot.notifications import build_birthday_notification, display_name


def test_display_name_with_tag():
    assert display_name("Anna", "@anna") == "<b>Anna</b> (@anna)"


def test_midnight_notification():
    now = datetime(2026, 6, 20, 0, 0)
    msg = build_birthday_notification(
        name="Anna",
        bday_str="20.06.1990",
        tg_username=None,
        now=now,
        notify_time=time(9, 0),
        intervals=[-1.0],
    )
    assert msg is not None
    assert "С днем рождения" in msg


def test_thirty_minutes_before():
    now = datetime(2026, 6, 19, 23, 30)
    msg = build_birthday_notification(
        name="Anna",
        bday_str="20.06.1990",
        tg_username=None,
        now=now,
        notify_time=time(9, 0),
        intervals=[0.5],
    )
    assert msg is not None
    assert "30 минут" in msg


def test_scheduled_tomorrow_at_notify_time():
    now = datetime(2026, 6, 19, 10, 0)
    msg = build_birthday_notification(
        name="Anna",
        bday_str="20.06.1990",
        tg_username=None,
        now=now,
        notify_time=time(10, 0),
        intervals=[1.0],
    )
    assert msg is not None
    assert "Завтра" in msg


def test_no_notification_wrong_time():
    now = datetime(2026, 6, 19, 15, 0)
    msg = build_birthday_notification(
        name="Anna",
        bday_str="20.06.1990",
        tg_username=None,
        now=now,
        notify_time=time(10, 0),
        intervals=[1.0],
    )
    assert msg is None
