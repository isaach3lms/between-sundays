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
- `/for-churches` For Churches (services, dashboard, phases, pricing at `#pricing`)
- `/for-nonprofits` For Nonprofits
- `/case-studies` Case Studies (live but unlinked; `noindex` while it holds placeholder copy)
- `/book-a-call` Book a Call (GET and POST)
- `/thank-you` Confirmation
- `/robots.txt`, `/sitemap.xml`, `/healthz`
- Custom 404
- 301 redirects from the first build: `/services`, `/about`, `/pricing`, `/contact`

## Editing the hero rotator

The rotating headline is data, not markup. Edit `DISCIPLESHIP_IS` in `app.py`.

```python
DISCIPLESHIP_IS = [
    ("reading your Bible.", "Bible engagement"),
    ("serving on a team.", "Service planning"),
]
```

First value is the phrase after "Discipleship is". Second is the field shown in the pill below it. Add or remove entries freely; the rotator measures the tallest phrase on load and reserves that height so the hero never shifts. Rotation is disabled automatically for visitors with reduced motion enabled, and the full list is exposed to screen readers as static text.

## Client login

The Client Login button in the header points at the Stripe customer portal. Get the link in Stripe under Settings, Billing, Customer portal, then copy the no-code portal link (`https://billing.stripe.com/p/login/...`) and set it as `CLIENT_PORTAL_URL`.

If the variable is unset or empty, the button does not render anywhere on the site. That is deliberate: the live site can never ship a dead login link, and turning the button on is an environment change rather than a deploy. Clients enter their billing email at the portal and receive a one-time link, so there is no password for you to manage.

## Logo files

The site logo is the stacked wordmark, two lines, cropped to the glyphs with two pixels of padding. Source artwork is 384 x 167, displayed at 40px tall in the header and 56px in the footer, which leaves more than 2x pixel density on retina screens.

- `static/img/logo-white.png` header and footer
- `static/img/logo-ink.png` `#0B1026` version for light backgrounds
- `static/img/logo-blue.png` `#2563FF` version
- `static/img/logo-horizontal-white.png` the earlier single-line wordmark, kept for email signatures, social headers, and anywhere a wide format fits better than a stacked one

The header is dark on every page, which is what lets the white wordmark run sitewide without a swap. The favicon stays as the `bs` monogram in `static/img/favicon.svg`, because a two-line wordmark is unreadable at 16 pixels.

## Case studies

`templates/case_studies.html` ships with bracketed placeholder text and a comment block marking it. The page is reachable by direct URL but is linked from nowhere, excluded from `sitemap.xml`, and carries `<meta name="robots" content="noindex, follow">`.

When real client content is ready: replace the bracketed values, remove the `robots` block from the template, add `/case-studies` back to the `paths` list in the `sitemap()` route, and restore the footer link in `base.html`.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py             # http://127.0.0.1:5000
```

With `SMTP_PASS` blank, the form validates and redirects normally and writes the message body to the log instead of sending. That is intentional for local work.

## Environment variables

| Key | Purpose |
| --- | --- |
| `SECRET_KEY` | Flask session key. Generate a long random string. |
| `SMTP_HOST` | `smtp.resend.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | `resend` |
| `SMTP_PASS` | Resend API key (`re_...`) |
| `MAIL_FROM` | Sender on a verified domain |
| `MAIL_TO` | Where form submissions are delivered. Defaults to isaac@betweensundaysconsulting.com |
| `CONTACT_EMAIL` | The address displayed publicly in the footer and on the Book a Call page. Can differ from `MAIL_TO` |
| `CLIENT_PORTAL_URL` | Stripe customer portal login link. Leave unset to hide the Client Login button. |

## Form behavior

Required: name, email, organization. Everything else is optional, so a qualified lead is never lost to a validation error. The hidden `website` field is a honeypot; any submission that fills it redirects to the thank-you page without sending. Client-side validation is off (`novalidate`) so the server is the single source of truth. The `source` hidden field records whether the lead came from the home page form or the Book a Call page.

## Deploy to Render

1. Push to GitHub.
2. Render, New, Blueprint, point at the repo. `render.yaml` defines the service.
3. Set `SMTP_PASS`, `MAIL_FROM`, `MAIL_TO`. `SECRET_KEY` generates automatically.
4. Deploy, test the live URL on a phone.
5. Add the custom domain, then cut DNS.

## Brand tokens

Defined once at the top of `static/css/styles.css`.

- `#2563FF` primary blue
- `#1E3A8A` deep blue
- `#0B1026` ink
- `#E6EEFF` mist
- Poppins 300 / 400 / 500 / 600

Two recurring devices: the rotating hero headline, and the week rail of eight marks running Sunday to Sunday with the six days between lit in blue.
