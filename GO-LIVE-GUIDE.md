# Babe's Bookstore — Step-by-Step Launch Guide

Everything below takes you from "code finished" to "first real sale".
Written in plain language — no coding knowledge needed.

**Total time:** ~2 hours of your attention + a few days waiting on
identity/bank checks. **Order matters** — each step uses something from the
one before it.

---

## Where things stand today

| Part | Status |
|---|---|
| Storefront + admin pages (incl. mobile) | ✅ Built |
| Book catalogue — 8 legal sources, ~96,000 books | ✅ Working |
| Payments — 5 providers, per-bundle prices | ✅ Built, needs your keys |
| Legal pages (/terms /privacy /refunds) | ✅ Built |
| Review queue for unclear licences | ✅ Built |
| Automated tests | ✅ 41/41 passing |
| Hosting, payments, storage, sign-in | ⬜ Steps 1–6 below — **only you can do these** (they need your ID, bank account and logins) |

Code: https://github.com/djbernie-cyber/Babes-Bookstore

**Before you start, have ready:** photo ID, bank account details (for
Stripe payouts), a card (for Fly.io verification), and your two admin
emails (`dj.bernie@hotmail.co.uk`, `williammajanja@gmail.com`).

---

## THE PLAN

| # | Step | Time | Can't continue without it because… |
|---|---|---|---|
| 1 | Fly.io — the engine | 30 min | everything else needs its web address |
| 2 | Netlify — the shop front | 15 min | customers need a page to visit |
| 3 | Cloudflare R2 — book storage | 10 min | without it, buyers get no download |
| 4 | Google sign-in | 10 min | you need it to log in as admin |
| 5 | Stripe — getting paid | 30 min + checks | this is how money reaches your bank |
| 6 | Fill the shop (books + bundles) | 30 min | you can't sell an empty shop |
| 7 | Test purchase | 15 min | proves the whole chain works |
| 8 | Go live | 15 min | switches test payments to real |

Optional extras (PayPal, Square, email receipts) are at the end — do them
**after** Stripe works.

---

## Step 1 — Fly.io (the engine)

**What it is:** the server that stores books, accounts and orders, and
talks to the payment providers.
**Cost:** ~£5–10/month (it runs two small machines: the site + a
background worker that builds your download files).

1. Create an account: https://fly.io/app/sign-in (add a card when asked —
   you won't be charged until the machines run).
2. Install the Fly command line (Mac: `brew install flyctl`).
3. In Terminal, from the project folder, run these one at a time:

```bash
fly auth login
fly launch --no-deploy        # if asked, keep the name babes-bookstore-api

# The database (where books/orders live):
fly postgres create --name babes-bookstore-db --region lhr
fly postgres attach babes-bookstore-db --app babes-bookstore-api
# ↑ attaching automatically sets the DATABASE_URL for you

# The queue (lets the background worker pick up jobs):
fly redis create --name babes-bookstore-redis --region lhr
fly redis attach babes-bookstore-redis --app babes-bookstore-api
# ↑ attaching automatically sets the REDIS_URL for you

# Your security key (makes logins unforgeable):
fly secrets set SECRET_KEY=$(openssl rand -hex 32)

fly deploy
```

4. **Checkpoint:** open `https://babes-bookstore-api.fly.dev/health` —
   you should see `{"status":"ok",...}`.
   Also run `fly status` — you should see **two machines**: one `app`,
   one `worker`. The worker is what actually builds customer downloads;
   if it's missing, sales will silently never deliver.
5. **Write down your Fly address** (e.g.
   `https://babes-bookstore-api.fly.dev`). Every later step needs it.

> **Won't boot?** The app deliberately refuses to start with a default
> security key or SQLite in production. Run `fly logs` — the error
> message tells you exactly which setting to fix.

---

## Step 2 — Netlify (the shop front)

**What it is:** the pages customers actually see.
**Cost:** free at your traffic level.

1. Go to https://app.netlify.com and **log in with GitHub**.
2. **Add new site → Import an existing project → GitHub → Babes-Bookstore.**
3. Leave every build setting as-is (the repo's `netlify.toml` is already
   correct) → **Deploy**.
4. **One manual edit.** Open `frontend/_redirects` in GitHub (click the
   pencil icon to edit) and check the first line says:

   ```
   /api/*  https://babes-bookstore-api.fly.dev/api/:splat  200
   ```

   …using **your** Fly address from Step 1. (It's the shop's forwarding
   address for payments and searches. If your Fly name differs, fix it
   here, then Netlify → **Deploys → Trigger deploy**.)
5. **Checkpoint:** open your Netlify site (something like
   `https://<your-site>.netlify.app`). You should see the Babe's
   Bookstore homepage. **Write down this address** — Step 4 and 5 need it.

---

## Step 3 — Cloudflare R2 (the book files)

**What it is:** storage for the ZIP files customers download.
**Cost:** free up to 10GB.

1. Sign up: https://dash.cloudflare.com/sign-up
2. Left menu → **R2 Object Storage** → **Create bucket** → name it
   exactly `babes-bookstore`.
3. R2 menu → **Manage R2 API Tokens** → **Create API token** →
   permission **Object Read & Write** → copy the
   **Access Key ID**, **Secret Access Key** and your **Account ID**
   (shown on the right side of the R2 page).
4. Give them to Fly:

```bash
fly secrets set \
  R2_ACCOUNT_ID=your_account_id \
  R2_ACCESS_KEY_ID=your_access_key \
  R2_SECRET_ACCESS_KEY=your_secret_key \
  R2_BUCKET_NAME=babes-bookstore
```

5. **Checkpoint:** run `fly secrets list` — you should now see
   DATABASE_URL, REDIS_URL, SECRET_KEY and the four R2 values.

---

## Step 4 — Google sign-in (and your admin logins)

You need this to sign into the admin panel. (Password login also exists,
but Google is the quickest route for your Gmail admin account.)

1. Go to https://console.cloud.google.com/apis/credentials
2. Create a project (any name, e.g. "Babes Bookstore").
3. **Create credentials → OAuth client ID → Web application.**
4. **Authorised redirect URIs** — paste exactly (use your Fly address):

   ```
   https://babes-bookstore-api.fly.dev/api/v1/auth/google/callback
   ```
5. Copy the **Client ID** and **Client Secret**, then:

```bash
fly secrets set \
  GOOGLE_CLIENT_ID=xxx \
  GOOGLE_CLIENT_SECRET=xxx \
  GOOGLE_REDIRECT_URI=https://babes-bookstore-api.fly.dev/api/v1/auth/google/callback \
  FRONTEND_URL=https://YOUR-NETLIFY-ADDRESS.netlify.app
```

> `FRONTEND_URL` is where customers land after paying — use your Netlify
> address from Step 2, **no trailing slash**.

6. The consent screen will say "Testing" — fine for now. Under
   **Audience → Test users**, add both admin emails so they can sign in.
7. **Checkpoint:** on your Netlify site, open **Login → Continue with
   Google** and sign in as `williammajanja@gmail.com`. You should land on
   your account page. Go to `/admin` — the dashboard should show stats,
   not "Access denied".

> **Hotmail admin account:** `dj.bernie@hotmail.co.uk` has no password
> (it was created automatically). Either link that Hotmail to a Google
> account and use Google sign-in, or set a password once:
>
> ```bash
> fly ssh console -a babes-bookstore-api
> # then, inside the machine:
> python -c "
> import asyncio
> from app.database import AsyncSessionLocal
> from app.services.security import hash_password
> from app.models.user import User
> from sqlalchemy import select
> async def go():
>     async with AsyncSessionLocal() as db:
>         u=(await db.execute(select(User).where(User.email=='dj.bernie@hotmail.co.uk'))).scalar_one()
>         u.hashed_password=hash_password('CHOOSE-A-PASSWORD')
>         await db.commit(); print('done')
> asyncio.run(go())"
> ```

---

## Step 5 — Stripe (getting paid)

**What it is:** takes card, Apple Pay and Google Pay payments and pays
out to your bank. **This is the money step — don't rush it.**

1. Register: https://dashboard.stripe.com/register
2. Complete **identity verification** (photo ID, address, bank details;
   company number if registering as a company). Payouts can only start
   once Stripe has finished these checks.
3. **Where the money goes:** Dashboard → **Settings → Bank accounts and
   payouts** → add your **bank account** (a current account, not a
   card). Payouts arrive automatically every 2–7 days.
4. **Start in test mode** (the toggle top-right says "Test mode"). Copy
   the **Secret key** and **Publishable key** (both start `sk_test_` /
   `pk_test_`) from https://dashboard.stripe.com/apikeys
5. Add the confirmation link ("webhook"):
   https://dashboard.stripe.com/test/webhooks → **Add endpoint**
   - URL: `https://babes-bookstore-api.fly.dev/api/v1/checkout/webhook/stripe`
     (your Fly address)
   - Select events: `checkout.session.completed` **and**
     `payment_intent.succeeded`
   - After creating, click it → **Signing secret → Reveal** → copy
     (`whsec_…`).
6. Load the test keys:

```bash
fly secrets set \
  STRIPE_SECRET_KEY=sk_test_xxx \
  STRIPE_PUBLISHABLE_KEY=pk_test_xxx \
  STRIPE_WEBHOOK_SECRET=whsec_xxx
```

> **Live keys come in Step 8** — not yet. Real money only after the
> test purchase in Step 7 passes.

---

## Step 6 — Fill the shop (books + bundles)

Sign in as admin on your Netlify site. Do this in order:

1. **Admin Dashboard → "Scrape Popular Books"** — pulls books in from
   all 8 sources. Wait a few minutes (the worker is fetching them).
2. **Admin → Manage Books** — this is your review queue. Books from
   trusted sources (Gutenberg, Standard Ebooks, Wikisource, OpenStax)
   auto-approve. Books from academic sources (DOAB, OAPEN) arrive as
   **pending** — the page shows each book's licence with a link.
   For each pending book, **click the licence link** and:
   - Licence says **CC BY**, **CC BY-SA** or **public domain** →
     **Approve** (safe to sell; attribution travels with the file).
   - Licence says **CC NC** (non-commercial) → **Reject** — selling
     these is not permitted.
   - Licence says **CC ND** (no derivatives) → **Reject** — our
     formatting counts as a derivative.
   - Unsure? **Reject** and move on. There are 96,000 books; err on
     the side of caution.
3. **Admin → Manage Bundles → New Bundle** — pick 10–20 approved books
   around a theme, give it a name, set its price. It appears on the
   storefront immediately.

**Good first bundles:** Classic Fiction, Sherlock Holmes Complete,
Philosophy Essentials, Victorian Gothic, Science Textbooks.

> **One legal task:** the three policy pages contain the placeholder
> email `support@babes-bookstore.example`. Search for it in
> `frontend/legal/*.html` on GitHub and replace it with an email you
> actually monitor (refunds and legal notices go there).

---

## Step 7 — Test purchase (do not skip)

1. On your Netlify site (still in Stripe **test mode**), open any bundle.
2. Click **Pay with Stripe** and check out with:
   - Card: `4242 4242 4242 4242`
   - Any future expiry, any CVC, any postcode
3. **What must happen, in order:**
   - Stripe's test checkout page appears and shows the bundle's **real
     price** (not a random number);
   - paying returns you to your site;
   - within a minute or so, your account page shows the purchase and a
     working download (a ZIP that opens, with books inside).
4. If anything in that chain fails:
   `fly logs -a babes-bookstore-api` and read the last 20 lines — it's
   nearly always a mistyped key from Steps 3–5. Fix, re-run Step 7.

---

## Step 8 — Go live 🚀

1. Stripe Dashboard → switch **Test mode → Live**.
2. Copy the live keys (`sk_live_…`, `pk_live_…`) from
   https://dashboard.stripe.com/apikeys.
3. **Create the webhook again in live mode:**
   https://dashboard.stripe.com/webhooks (no `/test` in the URL) — same
   URL and events as before — and copy its new signing secret.
4. Replace the keys:

```bash
fly secrets set \
  STRIPE_SECRET_KEY=sk_live_xxx \
  STRIPE_PUBLISHABLE_KEY=pk_live_xxx \
  STRIPE_WEBHOOK_SECRET=whsec_live_xxx
```

5. **Final checkpoint:** buy your cheapest bundle with a real card.
   Confirm the money shows in Stripe and the download arrives, then
   refund yourself from the Stripe dashboard (a real refund is also a
   test of the refund path).
6. You are live. Tell people.

---

## Optional extras (after launch, in this order)

Each needs its own account + identity check + payout bank account.

**Email receipts (do this first — customers expect receipts):**
https://signup.sendgrid.com → create an API key →

```bash
fly secrets set SENDGRID_API_KEY=xxx FROM_EMAIL=noreply@your-domain.com
```

**PayPal:** https://developer.paypal.com/dashboard →
```bash
fly secrets set PAYPAL_CLIENT_ID=xxx PAYPAL_CLIENT_SECRET=xxx PAYPAL_MODE=live PAYPAL_WEBHOOK_ID=xxx
```

**Square:** https://developer.squareup.com/apps →
```bash
fly secrets set SQUARE_ACCESS_TOKEN=xxx SQUARE_LOCATION_ID=xxx SQUARE_ENVIRONMENT=production
```

Apple Pay and Google Pay need **no separate setup** — they ride on
Stripe and appear automatically.

**A proper domain (e.g. babesbookstore.co.uk):** buy one, point it at
Netlify (custom domains) and at Fly, then update three things: the
`FRONTEND_URL` secret, the Google redirect URI, and the Stripe webhook
URL. Until then, the free addresses work fine.

---

## Running the shop day-to-day

- **New books arrive pending?** `/admin/books` → review the licence →
  approve/reject (rules in Step 6).
- **A customer wants a refund?** Find the payment in Stripe → Refund.
  Also email them — see `/refunds` for what you promised.
- **Something looks broken?** `fly logs -a babes-bookstore-api` first;
  `fly status` to confirm both `app` and `worker` machines are running.
- **Checklist each week:** pending review queue empty, worker machine
  running, Stripe payouts landing.

---

## Quick reference

| What | Where |
|---|---|
| Code | https://github.com/djbernie-cyber/Babes-Bookstore |
| Engine health | `https://babes-bookstore-api.fly.dev/health` |
| API docs | `https://babes-bookstore-api.fly.dev/docs` |
| Admin panel | `/admin` on your Netlify address |
| Review queue | `/admin/books` |
| Policies | `/terms` · `/privacy` · `/refunds` |
| Logs | `fly logs -a babes-bookstore-api` |
| Your keys | `fly secrets list -a babes-bookstore-api` |
| Machines | `fly status -a babes-bookstore-api` (app **and** worker) |
