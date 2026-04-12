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
    verify_line_signature,
)
from project_repo import get_project_overview
from progress_repo import create_progress, get_latest_user_progress, get_progress_records, get_service_journey_steps
from progress_service import (
    PROGRESS_STAGES,
    build_predicted_progress,
    build_sop_status,
    parse_progress_date,
)

app = Flask(__name__)


def row_to_dict(row):
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


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

        answer = find_faq_answer(user_message)
        reply_text = answer if answer else "目前找不到對應答案，你可以直接輸入 FAQ 或改問補助、投資、進度等關鍵字。"
        reply_line_message(reply_token, reply_text)

    return "OK", 200


@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "system": "citizen power line bot",
        "version": "0.8",
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
