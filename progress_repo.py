from db import get_connection


def get_progress_records():
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, stage, updated_at
        FROM progress_items
        ORDER BY updated_at DESC, id DESC
    """).fetchall()
    conn.close()
    return rows


def create_progress(stage, updated_at):
    conn = get_connection()
    conn.execute("""
        INSERT INTO progress_items (stage, updated_at)
        VALUES (?, ?)
    """, (stage, updated_at))
    conn.commit()
    conn.close()
