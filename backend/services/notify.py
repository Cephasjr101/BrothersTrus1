# Notifications: in-app (always) + SendGrid email + Africa's Talking SMS (when configured).
import json
import re
import urllib.parse
import urllib.request

import config
from deps import notify as _inapp


def normalize_phone(p: str) -> str:
    if not p:
        return ""
    d = re.sub(r"[^\d+]", "", p)
    if d.startswith("00"):
        d = "+" + d[2:]
    elif d.startswith("0"):
        d = "+234" + d[1:]
    elif d and not d.startswith("+"):
        d = "+" + d
    return d


def _post_json(url, headers, payload, timeout=15):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


def send_email(to: str, subject: str, html: str) -> bool:
    if not (config.SENDGRID_API_KEY and to):
        return False
    try:
        _post_json("https://api.sendgrid.com/v3/mail/send",
                   {"Authorization": "Bearer " + config.SENDGRID_API_KEY,
                    "Content-Type": "application/json"},
                   {"personalizations": [{"to": [{"email": to}]}],
                    "from": {"email": config.SENDGRID_FROM_EMAIL, "name": config.SENDGRID_FROM_NAME},
                    "subject": subject,
                    "content": [{"type": "text/html", "value": html}]})
        return True
    except Exception:
        return False


def send_sms(to: str, message: str) -> bool:
    if not (config.AT_API_KEY and to):
        return False
    phone = normalize_phone(to)
    try:
        body = urllib.parse.urlencode({
            "username": config.AT_USERNAME, "to": phone,
            "message": message[:470], "from": config.AT_SENDER_ID}).encode()
        req = urllib.request.Request(
            "https://api.africastalking.com/version1/messaging", data=body, method="POST",
            headers={"apiKey": config.AT_API_KEY, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status in (200, 201)
    except Exception:
        return False


def _template(title: str, body: str) -> str:
    return f"""<div style="font-family:Segoe UI,Arial,sans-serif;max-width:560px;margin:auto">
  <div style="background:#053f22;color:#fff;padding:18px 24px;border-radius:12px 12px 0 0">
    <b style="font-size:18px">Brother'sTrust <span style="color:#f6b51e">Travel</span></b>
  </div>
  <div style="border:1px solid #e2e9e4;border-top:0;padding:24px;border-radius:0 0 12px 12px">
    <h2 style="margin:0 0 10px">{title}</h2>
    <p style="color:#5d6f66;line-height:1.6">{body}</p>
    <p style="color:#9aa8a1;font-size:12px;margin-top:24px">Brother'sTrust Travel · Lagos · Abuja · Accra<br>
    hello@brotherstrusttravel.com · +234 800 276 8437</p>
  </div></div>"""


def send_notification(db, user_id: int, title: str, body: str = "",
                      email: str = "", phone: str = "") -> None:
    """In-app always; email/SMS fire-and-forget when services are configured."""
    _inapp(db, user_id, title, body)
    if email:
        send_email(email, f"{title} — Brother'sTrust Travel", _template(title, body))
    if phone:
        send_sms(phone, f"{title}: {body}")
