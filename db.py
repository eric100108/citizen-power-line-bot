import os
import shutil
import sqlite3
import tempfile


DB_NAME = os.environ.get("DB_NAME", os.path.join(tempfile.gettempdir(), "citizen_power_line_bot.db"))
BUNDLED_DB_NAME = "app.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    if not os.path.exists(DB_NAME) and os.path.exists(BUNDLED_DB_NAME):
        shutil.copyfile(BUNDLED_DB_NAME, DB_NAME)

    conn = get_connection()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS faq_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS progress_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stage TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS calculator_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_name TEXT NOT NULL,
        value REAL NOT NULL
    )
    """)

    cursor = conn.execute("SELECT COUNT(*) FROM calculator_rules")
    if cursor.fetchone()[0] == 0:
        conn.execute("""
        INSERT INTO calculator_rules (rule_name, value)
        VALUES (?, ?)
        """, ("share_rate", 0.5))

    cursor = conn.execute("SELECT COUNT(*) FROM faq_items")
    if cursor.fetchone()[0] == 0:
        conn.execute("""
        INSERT INTO faq_items (question, answer)
        VALUES (?, ?)
        """, ("什麼是公民電廠？", "公民電廠是由民眾共同參與投資、共享綠能收益的模式。"))
        conn.execute("""
        INSERT INTO faq_items (question, answer)
        VALUES (?, ?)
        """, ("為什麼要推動公民電廠？", "希望讓更多人參與再生能源，提升在地永續與能源轉型。"))

    cursor = conn.execute("SELECT COUNT(*) FROM progress_items")
    if cursor.fetchone()[0] == 0:
        conn.execute("""
        INSERT INTO progress_items (stage, updated_at)
        VALUES (?, ?)
        """, ("施工中", "2026-04-10"))

    conn.commit()
    conn.close()
