from datetime import datetime

from db import get_connection

DEFAULT_PROJECT_ID = 1


def get_or_create_user(conn, line_user_id, display_name):
    row = conn.execute(
        """
        SELECT id
        FROM users
        WHERE line_user_id = ?
        LIMIT 1
        """,
        (line_user_id,),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE users
            SET display_name = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (display_name, row["id"]),
        )
        return row["id"]

    conn.execute(
        """
        INSERT INTO users (line_user_id, display_name)
        VALUES (?, ?)
        """,
        (line_user_id, display_name),
    )
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def get_progress_records():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            pp.id,
            pp.stage,
            pp.updated_at,
            pp.note,
            COALESCE(u.line_user_id, '') AS line_user_id,
            COALESCE(u.display_name, '') AS display_name,
            pp.created_at
        FROM project_progress pp
        LEFT JOIN users u ON u.id = pp.user_id
        WHERE pp.project_id = ? AND pp.is_predicted = 0
        ORDER BY pp.updated_at DESC, pp.id DESC
        """,
        (DEFAULT_PROJECT_ID,),
    ).fetchall()

    if not rows:
        rows = conn.execute(
            """
            SELECT id, stage, updated_at, '' AS note, line_user_id, display_name, created_at
            FROM progress_items
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()

    conn.close()
    return rows


def get_latest_user_progress(line_user_id):
    if not line_user_id:
        return None

    conn = get_connection()
    row = conn.execute(
        """
        SELECT
            pp.id,
            pp.stage,
            pp.updated_at,
            pp.note,
            COALESCE(u.line_user_id, '') AS line_user_id,
            COALESCE(u.display_name, '') AS display_name,
            pp.created_at
        FROM project_progress pp
        INNER JOIN users u ON u.id = pp.user_id
        WHERE pp.project_id = ? AND pp.is_predicted = 0 AND u.line_user_id = ?
        ORDER BY pp.updated_at DESC, pp.id DESC
        LIMIT 1
        """,
        (DEFAULT_PROJECT_ID, line_user_id),
    ).fetchone()
    conn.close()
    return row


def get_service_journey_steps():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT step_code, title, stage_group, audience, summary, recommended_action, display_order
        FROM service_journey_steps
        WHERE project_id = ?
        ORDER BY display_order ASC, id ASC
        """,
        (DEFAULT_PROJECT_ID,),
    ).fetchall()
    conn.close()
    return rows


def create_progress(stage, updated_at, line_user_id, display_name):
    conn = get_connection()
    user_id = get_or_create_user(conn, line_user_id, display_name)

    conn.execute(
        """
        INSERT INTO project_progress (project_id, user_id, stage, updated_at, note, is_predicted)
        VALUES (?, ?, ?, ?, '', 0)
        """,
        (DEFAULT_PROJECT_ID, user_id, stage, updated_at),
    )

    conn.execute(
        """
        INSERT INTO progress_items (stage, updated_at, line_user_id, display_name, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (stage, updated_at, line_user_id, display_name, datetime.utcnow().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()
