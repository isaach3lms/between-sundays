# Between Sundays

Marketing site for Between Sundays. Flask + Jinja2, no database, deployed on Render with gunicorn.

## Stack

| Piece | Choice |
| --- | --- |
| Framework | Flask 3 |
| Server | gunicorn (2 workers, 4 threads) |
| Templates | Jinja2 |
| Assets | Static CSS and vanilla JS, no build step |
| Email | SMTP relay, Resend recommended |
| Host | Render, auto-deploy from Git |

## Pages

- `/` Home
- `/services` Services
- `/pricing` Pricing
- `/about` About
- `/contact` Book a call (GET and POST)
- `/thank-you` Confirmation
- `/robots.txt`, `/sitemap.xml`, `/healthz`
- Custom 404

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # fill in values, or leave SMTP_PASS blank
python app.py             # http://127.0.0.1:5000
```

With `SMTP_PASS` blank, the contact form validates and redirects normally and writes the message body to the log instead of sending. That is intentional for local work.

## Environment variables

| Key | Purpose |
| --- | --- |
| `SECRET_KEY` | Flask session key. Generate a long random string. |
| `SMTP_HOST` | `smtp.resend.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | `resend` |
| `SMTP_PASS` | Resend API key (`re_...`) |
| `MAIL_FROM` | Sender on a verified domain |
| `MAIL_TO` | Where inquiries land |

## Deploy to Render

1. Push this repo to GitHub.
2. Render dashboard, New, Blueprint, point at the repo. `render.yaml` defines the service.
3. Set `SMTP_PASS`, `MAIL_FROM`, and `MAIL_TO` in the Render environment. `SECRET_KEY` generates automatically.
4. Deploy, then test the live `.onrender.com` URL on a phone.
5. Add the custom domain in Render, then cut DNS over.

## Email setup (Resend)

1. Create the Resend account and add the sending domain.
2. Add the DNS records Resend provides (SPF, DKIM, and the return-path CNAME).
3. Wait for verification, then create an API key and paste it into `SMTP_PASS` on Render.
4. Submit the live contact form once and confirm delivery.

## Spam handling

The form includes a hidden honeypot field named `website`. Any submission with that field filled redirects to the thank-you page without sending. All fields are validated server side; client-side validation is deliberately off (`novalidate`) so the server is the single source of truth.

## Brand tokens

Defined once at the top of `static/css/styles.css`.

- `#2563FF` primary blue
- `#1E3A8A` deep blue
- `#0B1026` ink
- `#E6EEFF` mist
- Poppins 300 / 400 / 500 / 600

The recurring device is the week rail: eight marks running Sunday to Sunday, with the six days between lit in blue. It appears in the hero and is the visual argument for the name.
