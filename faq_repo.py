import re
from db import get_connection


FAQ_ALIAS_GROUPS = {
    "什麼叫陪伴式公民電廠建造服務？": [
        "陪伴式服務是什麼",
        "陪伴式服務是什麼呢",
        "什麼是陪伴式服務",
        "什麼叫陪伴式服務",
        "陪伴式公民電廠服務是什麼",
    ],
    "什麼是公民電廠？": [
        "公民電廠是什麼",
        "公民電廠是什麼意思",
        "什麼叫公民電廠",
        "公民電廠是啥",
    ],
    "申請補助前要先準備什麼？": [
        "補助要準備什麼",
        "申請補助要準備什麼",
        "補助附件要準備什麼",
        "補助文件要準備什麼",
    ],
    "公民電廠補助通常要去哪裡找？": [
        "補助去哪裡找",
        "補助哪裡找",
        "公民電廠補助哪裡找",
        "補助去哪找",
    ],
    "公民電廠補助是政府的還是民間的？": [
        "補助是政府還是民間",
        "政府補助還是民間補助",
        "補助是政府的嗎",
    ],
    "屋頂適不適合做公民電廠，要先看什麼？": [
        "我家屋頂適合嗎",
        "屋頂適合做公民電廠嗎",
        "屋頂要看什麼",
        "屋頂能不能做",
    ],
    "我不知道該不該做公民電廠，先怎麼判斷？": [
        "該不該做公民電廠",
        "值不值得做公民電廠",
        "要不要做公民電廠",
        "申請電廠需要注意什麼",
        "建電廠要注意什麼",
    ],
    "第一次找真人協助前，要先準備什麼？": [
        "找真人要準備什麼",
        "找人協助前要準備什麼",
        "找人談之前要準備什麼",
    ],
    "可以先看案例再決定要不要做嗎？": [
        "可以先看案例嗎",
        "先看案例再決定",
        "能不能先看案例",
    ],
}


def _normalize_text(text):
    text = (text or "").strip().lower()
    text = re.sub(r"[\s　]+", "", text)
    text = re.sub(r"[？?！!。．，,、；;：「」『』（）()\[\]{}<>\-_/]", "", text)
    return text


def _char_bigrams(text):
    if len(text) < 2:
        return {text} if text else set()
    return {text[index:index + 2] for index in range(len(text) - 1)}


def _build_alias_lookup():
    alias_lookup = {}
    for question, aliases in FAQ_ALIAS_GROUPS.items():
        for alias in aliases:
            normalized_alias = _normalize_text(alias)
            if normalized_alias:
                alias_lookup[normalized_alias] = question
        normalized_question = _normalize_text(question)
        if normalized_question:
            alias_lookup[normalized_question] = question
    return alias_lookup


FAQ_ALIAS_LOOKUP = _build_alias_lookup()


def resolve_faq_alias_question(query):
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return None

    direct = FAQ_ALIAS_LOOKUP.get(normalized_query)
    if direct:
        return direct

    for normalized_alias, question in FAQ_ALIAS_LOOKUP.items():
        if len(normalized_alias) >= 4 and normalized_alias in normalized_query:
            return question
    return None


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


def find_faq_matches(query, limit=3, min_score=18):
    alias_question = resolve_faq_alias_question(query)
    if alias_question:
        alias_answer = get_faq_answer_by_question(alias_question)
        if alias_answer:
            return [{
                "question": alias_question,
                "answer": alias_answer,
                "category_name": "",
                "score": 999,
            }]

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

    scored_rows = []
    for row in rows:
        score = _score_faq_match(query, row["question"], row["answer"], row["category_name"])
        if score >= min_score:
            scored_rows.append({
                "question": row["question"],
                "answer": row["answer"],
                "category_name": row["category_name"],
                "score": score,
            })

    scored_rows.sort(key=lambda item: item["score"], reverse=True)
    return scored_rows[:limit]


def find_faq_answer(query):
    matches = find_faq_matches(query, limit=2, min_score=24)
    if not matches:
        return None

    top_match = matches[0]
    if top_match["score"] >= 999:
        return top_match["answer"]

    second_score = matches[1]["score"] if len(matches) > 1 else -999
    if top_match["score"] < 36 and abs(top_match["score"] - second_score) < 10:
        return None

    return top_match["answer"]


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
