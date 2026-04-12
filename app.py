import os
from flask import Flask, jsonify, redirect, render_template, request, url_for

from calc_repo import build_calculator_result
from db import init_db
from faq_repo import find_faq_answer, list_faqs
from line_service import (
    get_liff_id,
    get_line_profile_from_access_token,
    reply_faq_quick_reply,
    reply_line_message,
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


def row_to_dict(row):
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def build_start_build_message(service_steps):
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

        if user_message in START_BUILD_KEYWORDS:
            reply_start_build_quick_reply(reply_token, build_start_build_message(service_steps))
            continue

        if user_message in FULL_SOP_KEYWORDS:
            reply_start_build_quick_reply(reply_token, build_full_sop_message(service_steps))
            continue

        if user_message in SUBSIDY_KEYWORDS:
            subsidy_answer = find_faq_answer("補助") or "補助準備建議先確認申請窗口、截止日期、附件清單與預算拆分。"
            reply_start_build_quick_reply(reply_token, subsidy_answer)
            continue

        if user_message in SITE_KEYWORDS:
            reply_start_build_quick_reply(reply_token, build_site_guidance_message(service_steps))
            continue

        if user_message in PROGRESS_KEYWORDS:
            reply_start_build_quick_reply(reply_token, build_progress_position_message(line_user_id, service_steps, project_rows))
            continue

        if user_message in HUMAN_HELP_KEYWORDS:
            reply_start_build_quick_reply(reply_token, build_human_help_message())
            continue

        answer = find_faq_answer(user_message)
        reply_text = answer if answer else "目前找不到對應答案，你可以輸入『開始建立電廠』、FAQ、補助、場址或真人協助。"
        reply_line_message(reply_token, reply_text)

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
    project_slug = request.args.get("project", default="nanliao-citizen-power", type=str).strip() or "nanliao-citizen-power"
    calc_result = build_calculator_result(amount, project_slug)
    return render_template("calc_v4.html", **calc_result)


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
