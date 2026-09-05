"""Tests for the user-facing reviews and wishlist features."""
import pytest
from app.services.security import hash_password


async def _make_user(db, email="user@example.com", pw="pw"):
    from app.models.user import User
    u = User(email=email, hashed_password=hash_password(pw), is_active=True)
    db.add(u)
    await db.commit()
    return u


async def _make_book(db, title="Pride and Prejudice", source_id="1342"):
    from app.models.book import Book, BookStatus
    b = Book(title=title, author="Jane Austen", source="gutenberg",
             source_id=source_id, license_type="public_domain",
             status=BookStatus.APPROVED)
    db.add(b)
    await db.commit()
    return b


async def _login(client, email="user@example.com", pw="pw"):
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_anonymous_cannot_review(client, db):
    book = await _make_book(db)
    r = await client.post(f"/api/v1/books/{book.id}/reviews",
                          json={"rating": 5, "title": "t", "body": "b"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_user_can_post_and_public_list_reviews(client, db):
    await _make_user(db)
    book = await _make_book(db)
    auth = await _login(client)

    r = await client.post(f"/api/v1/books/{book.id}/reviews",
                          headers=auth,
                          json={"rating": 5, "title": "Loved it", "body": "A triumph."})
    assert r.status_code == 200, r.text

    public = await client.get(f"/api/v1/books/{book.id}/reviews")
    assert public.status_code == 200
    data = public.json()
    assert data["summary"]["count"] == 1
    assert data["summary"]["average"] == 5.0
    assert data["items"][0]["title"] == "Loved it"


@pytest.mark.asyncio
async def test_one_review_per_user_per_book(client, db):
    await _make_user(db)
    book = await _make_book(db)
    auth = await _login(client)
    await client.post(f"/api/v1/books/{book.id}/reviews", headers=auth,
                      json={"rating": 3, "title": "first", "body": "one"})
    r = await client.post(f"/api/v1/books/{book.id}/reviews", headers=auth,
                          json={"rating": 5, "title": "second", "body": "two"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_user_can_delete_own_review(client, db):
    await _make_user(db)
    book = await _make_book(db)
    auth = await _login(client)
    await client.post(f"/api/v1/books/{book.id}/reviews", headers=auth,
                      json={"rating": 4, "title": "t", "body": "b"})
    r = await client.delete(f"/api/v1/books/{book.id}/reviews/mine", headers=auth)
    assert r.status_code == 200
    public = await client.get(f"/api/v1/books/{book.id}/reviews")
    assert public.json()["summary"]["count"] == 0


@pytest.mark.asyncio
async def test_user_can_update_own_review(client, db):
    await _make_user(db)
    book = await _make_book(db)
    auth = await _login(client)
    await client.post(f"/api/v1/books/{book.id}/reviews", headers=auth,
                      json={"rating": 2, "title": "t", "body": "b"})
    r = await client.patch(f"/api/v1/books/{book.id}/reviews/mine", headers=auth,
                           json={"rating": 5, "title": "updated", "body": "better"})
    assert r.status_code == 200
    assert r.json()["rating"] == 5


@pytest.mark.asyncio
async def test_wishlist_add_list_remove(client, db):
    await _make_user(db)
    book = await _make_book(db)
    auth = await _login(client)

    add = await client.post(f"/api/v1/wishlist/{book.id}", headers=auth)
    assert add.status_code == 200
    assert add.json()["wishlisted"] is True

    lst = await client.get("/api/v1/wishlist", headers=auth)
    assert lst.status_code == 200
    assert lst.json()["total"] == 1
    assert lst.json()["items"][0]["id"] == book.id

    st = await client.get(f"/api/v1/wishlist/status/{book.id}", headers=auth)
    assert st.json()["wishlisted"] is True

    rem = await client.delete(f"/api/v1/wishlist/{book.id}", headers=auth)
    assert rem.status_code == 200
    assert rem.json()["removed"] is True

    st2 = await client.get(f"/api/v1/wishlist/status/{book.id}", headers=auth)
    assert st2.json()["wishlisted"] is False


@pytest.mark.asyncio
async def test_wishlist_requires_auth(client, db):
    book = await _make_book(db)
    r = await client.post(f"/api/v1/wishlist/{book.id}")
    assert r.status_code == 401
