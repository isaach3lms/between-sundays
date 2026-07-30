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
MAIL_FROM = os.environ.get("MAIL_FROM", "website@betweensundaysconsulting.com")
# Where form submissions are delivered.
MAIL_TO = os.environ.get("MAIL_TO", "isaac@betweensundaysconsulting.com")
# The address shown publicly on the site. Can differ from MAIL_TO.
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "isaac@betweensundaysconsulting.com")

# Stripe customer portal login link (Billing > Customer portal > no-code link).
# Left empty by default so the live site never ships a dead button. Set this in
# Render > Environment and the Client Login button appears with no code change.
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

    try:
        send_notification(form)
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Contact send failed: %s", exc)
        errors["form"] = (
            "The message did not send. Email %s directly and we will follow up today." % CONTACT_EMAIL
        )
        return render_template("book_a_call.html", page="book", errors=errors, form=form), 500

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


def send_notification(form):
    org_type = form.get("org_type") or "not specified"
    msg = EmailMessage()
    msg["Subject"] = "New inquiry: %s (%s)" % (form.get("org", ""), form.get("name", ""))
    msg["From"] = MAIL_FROM
    msg["To"] = MAIL_TO
    msg["Reply-To"] = form.get("email", "")
    msg.set_content(
        "Name: {name}\n"
        "Organization: {org}\n"
        "Type: {org_type}\n"
        "Email: {email}\n"
        "Phone: {phone}\n"
        "Weekly attendance or size: {size}\n"
        "Interested in: {interest}\n"
        "Source: {source}\n\n"
        "Message:\n{message}\n".format(
            name=form.get("name", ""),
            org=form.get("org", ""),
            org_type=org_type,
            email=form.get("email", ""),
            phone=form.get("phone") or "not provided",
            size=form.get("size") or "not provided",
            interest=form.get("interest") or "not specified",
            source=form.get("source") or "site",
            message=form.get("message") or "(none)",
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
