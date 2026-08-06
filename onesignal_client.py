"""OneSignal integration. Primary delivery path for the Book a Call form.

Three things happen on submission:

1. The lead is upserted as a OneSignal user with tags, so they can be
   segmented and enrolled in sequences from the dashboard.
2. An alert with the full lead details is sent to the team. This is the
   message that must not be lost, so deliver_lead() runs synchronously and
   returns a boolean the caller uses to decide what the visitor sees.
3. A confirmation is sent to the lead on a background thread. Optional; the
   lead is already captured by then.

Resend stays in app.py as an automatic fallback. If OneSignal fails and SMTP
credentials are present, the alert is retried over SMTP before the visitor is
shown an error. With SMTP unset, the site is OneSignal-only.

Marketing consent is stored as a tag, not assumed. Everyone who submits is
recorded so you have the contact; only those who ticked the box are tagged
marketing_opt_in=true. Build every sequence segment on that tag.

API reference: https://documentation.onesignal.com/reference/create-user
"""

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger(__name__)

API_ROOT = "https://api.onesignal.com"
TIMEOUT = 10  # seconds per call

APP_ID = os.environ.get("ONESIGNAL_APP_ID", "")
API_KEY = os.environ.get("ONESIGNAL_API_KEY", "")

# Where lead alerts are delivered. Comma separated for multiple recipients.
NOTIFY_TO = [
    a.strip().lower()
    for a in os.environ.get("LEAD_NOTIFY_TO", "isaac@betweensundaysconsulting.com").split(",")
    if a.strip()
]

# Internal recipients only need to be registered once per process.
_known_internal = set()

# Optional. Design the confirmation email in the OneSignal dashboard and paste
# the template UUID here. If unset, the inline HTML below is used.
TEMPLATE_ID = os.environ.get("ONESIGNAL_TEMPLATE_ID", "")
FROM_NAME = os.environ.get("ONESIGNAL_FROM_NAME", "Between Sundays")
REPLY_TO = os.environ.get("ONESIGNAL_REPLY_TO", "")

def is_configured():
    return bool(APP_ID and API_KEY)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _post(path, payload):
    """POST JSON to OneSignal. Returns (status, parsed_body)."""
    req = urllib.request.Request(
        API_ROOT + path,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Key %s" % API_KEY,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        return exc.code, {"raw": exc.read().decode("utf-8", "replace")}


def _send_email(payload):
    """Send one email. Returns True only when OneSignal accepted and targeted
    at least one subscriber. A 200 with an empty id means nobody was reached."""
    status, body = _post("/notifications?c=email", payload)
    if status == 200 and body.get("id"):
        return True
    log.error("OneSignal send failed (%s): %s", status, body)
    return False


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def _upsert_user(email, tags):
    payload = {
        "identity": {"external_id": email},
        "properties": {"tags": tags},
        "subscriptions": [
            {"type": "Email", "token": email, "enabled": True, "notification_types": 1}
        ],
    }
    status, body = _post("/apps/%s/users" % APP_ID, payload)
    if status in (200, 201, 202):
        return True
    log.error("OneSignal user upsert failed (%s) for %s: %s", status, email, body)
    return False


def _lead_tags(form, opt_in):
    """OneSignal tags must be flat string key/value pairs."""
    tags = {
        "lead_source": form.get("source") or "site",
        "lead_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "marketing_opt_in": "true" if opt_in else "false",
        "status": "new_lead",
        "internal_team": "false",
    }
    optional = {
        "name": form.get("name"),
        "organization": form.get("org"),
        "org_type": form.get("org_type"),
        "org_size": form.get("size"),
        "interest": form.get("interest"),
        "phone": form.get("phone"),
    }
    for key, value in optional.items():
        if value:
            tags[key] = str(value)[:255]
    return tags


def _ensure_internal_recipients():
    """Register team addresses as tagged users so they can be targeted by alias
    and excluded from every marketing segment."""
    for address in NOTIFY_TO:
        if address in _known_internal:
            continue
        if _upsert_user(address, {"internal_team": "true", "status": "team"}):
            _known_internal.add(address)


def _esc(value):
    if not value:
        return "not provided"
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _alert_html(form, opt_in):
    rows = [
        ("Name", form.get("name")),
        ("Organization", form.get("org")),
        ("Type", form.get("org_type")),
        ("Size", form.get("size")),
        ("Email", form.get("email")),
        ("Phone", form.get("phone")),
        ("Interested in", form.get("interest")),
        ("Source", form.get("source") or "site"),
        ("Marketing opt in", "Yes" if opt_in else "No"),
    ]
    cells = "".join(
        '<tr><td style="padding:7px 0;color:#6b7280;font-size:13px;width:150px;'
        'vertical-align:top;">{label}</td>'
        '<td style="padding:7px 0;color:#0B1026;font-size:15px;font-weight:500;">'
        "{value}</td></tr>".format(label=_esc(label), value=_esc(value))
        for label, value in rows
    )
    message = _esc(form.get("message")).replace("\n", "<br>")
    reply_to = _esc(form.get("email"))
    return (
        '<!DOCTYPE html><html><body style="margin:0;padding:24px;'
        'background:#f7f9ff;font-family:Helvetica,Arial,sans-serif;">'
        '<div style="max-width:600px;margin:0 auto;background:#fff;'
        'border-radius:14px;padding:30px;">'
        '<p style="font-size:12px;letter-spacing:0.14em;text-transform:uppercase;'
        'color:#2563FF;margin:0 0 14px;font-weight:600;">New lead</p>'
        '<h1 style="font-size:22px;margin:0 0 22px;color:#0B1026;">'
        + _esc(form.get("org"))
        + "</h1>"
        '<table style="width:100%;border-collapse:collapse;">'
        + cells
        + "</table>"
        '<p style="font-size:13px;color:#6b7280;margin:24px 0 6px;'
        'border-top:1px solid #e5e7eb;padding-top:18px;">Message</p>'
        '<p style="font-size:15px;line-height:1.6;color:#0B1026;margin:0 0 24px;">'
        + (message or "none")
        + "</p>"
        '<a href="mailto:'
        + reply_to
        + '" style="display:inline-block;background:#2563FF;color:#fff;'
        'text-decoration:none;padding:13px 24px;border-radius:999px;'
        'font-weight:600;font-size:15px;">Reply to this lead</a>'
        "</div></body></html>"
    )


def deliver_lead(form, opt_in):
    """Synchronous. Upsert the lead and send the team alert.

    Returns True only if OneSignal accepted the alert and targeted at least one
    recipient. False tells the caller to try the SMTP fallback.
    """
    if not is_configured():
        log.warning("OneSignal not configured, cannot deliver lead alert.")
        return False

    email = (form.get("email") or "").strip().lower()
    try:
        # Order matters: the lead record must exist before the confirmation
        # targets it by alias.
        _upsert_user(email, _lead_tags(form, opt_in))
        _ensure_internal_recipients()
        return _send_email({
            "app_id": APP_ID,
            "name": "Lead alert",
            "include_aliases": {"external_id": NOTIFY_TO},
            "target_channel": "email",
            "email_subject": "New lead: %s (%s)" % (form.get("org", ""), form.get("name", "")),
            "email_preheader": "Reply within one business day.",
            "email_body": _alert_html(form, opt_in),
            "email_from_name": FROM_NAME,
            "email_reply_to_address": email,
            "include_unsubscribed": True,
            "disable_email_click_tracking": True,
        })
    except Exception as exc:  # noqa: BLE001
        log.error("OneSignal lead alert failed: %s", exc)
        return False


def _confirmation_html(first_name):
    greeting = "Hi %s," % first_name if first_name else "Hi,"
    return """\
<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f7f9ff;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f9ff;padding:32px 16px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:16px;padding:36px 32px;font-family:Helvetica,Arial,sans-serif;color:#0B1026;">
<tr><td>
<p style="font-size:12px;letter-spacing:0.16em;text-transform:uppercase;color:#2563FF;margin:0 0 18px;font-weight:600;">Between Sundays</p>
<h1 style="font-size:26px;line-height:1.2;margin:0 0 18px;font-weight:600;">{{GREETING}}</h1>
<p style="font-size:16px;line-height:1.6;color:#3b4257;margin:0 0 16px;">Thanks for reaching out. We have your request and will reply within one business day with a few times to talk.</p>
<p style="font-size:16px;line-height:1.6;color:#3b4257;margin:0 0 16px;">The call runs about twenty minutes. We will walk through where your data lives today, where people are falling through, and whether an operating system is worth building for you right now. No pitch deck.</p>
<p style="font-size:16px;line-height:1.6;color:#3b4257;margin:0 0 28px;">If anything comes up before then, just reply to this email.</p>
<p style="font-size:15px;line-height:1.6;color:#0B1026;margin:0;font-weight:600;">Between Sundays</p>
<p style="font-size:14px;line-height:1.6;color:#6b7280;margin:2px 0 0;">Helping churches and nonprofits build operating systems to know every person and lead them to their next step.</p>
</td></tr></table>
</td></tr></table>
</body></html>""".replace("{{GREETING}}", greeting)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _run(form):
    email = (form.get("email") or "").strip().lower()
    if not email:
        return
    first_name = (form.get("name") or "").strip().split(" ")[0]
    try:
        payload = {
            "app_id": APP_ID,
            "name": "Book a call confirmation",
            "include_aliases": {"external_id": [email]},
            "target_channel": "email",
            "email_subject": "We got your request",
            "email_preheader": "We reply within one business day.",
            "email_from_name": FROM_NAME,
            "include_unsubscribed": True,
        }
        if TEMPLATE_ID:
            payload["template_id"] = TEMPLATE_ID
            payload["custom_data"] = {"first_name": first_name or "there"}
        else:
            payload["email_body"] = _confirmation_html(first_name)
        if REPLY_TO:
            payload["email_reply_to_address"] = REPLY_TO
        _send_email(payload)
    except Exception as exc:  # noqa: BLE001
        log.error("OneSignal sync error for %s: %s", email, exc)


def send_confirmation_only(form):
    """Fire and forget. Returns immediately; the confirmation is sent on a
    daemon thread so a slow OneSignal response cannot delay the redirect."""
    if not is_configured():
        return
    threading.Thread(target=_run, args=(form,), daemon=True).start()
