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
            birth_date TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def add_birthday(user_id, name, birth_date):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO birthdays (user_id, name, birth_date) VALUES (?, ?, ?)', 
                   (user_id, name, birth_date))
    conn.commit()
    conn.close()

def get_all_birthdays():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, name, birth_date FROM birthdays')
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_birthday(user_id, name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM birthdays WHERE user_id = ? AND name = ?', (user_id, name))
    conn.commit()
    conn.close()
