"""Tokenised search: partial/drifted queries resolve to real works."""
import pytest
from sqlalchemy import select

from app.models.book import Book, BookStatus

BOOKS = [
    dict(title="Things Fall Apart", author="Chinua Achebe", description="The Igbo village tragedy."),
    dict(title="Mhudi", author="Sol T. Plaatje", description="A Setswana romance of war."),
    dict(title="The Story of an African Farm", author="Olive Schreiner", description="Life on the Karoo."),
    dict(title="Narrative of the Life of Frederick Douglass", author="Frederick Douglass", description="An American slave narrative."),
    dict(title="Pride and Prejudice", author="Jane Austen", description="A novel about manners and marriage."),
]


async def _seed(db):
    for i, b in enumerate(BOOKS):
        db.add(Book(
            title=b["title"], author=b["author"], description=b["description"],
            status=BookStatus.APPROVED, license_verified=True, source="gutenberg",
            source_id=str(i), license_type="public_domain",
            tags=[], category="Classics",
        ))
    await db.commit()


@pytest.mark.asyncio
async def test_tokenized_query_finds_partials(client, db):
    """'sol pla' must resolve to Sol T. Plaatje's Mhudi."""
    await _seed(db)
    r = await client.get("/api/v1/search", params={"q": "sol pla"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert any("Mhudi" in b["title"] for b in items), items


@pytest.mark.asyncio
async def test_tokenized_order_requires_every_token(client, db):
    await _seed(db)
    r = await client.get("/api/v1/search", params={"q": "olive african"})
    items = r.json()["items"]
    titles = [b["title"] for b in items]
    assert "The Story of an African Farm" in titles
    # Every token must appear somewhere; "olive" rules the rest out.
    assert all("Olive" in b["author"] or "olive" in b["description"].lower() or "olive" in b["title"].lower() for b in items)


@pytest.mark.asyncio
async def test_books_endpoint_tokenized(client, db):
    await _seed(db)
    r = await client.get("/api/v1/books", params={"search": "narrative fred"})
    items = r.json()["items"]
    assert r.json()["total"] >= 1
    assert any("Douglass" in b["author"] for b in items)
    # Non-matching tokens drop results entirely.
    r2 = await client.get("/api/v1/books", params={"search": "olive plaatje"})
    assert r2.json()["total"] == 0


@pytest.mark.asyncio
async def test_authors_endpoint_tokenized(client, db):
    await _seed(db)
    r = await client.get("/api/v1/authors", params={"q": "sol pla"})
    items = r.json()["items"]
    assert any("Plaatje" in a["name"] for a in items)


@pytest.mark.asyncio
async def test_rank_exact_title_first(client, db):
    await _seed(db)
    r = await client.get("/api/v1/search", params={"q": "mhudi"})
    items = r.json()["items"]
    assert items and items[0]["title"] == "Mhudi"


@pytest.mark.asyncio
async def test_single_token_returning_result(client, db):
    await _seed(db)
    r = await client.get("/api/v1/books", params={"search": "douglass"})
    assert r.json()["total"] >= 1