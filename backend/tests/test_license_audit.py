"""An unreachable source URL is not proof of infringement.

The licence audit rejected 2,209 books because their declared source URL did
not resolve, and recorded the reason only in a log line. Two problems followed.
The queue became unreviewable — an admin saw 2,099 withdrawn titles with no
stated cause — and the rejections themselves were largely wrong: a 404 or a
timeout is what a moved, rate-limited or briefly-down source looks like, not
evidence that a book is in copyright.

These tests pin the split. Curated evidence of a non-public-domain work still
rejects. An unconfirmed source now goes to PENDING, keeping the book and its
reason, because wrongly withdrawing genuine public-domain stock costs more than
leaving it for a human to check.
"""
import pytest
from sqlalchemy import select

from app.models.book import Book, BookStatus
from app.services.license_audit import (
    KNOWN_NOT_PUBLIC_DOMAIN_IDS,
    _classify,
    audit_approved_books,
)

SOURCE = "standard_ebooks"


async def add_book(db, **kw):
    defaults = dict(
        title="A Book",
        author="An Author",
        source=SOURCE,
        source_id="author/some-slug",
        source_url="https://example.org/some-slug",
        license_type="public_domain",
        license_verified=True,
        status=BookStatus.APPROVED,
    )
    defaults.update(kw)
    book = Book(**defaults)
    db.add(book)
    await db.commit()
    await db.refresh(book)
    return book


def fake_resolver(ok, reason):
    async def _inner(url):
        return ok, reason

    return _inner


def stub(monkeypatch, ok, reason):
    monkeypatch.setattr(
        "app.services.license_audit._source_resolves", fake_resolver(ok, reason)
    )


class TestClassification:
    def test_known_modern_work_is_rejected(self):
        """The fabricated-slug case, which is the audit's reason to exist."""
        book = type("B", (), {"source_id": "avi/crispin"})()
        assert _classify(book, False, "HTTP 404") == "rejected"

    def test_unresolvable_source_is_pending_not_rejected(self):
        book = type("B", (), {"source_id": "author/real-book"})()
        assert _classify(book, False, "HTTP 404") == "pending"
        assert _classify(book, False, "unreachable (ConnectTimeout)") == "pending"

    def test_resolved_source_is_unchanged(self):
        book = type("B", (), {"source_id": "author/real-book"})()
        assert _classify(book, True, "HTTP 200") == "ok"

    def test_known_bad_id_wins_even_if_it_resolves(self):
        """A modern novel whose URL happens to 200 is still not public domain."""
        book = type("B", (), {"source_id": "avi/crispin"})()
        assert _classify(book, True, "HTTP 200") == "rejected"

    def test_every_known_bad_id_is_rejected(self):
        for source_id in KNOWN_NOT_PUBLIC_DOMAIN_IDS:
            book = type("B", (), {"source_id": source_id})()
            assert _classify(book, False, "HTTP 404") == "rejected"


class TestAuditBehaviour:
    @pytest.mark.asyncio
    async def test_unconfirmed_book_goes_to_pending_with_a_reason(self, db, monkeypatch):
        book = await add_book(db)
        stub(monkeypatch, False, "HTTP 404")

        report = await audit_approved_books(db)

        assert report["pending"] == 1
        assert report["rejected"] == 0
        await db.refresh(book)
        assert book.status == BookStatus.PENDING
        assert book.license_verified is False
        assert "HTTP 404" in book.rejected_reason

    @pytest.mark.asyncio
    async def test_pending_book_is_reported_for_review(self, db, monkeypatch):
        await add_book(db)
        stub(monkeypatch, False, "unreachable (ConnectTimeout)")

        report = await audit_approved_books(db)

        assert report["pending_titles"][0]["reason"] == "unreachable (ConnectTimeout)"

    @pytest.mark.asyncio
    async def test_known_modern_work_is_still_rejected(self, db, monkeypatch):
        """The audit must keep its teeth for the case it was written for."""
        book = await add_book(db, source_id="avi/crispin")
        stub(monkeypatch, True, "HTTP 200")

        report = await audit_approved_books(db)

        assert report["rejected"] == 1
        assert report["pending"] == 0
        await db.refresh(book)
        assert book.status == BookStatus.REJECTED
        assert book.license_verified is False
        assert book.rejected_reason == "known non-public-domain modern work"

    @pytest.mark.asyncio
    async def test_resolvable_book_is_untouched(self, db, monkeypatch):
        book = await add_book(db)
        stub(monkeypatch, True, "HTTP 200")

        report = await audit_approved_books(db)

        assert report["ok"] == 1
        await db.refresh(book)
        assert book.status == BookStatus.APPROVED
        assert book.license_verified is True
        assert book.rejected_reason is None

    @pytest.mark.asyncio
    async def test_report_counts_add_up(self, db, monkeypatch):
        """A rejected and a pending book in one pass, both counted correctly."""
        await add_book(db, source_id="avi/crispin")
        await add_book(db, source_id="author/real-book")
        stub(monkeypatch, False, "HTTP 404")

        report = await audit_approved_books(db)

        assert report["checked"] == 2
        assert report["rejected"] == 1
        assert report["pending"] == 1
        assert report["rejected"] + report["pending"] + report["ok"] == report["checked"]

    @pytest.mark.asyncio
    async def test_pending_book_is_not_re_audited_in_the_same_pass(self, db, monkeypatch):
        """The query is scoped to approved, so a pass is idempotent."""
        await add_book(db)
        stub(monkeypatch, False, "HTTP 404")

        await audit_approved_books(db)
        second = await audit_approved_books(db)

        assert second["checked"] == 0

    @pytest.mark.asyncio
    async def test_gutenberg_is_excluded(self, db, monkeypatch):
        """gutendex already hard-filters on copyright=false."""
        await add_book(db, source="gutenberg", source_id="1342")
        stub(monkeypatch, False, "HTTP 404")

        report = await audit_approved_books(db)

        assert report["checked"] == 0


class TestSchemaAndModel:
    @pytest.mark.asyncio
    async def test_model_has_rejected_reason(self, db):
        book = await add_book(db, status=BookStatus.REJECTED)
        await db.refresh(book)
        assert book.rejected_reason is None

        book.rejected_reason = "source unconfirmed: HTTP 404"
        await db.commit()

        rows = (
            await db.execute(select(Book).where(Book.rejected_reason.isnot(None)))
        ).scalars().all()
        assert [r.id for r in rows] == [book.id]

    def test_response_schema_exposes_the_reason(self):
        from app.schemas.book import BookResponse

        assert "rejected_reason" in BookResponse.model_fields
