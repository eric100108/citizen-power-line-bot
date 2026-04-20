import os
import re
from flask import Flask, jsonify, redirect, render_template, request, url_for

from calc_repo import build_calculator_result, build_site_estimate_result
from db import init_db
from faq_repo import find_faq_answer, find_faq_matches, get_faq_answer_by_question, list_faqs
from line_service import (
    get_liff_id,
    get_line_profile_from_access_token,
    reply_faq_quick_reply,
    reply_line_message,
    reply_related_faq_quick_reply,
    reply_start_build_quick_reply,
    verify_line_signature,
)
from project_repo import get_project_overview
from progress_repo import create_progress, get_latest_user_progress, get_progress_records, get_service_journey_steps
from progress_service import PROGRESS_STAGES, build_predicted_progress, build_sop_status, parse_progress_date

app = Flask(__name__)

START_BUILD_KEYWORDS = {"開始建立電廠", "開始建電廠", "我要開始建立電廠", "開始建立電廠要做什麼？", "我要怎麼開始建立電廠"}
FULL_SOP_KEYWORDS = {"完整 SOP", "完整SOP", "我要看完整 SOP", "我要看完整SOP"}
SUBSIDY_KEYWORDS = {"補助", "我要了解補助", "補助怎麼申請", "有補助可以申請嗎？"}
SITE_KEYWORDS = {"場址", "我要先盤點場址", "場址盤點", "我要先盤點屋頂", "場址要怎麼評估？"}
PROGRESS_KEYWORDS = {"我現在進行到哪一步？", "我現在到哪一步", "我到哪一步", "我的進度"}
HUMAN_HELP_KEYWORDS = {"真人協助", "我要真人協助", "找人協助", "聯絡真人"}
CASE_KEYWORDS = {"案例", "先看案例", "南寮案例", "看案例"}


def normalize_user_message(text):
    text = (text or "").strip().lower()
    text = re.sub(r"[\s\u3000]+", "", text)
    text = re.sub(r"[？?！!。．，,、；;：「」『』（）()\[\]{}<>\-_/]", "", text)
    return text


def infer_user_intent(user_message):
    normalized = normalize_user_message(user_message)
    if not normalized:
        return None

    if any(term in normalized for term in ["真人協助", "找人協助", "聯絡真人", "真人", "人工協助", "找人談", "談談", "聊聊", "聊一下"]):
        return "human_help"
    if "完整sop" in normalized or ("sop" in normalized and "完整" in normalized):
        return "full_sop"
    if any(term in normalized for term in ["案例", "看案例", "南寮案例", "案例再決定"]):
        return "case"
    if any(term in normalized for term in ["怎麼開始", "如何開始", "從開始", "從哪開始", "從哪裡開始", "開始建立", "建立電廠", "啟動電廠", "先做什麼", "先幹嘛", "該不該做", "值不值得做"]):
        return "start_build"
    if ("??" in normalized and "??" in normalized) or ("??" in normalized and any(term in normalized for term in ["??", "??", "??", "??"])):
        return "start_build"
    if "補助" in normalized:
        return "subsidy"
    if any(term in normalized for term in ["場址", "屋頂", "盤點", "屋頂出租", "屋頂提供"]):
        return "site"
    if any(term in normalized for term in ["到哪一步", "哪一步", "我的進度", "目前進度", "做到哪", "走到哪", "卡在哪", "卡住"]):
        return "progress"
    return None


def row_to_dict(row):
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def build_start_build_message(service_steps, user_message=""):
    normalized = normalize_user_message(user_message)

    if any(term in normalized for term in ["該不該做", "值不值得做"]):
        answer = get_faq_answer_by_question("我不知道該不該做公民電廠，先怎麼判斷？")
        if answer:
            return answer

    if any(term in normalized for term in ["先做什麼", "先幹嘛", "還沒資料"]):
        answer = get_faq_answer_by_question("系統會先幫社區做哪些前期工作？")
        if answer:
            return answer

    if not service_steps:
        return "目前還沒有建立電廠 SOP 資料，建議先整理社區需求、可用場址與推動窗口。"

    step_lines = []
    for index, step in enumerate(service_steps[:4], start=1):
        step_lines.append(f"{index}. {step['title']}")

    first_step = service_steps[0]
    return (
        "開始建立公民電廠，建議先照著南寮的可複製 SOP 往前走：\n"
        + "\n".join(step_lines)
        + f"\n\n你現在最適合先做的是：{first_step['title']}"
        + f"\n建議動作：{first_step['recommended_action']}"
        + "\n\n你可以繼續查看完整 SOP、補助、場址盤點，或直接找真人協助。"
    )


def build_full_sop_message(service_steps):
    if not service_steps:
        return "目前還沒有可顯示的 SOP。"

    lines = ["南寮公民電廠完整 SOP："]
    for index, step in enumerate(service_steps, start=1):
        lines.append(f"{index}. {step['title']}｜{step['recommended_action']}")
    return "\n".join(lines)


def build_site_guidance_message(service_steps):
    survey_step = next((step for step in service_steps if step["step_code"] == "survey"), None)
    if survey_step:
        return (
            f"場址盤點對應南寮 SOP 的「{survey_step['title']}」。"
            f"\n你現在要先做的是：{survey_step['summary']}"
            f"\n建議動作：{survey_step['recommended_action']}"
            "\n\n最少先整理 3 件事：可用屋頂、建物現況照片、基本用電情境。"
        )
    return "場址盤點建議先確認可用屋頂、建物資料與用電情境，再進入容量與法規評估。"


def build_human_help_message():
    return (
        "如果你想直接進入陪伴式推進，下一步建議安排真人協助。"
        "\n你可以先準備：社區名稱、目前卡住的步驟、可用場址概況、是否要申請補助。"
        "\n這樣後續就能更快判斷你現在對應南寮 SOP 的哪一步。"
    )


def build_subsidy_guidance_message(user_message=""):
    normalized = normalize_user_message(user_message)

    if any(term in normalized for term in ["沒補助", "沒有補助", "補助不過", "補助沒過", "申請不到"]):
        answer = get_faq_answer_by_question("補助沒有申請到，案子還能做嗎？")
        if answer:
            return answer

    if any(term in normalized for term in ["去哪裡找", "哪裡找", "政府還是民間", "政府補助", "民間補助"]):
        source = get_faq_answer_by_question("公民電廠補助通常要去哪裡找？")
        kind = get_faq_answer_by_question("公民電廠補助是政府的還是民間的？")
        parts = [part for part in [source, kind] if part]
        if parts:
            return "補助資訊整理：\n\n" + "\n\n".join(parts)

    if any(term in normalized for term in ["準備", "附件", "資料", "文件"]):
        prep = get_faq_answer_by_question("申請補助前要先準備什麼？")
        if prep:
            return prep

    intro = get_faq_answer_by_question("這個案子有補助嗎？")
    source = get_faq_answer_by_question("公民電廠補助通常要去哪裡找？")
    prep = get_faq_answer_by_question("申請補助前要先準備什麼？")

    parts = [part for part in [intro, source, prep] if part]
    if parts:
        return "補助資訊整理：\n\n" + "\n\n".join(parts)

    return "補助準備建議先確認申請窗口、截止日期、附件清單與預算拆分。"


def build_faq_suggestion_message(related_matches):
    if not related_matches:
        return "目前找不到夠接近的答案，你可以輸入『開始建立電廠』、FAQ、補助、場址或真人協助。"

    lines = ["我先幫你找到幾個最接近的問題，你可以直接點下面其中一題："]
    for index, item in enumerate(related_matches[:3], start=1):
        lines.append(f"{index}. {item['question']}")
    return "\n".join(lines)


def build_case_intro_message():
    return (
        "可以，先看案例再決定很合理。"
        "\n南寮案例可以幫你先理解社區啟動、場址盤點、補助申請、施工到正式運轉的整體節奏。"
        "\n如果你現在還不確定要不要做，建議先看案例，再回來確認自己最接近哪一步。"
    )


def build_progress_position_message(line_user_id, service_steps, project_rows):
    user_latest = get_latest_user_progress(line_user_id) if line_user_id else None
    latest_record = user_latest or (project_rows[0] if project_rows else None)
    sop_status = build_sop_status(latest_record, service_steps)
    current_step = sop_status.get("current_step")
    if not current_step:
        return "目前還沒有足夠的進度資料可對位。"

    prefix = "你目前對應到" if user_latest else "目前系統先以南寮案最新進度對位到"
    return (
        f"{prefix}南寮 SOP 第 {sop_status['current_order']} / {sop_status['step_count']} 步。"
        f"\n目前階段：{sop_status['current_stage']}"
        f"\n當前步驟：{current_step['title']}"
        f"\n建議動作：{current_step['recommended_action']}"
    )


@app.route("/menu")
def menu():
    return render_template("menu_product_v2.html")


@app.route("/api/line-profile", methods=["POST"])
def line_profile():
    data = request.get_json(silent=True) or {}
    access_token = data.get("accessToken", "")

    try:
        profile = get_line_profile_from_access_token(access_token)
    except Exception:
        return jsonify({"ok": False, "message": "LINE 身分驗證失敗"}), 400

    return jsonify({"ok": True, "profile": profile})


@app.route("/api/progress-sop")
def progress_sop():
    line_user_id = request.args.get("line_user_id", default="", type=str).strip()
    service_steps = get_service_journey_steps()
    project_rows = get_progress_records()
    project_latest = project_rows[0] if project_rows else None
    user_latest = get_latest_user_progress(line_user_id) if line_user_id else None
    latest_record = user_latest or project_latest
    sop_status = build_sop_status(latest_record, service_steps)

    return jsonify({
        "ok": True,
        "has_user_progress": bool(user_latest),
        "latest_record": row_to_dict(latest_record),
        "project_latest_record": row_to_dict(project_latest),
        "sop_status": sop_status,
    })


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_line_signature(body, signature):
        return "Invalid signature", 403

    data = request.get_json(silent=True)
    if not data or "events" not in data:
        return "OK", 200

    for event in data["events"]:
        if event.get("type") != "message":
            continue

        message = event.get("message", {})
        if message.get("type") != "text":
            continue

        reply_token = event.get("replyToken")
        user_message = message.get("text", "").strip()
        if not reply_token or not user_message:
            continue

        if user_message.upper() == "FAQ":
            reply_faq_quick_reply(reply_token)
            continue

        service_steps = get_service_journey_steps()
        project_rows = get_progress_records()
        line_user_id = event.get("source", {}).get("userId", "").strip()

        inferred_intent = infer_user_intent(user_message)

        if user_message in START_BUILD_KEYWORDS or inferred_intent == "start_build":
            reply_start_build_quick_reply(reply_token, build_start_build_message(service_steps, user_message))
            continue

        if user_message in FULL_SOP_KEYWORDS or inferred_intent == "full_sop":
            reply_start_build_quick_reply(reply_token, build_full_sop_message(service_steps))
            continue

        if user_message in SUBSIDY_KEYWORDS or inferred_intent == "subsidy":
            reply_start_build_quick_reply(reply_token, build_subsidy_guidance_message(user_message))
            continue

        if user_message in SITE_KEYWORDS or inferred_intent == "site":
            site_answer = find_faq_answer(user_message)
            if site_answer:
                reply_start_build_quick_reply(reply_token, site_answer)
            else:
                reply_start_build_quick_reply(reply_token, build_site_guidance_message(service_steps))
            continue

        if user_message in PROGRESS_KEYWORDS or inferred_intent == "progress":
            reply_start_build_quick_reply(reply_token, build_progress_position_message(line_user_id, service_steps, project_rows))
            continue

        if user_message in HUMAN_HELP_KEYWORDS or inferred_intent == "human_help":
            human_answer = find_faq_answer(user_message)
            reply_line_message(reply_token, human_answer if human_answer else build_human_help_message())
            continue

        if user_message in CASE_KEYWORDS or inferred_intent == "case":
            reply_start_build_quick_reply(reply_token, build_case_intro_message())
            continue
        answer = find_faq_answer(user_message)
        if answer:
            reply_line_message(reply_token, answer)
            continue

        related_matches = find_faq_matches(user_message, limit=3, min_score=10)
        if related_matches:
            reply_related_faq_quick_reply(
                reply_token,
                build_faq_suggestion_message(related_matches),
                [item["question"] for item in related_matches],
            )
            continue

        reply_line_message(reply_token, "目前找不到對應答案，你可以輸入『開始建立電廠』、FAQ、補助、場址或真人協助。")

    return "OK", 200


@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "system": "citizen power line bot",
        "version": "1.0",
        "features": {
            "faq_all": "/faq",
            "faq_search": "/faq?keyword=補助",
            "calc": "/calc?amount=10000",
            "site_estimate": "/site-estimate?site_ping=30",
            "progress": "/progress",
            "progress_sop_api": "/api/progress-sop?line_user_id=YOUR_LINE_USER_ID",
            "webhook": "/webhook",
            "menu": "/menu",
            "line_profile_api": "/api/line-profile",
        },
    })


@app.route("/faq")
def faq():
    keyword = request.args.get("keyword", default="", type=str)
    rows = list_faqs(keyword)

    if not rows:
        return jsonify({"message": "查無符合條件的 FAQ"}), 404

    return jsonify([
        {"question": row["question"], "answer": row["answer"]}
        for row in rows
    ])


@app.route("/hello")
def hello():
    return "公民電廠小助手已上線"


@app.route("/calc")
def calc():
    amount = request.args.get("amount", default=10000, type=float)
    roof_ping = request.args.get("roof_ping", default=30, type=float)
    project_slug = request.args.get("project", default="nanliao-citizen-power", type=str).strip() or "nanliao-citizen-power"
    calc_result = build_calculator_result(amount, project_slug, roof_ping)
    return render_template("calc_v4.html", **calc_result)


@app.route("/site-estimate")
def site_estimate():
    site_ping = request.args.get("site_ping", default=30, type=float)
    usable_ratio_percent = request.args.get("usable_ratio", default=85, type=float)
    years = request.args.get("years", default=20, type=int)
    carbon_factor = request.args.get("carbon_factor", default=None, type=float)
    parameter_mode = request.args.get("parameter_mode", default="official_penghu_114", type=str).strip()
    area_input_type = request.args.get("area_input_type", default="gross_area", type=str).strip()
    degradation_method = request.args.get("degradation_method", default="compound", type=str).strip()
    sales_mode = request.args.get("sales_mode", default="wheeling_transfer", type=str).strip()
    project_slug = request.args.get("project", default="nanliao-citizen-power", type=str).strip() or "nanliao-citizen-power"
    estimate = build_site_estimate_result(
        site_ping=site_ping,
        usable_ratio=usable_ratio_percent / 100,
        project_slug=project_slug,
        years=years,
        carbon_factor_kg_per_kwh=carbon_factor,
        parameter_mode=parameter_mode,
        area_input_type=area_input_type,
        degradation_method=degradation_method,
        sales_mode=sales_mode,
        custom_area_m2_per_kwp=request.args.get("area_m2_per_kwp", default=None, type=float),
        custom_annual_generation_per_kwp=request.args.get("annual_generation_per_kwp", default=None, type=float),
        custom_module_watt=request.args.get("module_watt", default=None, type=float),
        custom_module_area_m2=request.args.get("module_area_m2", default=None, type=float),
        custom_sell_price_per_kwh=request.args.get("sell_price_per_kwh", default=None, type=float),
        custom_construction_unit_cost_per_kwp=request.args.get("construction_unit_cost_per_kwp", default=None, type=float),
    )
    estimate["usable_ratio_percent"] = usable_ratio_percent
    return render_template("site_estimate_v1.html", **estimate)


@app.route("/project")
@app.route("/project/<project_slug>")
def project_overview(project_slug="nanliao-citizen-power"):
    overview = get_project_overview(project_slug)
    if not overview:
        return jsonify({"message": "找不到指定案場"}), 404

    return render_template("project_overview_v3.html", **overview)


@app.route("/progress", methods=["GET", "POST"])
def progress():
    if request.method == "POST":
        stage = request.form.get("stage", "").strip()
        updated_at = request.form.get("updated_at", "").strip()
        line_user_id = request.form.get("line_user_id", "").strip()
        display_name = request.form.get("display_name", "").strip()

        if stage not in PROGRESS_STAGES or not updated_at or not line_user_id or not display_name:
            return redirect(url_for("progress", saved="0"))

        try:
            parse_progress_date(updated_at)
        except ValueError:
            return redirect(url_for("progress", saved="0"))

        create_progress(stage, updated_at, line_user_id, display_name)
        return redirect(url_for("progress", saved="1"))

    progress_rows = get_progress_records()
    latest_record = progress_rows[0] if progress_rows else None
    records_asc = list(reversed(progress_rows))
    predictions = build_predicted_progress(latest_record, records_asc)
    service_steps = get_service_journey_steps()
    default_sop_status = build_sop_status(latest_record, service_steps)

    return render_template(
        "progress_v3.html",
        latest_record=latest_record,
        progress_rows=progress_rows,
        predicted_rows=predictions,
        progress_stages=PROGRESS_STAGES,
        service_steps=service_steps,
        default_sop_status=default_sop_status,
        saved=request.args.get("saved"),
        liff_id=get_liff_id(),
    )


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)





