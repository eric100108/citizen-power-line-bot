from db import get_connection


def get_share_rate():
    conn = get_connection()
    row = conn.execute("""
        SELECT value
        FROM calculator_rules
        WHERE rule_name = ?
        LIMIT 1
    """, ("share_rate",)).fetchone()
    conn.close()
    return row["value"] if row else None
