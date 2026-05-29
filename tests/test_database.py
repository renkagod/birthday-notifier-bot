from bot.database import (
    add_birthday,
    delete_birthday,
    get_all_birthdays,
    get_user_settings,
    init_db,
    update_birthday_info,
    update_user_settings,
)


def test_init_and_crud(temp_db):
    assert temp_db.exists()
    add_birthday(42, "Alice", "01.01.1990", "@alice")
    rows = get_all_birthdays()
    assert len(rows) == 1
    assert rows[0] == (42, "Alice", "01.01.1990", "@alice")

    update_birthday_info(42, "Alice", "Alicia", "@alicia")
    rows = get_all_birthdays()
    assert rows[0][1] == "Alicia"
    assert rows[0][3] == "@alicia"

    delete_birthday(42, "Alicia")
    assert get_all_birthdays() == []


def test_duplicate_name_replaces(temp_db):
    add_birthday(1, "Bob", "01.01.1980", None)
    add_birthday(1, "Bob", "02.02.1985", "@bob")
    rows = get_all_birthdays()
    assert len(rows) == 1
    assert rows[0][2] == "02.02.1985"
    assert rows[0][3] == "@bob"


def test_user_settings_defaults(temp_db):
    settings = get_user_settings(99)
    assert settings["notify_time"] == "09:00"
    assert 30.0 in settings["intervals"]


def test_user_settings_update(temp_db):
    update_user_settings(99, notify_time="14:30", intervals=[7.0, 1.0])
    settings = get_user_settings(99)
    assert settings["notify_time"] == "14:30"
    assert settings["intervals"] == [7.0, 1.0]


def test_isolated_db_path(monkeypatch, tmp_path):
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    monkeypatch.setenv("BIRTHDAY_BOT_DB_PATH", str(db_a))
    init_db()
    add_birthday(1, "One", "01.01.2000", None)

    monkeypatch.setenv("BIRTHDAY_BOT_DB_PATH", str(db_b))
    init_db()
    assert get_all_birthdays() == []

    monkeypatch.setenv("BIRTHDAY_BOT_DB_PATH", str(db_a))
    assert len(get_all_birthdays()) == 1
