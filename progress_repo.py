from datetime import datetime

from db import get_connection


def get_progress_records():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, stage, updated_at, line_user_id, display_name, created_at
        FROM progress_items
        ORDER BY updated_at DESC, id DESC
        """
    ).fetchall()
    conn.close()
    return rows


def create_progress(stage, updated_at, line_user_id, display_name):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO progress_items (stage, updated_at, line_user_id, display_name, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (stage, updated_at, line_user_id, display_name, datetime.utcnow().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()
