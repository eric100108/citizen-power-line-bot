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


def reply_line_message(reply_token, text):
    channel_access_token = get_channel_access_token()
    if not channel_access_token:
        print("ERROR: CHANNEL_ACCESS_TOKEN is missing")
        return

    headers = {
        "Authorization": f"Bearer {channel_access_token}",
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


def reply_faq_quick_reply(reply_token):
    channel_access_token = get_channel_access_token()
    if not channel_access_token:
        print("ERROR: CHANNEL_ACCESS_TOKEN is missing")
        return

    headers = {
        "Authorization": f"Bearer {channel_access_token}",
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
