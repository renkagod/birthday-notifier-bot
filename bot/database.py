import os
import sqlite3
from contextlib import contextmanager

from bot.dates import DEFAULT_INTERVALS, DEFAULT_NOTIFY_TIME, format_intervals, parse_intervals

DB_PATH_ENV = "BIRTHDAY_BOT_DB_PATH"


def get_db_path() -> str:
    return os.environ.get(DB_PATH_ENV, os.path.join("data", "birthdays.db"))


@contextmanager
def get_connection():
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
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
                intervals TEXT DEFAULT '7,1,0'
            )
            """
        )
        # Bot messages that can be edited by replying to them: kind "person" (ref = birthday
        # id) or "settings".
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS message_refs (
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                ref INTEGER,
                PRIMARY KEY (user_id, message_id)
            )
            """
        )

        for column in ("tg_username", "note"):
            try:
                cursor.execute(f"ALTER TABLE birthdays ADD COLUMN {column} TEXT")
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


def get_user_settings(user_id: int) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT notify_time, intervals FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if row:
            return {"notify_time": row[0], "intervals": parse_intervals(row[1])}
        return {"notify_time": DEFAULT_NOTIFY_TIME, "intervals": list(DEFAULT_INTERVALS)}


def update_user_settings(user_id, notify_time=None, intervals=None):
    current = get_user_settings(user_id)
    time = notify_time if notify_time else current["notify_time"]
    ints = format_intervals(intervals if intervals is not None else current["intervals"])

    with get_connection() as conn:
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


def add_birthday(user_id, name, birth_date, tg_username=None, note=None) -> int:
    """Add a person or update the one with the same name, keeping its id and note."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO birthdays (user_id, name, birth_date, tg_username, note)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, name) DO UPDATE SET
                birth_date = excluded.birth_date,
                tg_username = excluded.tg_username,
                note = COALESCE(excluded.note, birthdays.note)
            """,
            (user_id, name, birth_date, tg_username, note),
        )
        conn.commit()
        cursor.execute("SELECT id FROM birthdays WHERE user_id = ? AND name = ?", (user_id, name))
        return cursor.fetchone()[0]


def find_birthday_id(user_id, name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM birthdays WHERE user_id = ? AND name = ?",
            (user_id, name),
        )
        row = cursor.fetchone()
        return row[0] if row else None


def get_all_birthdays():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name, birth_date, tg_username FROM birthdays")
        return cursor.fetchall()


def get_birthdays_for_user(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, birth_date, tg_username FROM birthdays WHERE user_id = ?",
            (user_id,),
        )
        return cursor.fetchall()


def iter_all_birthdays(batch_size=1000):
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT user_id, name, birth_date, tg_username FROM birthdays")
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                yield from rows
        finally:
            cursor.close()


def iter_user_birthdays(batch_size=1000):
    """(user_id, id, name, birth_date, tg_username, note), grouped by user."""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT user_id, id, name, birth_date, tg_username, note FROM birthdays ORDER BY user_id"
            )
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                yield from rows
        finally:
            cursor.close()


MESSAGE_REFS_PER_USER = 300


def remember_message(user_id, message_id, kind, ref=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO message_refs (user_id, message_id, kind, ref) VALUES (?, ?, ?, ?)",
            (user_id, message_id, kind, ref),
        )
        cursor.execute(
            """
            DELETE FROM message_refs WHERE user_id = ? AND message_id NOT IN (
                SELECT message_id FROM message_refs WHERE user_id = ?
                ORDER BY message_id DESC LIMIT ?
            )
            """,
            (user_id, user_id, MESSAGE_REFS_PER_USER),
        )
        conn.commit()


def find_message(user_id, message_id):
    """(kind, ref) of a remembered bot message, or None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT kind, ref FROM message_refs WHERE user_id = ? AND message_id = ?",
            (user_id, message_id),
        )
        return cursor.fetchone()


def delete_birthday(user_id, name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM birthdays WHERE user_id = ? AND name = ?", (user_id, name))
        conn.commit()


def update_birthday_info(user_id, old_name, new_name, new_tag):
    with get_connection() as conn:
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


def get_birthday_by_id(b_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, user_id, name, birth_date, tg_username FROM birthdays WHERE id = ?",
            (b_id,),
        )
        return cursor.fetchone()


def get_user_birthday(b_id, user_id):
    """Row by id, only if it belongs to user_id (callback data can be forged)."""
    row = get_birthday_by_id(b_id)
    return row if row and row[1] == user_id else None


def delete_birthday_by_id(b_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM birthdays WHERE id = ?", (b_id,))
        conn.commit()


def update_birthday_info_by_id(b_id, name, tg_username):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE birthdays
            SET name = ?, tg_username = ?
            WHERE id = ?
            """,
            (name, tg_username, b_id),
        )
        conn.commit()


def get_note(b_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT note FROM birthdays WHERE id = ?", (b_id,))
        row = cursor.fetchone()
        return row[0] if row else None


def get_notes_for_user(user_id) -> dict[int, str]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, note FROM birthdays WHERE user_id = ? AND note IS NOT NULL", (user_id,)
        )
        return dict(cursor.fetchall())


def set_note(b_id, note):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE birthdays SET note = ? WHERE id = ?", (note or None, b_id))
        conn.commit()


def update_birthday_date_by_id(b_id, birth_date):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE birthdays
            SET birth_date = ?
            WHERE id = ?
            """,
            (birth_date, b_id),
        )
        conn.commit()

