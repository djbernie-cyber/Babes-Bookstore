# M-Pesa Setup Guide — Babe's Bookstore

## 1. What the app supports

| Flow | API | Backend uses |
|---|---|---|
| Customer pays | `POST /api/v1/checkout/mpesa` (STK push / Lipa Na M-Pesa Online) | Consumer key/secret + Shortcode + Passkey |
| Payment result | `POST /checkout/webhook/mpesa` (Safaricom callback) | settles Purchase → PAID/FAILED |
| Admin refund | `POST /api/v1/admin/purchases/{id}/refund` (B2Pochi payout) | Consumer key/secret + B2C shortcode + Initiator + SecurityCredential |
| Refund result | `POST /checkout/webhook/b2pochi` | transitions Refund → succeeded/failed |

Amount is derived from the bundle price: GBP pence → KES at **1 GBP ≈ 170 KES**
(`max(1, round(cents/100×170))` for STK, `max(10,…)` for refunds, since KES has no cents).

## 2. Environment variables (Fly secrets — `backend/app/config.py`)

| Secret | Purpose | Sandbox value (test) | Production |
|---|---|---|---|
| `MPESA_CONSUMER_KEY` | OAuth | your sandbox app key | production app key |
| `MPESA_CONSUMER_SECRET` | OAuth | your sandbox app secret | production app secret |
| `MPESA_ENVIRONMENT` | `sandbox` / `production` | `sandbox` | `production` |
| `MPESA_SHORTCODE` | STK BusinessShortCode | `174379` | your real Paybill/Buy-Goods |
| `MPESA_PASSKEY` | STK LNM passkey | from portal | production passkey |
| `MPESA_CALLBACK_URL` | STK result webhook | optional — defaults to `https://babes-bookstore.fly.dev/api/v1/checkout/webhook/mpesa` | set publicly-reachable HTTPS |
| `MPESA_B2C_SHORTCODE` | refund PartyA | `600986` | your B2C/disbursement shortcode |
| `MPESA_B2C_INITIATOR_NAME` | refund initiator | `testapi` | your initiator (B2C role) |
| `MPESA_B2C_SECURITY_CREDENTIAL` | encrypted initiator password | RSA(PKCS#1)+Base64 of password | encrypted with production cert |
| `MPESA_B2POCHI_CALLBACK_URL` | refund result webhook | defaults to `…/webhook/b2pochi` | same |

Set them with:

```
fly secrets set MPESA_CONSUMER_KEY=… MPESA_CONSUMER_SECRET=… MPESA_SHORTCODE=174379 \
  MPESA_PASSKEY=… MPESA_B2C_SHORTCODE=600986 MPESA_B2C_INITIATOR_NAME=testapi \
  MPESA_B2C_SECURITY_CREDENTIAL=… -a babes-bookstore
```

## 3. Sandbox (test) verification

1. **OAuth works** — `GET https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials` with `Authorization: Basic base64(key:secret)` returns a 1-hour `access_token`.
2. **STK push E2E** (test phone `254708374149`):

   ```
   curl -X POST https://babes-bookstore.fly.dev/api/v1/checkout/mpesa \
     -H "Content-Type: application/json" \
     -d '{"bundle_slug":"<a bundle slug>","email":"you@example.com","phone":"254708374149"}'
   ```

   Expect `checkout_url` + `session_id`; a PENDING purchase is created. Simulate the
   callback from the Daraja portal **Simulate** tab → it hits `/checkout/webhook/mpesa`,
   which only transitions purchases we created (PENDING → PAID/FAILED).

3. **B2Pochi sandbox** — with the SecurityCredential configured, create a PAID M-Pesa
   purchase and call `/api/v1/admin/purchases/{id}/refund` with an admin token. The
   sandbox test Pochi wallet for PartyB is `600000`.

## 4. Getting `MPESA_B2C_SECURITY_CREDENTIAL`

It is the initiator password RSA/PKCS#1-v1.5-encrypted with Safaricom's certificate, then Base64:

```
openssl x509 -in SandboxCertificate.cer -pubkey -noout > pub.pem
printf '%s' "Safaricom123!!" | openssl rsautl -encrypt -pubin -inkey pub.pem -pkcs | base64 -w0
```

- Sandbox cert: `SandboxCertificate.cer` (Daraja portal → docs/B2C "Download Certificate";
  it is the shared sandbox cert, so the sandbox credential is a fixed published value).
- Production cert: `ProductionCertificate.cer` from the portal after go-live; the
  credential is then unique to your initiator password.

## 5. Going live (production checklist)

1. Get a real **M-Pesa Paybill / Buy-Goods shortcode** from Safaricom (a shortcode is
   never issued on a sandbox app) → fills `MPESA_SHORTCODE`.
2. In the Daraja portal, apply to **Go Live**; create the **Production app** and add
   products: *Lipa Na M-Pesa Online* (STK) and *B2C / Pochi* (refunds).
3. Production STK usually requires **registering callback URLs** with Safaricom (any
   public HTTPS URL works — ours is `https://babes-bookstore.fly.dev/api/v1/checkout/webhook/mpesa`).
4. Set up the **B2C initiator** (B2C API role, not "my account") and generate its
   SecurityCredential with the production certificate.
5. Flip `MPESA_ENVIRONMENT=production` and update every M-Pesa secret — never reuse
   sandbox credentials in production.
6. Live test with a small real amount: STK push arrives → webhook marks PAID → refund
   pays out to the Pochi wallet.

## 6. Notes / pitfalls

- **Phone format** must be `2547XXXXXXXX`; the app normalises `07…`, `+254…`, `7XXXXXXXX`.
- **Callbacks are unsigned** — the webhook deliberately only transitions existing
  PENDING purchases/refunds and never creates money.
- **OriginatorConversationID** (`BBREF-{purchaseId}-{ts}`) is the refund idempotency
  key; Daraja rejects duplicates.
- **Sandbox** is fake money — never point production at sandbox.
- Rotate any credentials shared via chat once live.