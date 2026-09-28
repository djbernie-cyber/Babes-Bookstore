"""Bulk restore must review, not approve.

The 2,099 rejected rows include three books that are on
KNOWN_NOT_PUBLIC_DOMAIN_IDS because they are modern in-copyright novels being
presented as public domain: Things Fall Apart, Nervous Conditions and Crispin.
A bulk action that moved the whole pile to APPROVED would assert a licence
verification nobody performed and put those three on the shelf.

So restore_rejected_books sends them to PENDING, keeps the known-bad ones
rejected, and preserves rejected_reason on everything it touches.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.book import Book, BookStatus


@pytest.fixture
def admin():
    from app.models.user import User

    return User(id=1, email="admin@example.org", is_admin=True, hashed_password="x")


async def add_rejected(db, n, **kw):
    books = []
    for i in range(n):
        book = Book(
            title=f"Rejected {i}",
            author="An Author",
            source=kw.get("source", "standard_ebooks"),
            source_id=kw.get("source_id", f"author/book-{i}"),
            source_url=f"https://example.org/{i}",
            license_type="public_domain",
            asset_verified=False,
            status=BookStatus.REJECTED,
            rejected_reason=kw.get("rejected_reason", "source unconfirmed: HTTP 404"),
        )
        db.add(book)
        books.append(book)
    await db.commit()
    for b in books:
        await db.refresh(b)
    return books


async def call_restore(db, admin, monkeypatch):
    from app.api.v1 import admin as admin_api

    called = {}

    async def fake_log(db_, **kw):
        called.update(kw)

    monkeypatch.setattr(admin_api, "log_action", fake_log)
    return await admin_api.restore_rejected_books(db=db, admin=admin)


class TestRestoreRejected:
    @pytest.mark.asyncio
    async def test_restores_to_pending_not_approved(self, db, admin, monkeypatch):
        """The whole point: review, not a licence decision."""
        await add_rejected(db, 3)
        result = await call_restore(db, admin, monkeypatch)

        assert result["restored"] == 3
        assert result["status"] == "pending"
        books = (await db.execute(select(Book))).scalars().all()
        assert all(b.status == BookStatus.PENDING for b in books)
        assert not any(b.status == BookStatus.APPROVED for b in books)

    @pytest.mark.asyncio
    async def test_known_in_copyright_works_stay_rejected(self, db, admin, monkeypatch):
        """Things Fall Apart et al must never return to a reviewable state."""
        for bad in (
            "chinua-achebe/things-fall-apart",
            "tsitsi-dangarembga/nervous-conditions",
            "avi/crispin",
        ):
            await add_rejected(db, 1, source_id=bad)
        result = await call_restore(db, admin, monkeypatch)

        assert result["restored"] == 0
        assert result["kept_rejected"] == 3
        books = (await db.execute(select(Book))).scalars().all()
        assert all(b.status == BookStatus.REJECTED for b in books)

    @pytest.mark.asyncio
    async def test_mixed_pile_splits_correctly(self, db, admin, monkeypatch):
        # (source, source_id) is unique, so each needs its own id.
        await add_rejected(db, 1, source_id="author/good-1")
        await add_rejected(db, 1, source_id="author/good-2")
        await add_rejected(db, 1, source_id="avi/crispin")

        result = await call_restore(db, admin, monkeypatch)

        assert result["restored"] == 2
        assert result["kept_rejected"] == 1
        assert result["kept"][0]["source_id"] == "avi/crispin"

    @pytest.mark.asyncio
    async def test_reason_is_preserved(self, db, admin, monkeypatch):
        """The reason is what makes the queue reviewable; do not clear it."""
        await add_rejected(db, 2, rejected_reason="known non-public-domain modern work")
        await call_restore(db, admin, monkeypatch)

        books = (await db.execute(select(Book))).scalars().all()
        assert all(b.rejected_reason == "known non-public-domain modern work" for b in books)

    @pytest.mark.asyncio
    async def test_approved_books_are_untouched(self, db, admin, monkeypatch):
        approved = Book(
            title="Fine book", author="A", source="gutenberg", source_id="1342",
            source_url="https://example.org/1342", license_type="public_domain",
            asset_verified=True, status=BookStatus.APPROVED,
        )
        db.add(approved)
        await db.commit()

        result = await call_restore(db, admin, monkeypatch)

        assert result["restored"] == 0
        await db.refresh(approved)
        assert approved.status == BookStatus.APPROVED
        assert approved.asset_verified is True

    @pytest.mark.asyncio
    async def test_is_idempotent(self, db, admin, monkeypatch):
        await add_rejected(db, 2)
        first = await call_restore(db, admin, monkeypatch)
        second = await call_restore(db, admin, monkeypatch)
        assert first["restored"] == 2
        assert second["restored"] == 0

    @pytest.mark.asyncio
    async def test_requires_admin(self):
        from app.api.v1.deps import require_admin
        from fastapi import HTTPException
        import inspect

        src = inspect.getsource(require_admin)
        assert "403" in src or "HTTP_403" in src or "is_admin" in src
