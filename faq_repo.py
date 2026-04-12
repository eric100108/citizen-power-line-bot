import re
from db import get_connection


def _normalize_text(text):
    text = (text or "").strip().lower()
    text = re.sub(r"[\s\u3000]+", "", text)
    text = re.sub(r"[？?！!。．，,、；;：「」『』（）()\[\]{}<>\-_/]", "", text)
    return text


def _char_bigrams(text):
    if len(text) < 2:
        return {text} if text else set()
    return {text[index:index + 2] for index in range(len(text) - 1)}


def _score_faq_match(query, question, answer, category_name):
    normalized_query = _normalize_text(query)
    normalized_question = _normalize_text(question)
    normalized_answer = _normalize_text(answer)
    normalized_category = _normalize_text(category_name)

    if not normalized_query:
        return 0

    score = 0
    combined = normalized_question + normalized_answer + normalized_category

    if normalized_query == normalized_question:
        score += 200
    if normalized_query and normalized_query in normalized_question:
        score += 120
    if normalized_question and normalized_question in normalized_query:
        score += 90
    if normalized_query and normalized_query in normalized_answer:
        score += 40
    if normalized_query and normalized_query in normalized_category:
        score += 30

    query_chars = set(normalized_query)
    combined_chars = set(combined)
    score += len(query_chars & combined_chars) * 5

    query_bigrams = _char_bigrams(normalized_query)
    combined_bigrams = _char_bigrams(combined)
    score += len(query_bigrams & combined_bigrams) * 12

    return score


def get_faq_answer_by_question(question):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT answer
        FROM faq_items
        WHERE is_active = 1 AND question = ?
        LIMIT 1
        """,
        (question,),
    ).fetchone()
    conn.close()
    return row["answer"] if row else None


def find_faq_answer(query):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT fi.question, fi.answer, COALESCE(fc.name, '') AS category_name
        FROM faq_items fi
        LEFT JOIN faq_categories fc ON fc.id = fi.category_id
        WHERE fi.is_active = 1
        ORDER BY fi.id ASC
        """
    ).fetchall()
    conn.close()

    best_row = None
    best_score = 0
    for row in rows:
        score = _score_faq_match(query, row["question"], row["answer"], row["category_name"])
        if score > best_score:
            best_score = score
            best_row = row

    return best_row["answer"] if best_row and best_score >= 18 else None


def list_faqs(keyword=""):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT fi.question, fi.answer, COALESCE(fc.name, '') AS category_name
        FROM faq_items fi
        LEFT JOIN faq_categories fc ON fc.id = fi.category_id
        WHERE fi.is_active = 1
        ORDER BY fi.id ASC
        """
    ).fetchall()
    conn.close()

    if not keyword:
        return rows

    scored_rows = []
    for row in rows:
        score = _score_faq_match(keyword, row["question"], row["answer"], row["category_name"])
        if score > 0:
            scored_rows.append((score, row))

    scored_rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored_rows]
