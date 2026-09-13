"""Tests for the system-bundle randomiser and banned-works integration."""
import pytest
from sqlalchemy import func, select

from app.models.book import Book, BookStatus
from app.models.bundle import Bundle, BundleBook


@pytest.mark.asyncio
async def test_randomise_curated_bundles_repicks_book_membership(db):
    """Curated bundles get a fresh, themed subset of approved books."""
    from app.services.bundle_randomise import randomise_curated_bundles

    for i in range(8):
        db.add(Book(
            title=f"Theme Book {i}", author="Theme Author",
            source="gutenberg", source_id=str(i),
            license_type="public_domain", status=BookStatus.APPROVED, license_verified=True,
            tags=["Suppressed Classics"],
        ))
    # An unrelated approved book (should be usable via full-pool fallback only).
    db.add(Book(
        title="Off-Theme", author="Other Author", source="gutenberg",
        source_id="999", license_type="public_domain", status=BookStatus.APPROVED, license_verified=True,
        tags=["Travel"],
    ))
    await db.flush()

    bun = Bundle(name="Banned", slug="banned-test", category="Banned & Suppressed",
                 tags=["Suppressed Classics"], price_cents=1000, active=True,
                 bundle_type="curated")
    db.add(bun)
    await db.flush()

    theme_books = (
        await db.execute(
            select(Book).where(
                Book.tags != None  # noqa: E711
            )
        )
    ).scalars().all()
    for n, b in enumerate(list(theme_books)[:3]):
        db.add(BundleBook(bundle_id=bun.id, book_id=b.id, sort_order=n))
    await db.commit()

    result = await randomise_curated_bundles(db)

    assert len(result["updated"]) == 1
    assert "banned-test" in result["updated"][0]

    # Membership must now come purely from the approved pool, be themed, and
    # keep a sane size.
    rows = (await db.execute(
        select(Book.id, Book.tags).join(
            BundleBook, Book.id == BundleBook.book_id
        ).where(BundleBook.bundle_id == bun.id)
    )).all()
    assert 3 <= len(rows) <= 8
    for _, tags in rows:
        assert "Suppressed Classics" in tags


@pytest.mark.asyncio
async def test_randomise_skips_custom_bundles_and_inactive(db):
    """User (custom) bundles and inactive bundles are never touched."""
    from app.services.bundle_randomise import randomise_curated_bundles

    b1 = Book(title="A", author="A", source="gutenberg", source_id="1",
              license_type="public_domain", status=BookStatus.APPROVED)
    b2 = Book(title="B", author="B", source="gutenberg", source_id="2",
              license_type="public_domain", status=BookStatus.APPROVED)
    db.add_all([b1, b2])
    await db.flush()

    custom = Bundle(name="My Shelf", slug="custom-shelf", price_cents=500,
                    bundle_type="custom", active=True)
    inactive = Bundle(name="Dormant", slug="dormant", price_cents=500,
                      bundle_type="curated", active=False)
    db.add_all([custom, inactive])
    await db.flush()
    db.add_all([
        BundleBook(bundle_id=custom.id, book_id=b1.id, sort_order=0),
        BundleBook(bundle_id=inactive.id, book_id=b2.id, sort_order=0),
    ])
    await db.commit()

    result = await randomise_curated_bundles(db)
    assert result["updated"] == []
    assert result["skipped"] == ["no active curated bundles"]


@pytest.mark.asyncio
async def test_randomise_preserves_book_count_in_expected_range(db):
    """A curated bundle keeps a MIN..MAX sized, approved-only membership."""
    import random
    from app.services.bundle_randomise import randomise_curated_bundles

    random.seed(7)
    for i in range(30):
        db.add(Book(
            title=f"B{i}", author=f"Author {i}", source="gutenberg",
            source_id=str(i), license_type="public_domain",
            status=BookStatus.APPROVED, license_verified=True, tags=["Matched"],
        ))
    await db.flush()

    bun = Bundle(name="Matched", slug="matched", tags=["Matched"],
                 price_cents=1000, active=True, bundle_type="curated")
    db.add(bun)
    await db.flush()
    # Seed two members so the bundle isn't "empty".
    all_books = (await db.execute(
        select(Book)
    )).scalars().all()
    for n, b in enumerate(all_books[:2]):
        db.add(BundleBook(bundle_id=bun.id, book_id=b.id, sort_order=n))
    await db.commit()

    result = await randomise_curated_bundles(db)
    assert len(result["updated"]) == 1

    count = (await db.execute(
        select(func.count()).select_from(
            BundleBook
        ).where(BundleBook.bundle_id == bun.id)
    )).scalar()
    assert count >= 3


@pytest.mark.asyncio
async def test_randomise_endpoint_blocked_for_anonymous_and_normal(client):
    assert (await client.post("/api/v1/admin/bundles/randomise")).status_code in (401, 403)

    reg = await client.post("/api/v1/auth/register", json={
        "email": "reader2@example.com", "password": "s3cret-pass", "name": "Reader",
    })
    token = reg.json()["access_token"]
    r = await client.post("/api/v1/admin/bundles/randomise",
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_african_authors_carries_banned_flag(db):
    """Revolutionary writers are flagged as banned for the badge UI."""
    from app.models.bundle import Bundle  # noqa: F401  (model import sanity)

    # Real canon entries; one tagged African Literature, one not.
    db.add(Book(
        title="No Easy Walk to Freedom", author="Nelson Mandela",
        source="african", source_id="m1", license_type="public_domain",
        status=BookStatus.APPROVED, tags=["African Literature", "African Author", "Revolutionary"],
    ))
    db.add(Book(
        title="I Write What I Like", author="Steve Biko",
        source="african", source_id="b1", license_type="public_domain",
        status=BookStatus.APPROVED, tags=["African Literature", "African Author", "Revolutionary"],
    ))
    await db.commit()

    from app.api.v1.authors import _banned
    assert _banned("Steve Biko") is True
    assert _banned("nelson mandela") is True
    assert _banned("Goldman, Emma") is True
    assert _banned("Trotsky, Leon") is True
    assert _banned("McKay, Claude") is True
    assert _banned("Jane Austen") is False