from db import get_connection


def find_faq_answer(keyword):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT answer
        FROM faq_items
        WHERE question LIKE ? OR answer LIKE ?
        LIMIT 1
        """,
        (f"%{keyword}%", f"%{keyword}%"),
    ).fetchone()
    conn.close()
    return row["answer"] if row else None


def list_faqs(keyword=""):
    conn = get_connection()
    if keyword:
        rows = conn.execute(
            """
            SELECT question, answer
            FROM faq_items
            WHERE question LIKE ? OR answer LIKE ?
            """,
            (f"%{keyword}%", f"%{keyword}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT question, answer FROM faq_items"
        ).fetchall()
    conn.close()
    return rows
