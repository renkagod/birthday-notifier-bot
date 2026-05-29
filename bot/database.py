import os
import sqlite3

from bot.dates import DEFAULT_INTERVALS, DEFAULT_NOTIFY_TIME, format_intervals, parse_intervals

DB_PATH_ENV = "BIRTHDAY_BOT_DB_PATH"


def get_db_path() -> str:
    return os.environ.get(DB_PATH_ENV, os.path.join("data", "birthdays.db"))


def init_db() -> None:
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS birthdays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            birth_date TEXT NOT NULL,
            tg_username TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            notify_time TEXT DEFAULT '09:00',
            intervals TEXT DEFAULT '30,7,3,1,0,-1,0.5,0.08'
        )
        """
    )

    try:
        cursor.execute("ALTER TABLE birthdays ADD COLUMN tg_username TEXT")
    except sqlite3.OperationalError:
        pass

    cursor.execute(
        """
        DELETE FROM birthdays
        WHERE id NOT IN (
            SELECT MAX(id) FROM birthdays GROUP BY user_id, name
        )
        """
    )

    try:
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_name ON birthdays(user_id, name)"
        )
    except (sqlite3.OperationalError, sqlite3.IntegrityError):
        pass

    conn.commit()
    conn.close()


def get_user_settings(user_id: int) -> dict:
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT notify_time, intervals FROM user_settings WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"notify_time": row[0], "intervals": parse_intervals(row[1])}
    return {"notify_time": DEFAULT_NOTIFY_TIME, "intervals": list(DEFAULT_INTERVALS)}


def update_user_settings(user_id, notify_time=None, intervals=None):
    current = get_user_settings(user_id)
    time = notify_time if notify_time else current["notify_time"]
    ints = format_intervals(intervals) if intervals else format_intervals(current["intervals"])

    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO user_settings (user_id, notify_time, intervals)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            notify_time=excluded.notify_time,
            intervals=excluded.intervals
        """,
        (user_id, time, ints),
    )
    conn.commit()
    conn.close()


def add_birthday(user_id, name, birth_date, tg_username=None):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO birthdays (user_id, name, birth_date, tg_username)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, name, birth_date, tg_username),
    )
    conn.commit()
    conn.close()


def get_all_birthdays():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, name, birth_date, tg_username FROM birthdays")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_birthdays_for_user(user_id):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, name, birth_date, tg_username FROM birthdays WHERE user_id = ?",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def iter_all_birthdays(batch_size=1000):
    conn = sqlite3.connect(get_db_path())
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name, birth_date, tg_username FROM birthdays")
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            yield from rows
    finally:
        if cursor:
            cursor.close()
        conn.close()


def delete_birthday(user_id, name):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("DELETE FROM birthdays WHERE user_id = ? AND name = ?", (user_id, name))
    conn.commit()
    conn.close()


def update_birthday_info(user_id, old_name, new_name, new_tag):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE birthdays
        SET name = ?, tg_username = ?
        WHERE user_id = ? AND name = ?
        """,
        (new_name, new_tag, user_id, old_name),
    )
    conn.commit()
    conn.close()
