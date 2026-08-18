"""Tests for the admin book-review workflow.

Covers the access-control fix on GET /books (unapproved material was
enumerable by anyone) and the approve/reject endpoints the review
queue UI depends on.
"""
import pytest
from app.services.security import hash_password


async def _make_admin(db):
    from app.models.user import User
    admin = User(email="admin@example.com", hashed_password=hash_password("pw"),
                 is_admin=True, is_active=True)
    db.add(admin)
    await db.commit()
    return admin


async def _login(client, email="admin@example.com", password="pw"):
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _seed_pending_book(db):
    from app.models.book import Book, BookStatus
    book = Book(title="Suspicious Textbook", author="A. Author", source="doab",
                source_id="xyz-1", license_type="open_access",
                license_url="https://doab.org/doc/xyz-1",
                status=BookStatus.PENDING)
    db.add(book)
    await db.commit()
    return book


@pytest.mark.asyncio
async def test_anonymous_cannot_list_unapproved(client, db):
    await _seed_pending_book(db)
    r = await client.get("/api/v1/books?approved_only=false")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_anonymous_cannot_filter_by_status(client, db):
    await _seed_pending_book(db)
    r = await client.get("/api/v1/books?status=pending")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_public_listing_hides_pending_books(client, db):
    await _seed_pending_book(db)
    r = await client.get("/api/v1/books")
    assert r.status_code == 200
    assert r.json()["total"] == 0


@pytest.mark.asyncio
async def test_admin_can_list_pending(client, db):
    await _make_admin(db)
    await _seed_pending_book(db)
    auth = await _login(client)
    r = await client.get("/api/v1/books?status=pending", headers=auth)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    item = data["items"][0]
    # The fields the review UI relies on must be present.
    assert item["license_type"] == "open_access"
    assert item["license_url"] == "https://doab.org/doc/xyz-1"
    assert item["source"] == "doab"


@pytest.mark.asyncio
async def test_approve_marks_verified_and_public(client, db):
    await _make_admin(db)
    book = await _seed_pending_book(db)
    auth = await _login(client)

    r = await client.post(f"/api/v1/books/{book.id}/approve", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert r.json()["license_verified"] is True

    # Now visible anonymously.
    public = await client.get("/api/v1/books")
    assert public.json()["total"] == 1


@pytest.mark.asyncio
async def test_reject_hides_book(client, db):
    await _make_admin(db)
    book = await _seed_pending_book(db)
    auth = await _login(client)

    r = await client.post(f"/api/v1/books/{book.id}/reject", headers=auth)
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    public = await client.get("/api/v1/books")
    assert public.json()["total"] == 0


@pytest.mark.asyncio
async def test_admin_stats_include_pending_count(client, db):
    await _make_admin(db)
    await _seed_pending_book(db)
    auth = await _login(client)
    r = await client.get("/api/v1/admin/stats", headers=auth)
    assert r.status_code == 200
    assert r.json()["books"]["pending"] == 1
