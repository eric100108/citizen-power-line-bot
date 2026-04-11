import os

import requests


CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")


def reply_line_message(reply_token, text):
    if not CHANNEL_ACCESS_TOKEN:
        print("ERROR: CHANNEL_ACCESS_TOKEN is missing")
        return

    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }

    response = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=headers,
        json=body,
        timeout=10,
    )
    print("LINE reply status:", response.status_code)
    print("LINE reply body:", response.text)


def reply_faq_quick_reply(reply_token):
    if not CHANNEL_ACCESS_TOKEN:
        print("ERROR: CHANNEL_ACCESS_TOKEN is missing")
        return

    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": "請選擇想了解的問題：",
                "quickReply": {
                    "items": [
                        {
                            "type": "action",
                            "action": {
                                "type": "message",
                                "label": "什麼是公民電廠？",
                                "text": "什麼是公民電廠？",
                            },
                        },
                        {
                            "type": "action",
                            "action": {
                                "type": "message",
                                "label": "為什麼要推動公民電廠？",
                                "text": "為什麼要推動公民電廠？",
                            },
                        },
                    ]
                },
            }
        ],
    }

    response = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=headers,
        json=body,
        timeout=10,
    )
    print("LINE quick reply status:", response.status_code)
    print("LINE quick reply body:", response.text)
