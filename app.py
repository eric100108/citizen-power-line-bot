import os
import sqlite3
import requests
from flask import Flask, jsonify, request
app = Flask(__name__)#建立Flask應用程式

DB_NAME = "app.db"
CHANNEL_ACCESS_TOKEN = "FqcdztZgTNH5UxO1pklwcyZFPHVz0f7WV7NQ59z6VP9DE2vyB0cRsiF1ZcV7LBcPxazjJhzFn1U+JusP7goxQ7qf/UKmn6G4BhesEMaSZ/8n775N8Jkgo4e0LO2Vcv82bljisDJEoMxc6bVwBUmADwdB04t89/1O/w1cDnyilFU="

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



#建立網站首頁回應
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if "events" in data:
        for event in data["events"]:
            if event["type"] == "message":
                reply_token = event["replyToken"]
                user_message = event["message"]["text"]

                headers = {
                    "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
                    "Content-Type": "application/json"
                }

                body = {
                    "replyToken": reply_token,
                    "messages": [
                        {
                            "type": "text",
                            "text": f"你說：{user_message}"
                        }
                    ]
                }

                requests.post(
                    "https://api.line.me/v2/bot/message/reply",
                    headers=headers,
                    json=body
                )

    return "OK"
@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "system": "citizen power line bot",
        "version": "0.1",
        "features": {
            "faq_all": "/faq",
            "faq_search": "/faq?keyword=公民電廠",
            "calc": "/calc?amount=10000",
            "progress": "/progress"
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
if __name__ == "__main__":
    init_db()  # 初始化資料庫
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)