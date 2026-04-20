import base64
import hashlib
import hmac
import os

import requests


def get_channel_access_token():
    return os.environ.get("CHANNEL_ACCESS_TOKEN", "").strip()


def get_channel_secret():
    return os.environ.get("CHANNEL_SECRET", "").strip()


def get_line_login_channel_id():
    return os.environ.get("LINE_LOGIN_CHANNEL_ID", "").strip()


def get_public_base_url():
    return os.environ.get("PUBLIC_BASE_URL", "https://citizen-power-line-bot.onrender.com").strip().rstrip("/")


def _reply_payload(reply_token, messages):
    channel_access_token = get_channel_access_token()
    if not channel_access_token:
        print("ERROR: CHANNEL_ACCESS_TOKEN is missing")
        return None, None

    headers = {
        "Authorization": f"Bearer {channel_access_token}",
        "Content-Type": "application/json",
    }
    body = {
        "replyToken": reply_token,
        "messages": messages,
    }
    return headers, body


def reply_line_message(reply_token, text):
    headers, body = _reply_payload(reply_token, [{"type": "text", "text": text}])
    if not headers:
        return

    response = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=headers,
        json=body,
        timeout=10,
    )
    print("LINE reply status:", response.status_code)


def reply_line_quick_reply(reply_token, text, items):
    headers, body = _reply_payload(
        reply_token,
        [
            {
                "type": "text",
                "text": text,
                "quickReply": {"items": items},
            }
        ],
    )
    if not headers:
        return

    response = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=headers,
        json=body,
        timeout=10,
    )
    print("LINE quick reply status:", response.status_code)


def _quick_reply_item(label, text):
    return {
        "type": "action",
        "action": {
            "type": "message",
            "label": label[:20],
            "text": text,
        },
    }


def _compact_lines(text, limit=5):
    lines = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = []
        current = ""
        for char in line:
            current += char
            if char in "。；;，," or len(current) >= 38:
                parts.append(current.strip("，,；;。 "))
                current = ""
        if current.strip():
            parts.append(current.strip())

        for part in parts:
            if part:
                lines.append(part)
            if len(lines) >= limit:
                break
        if len(lines) >= limit:
            break
    return lines or ["請直接選擇下方功能。"]


def _card_title(text, default_title="公民電廠助手"):
    normalized = (text or "").replace(" ", "")
    if "補助" in normalized:
        return "補助資訊"
    if "場址" in normalized or "屋頂" in normalized:
        return "場址盤點"
    if "SOP" in normalized or "sop" in normalized:
        return "SOP 進度"
    if "開始" in normalized or "建立電廠" in normalized:
        return "開始建立電廠"
    if "你好" in normalized or "可以協助" in normalized:
        return "公民電廠助手"
    return default_title


def _hero_image_url():
    base_url = get_public_base_url()
    if not base_url.startswith("https://"):
        return ""
    return f"{base_url}/static/hero-photo.jpg"


def _build_flex_quick_reply_message(title, subtitle, text, items):
    body_contents = []
    for line in _compact_lines(text):
        body_contents.append(
            {
                "type": "box",
                "layout": "horizontal",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "width": "6px",
                        "height": "6px",
                        "cornerRadius": "3px",
                        "backgroundColor": "#23C55E",
                        "margin": "md",
                        "contents": [],
                    },
                    {
                        "type": "text",
                        "text": line,
                        "size": "sm",
                        "color": "#17342F",
                        "wrap": True,
                        "flex": 1,
                    },
                ],
            }
        )

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "18px",
            "backgroundColor": "#0F3D3E",
            "contents": [
                {
                    "type": "text",
                    "text": title,
                    "weight": "bold",
                    "size": "lg",
                    "color": "#FFFFFF",
                    "wrap": True,
                },
                {
                    "type": "text",
                    "text": subtitle,
                    "size": "xs",
                    "color": "#B9FBCB",
                    "margin": "sm",
                    "wrap": True,
                },
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "paddingAll": "18px",
            "backgroundColor": "#F7FBF6",
            "contents": body_contents,
        },
    }

    image_url = _hero_image_url()
    if image_url:
        bubble["hero"] = {
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "20:9",
            "aspectMode": "cover",
        }

    message = {
        "type": "flex",
        "altText": title,
        "contents": bubble,
    }
    if items:
        message["quickReply"] = {"items": items}
    return message


def reply_line_flex_quick_reply(reply_token, title, subtitle, text, items):
    headers, body = _reply_payload(
        reply_token,
        [_build_flex_quick_reply_message(title, subtitle, text, items)],
    )
    if not headers:
        return

    response = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=headers,
        json=body,
        timeout=10,
    )
    print("LINE flex quick reply status:", response.status_code)


def reply_faq_quick_reply(reply_token):
    items = [
        _quick_reply_item("什麼是公民電廠？", "什麼是公民電廠？"),
        _quick_reply_item("開始建立電廠", "開始建立電廠要做什麼？"),
        _quick_reply_item("有補助嗎", "有補助可以申請嗎？"),
        _quick_reply_item("場址怎麼看", "場址要怎麼評估？"),
        _quick_reply_item("我到哪一步", "我現在進行到哪一步？"),
    ]
    reply_line_flex_quick_reply(
        reply_token,
        "常見問題",
        "選一個主題，我會直接帶你看重點。",
        "可以從建立流程、補助、場址或進度開始。",
        items,
    )


def reply_start_build_quick_reply(reply_token, text):
    items = [
        _quick_reply_item("完整 SOP", "完整 SOP"),
        _quick_reply_item("補助", "補助"),
        _quick_reply_item("場址", "場址"),
        _quick_reply_item("真人協助", "真人協助"),
    ]
    reply_line_flex_quick_reply(
        reply_token,
        _card_title(text),
        "先看重點，再選下一步。",
        text,
        items,
    )


def reply_related_faq_quick_reply(reply_token, text, questions):
    items = []
    for question in questions[:4]:
        items.append(_quick_reply_item(question, question))

    if items:
        reply_line_flex_quick_reply(
            reply_token,
            "相關問題",
            "請點選最接近你想問的問題。",
            text,
            items,
        )
        return

    reply_line_message(reply_token, text)


def get_liff_id():
    return os.environ.get("LIFF_ID", "").strip()


def verify_line_signature(body, signature):
    channel_secret = get_channel_secret()
    if not channel_secret or not signature:
        return False

    digest = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected_signature = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected_signature, signature)


def get_line_profile_from_access_token(access_token):
    if not access_token:
        raise ValueError("missing access token")

    verify_response = requests.get(
        "https://api.line.me/oauth2/v2.1/verify",
        params={"access_token": access_token},
        timeout=10,
    )
    verify_response.raise_for_status()
    verify_data = verify_response.json()

    line_login_channel_id = get_line_login_channel_id()
    if line_login_channel_id and verify_data.get("client_id") != line_login_channel_id:
        raise ValueError("channel id mismatch")

    scopes = verify_data.get("scope", "")
    if "profile" not in scopes.split():
        raise ValueError("profile scope missing")

    profile_response = requests.get(
        "https://api.line.me/v2/profile",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    profile_response.raise_for_status()
    profile = profile_response.json()

    return {
        "line_user_id": profile.get("userId", ""),
        "display_name": profile.get("displayName", ""),
        "picture_url": profile.get("pictureUrl", ""),
    }

