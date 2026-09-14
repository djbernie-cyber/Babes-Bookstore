"""Author page slug round-trips.

Covers the bug where the author listing built slugs from the raw Gutenberg
record ("Lytton, Edward Bulwer Lytton, Baron" -> "lytton-edward-...") while
the detail endpoint normalized slugs without stripping punctuation, so every
comma-bearing author returned 404.
"""
import pytest


@pytest.mark.asyncio
async def test_author_list_slug_resolves_on_detail(client, db):
    from app.models.book import Book, BookStatus
    db.add_all([
        Book(title="One", author="Lytton, Edward Bulwer Lytton, Baron",
             source="gutenberg", source_id="1", license_type="public_domain",
             status=BookStatus.APPROVED, license_verified=True),
        Book(title="Two", author="Equiano, Olaudah",
             source="gutenberg", source_id="2", license_type="public_domain",
             status=BookStatus.APPROVED, license_verified=True),
        Book(title="Three", author="Plaatje, Sol. T. (Solomon Tshekisho)",
             source="gutenberg", source_id="3", license_type="public_domain",
             status=BookStatus.APPROVED, license_verified=True),
    ])
    await db.commit()

    r = await client.get("/api/v1/authors?page_size=100")
    assert r.status_code == 200, r.text
    by_name = {a["name"]: a for a in r.json()["items"]
               if a["name"] in ("Edward Bulwer Lytton, Baron", "Olaudah Equiano", "Sol T. Plaatje")}
    assert by_name, r.json()["items"]

    for name, detail in by_name.items():
        d = await client.get(f"/api/v1/authors/{detail['slug']}")
        assert d.status_code == 200, (name, detail["slug"], d.text)
        assert d.json()["total"] >= 1


@pytest.mark.asyncio
async def test_author_list_uses_display_name(client, db):
    from app.models.book import Book, BookStatus
    db.add(Book(title="X", author="Douglass, Frederick (Frederick Bailey)",
                source="gutenberg", source_id="4", license_type="public_domain",
                status=BookStatus.APPROVED, license_verified=True))
    await db.commit()
    r = await client.get("/api/v1/authors?q=douglass")
    items = r.json()["items"]
    assert items, "expected a Douglass entry"
    assert items[0]["name"] == "Frederick Douglass"
    d = await client.get(f"/api/v1/authors/{items[0]['slug']}")
    assert d.status_code == 200


@pytest.mark.asyncio
async def test_unknown_author_slug_is_404(client):
    r = await client.get("/api/v1/authors/no-such-person-anywhere")
    assert r.status_code == 404