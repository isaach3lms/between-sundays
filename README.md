# Between Sundays

Marketing site for Between Sundays. Flask + Jinja2, no database, deployed on Render with gunicorn.

## Stack

| Piece | Choice |
| --- | --- |
| Framework | Flask 3 |
| Server | gunicorn (2 workers, 4 threads) |
| Templates | Jinja2 |
| Assets | Static CSS and vanilla JS, no build step |
| Email | OneSignal (primary), Resend over SMTP (automatic fallback) |
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

## View demo

Every `Book a call` button is paired with a `View demo` button in the lighter brand tone (`--mist` fill, `--deep` text, subtle border so it stays visible on `section--mist` where the fill matches the background). Demo links open in a new tab so the visitor keeps the marketing page.

The URL is read from `DEMO_URL` and every button is wrapped in `{% if site.demo_url %}`. Blank the variable and all of them disappear at once, which is the switch to use if the subdomain goes down or is not ready.

Pricing card buttons (`Start with Launch`, `Choose Connect`, and so on) are deliberately left alone. They are selection actions inside a comparison, not calls to action, and a second button on each of eight cards would bury the choice.

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
| `SMTP_PASS` | Resend API key (`re_...`). A send-only key is the correct scope |
| `MAIL_FROM` | Sender on a domain verified in Resend |
| `MAIL_TO` | Comma separated. Fallback recipients. Keep in sync with `LEAD_NOTIFY_TO` |
| `LEAD_NOTIFY_TO` | Comma separated. Where OneSignal delivers lead alerts |
| `CONTACT_EMAIL` | The address displayed publicly in the footer and on the Book a Call page |
| `CLIENT_PORTAL_URL` | Stripe customer portal login link. Leave unset to hide the Client Login button. |
| `DEMO_URL` | Product demo link. Defaults to demo.betweensundaysconsulting.com. Blank it to hide every View demo button. |
| `ONESIGNAL_APP_ID` | OneSignal App ID, UUID v4. Leave unset to disable the integration. |
| `ONESIGNAL_API_KEY` | OneSignal App API key. Sent as `Authorization: Key <value>` |
| `ONESIGNAL_TEMPLATE_ID` | Optional. Template UUID for the confirmation email. Falls back to inline HTML. |
| `ONESIGNAL_FROM_NAME` | Sender name override. Defaults to Between Sundays. |
| `ONESIGNAL_REPLY_TO` | Reply-to on the confirmation email. |

## Email architecture

OneSignal is the primary path. Resend is an automatic fallback, not a parallel system.

| Step | Provider | Timing | On failure |
| --- | --- | --- | --- |
| 1. Lead alert to the team | OneSignal | Synchronous | Falls through to step 2 |
| 2. Lead alert retry | Resend (SMTP) | Synchronous | Visitor sees the fallback error, lead logged under `LEAD NOT DELIVERED` |
| 3. Confirmation to the lead | OneSignal | Background daemon thread | Logged and ignored; the lead is already captured |

The visitor only ever sees an error if **both** providers fail. If `SMTP_PASS` is unset the fallback does not exist and the site is OneSignal-only, which is a supported configuration but leaves lead capture on a single provider.

The alert sets `include_unsubscribed: true` and `disable_email_click_tracking: true`, so an accidental unsubscribe by a team member cannot stop lead alerts and internal ops mail carries no tracked links.

**Internal recipients.** Every address in `LEAD_NOTIFY_TO` is upserted as a OneSignal user tagged `internal_team=true` and targeted by alias. Exclude that tag from every marketing segment so the team never receives its own campaigns.

**Consent.** The form carries an unchecked opt-in box. Everyone who submits is recorded so you have the contact, but only those who ticked the box are tagged `marketing_opt_in=true`. Build every marketing segment on that tag. Sequences built in the dashboard must not set `include_unsubscribed`.

**Tags written per lead:** `lead_source`, `lead_date`, `marketing_opt_in`, `status`, `internal_team`, `name`, `organization`, `org_type`, `org_size`, `interest`, `phone`.

## OneSignal setup

1. In the app, add the **Email** channel and verify the sending domain in DNS (SPF, DKIM, CNAME). Nothing sends until this is green.
2. Settings, Keys & IDs: copy the App ID and the App API key.
3. Set `ONESIGNAL_APP_ID`, `ONESIGNAL_API_KEY`, and `LEAD_NOTIFY_TO`.
4. Submit one test lead and confirm both the alert and the confirmation arrive.

## Resend setup

1. Add `betweensundaysconsulting.com` in Resend under Domains.
2. Add the DNS records Resend provides: SPF, DKIM, and the return-path CNAME.
3. Wait for verification. `MAIL_FROM` must be on the verified domain or every send is rejected.
4. Create a **sending-only** API key rather than a full-access one. The site only ever sends.
5. Submit one test lead and confirm delivery before pointing traffic at the form.

## Form behavior

Required: name, email, organization. Everything else is optional, so a qualified lead is never lost to a validation error. The hidden `website` field is a honeypot; any submission that fills it redirects to the thank-you page without sending. Client-side validation is off (`novalidate`) so the server is the single source of truth. The `source` hidden field records whether the lead came from the home page form or the Book a Call page.

## Deploy to Render

1. Push to GitHub.
2. Render, New, Blueprint, point at the repo. `render.yaml` defines the service.
3. Set `SMTP_PASS`, `MAIL_FROM`, and `MAIL_TO`. `SECRET_KEY` generates automatically.
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
