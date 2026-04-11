from db import get_connection


def find_faq_answer(keyword):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT fi.answer
        FROM faq_items fi
        LEFT JOIN faq_categories fc ON fc.id = fi.category_id
        WHERE fi.is_active = 1
          AND (fi.question LIKE ? OR fi.answer LIKE ? OR COALESCE(fc.name, '') LIKE ?)
        ORDER BY fi.id ASC
        LIMIT 1
        """,
        (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"),
    ).fetchone()
    conn.close()
    return row["answer"] if row else None


def list_faqs(keyword=""):
    conn = get_connection()
    if keyword:
        rows = conn.execute(
            """
            SELECT fi.question, fi.answer
            FROM faq_items fi
            LEFT JOIN faq_categories fc ON fc.id = fi.category_id
            WHERE fi.is_active = 1
              AND (fi.question LIKE ? OR fi.answer LIKE ? OR COALESCE(fc.name, '') LIKE ?)
            ORDER BY fi.id ASC
            """,
            (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT question, answer
            FROM faq_items
            WHERE is_active = 1
            ORDER BY id ASC
            """
        ).fetchall()
    conn.close()
    return rows
