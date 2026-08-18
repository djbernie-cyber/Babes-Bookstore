# Babe's Bookstore — Go-Live Guide

Plain-language steps to finish launching. Written for whoever is running the
business, not just developers.

**Time needed:** about 2–3 hours of your attention, spread over a few days
(some steps wait on bank/identity checks).

---

## Where things stand

| Part | Status |
|---|---|
| Website pages (design, layout) | Built |
| Book catalogue (8 sources, ~96,000 books) | Working |
| Login, accounts, admin panel | Working |
| Your two admin accounts + free downloads | Built |
| Payment code (5 methods) | Built — needs your accounts connected |
| Automated tests (25) | Passing |
| Live on the internet | **Not yet — needs steps 1–5 below** |
| Legal policy pages | **Not written yet** |

The code is on GitHub: https://github.com/djbernie-cyber/Babes-Bookstore

---

## The short version

You need to create accounts on 5 services and paste some keys in. Nothing
here requires coding. The order matters — do 1, 2, 3 first, because the
website can't go live without them.

1. **Fly.io** — runs the engine (the part that stores books and takes payment)
2. **Netlify** — runs the shop front (what customers see)
3. **Stripe** — takes card payments, and pays you
4. **Cloudflare R2** — stores the book files customers download
5. **Google** — the "Sign in with Google" button

Then optionally: PayPal, Square, and email receipts.

---

## Step 1 — Fly.io (the engine)

**What it does:** Runs the behind-the-scenes part of the shop.
**Cost:** Free to start. Roughly £4–8/month once busy.

1. Sign up: https://fly.io/app/sign-in
2. You'll need to add a card. Fly won't charge you on the free allowance,
   but they require it to stop abuse.
3. Hand these commands to your developer, or run them in Terminal:

```bash
fly auth login
fly launch --no-deploy          # say NO to "tweak settings"
fly postgres create -a babes-bookstore-api
fly redis create
fly secrets set SECRET_KEY=$(openssl rand -hex 32)
fly deploy
```

4. When it finishes, note the web address it gives you. It will look like
   `https://babes-bookstore-api.fly.dev`. **Write it down — later steps need it.**

**How to check it worked:** open `https://babes-bookstore-api.fly.dev/health`
in a browser. You should see `{"status":"ok"}`.

> **Safety note:** the app is built to refuse to start if the security key
> is missing or left at its default. If it won't boot, that's the reason —
> it's protecting you, not broken.

---

## Step 2 — Netlify (the shop front)

**What it does:** Serves the pages customers actually see.
**Cost:** Free for your traffic level.

1. Go to https://app.netlify.com and log in **with GitHub**.
2. Click **Add new site → Import an existing project → GitHub**.
3. Choose the **Babes-Bookstore** repository.
4. Leave the build settings alone — they're already in the project file.
5. Click **Deploy**.

Then point the shop front at the engine:

6. Go to **Site configuration → Environment variables**.
7. Add one variable:
   - Name: `API_URL`
   - Value: your Fly address from Step 1
8. Also open `frontend/_redirects` in GitHub and make sure the first line
   points at your real Fly address.

**Currently your Netlify site shows "Page not found."** That's because it was
never given a proper homepage. That's now fixed in the code — redeploying
after Step 2 will resolve it.

**If the site is showing as private:** Netlify → **Site configuration →
Access control → Visitors**, and set it to public.

---

## Step 3 — Stripe (getting paid)

**What it does:** Takes card payments, Apple Pay and Google Pay. This is
the one that puts money in your account.

1. Sign up: https://dashboard.stripe.com/register
2. Complete **identity verification**. Stripe legally must check who you
   are. Have ready:
   - Photo ID (passport or driving licence)
   - Your address
   - Your bank details
   - *If a company:* company number and registered address
3. **This is where you set where the money goes:**
   Dashboard → **Settings → Business → Payouts → Add bank account**

   > Stripe pays out to a **bank account**, not a credit card. Debit cards
   > are accepted in some countries but bank transfer is standard in the UK.
   > Payouts arrive roughly every 2–7 days automatically.

4. Get your keys: https://dashboard.stripe.com/apikeys
   Copy the **Secret key** and **Publishable key**.
5. Set up the payment confirmation link:
   https://dashboard.stripe.com/webhooks → **Add endpoint**
   - URL: `https://babes-bookstore-api.fly.dev/api/v1/checkout/webhook/stripe`
   - Events: choose `checkout.session.completed` and `payment_intent.succeeded`
   - Copy the **Signing secret** it shows you.

6. Give those three values to Fly:

```bash
fly secrets set \
  STRIPE_SECRET_KEY=sk_live_xxx \
  STRIPE_PUBLISHABLE_KEY=pk_live_xxx \
  STRIPE_WEBHOOK_SECRET=whsec_xxx
```

> **Test first.** Stripe gives you "test mode" keys (`sk_test_...`). Use
> those and card number `4242 4242 4242 4242` to make a fake purchase before
> switching to live keys. Do not skip this.

---

## Step 4 — Cloudflare R2 (the book files)

**What it does:** Stores the ZIP files customers download after buying.
Without this, purchases succeed but customers get nothing.

**Cost:** Free up to 10GB — far more than you need.

1. Sign up: https://dash.cloudflare.com/sign-up
2. Left menu → **R2** → **Create bucket** → name it `babes-bookstore`
3. **Manage R2 API Tokens** → **Create API token** → permission
   **Object Read & Write**
4. Copy the Access Key ID, Secret Access Key, and your Account ID.

```bash
fly secrets set \
  R2_ACCOUNT_ID=xxx \
  R2_ACCESS_KEY_ID=xxx \
  R2_SECRET_ACCESS_KEY=xxx \
  R2_BUCKET_NAME=babes-bookstore
```

---

## Step 5 — Google sign-in

1. Go to https://console.cloud.google.com/apis/credentials
2. Create a project (any name).
3. **Create credentials → OAuth client ID → Web application**
4. Under **Authorised redirect URIs**, add exactly:
   `https://babes-bookstore-api.fly.dev/api/v1/auth/google/callback`
5. Copy the Client ID and Client Secret.

```bash
fly secrets set \
  GOOGLE_CLIENT_ID=xxx \
  GOOGLE_CLIENT_SECRET=xxx \
  GOOGLE_REDIRECT_URI=https://babes-bookstore-api.fly.dev/api/v1/auth/google/callback
```

> Google will ask you to complete a "consent screen". Until it's verified,
> only accounts you add as test users can sign in — add both admin emails.

---

## Optional — more payment methods

Only worth doing once Stripe works. Each needs its own identity check and
its own payout bank account.

**PayPal** — https://developer.paypal.com/dashboard
```bash
fly secrets set PAYPAL_CLIENT_ID=xxx PAYPAL_CLIENT_SECRET=xxx PAYPAL_MODE=live
```

**Square** — https://developer.squareup.com/apps
```bash
fly secrets set SQUARE_ACCESS_TOKEN=xxx SQUARE_LOCATION_ID=xxx SQUARE_ENVIRONMENT=production
```

**Email receipts** — https://signup.sendgrid.com
```bash
fly secrets set SENDGRID_API_KEY=xxx FROM_EMAIL=noreply@yourdomain.com
```

Apple Pay and Google Pay need no separate account — they run through Stripe
and appear automatically once Stripe is live.

---

## Your admin accounts

These two are created automatically when the app starts:

- `dj.bernie@hotmail.co.uk`
- `williammajanja@gmail.com`

Both get admin access and **free downloads on every bundle**.

**To sign in:** go to `/login` and use **Continue with Google**
(`williammajanja@gmail.com` is a Google address, so this works directly).

For the Hotmail address, either use Google sign-in if it's linked to a
Google account, or set a password:

```bash
fly ssh console -a babes-bookstore-api
# then, inside:
python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.services.security import hash_password
from app.models.user import User
from sqlalchemy import select
async def go():
    async with AsyncSessionLocal() as db:
        u=(await db.execute(select(User).where(User.email=='dj.bernie@hotmail.co.uk'))).scalar_one()
        u.hashed_password=hash_password('CHANGE-THIS-PASSWORD')
        await db.commit(); print('done')
asyncio.run(go())"
```

**Admin panel:** `/admin` — stats, book approval, bundle creation.

---

## Filling the shop with books

Once live, sign in as admin and go to `/admin`:

1. Click **Scrape Popular Books** — pulls in books from all 8 sources.
2. Go to **Manage Books** — anything marked *pending* needs your decision.
   Gutenberg, Standard Ebooks, Wikisource and OpenStax auto-approve because
   their licences are confirmed. Academic sources (DOAB, OAPEN) come through
   as *pending* because "open access" alone doesn't legally permit resale —
   check the licence before approving.
3. Go to **Manage Bundles** → **New Bundle** — group 10–20 books under a
   theme, and it goes on sale at £10.

**Sensible first bundles:** Classic Fiction, Sherlock Holmes Complete,
Philosophy Essentials, Science Textbooks, Victorian Novels.

---

## Still to do (not built yet)

Be aware of these before taking real money:

1. **Legal pages — required.** You have no Terms of Service, Privacy Policy,
   Refund Policy or Cookie Notice. UK/EU law requires a privacy policy, and
   Stripe requires visible terms and refund terms. Selling without them risks
   your payment account.

2. **Refund policy for digital goods.** UK consumer law gives a 14-day
   cancellation right, but you can ask customers to waive it for instant
   downloads — you must state this clearly at checkout.

3. **Attribution for CC-BY books.** OpenStax and DOAB books are free to sell
   *but only with credit given*. The ZIP includes a licence file, but the
   bundle page should show it too.

4. **Price is fixed at £10 in the code**, not per-bundle. Changing one bundle's
   price needs a code change.

5. **Frontend polish.** Pages work but haven't had a design pass —
   loading states, mobile layout, and empty states are basic.

---

## Quick reference

| What | Where |
|---|---|
| Code | https://github.com/djbernie-cyber/Babes-Bookstore |
| Engine health | `https://babes-bookstore-api.fly.dev/health` |
| API documentation | `https://babes-bookstore-api.fly.dev/docs` |
| Admin panel | `/admin` on your Netlify address |
| See the logs | `fly logs -a babes-bookstore-api` |
| List your keys | `fly secrets list -a babes-bookstore-api` |

**If something breaks:** run `fly logs -a babes-bookstore-api` and read the
last 20 lines. Most problems are a missing or mistyped key.
