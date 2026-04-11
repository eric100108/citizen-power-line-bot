import os
from flask import Flask, jsonify, redirect, render_template, request, url_for

from calc_repo import get_share_rate
from db import init_db
from faq_repo import find_faq_answer, list_faqs
from line_service import reply_faq_quick_reply, reply_line_message
from progress_repo import create_progress, get_progress_records
from progress_service import PROGRESS_STAGES, build_predicted_progress, parse_progress_date

app = Flask(__name__)


@app.route("/menu")
def menu():
    return render_template("menu.html")


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)
    print("=== webhook received ===")
    print(data)

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
        reply_text = answer if answer else "查無相關 FAQ，請輸入 FAQ 查看可選問題。"
        reply_line_message(reply_token, reply_text)

    return "OK", 200


@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "system": "citizen power line bot",
        "version": "0.5",
        "features": {
            "faq_all": "/faq",
            "faq_search": "/faq?keyword=公民電廠",
            "calc": "/calc?amount=10000",
            "progress": "/progress",
            "webhook": "/webhook",
            "menu": "/menu",
        },
    })


@app.route("/faq")
def faq():
    keyword = request.args.get("keyword", default="", type=str)
    rows = list_faqs(keyword)

    if not rows:
        return jsonify({"message": "找不到相關 FAQ"}), 404

    return jsonify([
        {"question": row["question"], "answer": row["answer"]}
        for row in rows
    ])


@app.route("/hello")
def hello():
    return "歡迎使用公民電廠服務"


@app.route("/calc")
def calc():
    amount = request.args.get("amount", default=10000, type=float)
    share_rate = get_share_rate()

    if share_rate is None:
        return "找不到投資試算規則", 404

    estimated_return = amount * share_rate
    return render_template(
        "calc.html",
        amount=amount,
        share_rate=share_rate,
        estimated_return=estimated_return,
    )


@app.route("/progress", methods=["GET", "POST"])
def progress():
    if request.method == "POST":
        stage = request.form.get("stage", "").strip()
        updated_at = request.form.get("updated_at", "").strip()

        if stage not in PROGRESS_STAGES or not updated_at:
            return redirect(url_for("progress", saved="0"))

        try:
            parse_progress_date(updated_at)
        except ValueError:
            return redirect(url_for("progress", saved="0"))

        create_progress(stage, updated_at)
        return redirect(url_for("progress", saved="1"))

    progress_rows = get_progress_records()
    latest_record = progress_rows[0] if progress_rows else None
    records_asc = list(reversed(progress_rows))
    predictions = build_predicted_progress(latest_record, records_asc)

    return render_template(
        "progress.html",
        latest_record=latest_record,
        progress_rows=progress_rows,
        predicted_rows=predictions,
        progress_stages=PROGRESS_STAGES,
        saved=request.args.get("saved"),
    )


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
