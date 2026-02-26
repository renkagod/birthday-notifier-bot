import sqlite3
import os

DB_PATH = os.path.join("data", "birthdays.db")

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Birthdays table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS birthdays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            birth_date TEXT NOT NULL,
            tg_username TEXT
        )
    ''')
    
    # User settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            notify_time TEXT DEFAULT '09:00',
            intervals TEXT DEFAULT '30,7,3,1,0.5,0.08,0'
        )
    ''')
    
    # Migrations
    try:
        cursor.execute('ALTER TABLE birthdays ADD COLUMN tg_username TEXT')
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()

def get_user_settings(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT notify_time, intervals FROM user_settings WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"notify_time": row[0], "intervals": [float(i) for i in row[1].split(',')]}
    return {"notify_time": "09:00", "intervals": [30.0, 7.0, 3.0, 1.0, 0.5, 0.08, 0.0]}

def update_user_settings(user_id, notify_time=None, intervals=None):
    current = get_user_settings(user_id)
    time = notify_time if notify_time else current['notify_time']
    ints = ",".join([str(i) for i in intervals]) if intervals else ",".join([str(i) for i in current['intervals']])
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_settings (user_id, notify_time, intervals) 
        VALUES (?, ?, ?) 
        ON CONFLICT(user_id) DO UPDATE SET notify_time=excluded.notify_time, intervals=excluded.intervals
    ''', (user_id, time, ints))
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
