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
    "南寮案的規劃規模大概是多少？": "南寮可作為社區型公民電廠案例參考，重點在推動流程、場址盤點、補助評估與營運回饋。",
    "這個案子有補助嗎？": "公民電廠通常會先評估中央、地方或專案型資源。建議先確認申請窗口、資格條件、容量門檻、社區參與要求與附件清單。",
    "如何參與投資？": "先看募集規則、最低投入金額、權利義務、收益方式與退出規則，再決定是否參與。",
    "居民要怎麼參與投資？": "居民參與方式會依社區共識、募集規則與案場條件設計。一般會先辦說明，再確認投入金額、權利義務、回饋方式與退出規則。",
    "投資收益會怎麼分配？": "收益分配通常會同時考量維運、場址租金、參與者回饋與社區公共用途。實際比例需要依合約、治理規則與案場財務條件確認。",
    "公民電廠有機會賺錢嗎？": "有機會，但不能只看單一報酬數字。需要一起看案場條件、補助、售電模式、維運成本、合約年期與社區目標。",
    "社區回饋通常會怎麼安排？": "社區回饋可以用在能源教育、公共空間、社區活動、弱勢支持或地方共同需求。重點是先把用途、管理方式與揭露節奏說清楚。",
    "南寮案現在進行到哪裡？": "南寮案例已可作為營運後的流程參考，重點在於它如何從社區啟動、場址盤點、補助申請、施工協調走到營運回饋。",
    "案場現在進行到哪裡？": "目前進度可到進度頁查看，重點是確認現在階段、已完成項目與下一步待辦。",
    "目前已經做出哪些成果？": "目前可參考的是南寮累積的社區推進經驗，包含社區啟動、場址盤點、補助評估、施工協調與營運回饋。",
    "開始前要先整理哪些資料？": "開始前先確認社區需求、可用屋頂、用電情境、補助資格與推動窗口，再進入場址評估。",
    "申請補助前要先準備什麼？": "先準備組織資料、場址現況、初步容量、預算、期程與地方效益說明。",
    "屋頂適不適合做公民電廠，要先看什麼？": "先看屋頂使用權、遮蔭、結構安全、可用面積、併網條件與後續維運。",
    "補助沒有申請到，案子還能做嗎？": "可以，但要重算案場規模、募集金額、售電模式、維運成本與回收期。",
    "公民電廠最大的風險通常是什麼？": "常見風險包含場址條件、行政時程、居民共識、施工驗收、維運成本與售電合約。",
    "系統會先幫社區做哪些前期工作？": "開始前先確認社區需求、可用屋頂、用電情境、補助資格與推動窗口，再進入場址評估。",
    "為什麼系統要把文件整理進資料庫？": "會用到的資料包含計畫書、補助規則、案場資料與營運摘要。",
    "系統怎麼估算需要幾片太陽能板？": "先用可用面積估容量，再用容量換算模組片數。預設以 410W/片估算，正式設計仍需依實際模組與現場排布確認。",
}

PUBLIC_QUESTION_LABELS = {
    "系統會先幫社區做哪些前期工作？": "開始前要先準備哪些資料？",
    "開始前要先整理哪些資料？": "開始前要先準備哪些資料？",
    "我不知道該不該做公民電廠，先怎麼判斷？": "還不確定要不要做，先看哪些條件？",
    "為什麼系統要把文件整理進資料庫？": "平台會用到哪些專案資料？",
    "系統怎麼估算需要幾片太陽能板？": "太陽能板片數怎麼估？",
}

HIDDEN_PUBLIC_QUESTIONS = {
    "為什麼系統要把文件整理進資料庫？",
    "平台會整理哪些專案資料？",
    "平台會用到哪些專案資料？",
}

SENSITIVE_PATTERNS = [
    "2,632,500", "5,265,000", "8.78%", "62.335", "393,615", "78,723", "IRR", "股利", "補助金額",
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
        return "請先確認場址、合約、補助、維運與社區共識，再進一步試算。"
    return answer


def display_faq_question(question):
    return PUBLIC_QUESTION_LABELS.get(question, question)


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
    candidates = {question, display_faq_question(question)}
    for stored_question, display_question in PUBLIC_QUESTION_LABELS.items():
        if question == display_question:
            candidates.add(stored_question)
    for row in rows:
        if row["question"] in candidates:
            return row
    return None


def get_faq_answer_by_question(question):
    row = _find_question_row(question, PUBLIC_VISIBILITY)
    if not row:
        return None
    return sanitize_faq_answer(row["question"], row["answer"])


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
            return [{"question": display_faq_question(alias_question), "answer": alias_answer, "category_name": "", "score": 999, "visibility_level": "public"}]

    rows = _fetch_faq_rows(visibility_levels)
    scored_rows = []
    for row in rows:
        if sanitize_output and (row["question"] in HIDDEN_PUBLIC_QUESTIONS or display_faq_question(row["question"]) in HIDDEN_PUBLIC_QUESTIONS):
            continue
        score = _score_faq_match(query, row["question"], row["answer"], row["category_name"])
        if score >= min_score:
            scored_rows.append(
                {
                    "question": display_faq_question(row["question"]) if sanitize_output else row["question"],
                    "answer": sanitize_faq_answer(row["question"], row["answer"]) if sanitize_output else row["answer"],
                    "category_name": row["category_name"],
                    "score": score,
                    "visibility_level": row["visibility_level"],
                }
            )
    scored_rows.sort(key=lambda item: item["score"], reverse=True)
    deduped_rows = []
    seen_questions = set()
    for row in scored_rows:
        if row["question"] in seen_questions:
            continue
        seen_questions.add(row["question"])
        deduped_rows.append(row)
        if len(deduped_rows) >= limit:
            break
    return deduped_rows


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
    deduped_rows = {}
    for row in rows:
        question = display_faq_question(row["question"])
        if row["question"] in HIDDEN_PUBLIC_QUESTIONS or question in HIDDEN_PUBLIC_QUESTIONS:
            continue
        if question in deduped_rows:
            continue
        deduped_rows[question] = {
            "question": question,
            "answer": sanitize_faq_answer(row["question"], row["answer"]),
            "category_name": row["category_name"],
        }
    sanitized_rows = list(deduped_rows.values())
    if not keyword:
        return sanitized_rows
    scored_rows = []
    for row in sanitized_rows:
        score = _score_faq_match(keyword, row["question"], row["answer"], row["category_name"])
        if score > 0:
            scored_rows.append((score, row))
    scored_rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored_rows]
