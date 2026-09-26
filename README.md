# Babe's Bookstore

**Built for a neutral internet — by William Majanja.**

A curated marketplace for public domain and openly-licensed books.

## Mission

Illiteracy is the enemy. Not a metaphor, not a talking point — the single
thing that keeps a person poor, voiceless and easy to govern is the inability
to read.

This library exists to end it. Every text here is free to read online and free
to download, in the reader's own language, on whatever device they already own.
No subscription, no DRM, no expiring licence, no paywall between a person and
a book. Take the whole shelf if you want it; it stays yours.

**We are building for a neutral internet.** The internet is at its best when it
simply carries knowledge from the people who wrote it to the people who want it,
with nothing in between: no gatekeeper deciding who is worth educating, no
subscription wall scaling with income, no algorithm deciding which minds count.
Censorship, paywalls and pay-per-view are not neutral. This project is a
standing argument against them.

The work is deliberately unglamorous: texts are licence-verified, cleaned,
typeset and delivered as print-ready PDF and reflowable EPUB. A library that
cannot be trusted to serve the book is not a library, it is a stall.

## What we will not do

- We will not serve an in-copyright text as though it were free.
- We will not hide a broken link behind a "coming soon".
- We will not charge twice for the same public-domain work.

## Quick Start

```bash
# 1. Clone and setup
cd babes-bookstore
cp .env.example backend/.env
# Edit backend/.env with your credentials

# 2. Start with Docker
docker-compose up -d

# 3. Run migrations
cd backend
alembic upgrade head

# 4. Create admin user
python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.models.user import User
from passlib.context import CryptContext

pwd = CryptContext(schemes=['bcrypt'], deprecated='auto')

async def create():
    async with AsyncSessionLocal() as db:
        user = User(email='admin@example.com', name='Admin', hashed_password=pwd.hash('admin123'), is_admin=True)
        db.add(user)
        await db.commit()
        print('Admin user created: admin@example.com / admin123')

asyncio.run(create())
"

# 5. Scrape initial books
curl -X POST http://localhost:8000/api/v1/admin/scrape/popular \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

## Deployment

### Backend (Fly.io / Railway)

```bash
# Build and deploy
fly launch
fly deploy
```

### Backend (Kubernetes — production rolling updates)

The `infra/kubernetes/` bundle deploys the API + Celery worker + Postgres +
Redis with zero-downtime rolling updates (health-gated, PDB-protected,
autoscaled). Pushing to `main` runs the GitHub Actions pipeline
(`.github/workflows/deploy-kubernetes.yml`) that builds a new image and rolls
it through the cluster. See `infra/kubernetes/README.md`.

```bash
kubectl apply -k infra/kubernetes   # build image & push ghcr first
```

### Frontend (Netlify)

```bash
# Install Netlify CLI
npm install -g netlify-cli

# Deploy
cd frontend
netlify deploy --prod
```

### Environment Variables

Set these in your hosting platform:

- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string
- `SECRET_KEY` — Random hex string for JWT
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` — Cloudflare R2
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` — Stripe
- `SENDGRID_API_KEY` — SendGrid (optional)

## Architecture

```
Netlify (Frontend)  →  FastAPI Backend  →  PostgreSQL
                        ↓
                     Celery Worker  →  Redis (broker)
                        ↓
                     Source Adapters (Gutenberg, DOAB, etc.)
                        ↓
                     Cloudflare R2 (PDF storage)
```

## Sources

| Source | License | Content |
|--------|---------|---------|
| Project Gutenberg | Public Domain | 70,000+ ebooks |
| Standard Ebooks | Public Domain | 1,000+ enhanced ebooks |
| DOAB | CC-BY / CC-BY-SA | 25,000+ academic books |
| OAPEN | CC licenses | Open access academic |
| Open Library | Per-item verified | Large catalog |
| Internet Archive | Per-item verified | Millions of items |

## License

MIT