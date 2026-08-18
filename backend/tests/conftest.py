"""Shared pytest fixtures: isolated in-memory app + database per test."""
import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-000000")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
# Test-only Stripe config so checkout endpoints take the provider branch
# rather than returning 500. The actual Stripe SDK is patched in tests.
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_dummy")
os.environ.setdefault("STRIPE_PUBLISHABLE_KEY", "pk_test_dummy")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_dummy")
os.environ.setdefault("PAYPAL_CLIENT_ID", "paypal_test_dummy")
os.environ.setdefault("PAYPAL_CLIENT_SECRET", "paypal_secret_dummy")
os.environ.setdefault("SQUARE_ACCESS_TOKEN", "sq_test_dummy")
os.environ.setdefault("SQUARE_LOCATION_ID", "L_test_dummy")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import book, bundle, user, purchase, audit  # noqa: F401


@pytest_asyncio.fixture
async def engine(tmp_path):
    """A real file-backed SQLite database, isolated per test.

    A file (rather than ":memory:") is required because the connection pool
    may open several connections, and each in-memory connection would
    otherwise see its own empty database.
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    eng = create_async_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(session_factory):
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def client(session_factory):
    """App client with the DB dependency overridden to the test database."""
    from app.main import app
    from app.api.v1.deps import get_db

    async def _override_get_db():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded(db):
    """Two approved books inside one active, featured bundle."""
    from app.models.book import Book, BookStatus
    from app.models.bundle import Bundle, BundleBook

    b1 = Book(title="Pride and Prejudice", author="Jane Austen", source="gutenberg",
              source_id="1342", license_type="public_domain", status=BookStatus.APPROVED)
    b2 = Book(title="Moby Dick", author="Herman Melville", source="gutenberg",
              source_id="2701", license_type="public_domain", status=BookStatus.APPROVED)
    db.add_all([b1, b2])
    await db.flush()

    bun = Bundle(name="Classic Literature", slug="classic-literature",
                 description="Timeless novels", price_cents=1000, currency="gbp",
                 category="fiction", active=True, featured=True)
    db.add(bun)
    await db.flush()
    db.add_all([
        BundleBook(bundle_id=bun.id, book_id=b1.id, sort_order=0),
        BundleBook(bundle_id=bun.id, book_id=b2.id, sort_order=1),
    ])
    await db.commit()
    return {"bundle": bun, "books": [b1, b2]}
