# Babe's Bookstore — Netlify-Only Launch Guide (Zero External Service Dependencies)

This project is refactored to run **entirely on Netlify**:
- **Frontend**: static files in `frontend/` (published by Netlify)
- **API**: Netlify Functions (`netlify/functions/api.mjs`) served at `/api/v1/*`
- **Data/NoSQL**: Netlify Blobs (key-value/object store)
- **No Fly.io, no external Postgres/Redis/Celery, no third-party payment/email/storage/OAuth services** required for core operation

## 1) Deploy to Netlify

1. Push this repo to GitHub (if not already).
2. Netlify → **Add new site** → **Import an existing project** → select the repo.
3. Netlify reads `netlify.toml`:
   - `publish = "frontend"`
   - `functions = "netlify/functions"`
   - build command `npm install`
4. Deploy the site.

## 2) Configure environment variables (Netlify UI)

Set in **Site configuration → Environment variables**:
- `TOKEN_SECRET` (recommended): a long random string for auth token signing
- `ADMIN_EMAILS` (optional): comma-separated emails to grant admin access

Notes:
- **Admin access bootstrap**: the first registered user becomes admin automatically (and `ADMIN_EMAILS` can grant admin). This replaces Fly/Grafana-era ops workflows with Netlify function logs/analytics.
- Data is stored in **Netlify Blobs**; the API seeds a small sample catalog on first use. Import/extend book data in Blobs for real catalog scale.

## 3) Verify

- Open `https://<your-site>.netlify.app/api/v1/health` → should return `{"status":"ok"...}`
- Open the site → browse, search, and register/login.
- Sign in as the first user (or an `ADMIN_EMAILS` user) → `/admin` dashboard should load stats.

## 4) Store books (Netlify-only / NoSQL)

Books/catalog metadata are stored in Netlify Blobs (`meta:books`, etc.). For production:
- Load/import your catalog into the Blobs store used by the API (`babes` store).
- Book files/content can be stored and served via Netlify Blobs (extend `netlify/functions/api.mjs` download handlers) or included as static assets where appropriate.
- Optimize for your size/bandwidth needs (chunked datasets, indexed keys per book, or split metadata blobs) — Netlify Blobs is the NoSQL layer in this architecture.

## 5) What changed vs. the old architecture

- **Removed**: Fly.io, Docker/Celery/Redis/Postgres deployment path, Google OAuth, SendGrid, Cloudflare R2, Stripe/PayPal/Square/M-Pesa integrations, and scraping/worker pipelines.
- **Replaced**: backend API with Netlify Functions; relational/external storage with Netlify Blobs (NoSQL); Grafana/host metrics with Netlify logs/analytics + in-app `/health` and admin stats.
- **Kept for reference**: `backend/` (legacy FastAPI code) is not used by the Netlify deployment.

## Troubleshooting

- **Admin inaccessible**: ensure you're signed in; register the first user (auto-admin) or set `ADMIN_EMAILS` in Netlify env vars, then sign in again.
- **Nav/API issues**: confirm redirects are active (`/api/v1/*` → `/.netlify/functions/api/:splat` per `netlify.toml`) and functions deployed successfully; check Netlify function logs.
- **Token/auth issues after deploy**: set a stable `TOKEN_SECRET` env var (changing it invalidates existing tokens).
