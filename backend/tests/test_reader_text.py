"""Reader-text feature tests: EPUB-only books must still be readable in the
in-browser reader via on-the-fly EPUB → plain-text rendering."""
import io
import zipfile

import pytest


def _synthetic_epub() -> bytes:
    """A minimal valid EPUB: container -> opf -> two HTML chapters."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile media-type="application/oebps-package+xml" '
            'full-path="OEBPS/content.opf"/></rootfiles></container>',
        )
        zf.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<manifest>'
            '<item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="c2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest>'
            '<spine><itemref idref="c1"/><itemref idref="c2"/></spine>'
            '</package>',
        )
        zf.writestr(
            "OEBPS/chapter1.xhtml",
            "<html><body><h1>Chapter One</h1><p>Arise, wallet. Go forth.</p></body></html>",
        )
        zf.writestr(
            "OEBPS/chapter2.xhtml",
            "<html><body><h1>Chapter Two</h1><p>Gold speaks softly.</p></body></html>",
        )
    return buf.getvalue()


@pytest.mark.asyncio
async def test_epub_to_plain_renders_spine_in_order():
    from app.services.packaging import packaging

    epub = _synthetic_epub()
    text = packaging._epub_to_plain(epub)
    assert text
    assert "Chapter One" in text
    assert "Arise, wallet. Go forth." in text
    assert text.index("Chapter One") < text.index("Chapter Two")


@pytest.mark.asyncio
async def test_text_fetch_renders_epub_only_book(client, db, monkeypatch):
    """A book with no txt anywhere resolves via its EPUB in the reader."""
    from app.models.book import Book, BookStatus
    from app.services.packaging import packaging

    epub = _synthetic_epub()

    # Serve the synthetic EPUB whenever the resolver fetches the book's
    # epub_path, and never hand back a cached copy in tests.
    monkeypatch.setattr(packaging, "_fetch_remote", lambda url, timeout=30.0: epub)
    monkeypatch.setattr(packaging, "_try_local_r2", lambda key: None)

    book = Book(
        title="EPUB Only Sampler",
        author="Test Author",
        source="std_sample",
        source_id="epub-only-sampler",
        category="Classics",
        tags=["Sample"],
        license_type="public_domain",
        status=BookStatus.APPROVED,
        license_verified=True,
        epub_path="https://example.test/epub-only-sampler.epub",
    )
    db.add(book)
    await db.commit()

    r = await client.get(f"/api/v1/books/{book.id}/text")
    assert r.status_code == 200, r.text
    assert "Arise, wallet. Go forth." in r.text
    assert "Chapter Two" in r.text


@pytest.mark.asyncio
async def test_text_still_422_when_no_epub_and_no_txt(client, db, monkeypatch):
    from app.models.book import Book, BookStatus
    from app.services.packaging import packaging

    monkeypatch.setattr(packaging, "_try_local_r2", lambda key: None)

    book = Book(
        title="Nothing Here",
        author="N/A",
        source="std_sample",
        source_id="nothing-here",
        category="Classics",
        tags=[],
        license_type="public_domain",
        status=BookStatus.APPROVED,
        license_verified=True,
    )
    db.add(book)
    await db.commit()

    r = await client.get(f"/api/v1/books/{book.id}/text")
    assert r.status_code == 422
    assert "download the book instead" in r.json()["detail"]

@pytest.mark.asyncio
async def test_withdrawn_book_reports_gone_not_missing(client, db):
    """A withdrawn title must be distinguishable from one that never existed:
    the reader/detail page renders a 'no longer available' state off 410."""
    from app.models.book import Book, BookStatus

    book = Book(
        title="Withdrawn Work", author="A. Author", source="standard_ebooks",
        source_id="a-author/withdrawn-work", status=BookStatus.REJECTED,
        license_type="public_domain", license_verified=True,
    )
    db.add(book)
    await db.commit()

    r = await client.get(f"/api/v1/books/{book.id}")
    assert r.status_code == 410
    assert r.json()["detail"]["code"] == "withdrawn"

    # A genuinely unknown id is still a 404.
    missing = await client.get(f"/api/v1/books/{book.id + 9999}")
    assert missing.status_code == 404
