"""Discoverable is not the same as sellable.

The catalogue used to hide any book whose licence had not been confirmed, on
every read path at once. That made the catalogue look censored: a title the
curator had approved was simply absent, and a reader asking whether a book
existed got silence instead of an answer.

The split:

* approved + unconfirmed licence -> LISTED everywhere (catalogue, search,
  categories, authors, home feed), flagged so the UI can say why there is no
  download button.
* unapproved, or unconfirmed licence -> still NOT deliverable. Download, the
  plain-text reader, and the purchased library all refuse.

Both halves are asserted here, because the failure that matters is shipping
the first without the second.
"""
import pytest

from app.models.book import Book, BookStatus

CATALOGUE = "/api/v1/books"
SEARCH = "/api/v1/search"
CATEGORIES = "/api/v1/categories"
AUTHORS = "/api/v1/authors"


async def _add(db, title, author, *, status=BookStatus.APPROVED, verified=True,
               category="Classics", n=0):
    b = Book(
        title=title, author=author, status=status, asset_verified=verified,
        source="test", source_id=f"vis-{n}-{title}", license_type="public_domain",
        tags=[], category=category, description="A book.",
    )
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return b


# ── The relaxed half: an approved but unconfirmed title is findable ──────────

@pytest.mark.asyncio
async def test_unconfirmed_book_appears_in_the_catalogue(client, db):
    await _add(db, "Half Verified Classic", "Some Author", verified=False)
    items = (await client.get(CATALOGUE)).json()["items"]
    assert [b["title"] for b in items] == ["Half Verified Classic"]


@pytest.mark.asyncio
async def test_unconfirmed_book_is_searchable(client, db):
    await _add(db, "Findable Unconfirmed", "Some Author", verified=False)
    items = (await client.get(SEARCH, params={"q": "findable"})).json()["items"]
    assert any(b["title"] == "Findable Unconfirmed" for b in items), \
        "an approved title must be findable even before its licence is confirmed"


@pytest.mark.asyncio
async def test_unconfirmed_book_is_listed_in_categories(client, db):
    await _add(db, "Category Visible", "Some Author", verified=False,
               category="African Literature")
    cats = (await client.get(CATEGORIES)).json()
    row = next((c for c in cats if c["name"] == "African Literature"), None)
    assert row is not None, "category vanishes because its only book is unconfirmed"
    assert row["count"] >= 1
    assert row["slug"] == "african-literature"


@pytest.mark.asyncio
async def test_unconfirmed_book_appears_under_its_author(client, db):
    await _add(db, "Author Visible", "Nnamdi Azikiwe", verified=False)

    listed = (await client.get(AUTHORS)).json()["items"]
    assert any("Nnamdi Azikiwe" in (a.get("name") or "") for a in listed), \
        "an author disappears from the index because one of their books is unconfirmed"

    detail = (await client.get(f"{AUTHORS}/nnamdi-azikiwe")).json()["items"]
    assert any(b["title"] == "Author Visible" for b in detail)


@pytest.mark.asyncio
async def test_catalogue_tells_the_client_the_licence_is_unconfirmed(client, db):
    """The UI cannot be honest about a file it cannot offer without this flag."""
    await _add(db, "Flagged Book", "Some Author", verified=False)
    item = (await client.get(CATALOGUE)).json()["items"][0]
    assert "asset_verified" in item
    assert item["asset_verified"] is False


# ── The half that does not move: delivery stays gated ──────────────────────

@pytest.mark.asyncio
async def test_unconfirmed_book_is_not_downloadable(client, db):
    b = await _add(db, "No Download Yet", "Some Author", verified=False)
    r = await client.get(f"{CATALOGUE}/{b.id}/download")
    assert r.status_code == 403
    assert "verified" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unconfirmed_book_is_not_readable(client, db):
    b = await _add(db, "No Read Yet", "Some Author", verified=False)
    r = await client.get(f"{CATALOGUE}/{b.id}/text")
    assert r.status_code == 403
    assert "verified" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unapproved_book_is_nowhere_at_all(client, db):
    """Relaxing the licence gate must not relax the editorial gate."""
    await _add(db, "Still Pending", "Some Author", status=BookStatus.PENDING,
               verified=False)
    assert (await client.get(CATALOGUE)).json()["items"] == []
    assert (await client.get(SEARCH, params={"q": "pending"})).json()["items"] == []


@pytest.mark.asyncio
async def test_confirmed_book_is_still_fully_available(client, db):
    """The common case must be untouched by any of this."""
    b = await _add(db, "Fully Cleared", "Some Author", verified=True)
    assert b.id in [x["id"] for x in (await client.get(CATALOGUE)).json()["items"]]
    # Delivery still refuses, but for the honest reason: no source file here.
    r = await client.get(f"{CATALOGUE}/{b.id}/download")
    assert r.status_code in (403, 502), r.text
    assert "verified" not in r.json().get("detail", "").lower()
