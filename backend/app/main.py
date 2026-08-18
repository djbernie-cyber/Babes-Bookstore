import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from sqlalchemy import select, func

from .config import settings
from .database import init_db, AsyncSessionLocal
from .models.user import User
from .models.book import Book, BookStatus
from .models.bundle import Bundle
from .api.v1.router import api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _seed_admin_users(session_factory=None):
    """Ensure every address in ADMIN_EMAILS is an admin with free downloads.

    Idempotent: creates missing accounts and promotes existing ones.
    `session_factory` is injectable so tests can supply their own database.
    """
    if session_factory is None:
        import app.database as _db
        session_factory = _db.AsyncSessionLocal

    async with session_factory() as db:
        for email in settings.ADMIN_EMAILS:
            stmt = select(User).where(User.email == email)
            user = (await db.execute(stmt)).scalar_one_or_none()
            if not user:
                user = User(
                    email=email,
                    name=email.split("@")[0].replace(".", " ").title(),
                    is_admin=True,
                    free_downloads=True,
                    is_active=True,
                )
                db.add(user)
                logger.info(f"Created admin user: {email}")
            else:
                changed = False
                if not user.is_admin:
                    user.is_admin = True
                    changed = True
                if not user.free_downloads:
                    user.free_downloads = True
                    changed = True
                if changed:
                    logger.info(f"Updated user to admin with free downloads: {email}")
        await db.commit()


_INSECURE_KEYS = {
    "change-me-in-production-please-use-openssl-rand-hex-32",
    "change-me-use-openssl-rand-hex-32",
}


def _validate_production_config():
    """Fail fast on insecure or incomplete production configuration."""
    if settings.DEBUG:
        return

    errors = []
    if settings.SECRET_KEY in _INSECURE_KEYS or len(settings.SECRET_KEY) < 32:
        errors.append("SECRET_KEY must be a unique value of at least 32 chars (openssl rand -hex 32)")
    if settings.DATABASE_URL.startswith("sqlite"):
        errors.append("SQLite is not supported in production; use PostgreSQL")
    if errors:
        raise RuntimeError(
            "Refusing to start with insecure production config:\n  - " + "\n  - ".join(errors)
        )

    for name, value in [
        ("STRIPE_SECRET_KEY", settings.STRIPE_SECRET_KEY),
        ("R2_ACCESS_KEY_ID", settings.R2_ACCESS_KEY_ID),
        ("GOOGLE_CLIENT_ID", settings.GOOGLE_CLIENT_ID),
    ]:
        if not value:
            logger.warning(f"{name} is not configured — related features will be unavailable")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    _validate_production_config()
    await init_db()
    await _seed_admin_users()
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

_origins = list(settings.CORS_ORIGINS)
if settings.FRONTEND_URL and settings.FRONTEND_URL not in _origins:
    _origins.append(settings.FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"https://.*\.netlify\.app|https://deploy-preview-\d+--.*\.netlify\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "frontend" / "templates"))
app.state.templates = templates

app.include_router(api_router)


@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
        },
    )


@app.get("/bundles")
async def bundles_page(request: Request):
    return templates.TemplateResponse("bundles/list.html", {"request": request, "app_name": settings.APP_NAME})


@app.get("/bundles/{slug}")
async def bundle_detail_page(request: Request, slug: str):
    return templates.TemplateResponse("bundles/detail.html", {"request": request, "app_name": settings.APP_NAME, "slug": slug})


@app.get("/books/{book_id}")
async def book_detail_page(request: Request, book_id: int):
    return templates.TemplateResponse("books/detail.html", {"request": request, "app_name": settings.APP_NAME, "book_id": book_id})


@app.get("/search")
async def search_page(request: Request, q: str = ""):
    return templates.TemplateResponse("books/search.html", {"request": request, "app_name": settings.APP_NAME, "query": q})


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("account/login.html", {"request": request, "app_name": settings.APP_NAME})


@app.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("account/register.html", {"request": request, "app_name": settings.APP_NAME})


@app.get("/account")
async def account_page(request: Request):
    return templates.TemplateResponse("account/purchases.html", {"request": request, "app_name": settings.APP_NAME})


@app.get("/admin")
async def admin_dashboard(request: Request):
    return templates.TemplateResponse("admin/dashboard.html", {"request": request, "app_name": settings.APP_NAME})


@app.get("/admin/books")
async def admin_books(request: Request):
    return templates.TemplateResponse("admin/books.html", {"request": request, "app_name": settings.APP_NAME})


@app.get("/admin/bundles")
async def admin_bundles(request: Request):
    return templates.TemplateResponse("admin/bundles.html", {"request": request, "app_name": settings.APP_NAME})


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)