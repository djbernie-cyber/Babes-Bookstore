# Babe's Bookstore — Launch Guide (current state)

Everything below takes you from "code finished" to "first real sale" using the
**M-Pesa (Daraja)** setup that is already configured in the app. Written in plain
language — no coding knowledge needed.

**Where things stand today**

| Part | Status |
|---|---|
| Storefront + admin pages (incl. mobile) at `https://babesbooks.store` | ✅ Live |
| Backend API at `https://babes-bookstore.fly.dev` (app + worker machines) | ✅ Live |
| Book catalogue (~83k books, incl. full Gutenberg) | ✅ Live |
| Covers backfilled, bundles priced, 6 featured | ✅ Done |
| Payments — **M-Pesa STK push** (only payment method) | ⚠️ Sandbox configured; needs production Daraja keys (Step 1) |
| Refunds — **B2Pochi** payout via admin panel | ⚠️ Needs production B2C initiator (Step 1) |
| Legal pages (/terms /privacy /refunds /cookies) | ✅ Live (`support@babesbooks.store`) |
| Automated tests | ✅ 108 passing (CI green) |
| R2 storage, Google sign-in, SendGrid email | ✅ Secrets set (email needs your SendGrid key) |

Code: https://github.com/djbernie-cyber/Babes-Bookstore

---

## THE REMAINING TASKS

| # | Task | Time | Blocker if you skip it |
|---|---|---|---|
| 1 | M-Pesa production go-live (Daraja) | ~1–2 hrs + Safaricom checks | no real payments happen |
| 2 | SendGrid API key (receipt email) | 10 min | customers get no email receipt |
| 3 | Final live test purchase + refund | 15 min | unproven money flow |
| 4 | Rotate any shared test credentials | 5 min | security hygiene |

---

## Step 1 — M-Pesa production go-live (the money step)

The app already talks to Safaricom Daraja in **sandbox** using the test
shortcode `174379`, test passkey, `testapi` initiator and `254708374149` phone.
To take real money you need a **production** set of the same things. Two parts:

### 1a. STK push (customer payments)

1. Safaricom must issue you a real **M-Pesa Paybill (or Buy-Goods) shortcode** — a
   shortcode is only issued to a registered business account, never on a sandbox app.
2. In the Daraja portal (https://developer.safaricom.co.ke) apply to **Go Live** on the
   app and add the **Lipa Na M-Pesa Online** product.
3. Register your callback URL with Safaricom: `https://babes-bookstore.fly.dev/api/v1/checkout/webhook/mpesa`
   (it must be public HTTPS — ours already is).
4. Load the production values:

```bash
fly secrets set \
  MPESA_ENVIRONMENT=production \
  MPESA_CONSUMER_KEY=<production consumer key> \
  MPESA_CONSUMER_SECRET=<production consumer secret> \
  MPESA_SHORTCODE=<your real shortcode> \
  MPESA_PASSKEY=<your production passkey> \
  -a babes-bookstore
```

### 1b. B2Pochi (admin refunds to customer Pochi wallets)

1. In the portal create the **B2C / Pochi** API + initiator with the **B2C role**
   (not "my account"). You'll get a **B2C shortcode** and an **initiator password**.
2. Encrypt the initiator password with the **production** certificate and Base64 it:

```bash
openssl x509 -in ProductionCertificate.cer -pubkey -noout > pub.pem
printf '%s' "<initiator password>" | \
  openssl rsautl -encrypt -pubin -inkey pub.pem -pkcs | base64 -w0
```

3. Load them:

```bash
fly secrets set \
  MPESA_B2C_SHORTCODE=<your B2C shortcode> \
  MPESA_B2C_INITIATOR_NAME=<your initiator username> \
  MPESA_B2C_SECURITY_CREDENTIAL=<the long base64 string from above> \
  -a babes-bookstore
```

> Refunds are initiated from the admin panel (admin → Purchases → Refund) and
> the money returns to the customer's **Pochi wallet** (their M-Pesa account).
> Production B2Pochi often needs a **Result URL + QueueTimeOut URL** approved by
> Safaricom — they are already defaulted to `https://babes-bookstore.fly.dev/api/v1/checkout/webhook/b2pochi`.

### Sandbox note (current state)

STK push and B2Pochi are wired and tested to the point of hitting the sandbox
API, but the sandbox **consumer key/secret** currently in Fly are being rejected
(HTTP 400) — the credentials in the portal have changed since they were set.
Before any further testing, copy the current sandbox **Consumer Key + Consumer
Secret** from the portal app and:

```bash
fly secrets set MPESA_CONSUMER_KEY=<current> MPESA_CONSUMER_SECRET=<current> -a babes-bookstore
```

---

## Step 2 — SendGrid email receipts (recommended before launch)

Customers are used to a confirmation email. Without it the download link lives
only on the checkout screen/account page.

1. Sign up at https://signup.sendgrid.com → create an **API key**.
2. Add the sender address under Settings → Sender Authentication.
3. Load the key:

```bash
fly secrets set SENDGRID_API_KEY=<key> FROM_EMAIL=noreply@babesbooks.store -a babes-bookstore
```

> Without a key the app still works — it just logs "Would send: …" instead of emailing.

---

## Step 3 — Final live test purchase

1. Open any bundle at `https://babesbooks.store/bundles` (suggest the cheapest).
2. **Pay with M-Pesa** — enter your email and a real Kenyan phone number
   (format `2547XXXXXXXX`).
3. Complete the STK push on your phone. Within a minute the purchase should show
   **PAID** on your account page with a working download (PDF + EPUB).
4. Now test the **refund**: admin → Purchases → find the purchase → **Refund**.
   Money returns to your Pochi wallet. Confirm the Refund row shows succeeded.
5. Anything off? `fly logs -a babes-bookstore` and read the last 20 lines — a
   message like `M-Pesa OAuth token failed` or `M-Pesa STK push failed (HTTP n)`
   points straight at the secret to fix.

---

## Step 4 — Rotate shared credentials

Several M-Pesa test credentials appeared in chat while setting up. They are
sandbox-only, but rotate any **consumer key/secret** you're not using once
testing moves to production.

---

## Day-to-day runbook

- **New books arrive pending?** `/admin/books` → check the licence link → Approve
  (public domain / CC BY / CC BY-SA) or Reject (CC-NC, CC-ND, proprietary, unclear).
- **Customer wants a refund?** `/admin/purchases` → **Refund** (pays back via B2Pochi),
  then email them — see `/refunds` for the promise.
- **Something broken?** `fly logs -a babes-bookstore` first; `fly status` to confirm both
  `app` and `worker` machines are up.
- **Weekly:** review queue empty, worker machine running, refunds/purchases reconcile
  in the Daraja portal transaction list.

---

## Quick reference

| What | Where |
|---|---|
| Storefront | `https://babesbooks.store` |
| Engine health | `https://babes-bookstore.fly.dev/health` |
| API docs | `https://babes-bookstore.fly.dev/docs` |
| Admin panel | `https://babesbooks.store/admin` |
| Review queue | `/admin/books` |
| Refund purchases | `/admin/purchases` |
| Policies | `/terms` · `/privacy` · `/refunds` · `/cookies` |
| Logs | `fly logs -a babes-bookstore` |
| Keys | `fly secrets list -a babes-bookstore` |
| Machines | `fly status -a babes-bookstore` (app **and** worker) |
| M-Pesa setup detail | see `docs/MPESA.md` in the repo |