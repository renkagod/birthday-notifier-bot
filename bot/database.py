import sqlite3
import os

DB_PATH = os.path.join("data", "birthdays.db")

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS birthdays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            birth_date TEXT NOT NULL,
            tg_username TEXT
        )
    ''')
    # Migration for existing databases
    try:
        cursor.execute('ALTER TABLE birthdays ADD COLUMN tg_username TEXT')
    except sqlite3.OperationalError:
        pass # Column already exists
    conn.commit()
    conn.close()

def add_birthday(user_id, name, birth_date, tg_username=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO birthdays (user_id, name, birth_date, tg_username) VALUES (?, ?, ?, ?)', 
                   (user_id, name, birth_date, tg_username))
    conn.commit()
    conn.close()

def get_all_birthdays():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, name, birth_date, tg_username FROM birthdays')
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_birthday(user_id, name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM birthdays WHERE user_id = ? AND name = ?', (user_id, name))
    conn.commit()
    conn.close()

def update_birthday_info(user_id, old_name, new_name, new_tag):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE birthdays 
        SET name = ?, tg_username = ? 
        WHERE user_id = ? AND name = ?
    ''', (new_name, new_tag, user_id, old_name))
    conn.commit()
    conn.close()
