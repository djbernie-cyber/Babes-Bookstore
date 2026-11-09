# Babe's Bookstore

A curated catalog/storefront for public-domain and openly-licensed books.

> **Current architecture (zero external service dependencies):** deployed on
> **Netlify only** using static frontend files, **Netlify Functions** for the
> API, and **Netlify Blobs** (NoSQL key-value/object store) for data/book
> metadata. No Fly.io, no external Postgres/Redis/Celery services, no
> third-party payment/email/storage/OAuth integrations are required for core
> operation.

## Quick start (local)

```bash
npm install
# Requires Netlify CLI for local Functions + Blobs emulation:
npx netlify dev
```

Then open the local URL shown by Netlify CLI.

## Deployment

1. Push this repo to GitHub.
2. In Netlify: **Add new site → Import from Git** → select the repo.
3. Build settings come from `netlify.toml`:
   - Base: `.`
   - Publish: `frontend`
   - Functions: `netlify/functions`
   - Build command: `npm install`
4. (Recommended) Set `TOKEN_SECRET` in Netlify environment variables.
5. (Optional) Set `ADMIN_EMAILS` (comma-separated) to grant admin access.

The API is served at `/api/v1/*` via Netlify Functions (`netlify/functions/api.mjs`),
and data is stored in Netlify Blobs.

## Notes / limitations of this rewrite

This is an aggressive Netlify-only refactor. Some features from the previous
Python/FastAPI architecture are simplified or stubbed:
- Payments (Stripe/PayPal/Square/M-Pesa), SendGrid email, Cloudflare R2, and
  Google OAuth are removed/disabled.
- Background scraping/packaging workers (Celery/Redis) are not used; admin/job
  endpoints return limited responses.
- The catalog is stored in Netlify Blobs and seeded with sample data on first
  run; import your full book dataset into Blobs for production-scale content.
- Book file storage/serving should be implemented via Netlify Blobs (or your
  chosen Netlify-native approach) based on your content size needs.

## Legacy code

The `backend/` directory contains the previous FastAPI implementation and is
kept for reference during migration. The active deployment path is Netlify-only.

## License

Proprietary — Copyright (c) 2026 William Majanja and the Contributors of Mafutani.
All rights reserved. See [`LICENSE`](./LICENSE). No use, copying, modification,
or distribution is permitted without prior written authorization.
