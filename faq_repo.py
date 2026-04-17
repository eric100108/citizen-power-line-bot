import re
from db import get_connection

PUBLIC_VISIBILITY = ("public",)
INTERNAL_VISIBILITY = ("public", "restricted", "internal")

FAQ_ALIAS_GROUPS = {
    "什麼叫陪伴式公民電廠建造服務？": [
        "陪伴式服務是什麼",
        "陪伴式服務是什麼呢",
        "什麼是陪伴式服務",
        "什麼叫陪伴式服務",
        "陪伴式公民電廠建造服務是什麼",
    ],
    "什麼是公民電廠？": [
        "公民電廠是什麼",
        "公民電廠是什麼呢",
        "什麼叫公民電廠",
        "公民電廠意思",
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
        "補助來源是政府還是民間",
    ],
    "屋頂適不適合做公民電廠，要先看什麼？": [
        "我家屋頂適合嗎",
        "屋頂適不適合做",
        "屋頂能不能做",
        "屋頂可不可以做公民電廠",
    ],
    "我不知道該不該做公民電廠，先怎麼判斷？": [
        "該不該做公民電廠",
        "值不值得做公民電廠",
        "要不要做公民電廠",
        "申請電廠需要注意什麼",
        "開始前要注意什麼",
    ],
    "第一次找真人協助前，要先準備什麼？": [
        "找真人之前要準備什麼",
        "找人協助前要準備什麼",
        "找真人要準備什麼",
    ],
    "可以先看案例再決定要不要做嗎？": [
        "可以先看案例嗎",
        "先看案例再決定",
        "看案例再決定要不要做",
    ],
}

PUBLIC_SAFE_ANSWERS = {
    "南寮案的規劃規模大概是多少？": "這個案例可作為社區型公民電廠的參考樣態，但網站與對外回覆不公開南寮的細部容量、預算與投資結構。若系統要做流程對位，仍會使用資料庫中的內部資料進行比對。",
    "這個案子有補助嗎？": "這類案例通常會先評估是否有政府計畫或地方型資源可申請，但網站與對外回覆不公開南寮的補助金額、比例與內部申請細節。建議先確認申請窗口、資格與附件需求。",
    "居民要怎麼參與投資？": "居民是否參與、如何參與，通常會依社區共識、法規條件與推進方式另行設計。網站與對外回覆不公開南寮的投資安排、金額門檻或內部分配資料。",
    "投資收益會怎麼分配？": "收益與回饋的細部設計屬於案場內部規劃資料。對外只會說明公民電廠通常會兼顧營運、維護、合作方與社區回饋，但不公開南寮的具體分配比例。",
    "公民電廠有機會賺錢嗎？": "是否值得投入，應該看案場條件、法規、維運能力與社區目標，而不是單看單一財務數字。網站與對外回覆不公開南寮的內部收益模型或報酬指標。",
    "社區回饋通常會怎麼安排？": "社區回饋通常會回到地方公共需求、教育推廣、公共空間或社區活動，但個別案場的回饋比例與方式屬於內部規劃資料，不會在網站與對外回覆中公開。",
    "南寮案現在進行到哪裡？": "目前系統會把這個案例當成正式運轉後的示範流程參考，但網站與對外回覆不公開南寮的細部營運數據或內部節點資料。",
    "目前已經做出哪些成果？": "目前可對外說明的是：這個案例已累積可供複製的社區推進經驗，涵蓋社區啟動、場址盤點、補助評估、施工協調到營運回饋；但不公開南寮的細部營運數字。",
}

SENSITIVE_PATTERNS = [
    "2,632,500", "5,265,000", "8.78%", "62.335", "393,615", "78,723", "50%", "IRR", "分配", "股利", "預算", "補助金額", "比例", "營收", "容量",
]


def _normalize_text(text):
    text = (text or "").strip().lower()
    text = re.sub(r"[\s\u3000]+", "", text)
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
    score += len(set(normalized_query) & set(combined)) * 5
    score += len(_char_bigrams(normalized_query) & _char_bigrams(combined)) * 12
    return score


def _looks_sensitive(text):
    return any(token in (text or "") for token in SENSITIVE_PATTERNS)


def sanitize_faq_answer(question, answer):
    if question in PUBLIC_SAFE_ANSWERS:
        return PUBLIC_SAFE_ANSWERS[question]
    if _looks_sensitive(answer):
        return "這題涉及個別案場的敏感或較私密資料，網站與對外回覆不公開南寮的細部數字與分配內容。若系統需要判斷流程位置，仍會使用資料庫中的內部資料進行比對。"
    return answer


def _fetch_faq_rows(visibility_levels):
    conn = get_connection()
    placeholders = ",".join("?" for _ in visibility_levels)
    rows = conn.execute(
        f"""
        SELECT fi.question, fi.answer, COALESCE(fc.name, '') AS category_name, fi.visibility_level
        FROM faq_items fi
        LEFT JOIN faq_categories fc ON fc.id = fi.category_id
        WHERE fi.is_active = 1 AND fi.visibility_level IN ({placeholders})
        ORDER BY fi.id ASC
        """,
        visibility_levels,
    ).fetchall()
    conn.close()
    return rows


def _find_question_row(question, visibility_levels):
    rows = _fetch_faq_rows(visibility_levels)
    for row in rows:
        if row["question"] == question:
            return row
    return None


def get_faq_answer_by_question(question):
    row = _find_question_row(question, PUBLIC_VISIBILITY)
    if not row:
        return None
    return sanitize_faq_answer(question, row["answer"])


def get_faq_answer_by_question_internal(question):
    row = _find_question_row(question, INTERNAL_VISIBILITY)
    if not row:
        return None
    return row["answer"]


def _find_faq_matches(query, limit=3, min_score=18, visibility_levels=PUBLIC_VISIBILITY, sanitize_output=True):
    alias_question = resolve_faq_alias_question(query)
    if alias_question:
        alias_answer = get_faq_answer_by_question(alias_question) if sanitize_output else get_faq_answer_by_question_internal(alias_question)
        if alias_answer:
            return [{"question": alias_question, "answer": alias_answer, "category_name": "", "score": 999, "visibility_level": "public"}]

    rows = _fetch_faq_rows(visibility_levels)
    scored_rows = []
    for row in rows:
        score = _score_faq_match(query, row["question"], row["answer"], row["category_name"])
        if score >= min_score:
            scored_rows.append(
                {
                    "question": row["question"],
                    "answer": sanitize_faq_answer(row["question"], row["answer"]) if sanitize_output else row["answer"],
                    "category_name": row["category_name"],
                    "score": score,
                    "visibility_level": row["visibility_level"],
                }
            )
    scored_rows.sort(key=lambda item: item["score"], reverse=True)
    return scored_rows[:limit]


def find_faq_matches(query, limit=3, min_score=18):
    return _find_faq_matches(query, limit=limit, min_score=min_score, visibility_levels=PUBLIC_VISIBILITY, sanitize_output=True)


def find_faq_matches_internal(query, limit=3, min_score=18):
    return _find_faq_matches(query, limit=limit, min_score=min_score, visibility_levels=INTERNAL_VISIBILITY, sanitize_output=False)


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


def find_faq_answer_internal(query):
    matches = find_faq_matches_internal(query, limit=2, min_score=24)
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
    rows = _fetch_faq_rows(PUBLIC_VISIBILITY)
    sanitized_rows = [
        {"question": row["question"], "answer": sanitize_faq_answer(row["question"], row["answer"]), "category_name": row["category_name"]}
        for row in rows
    ]
    if not keyword:
        return sanitized_rows
    scored_rows = []
    for row in sanitized_rows:
        score = _score_faq_match(keyword, row["question"], row["answer"], row["category_name"])
        if score > 0:
            scored_rows.append((score, row))
    scored_rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored_rows]
