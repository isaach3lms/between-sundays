"""Between Sundays marketing site.

Flask + Jinja2, no database. Contact form posts server side, validates,
and delivers email through the Resend HTTP API over port 443.

The HTTP API is used rather than SMTP because 443 is never blocked by a host
or firewall, errors come back as readable JSON instead of SMTP status codes,
and there is no TLS handshake or login round trip to fail.

Two messages per submission. The lead alert to the team is sent synchronously
and its result decides whether the visitor sees the thank-you page or a
fallback address. The confirmation to the lead is best effort and can never
fail the form.
"""

import json
import os
import re
import urllib.error
import urllib.request

from flask import Flask, redirect, render_template, request, url_for

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")

# ---------------------------------------------------------------------------
# Configuration (set these as environment variables on your host)
# ---------------------------------------------------------------------------
# Resend. RESEND_API_KEY is never committed; it is set as an environment
# variable on the host. SMTP_PASS is accepted as a legacy alias.
RESEND_API_KEY = os.environ.get("RESEND_API_KEY") or os.environ.get("SMTP_PASS", "")
RESEND_ENDPOINT = "https://api.resend.com/emails"

# Must be on a domain verified in Resend.
MAIL_FROM = os.environ.get("MAIL_FROM", "website@betweensundaysconsulting.com")
MAIL_FROM_NAME = os.environ.get("MAIL_FROM_NAME", "Between Sundays")

# Set to "false" to stop sending the confirmation email to the lead.
SEND_CONFIRMATION = os.environ.get("SEND_CONFIRMATION", "true").lower() != "false"
# Where lead alerts are delivered. Comma separated for multiple recipients.
MAIL_TO = [
    a.strip()
    for a in os.environ.get("MAIL_TO", "isaac@betweensundaysconsulting.com").split(",")
    if a.strip()
]

# The address displayed publicly in the footer and on the Book a Call page.
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "isaac@betweensundaysconsulting.com")

# Live product demo. Blank this env var to hide every View demo button.
DEMO_URL = os.environ.get("DEMO_URL", "https://demo.betweensundaysconsulting.com")

# Stripe customer portal login link (Billing > Customer portal > no-code link).
# Left empty by default so the live site never ships a dead button.
CLIENT_PORTAL_URL = os.environ.get("CLIENT_PORTAL_URL", "")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")

SITE = {
    "name": "Between Sundays",
    "tagline": (
        "Helping churches and nonprofits build operating systems to know every "
        "person and lead them to their next step."
    ),
    "email": CONTACT_EMAIL,
    "client_portal": CLIENT_PORTAL_URL,
    "demo_url": DEMO_URL,
    "linkedin": "https://www.linkedin.com/company/between-sundays-consulting/",
}

# Rotating hero phrases. Each pair is (what a person does, what the system tracks).
DISCIPLESHIP_IS = [
    ("reading your Bible.", "Bible engagement"),
    ("serving on a team.", "Service planning"),
    ("giving.", "Generosity"),
    ("showing up on a Wednesday.", "Attendance"),
    ("joining a small group.", "Groups"),
    ("following up with a guest.", "First-time guests"),
    ("getting baptized.", "Milestones"),
    ("praying for someone by name.", "Care requests"),
    ("inviting your neighbor.", "Invites"),
    ("leading a group of your own.", "Multiplication"),
]


@app.context_processor
def inject_site():
    return {"site": SITE}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html", page="home", phrases=DISCIPLESHIP_IS)


@app.route("/for-churches")
def for_churches():
    return render_template("for_churches.html", page="churches")


@app.route("/for-nonprofits")
def for_nonprofits():
    return render_template("for_nonprofits.html", page="nonprofits")


@app.route("/case-studies")
def case_studies():
    return render_template("case_studies.html", page="case-studies")


@app.route("/book-a-call", methods=["GET", "POST"])
def book_a_call():
    if request.method == "GET":
        return render_template("book_a_call.html", page="book", errors={}, form={})

    form = {k: (v or "").strip() for k, v in request.form.items()}

    # Honeypot: real people leave this empty. Bots fill it.
    if form.get("website"):
        return redirect(url_for("thank_you"))

    errors = validate(form)
    if errors:
        return render_template("book_a_call.html", page="book", errors=errors, form=form), 400

    opt_in = bool(request.form.get("opt_in"))

    # Synchronous: the lead alert is the message that must not be lost, so its
    # result decides what the visitor sees.
    try:
        send_lead_alert(form, opt_in)
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Lead alert failed: %s", exc)
        # Never lose a lead silently. The log is the recovery path.
        app.logger.error("LEAD NOT DELIVERED, recover from this record: %s", form)
        errors["form"] = (
            "The message did not send. Email %s directly and we will follow up today."
            % CONTACT_EMAIL
        )
        return render_template("book_a_call.html", page="book", errors=errors, form=form), 500

    # Best effort: the lead is already captured, so a failure here is logged
    # and ignored rather than shown to the visitor.
    if SEND_CONFIRMATION:
        try:
            send_confirmation(form)
        except Exception as exc:  # noqa: BLE001
            app.logger.error("Confirmation to %s failed: %s", form.get("email"), exc)

    return redirect(url_for("thank_you"))


@app.route("/thank-you")
def thank_you():
    return render_template("thank_you.html", page="thank-you")


# Legacy paths from the first build.
@app.route("/services")
@app.route("/about")
def legacy_churches():
    return redirect(url_for("for_churches"), code=301)


@app.route("/pricing")
def legacy_pricing():
    return redirect(url_for("for_churches") + "#pricing", code=301)


@app.route("/contact")
def legacy_contact():
    return redirect(url_for("book_a_call"), code=301)


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html", page="404"), 404


@app.route("/healthz")
def healthz():
    return "ok", 200


@app.route("/robots.txt")
def robots():
    base = request.url_root.rstrip("/")
    body = "User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % base
    return body, 200, {"Content-Type": "text/plain"}


@app.route("/sitemap.xml")
def sitemap():
    base = request.url_root.rstrip("/")
    paths = ["/", "/for-churches", "/for-nonprofits", "/book-a-call"]
    urls = "".join("<url><loc>%s%s</loc></url>" % (base, p) for p in paths)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>' % urls
    )
    return body, 200, {"Content-Type": "application/xml"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def validate(form):
    """Required: name, email, organization. Everything else is optional so a
    qualified lead is never lost to a form error."""
    errors = {}
    if len(form.get("name", "")) < 2:
        errors["name"] = "Enter your name."
    if not EMAIL_RE.match(form.get("email", "")):
        errors["email"] = "Enter an email address we can reply to."
    if len(form.get("org", "")) < 2:
        errors["org"] = "Enter your church or organization name."
    return errors


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


def _resend_send(to, subject, text, html, reply_to=None):
    """Deliver one message through the Resend HTTP API. Raises on failure."""
    if not RESEND_API_KEY:
        # Local development: log instead of sending.
        app.logger.info("Resend not configured. Would send to %s: %s\n%s", to, subject, text)
        return

    payload = {
        "from": "%s <%s>" % (MAIL_FROM_NAME, MAIL_FROM),
        "to": to,
        "subject": subject,
        "text": text,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    req = urllib.request.Request(
        RESEND_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % RESEND_API_KEY,
            # Default urllib agents are blocked by Resend's edge. Be explicit.
            "User-Agent": "between-sundays-site/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError("Resend rejected the message (%s): %s" % (exc.code, detail))

    if not body.get("id"):
        raise RuntimeError("Resend returned no message id: %s" % body)
    app.logger.info("Resend accepted message %s to %s", body["id"], to)
    return body["id"]


def send_lead_alert(form, opt_in):
    """Send the full lead details to the team. Raises on failure so the caller
    can show the visitor a fallback address."""
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

    plain = "\n".join("%s: %s" % (label, value or "not provided") for label, value in rows)
    plain += "\n\nMessage:\n%s\n" % (form.get("message") or "(none)")

    cells = "".join(
        '<tr><td style="padding:7px 0;color:#6b7280;font-size:13px;width:150px;'
        'vertical-align:top;">%s</td>'
        '<td style="padding:7px 0;color:#0B1026;font-size:15px;font-weight:500;">'
        "%s</td></tr>" % (_esc(label), _esc(value))
        for label, value in rows
    )
    message_html = _esc(form.get("message")).replace("\n", "<br>")
    lead_email = _esc(form.get("email"))

    html = (
        '<!DOCTYPE html><html><body style="margin:0;padding:24px;'
        'background:#f7f9ff;font-family:Helvetica,Arial,sans-serif;">'
        '<div style="max-width:600px;margin:0 auto;background:#fff;'
        'border-radius:14px;padding:30px;">'
        '<p style="font-size:12px;letter-spacing:0.14em;text-transform:uppercase;'
        'color:#2563FF;margin:0 0 14px;font-weight:600;">New lead</p>'
        '<h1 style="font-size:22px;margin:0 0 22px;color:#0B1026;">' + _esc(form.get("org")) + "</h1>"
        '<table style="width:100%;border-collapse:collapse;">' + cells + "</table>"
        '<p style="font-size:13px;color:#6b7280;margin:24px 0 6px;'
        'border-top:1px solid #e5e7eb;padding-top:18px;">Message</p>'
        '<p style="font-size:15px;line-height:1.6;color:#0B1026;margin:0 0 24px;">'
        + (message_html or "none")
        + "</p>"
        '<a href="mailto:' + lead_email + '" style="display:inline-block;'
        'background:#2563FF;color:#fff;text-decoration:none;padding:13px 24px;'
        'border-radius:999px;font-weight:600;font-size:15px;">Reply to this lead</a>'
        "</div></body></html>"
    )

    _resend_send(
        to=MAIL_TO,
        subject="New lead: %s (%s)" % (form.get("org", ""), form.get("name", "")),
        text=plain,
        html=html,
        # Hitting reply goes straight to the lead, not back to the site address.
        reply_to=form.get("email", ""),
    )


def send_confirmation(form):
    """Acknowledge the submission to the person who sent it."""
    first_name = (form.get("name") or "").strip().split(" ")[0]
    greeting = "Hi %s," % first_name if first_name else "Hi,"

    plain = (
        "%s\n\n"
        "Thanks for reaching out. We have your request and will reply within one "
        "business day with a few times to talk.\n\n"
        "The call runs about twenty minutes. We will walk through where your data "
        "lives today, where people are falling through, and whether an operating "
        "system is worth building for you right now. No pitch deck.\n\n"
        "If anything comes up before then, just reply to this email.\n\n"
        "Between Sundays\n"
        "Helping churches and nonprofits build operating systems to know every "
        "person and lead them to their next step.\n" % greeting
    )

    html = (
        '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f9ff;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f7f9ff;padding:32px 16px;"><tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:560px;background:#ffffff;border-radius:16px;padding:36px 32px;'
        'font-family:Helvetica,Arial,sans-serif;color:#0B1026;"><tr><td>'
        '<p style="font-size:12px;letter-spacing:0.16em;text-transform:uppercase;'
        'color:#2563FF;margin:0 0 18px;font-weight:600;">Between Sundays</p>'
        '<h1 style="font-size:26px;line-height:1.2;margin:0 0 18px;font-weight:600;">'
        + _esc(greeting)
        + "</h1>"
        '<p style="font-size:16px;line-height:1.6;color:#3b4257;margin:0 0 16px;">'
        "Thanks for reaching out. We have your request and will reply within one "
        "business day with a few times to talk.</p>"
        '<p style="font-size:16px;line-height:1.6;color:#3b4257;margin:0 0 16px;">'
        "The call runs about twenty minutes. We will walk through where your data "
        "lives today, where people are falling through, and whether an operating "
        "system is worth building for you right now. No pitch deck.</p>"
        '<p style="font-size:16px;line-height:1.6;color:#3b4257;margin:0 0 28px;">'
        "If anything comes up before then, just reply to this email.</p>"
        '<p style="font-size:15px;line-height:1.6;color:#0B1026;margin:0;font-weight:600;">'
        "Between Sundays</p>"
        '<p style="font-size:14px;line-height:1.6;color:#6b7280;margin:2px 0 0;">'
        "Helping churches and nonprofits build operating systems to know every "
        "person and lead them to their next step.</p>"
        "</td></tr></table></td></tr></table></body></html>"
    )

    _resend_send(
        to=[form.get("email", "")],
        subject="We got your request",
        text=plain,
        html=html,
        reply_to=CONTACT_EMAIL,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
