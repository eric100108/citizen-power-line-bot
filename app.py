import os
import sqlite3
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

DB_NAME = "app.db"
CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")


def init_db():
    conn = sqlite3.connect(DB_NAME)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS faq_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS progress_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stage TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS calculator_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_name TEXT NOT NULL,
        value REAL NOT NULL
    )
    """)

    cursor = conn.execute("SELECT COUNT(*) FROM calculator_rules")
    count = cursor.fetchone()[0]
    if count == 0:
        conn.execute("""
        INSERT INTO calculator_rules (rule_name, value)
        VALUES (?, ?)
        """, ("share_rate", 0.5))

    cursor = conn.execute("SELECT COUNT(*) FROM faq_items")
    count = cursor.fetchone()[0]
    if count == 0:
        conn.execute("""
        INSERT INTO faq_items (question, answer)
        VALUES (?, ?)
        """, ("什麼是公民電廠？", "公民電廠是由社區居民共同參與的再生能源建置與收益共享模式。"))

        conn.execute("""
        INSERT INTO faq_items (question, answer)
        VALUES (?, ?)
        """, ("為什麼要推動公民電廠？", "因為它可以提升在地能源自主、促進社區參與，並創造地方收益。"))

    cursor = conn.execute("SELECT COUNT(*) FROM progress_items")
    count = cursor.fetchone()[0]
    if count == 0:
        conn.execute("""
        INSERT INTO progress_items (stage, updated_at)
        VALUES (?, ?)
        """, ("申請中", "2026-04-10"))

    conn.commit()
    conn.close()


def find_faq_answer(keyword):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    row = conn.execute("""
        SELECT answer
        FROM faq_items
        WHERE question LIKE ? OR answer LIKE ?
        LIMIT 1
    """, (f"%{keyword}%", f"%{keyword}%")).fetchone()

    conn.close()

    if row:
        return row["answer"]
    return None


def reply_line_message(reply_token, text):
    if not CHANNEL_ACCESS_TOKEN:
        print("ERROR: CHANNEL_ACCESS_TOKEN 未設定")
        return

    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    body = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
    }

    response = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=headers,
        json=body,
        timeout=10
    )

    print("LINE reply status:", response.status_code)
    print("LINE reply body:", response.text)


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

        answer = find_faq_answer(user_message)

        if answer:
            reply_text = answer
        else:
            reply_text = "查無相關 FAQ\n你可以試試看問：\n- 公民電廠\n- 為什麼要推動公民電廠"

        reply_line_message(reply_token, reply_text)

    return "OK", 200


@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "system": "citizen power line bot",
        "version": "0.2",
        "features": {
            "faq_all": "/faq",
            "faq_search": "/faq?keyword=公民電廠",
            "calc": "/calc?amount=10000",
            "progress": "/progress",
            "webhook": "/webhook"
        }
    })


@app.route("/faq")
def faq():
    keyword = request.args.get("keyword", default="", type=str)

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    if keyword:
        rows = conn.execute("""
            SELECT question, answer
            FROM faq_items
            WHERE question LIKE ? OR answer LIKE ?
        """, (f"%{keyword}%", f"%{keyword}%")).fetchall()
    else:
        rows = conn.execute("""
            SELECT question, answer
            FROM faq_items
        """).fetchall()

    conn.close()

    if not rows:
        return jsonify({
            "message": "查無相關 FAQ"
        }), 404

    result = []
    for row in rows:
        result.append({
            "question": row["question"],
            "answer": row["answer"]
        })

    return jsonify(result)


@app.route("/hello")
def hello():
    return "你好，這是我自己新增的頁面"


@app.route("/calc")
def calc():
    amount = request.args.get("amount", default=0, type=float)

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    row = conn.execute("""
        SELECT value
        FROM calculator_rules
        WHERE rule_name = ?
        LIMIT 1
    """, ("share_rate",)).fetchone()

    conn.close()

    if row is None:
        return jsonify({
            "error": "查無試算規則"
        }), 404

    share_rate = row["value"]
    estimated_return = amount * share_rate

    return jsonify({
        "input_amount": amount,
        "share_rate": share_rate,
        "estimated_return": estimated_return
    })


@app.route("/progress")
def progress():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    row = conn.execute("""
        SELECT stage, updated_at
        FROM progress_items
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    conn.close()

    if row is None:
        return jsonify({
            "error": "目前查無進度資料"
        }), 404

    return jsonify({
        "stage": row["stage"],
        "updated_at": row["updated_at"]
    })


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)