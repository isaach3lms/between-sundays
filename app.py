"""Between Sundays marketing site.

Flask + Jinja2, no database. Contact form posts server side, validates,
and relays through SMTP (Resend recommended). Deployed on Render with
gunicorn via Procfile / render.yaml.
"""

import os
import re
import smtplib
import ssl
from email.message import EmailMessage

from flask import Flask, redirect, render_template, request, url_for

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")

# ---------------------------------------------------------------------------
# Configuration (set these in Render > Environment)
# ---------------------------------------------------------------------------
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.resend.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "resend")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "website@betweensundays.co")
MAIL_TO = os.environ.get("MAIL_TO", "dennis@betweensundays.co")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")

SITE = {
    "name": "Between Sundays",
    "tagline": "Focused on ministry. Every day between Sundays.",
    "email": MAIL_TO,
    "instagram": "https://instagram.com/",
    "youtube": "https://youtube.com/",
    "linkedin": "https://linkedin.com/",
}


@app.context_processor
def inject_site():
    return {"site": SITE}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html", page="home")


@app.route("/services")
def services():
    return render_template("services.html", page="services")


@app.route("/pricing")
def pricing():
    return render_template("pricing.html", page="pricing")


@app.route("/about")
def about():
    return render_template("about.html", page="about")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        return render_template("contact.html", page="contact", errors={}, form={})

    form = {k: (v or "").strip() for k, v in request.form.items()}

    # Honeypot: real people leave this empty. Bots fill it.
    if form.get("website"):
        return redirect(url_for("thank_you"))

    errors = validate(form)
    if errors:
        return render_template("contact.html", page="contact", errors=errors, form=form), 400

    try:
        send_notification(form)
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Contact send failed: %s", exc)
        errors["form"] = (
            "The message did not send. Email %s directly and we will follow up today." % MAIL_TO
        )
        return render_template("contact.html", page="contact", errors=errors, form=form), 500

    return redirect(url_for("thank_you"))


@app.route("/thank-you")
def thank_you():
    return render_template("thank_you.html", page="thank-you")


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
    paths = ["/", "/services", "/pricing", "/about", "/contact"]
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
    errors = {}
    if len(form.get("name", "")) < 2:
        errors["name"] = "Enter your name."
    if not EMAIL_RE.match(form.get("email", "")):
        errors["email"] = "Enter an email address we can reply to."
    if len(form.get("church", "")) < 2:
        errors["church"] = "Enter your church or ministry name."
    if len(form.get("message", "")) < 10:
        errors["message"] = "Tell us a little about what your church needs."
    return errors


def send_notification(form):
    msg = EmailMessage()
    msg["Subject"] = "New inquiry: %s (%s)" % (form.get("church", ""), form.get("name", ""))
    msg["From"] = MAIL_FROM
    msg["To"] = MAIL_TO
    msg["Reply-To"] = form.get("email", "")
    msg.set_content(
        "Name: {name}\n"
        "Church: {church}\n"
        "Email: {email}\n"
        "Phone: {phone}\n"
        "Weekly attendance: {size}\n"
        "Interested in: {interest}\n\n"
        "Message:\n{message}\n".format(
            name=form.get("name", ""),
            church=form.get("church", ""),
            email=form.get("email", ""),
            phone=form.get("phone", "not provided"),
            size=form.get("size", "not provided"),
            interest=form.get("interest", "not specified"),
            message=form.get("message", ""),
        )
    )

    if not SMTP_PASS:
        # Local development: log instead of sending.
        app.logger.info("SMTP not configured. Message body:\n%s", msg.get_content())
        return

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
