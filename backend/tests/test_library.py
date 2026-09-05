"""Tests for the user library API: shelves, reading progress, prefs."""
import pytest
from app.services.security import hash_password


async def _make_user(db, email="library@example.com", pw="pw"):
    from app.models.user import User
    u = User(email=email, hashed_password=hash_password(pw), is_active=True)
    db.add(u)
    await db.commit()
    return u


async def _make_book(db, title="Sula", author="Toni Morrison", source_id="x1"):
    from app.models.book import Book, BookStatus
    b = Book(title=title, author=author, source="gutenberg", source_id=source_id,
             license_type="public_domain", status=BookStatus.APPROVED,
             license_verified=True)
    db.add(b)
    await db.commit()
    return b


async def _login(client, email="library@example.com", pw="pw"):
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json().get("access_token") or r.json().get("token")


def _h(token):
    return {"Authorization": f"Bearer {token}"}


async def _seed_user_and_book(client, db):
    from app.models.book import Book, BookStatus
    u = await _make_user(db)
    b = await _make_book(db)
    token = await _login(client)
    return u, b, token


@pytest.mark.asyncio
async def test_default_shelf_auto_created(client, db):
    _, b, token = await _seed_user_and_book(client, db)
    r = await client.post(f"/api/v1/library/{await _shelf_lookup(client, token)}/books/{b.id}", headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["added"] is True


async def _shelf_lookup(client, token):
    r = await client.get("/api/v1/library", headers=_h(token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items, "no shelves returned"
    return items[0]["id"]


@pytest.mark.asyncio
async def test_create_and_list_shelves(client, db):
    _, _, token = await _seed_user_and_book(client, db)
    r = await client.post("/api/v1/library", json={"name": "Reading Now"}, headers=_h(token))
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    r2 = await client.get("/api/v1/library", headers=_h(token))
    names = [s["name"] for s in r2.json()["items"]]
    assert "Reading Now" in names


@pytest.mark.asyncio
async def test_shelf_rename_and_delete(client, db):
    _, b, token = await _seed_user_and_book(client, db)
    r = await client.post("/api/v1/library", json={"name": "Temp"}, headers=_h(token))
    sid = r.json()["id"]
    r2 = await client.patch(f"/api/v1/library/{sid}", json={"name": "Finished"}, headers=_h(token))
    assert r2.status_code == 200
    assert r2.json()["name"] == "Finished"
    r3 = await client.delete(f"/api/v1/library/{sid}", headers=_h(token))
    assert r3.status_code == 200


@pytest.mark.asyncio
async def test_add_remove_and_list_shelf_books(client, db):
    _, b, token = await _seed_user_and_book(client, db)
    sid = await _shelf_lookup(client, token)
    await client.post(f"/api/v1/library/{sid}/books/{b.id}", headers=_h(token))
    r = await client.get(f"/api/v1/library/{sid}/books", headers=_h(token))
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["id"] == b.id
    r2 = await client.delete(f"/api/v1/library/{sid}/books/{b.id}", headers=_h(token))
    assert r2.json()["removed"] is True
    r3 = await client.get(f"/api/v1/library/{sid}/books", headers=_h(token))
    assert r3.json()["total"] == 0


@pytest.mark.asyncio
async def test_save_and_get_reading_progress(client, db):
    _, b, token = await _seed_user_and_book(client, db)
    r = await client.put(
        f"/api/v1/library/progress/{b.id}",
        json={"percent": 0.42, "position": "para-123"},
        headers=_h(token),
    )
    assert r.status_code == 200, r.text
    r2 = await client.get(f"/api/v1/library/progress/{b.id}", headers=_h(token))
    data = r2.json()
    assert data["progressed"] is True
    assert abs(data["percent"] - 0.42) < 0.001
    assert data["position"] == "para-123"


@pytest.mark.asyncio
async def test_continue_reading_returns_in_progress(client, db):
    _, b, token = await _seed_user_and_book(client, db)
    await client.put(f"/api/v1/library/progress/{b.id}",
                     json={"percent": 0.5}, headers=_h(token))
    r = await client.get("/api/v1/library/continue-reading", headers=_h(token))
    assert r.status_code == 200
    assert r.json()["items"][0]["percent_label"] in ("50%", "50%")


@pytest.mark.asyncio
async def test_prefs_save_and_get(client, db):
    _, _, token = await _seed_user_and_book(client, db)
    r = await client.put("/api/v1/library/prefs",
                         json={"theme": "dark", "reader_font_size": "xl"},
                         headers=_h(token))
    assert r.status_code == 200
    r2 = await client.get("/api/v1/library/prefs", headers=_h(token))
    assert r2.json()["theme"] == "dark"
    assert r2.json()["reader_font_size"] == "xl"
    # sanity: invalid theme rejected
    r3 = await client.put("/api/v1/library/prefs", json={"theme": "neon"}, headers=_h(token))
    assert r3.status_code == 422


@pytest.mark.asyncio
async def test_library_summary_counts(client, db):
    _, b, token = await _seed_user_and_book(client, db)
    sid = await _shelf_lookup(client, token)
    await client.post(f"/api/v1/library/{sid}/books/{b.id}", headers=_h(token))
    r = await client.get("/api/v1/library/summary", headers=_h(token))
    assert r.status_code == 200
    data = r.json()
    assert data["total_saved"] == 1
    assert data["catalogue_total"] >= 1


@pytest.mark.asyncio
async def test_library_requires_auth(client, db):
    r = await client.get("/api/v1/library")
    assert r.status_code == 401

@pytest.mark.asyncio
async def test_my_reviews_lists_users_own_reviews(client, db):
    from app.models.review import Review
    _, b, token = await _seed_user_and_book(client, db)
    r = await client.post(f"/api/v1/books/{b.id}/reviews",
                          json={"rating": 5, "title": "Great", "body": "Loved it"},
                          headers=_h(token))
    assert r.status_code == 200, r.text
    r2 = await client.get("/api/v1/library/my-reviews", headers=_h(token))
    assert r2.status_code == 200
    assert r2.json()["total"] == 1
    assert r2.json()["items"][0]["rating"] == 5
    assert r2.json()["items"][0]["book"]["id"] == b.id
