"""Regression tests for the bundles API.

Covers the bug that made "Featured Bundles" fail to load: nested
relationships were lazy-loaded on an async session, raising MissingGreenlet.
"""
import pytest


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_featured_bundles_loads_with_books(client, seeded):
    """The exact request the homepage makes."""
    r = await client.get("/api/v1/bundles?featured=true&page_size=6")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["total"] == 1
    assert len(data["items"]) == 1

    item = data["items"][0]
    assert item["name"] == "Classic Literature"
    assert item["price_cents"] == 1000
    # Regression: nested books must be eagerly loaded and serialized.
    assert len(item["books"]) == 2
    assert {b["title"] for b in item["books"]} == {"Pride and Prejudice", "Moby Dick"}
    assert all(b["author"] for b in item["books"])


@pytest.mark.asyncio
async def test_bundle_books_are_ordered(client, seeded):
    r = await client.get("/api/v1/bundles?featured=true")
    books = r.json()["items"][0]["books"]
    assert [b["title"] for b in books] == ["Pride and Prejudice", "Moby Dick"]


@pytest.mark.asyncio
async def test_bundle_detail_by_slug(client, seeded):
    r = await client.get("/api/v1/bundles/classic-literature")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["slug"] == "classic-literature"
    assert len(data["books"]) == 2


@pytest.mark.asyncio
async def test_bundle_detail_by_id(client, seeded):
    bundle_id = seeded["bundle"].id
    r = await client.get(f"/api/v1/bundles/{bundle_id}")
    assert r.status_code == 200
    assert r.json()["id"] == bundle_id


@pytest.mark.asyncio
async def test_bundle_detail_missing_returns_404(client):
    r = await client.get("/api/v1/bundles/does-not-exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_huge_numeric_slug_does_not_500(client):
    """Regression: int() overflow on a numeric path segment."""
    r = await client.get(f"/api/v1/bundles/{'9' * 400}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_category_filter(client, seeded):
    hit = await client.get("/api/v1/bundles?category=fiction")
    assert hit.json()["total"] == 1

    miss = await client.get("/api/v1/bundles?category=science")
    assert miss.json()["total"] == 0


@pytest.mark.asyncio
async def test_pagination_metadata(client, seeded):
    r = await client.get("/api/v1/bundles?page=1&page_size=1")
    data = r.json()
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_empty_state_returns_empty_list(client):
    """No bundles seeded: must return an empty list, not an error."""
    r = await client.get("/api/v1/bundles?featured=true")
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}


@pytest.mark.asyncio
async def test_checkout_config_exposes_price(client):
    r = await client.get("/api/v1/checkout/config")
    assert r.status_code == 200
    data = r.json()
    assert data["price_pence"] == 1000
    assert data["currency"] == "gbp"
    assert data["price_display"] == "£10.00"
    # Secrets must never be exposed to the browser.
    assert "stripe_secret_key" not in data
