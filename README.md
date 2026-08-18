# Babe's Bookstore

A curated marketplace for public domain and openly-licensed books.

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