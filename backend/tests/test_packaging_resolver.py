"""Packaging resolver tests: books harvested under sibling source buckets
(suppressed, military, …) must still download and read via Gutenberg."""
import pytest


@pytest.mark.asyncio
async def test_gutenberg_url_bucket_downloads(client, db, monkeypatch):
    """A 'suppressed'-sourced book with a gutenberg URL resolves a file."""
    from app.models.book import Book, BookStatus
    from app.services.packaging import packaging

    monkeypatch.setattr(packaging, "_try_local_r2", lambda key: None)
    monkeypatch.setattr(packaging, "_fetch_remote", lambda url, timeout=30.0: b"P" * 600)

    book = Book(
        title="Suppressed Classic",
        author="Someone",
        source="suppressed",
        source_id="63132",
        category="Classics",
        tags=["Suppressed Classics"],
        license_type="public_domain",
        status=BookStatus.APPROVED,
        license_verified=True,
        source_url="https://www.gutenberg.org/ebooks/63132",
    )
    db.add(book)
    await db.commit()

    content, ext = packaging._resolve_book_content(book)
    assert content == b"P" * 600
    assert ext == "epub" or ext == "txt"


@pytest.mark.asyncio
async def test_gutenberg_url_bucket_reader_text(client, db, monkeypatch):
    """Reader text for the same bucket falls back to the Gutenberg mirror."""
    from app.models.book import Book, BookStatus
    from app.services.packaging import packaging

    monkeypatch.setattr(packaging, "_try_local_r2", lambda key: None)
    monkeypatch.setattr(packaging, "_fetch_remote", lambda url, timeout=30.0: b"*** START OF THE PROJECT GUTENBERG EBOOK ***\n\nChapter one\n\nFull text here.\n" + b"P" * 600)

    book = Book(
        title="Suppressed Classic",
        author="Someone",
        source="suppressed",
        source_id="63132",
        category="Classics",
        tags=["Suppressed Classics"],
        license_type="public_domain",
        status=BookStatus.APPROVED,
        license_verified=True,
        source_url="https://www.gutenberg.org/ebooks/63132",
    )
    db.add(book)
    await db.commit()

    text = await packaging._resolve_book_text(book)
    assert text
    assert "Full text here." in text


@pytest.mark.asyncio
async def test_epub_only_book_downloads(client, db, monkeypatch):
    """A standardebooks-style record with just an epub_path downloads the epub."""
    from app.models.book import Book, BookStatus
    from app.services.packaging import packaging

    monkeypatch.setattr(packaging, "_try_local_r2", lambda key: None)
    monkeypatch.setattr(packaging, "_fetch_remote", lambda url, timeout=30.0: b"PK" + b"E" * 600)

    book = Book(
        title="Epub Only",
        author="Test",
        source="standard_ebooks",
        source_id="slug",
        category="Classics",
        tags=[],
        license_type="public_domain",
        status=BookStatus.APPROVED,
        license_verified=True,
        epub_path="https://standardebooks.org/ebooks/slug/downloads/slug.epub",
    )
    db.add(book)
    await db.commit()

    content, ext = packaging._resolve_book_content(book)
    assert content
    assert ext == "epub"


@pytest.mark.asyncio
async def test_standardebooks_slug_derives_epub_runtime(client, db, monkeypatch):
    """A standardebooks record with only a landing URL still downloads — the
    resolver derives the download path from the slug at runtime."""
    from app.models.book import Book, BookStatus
    from app.services.packaging import packaging

    monkeypatch.setattr(packaging, "_try_local_r2", lambda key: None)
    monkeypatch.setattr(packaging, "_fetch_remote", lambda url, timeout=30.0: b"PK" + b"E" * 600)

    book = Book(
        title="Runtime Derived",
        author="Test",
        source="standard_ebooks",
        source_id="runtime-derived",
        category="Classics",
        tags=[],
        license_type="public_domain",
        status=BookStatus.APPROVED,
        license_verified=True,
        source_url="https://standardebooks.org/ebooks/g-k-chesterton/the-man-who-was-thursday",
    )
    db.add(book)
    await db.commit()

    content, ext = packaging._resolve_book_content(book)
    assert content
    assert ext == "epub"


def test_standardebooks_derivation_uses_underscore():
    """The SE download path joins collection and work with an underscore, not a
    dash — a dash slug 404s and makes the whole download look broken."""
    from app.services.packaging import packaging

    url = packaging._standard_ebooks_epub(
        type("B", (), {"source_url": "https://standardebooks.org/ebooks/h-g-wells/the-time-machine"})()
    )
    assert url == ("https://standardebooks.org/ebooks/h-g-wells/the-time-machine"
                   "/downloads/h-g-wells_the-time-machine.epub")