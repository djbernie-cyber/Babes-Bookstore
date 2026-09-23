"""Tests for the personalized home feed, strict-auth dependency, and the
admin licence gate on mass approval."""
import pytest
from app.services.security import hash_password


async def _make_user(db, email="home@example.com", pw="pw", admin=False):
    from app.models.user import User
    u = User(email=email, hashed_password=hash_password(pw), is_active=True,
             is_admin=admin, name="Test Reader")
    db.add(u)
    await db.commit()
    return u


async def _make_book(db, title, tags=None, category="Classics", source_id=None, verified=True, pending=False):
    from app.models.book import Book, BookStatus
    status = BookStatus.PENDING if pending or not verified else BookStatus.APPROVED
    b = Book(title=title, author="Someone",
             source="gutenberg", source_id=source_id or f"id-{title}",
             category=category, tags=tags or [],
             license_type="public_domain",
             status=status,
             license_verified=verified)
    db.add(b)
    await db.commit()
    return b


async def _login(client, email="home@example.com", pw="pw"):
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_anonymous_feed_is_curated_rows(client, db):
    await _make_book(db, "Suppress Me", tags=["Suppressed Classics"], source_id="s1")
    await _make_book(db, "African Classic", tags=["African Literature"], source_id="s2")
    await _make_book(db, "Revolution X", tags=["Revolutionary"], source_id="s3")
    await _make_book(db, "Plain Classic", category="Classics", source_id="s4")

    r = await client.get("/api/v1/home/feed")
    assert r.status_code == 200, r.text
    keys = [s["key"] for s in r.json()["sections"]]
    assert "start-here" in keys          # anonymous tease row
    assert "suppressed" in keys
    assert "african" in keys
    assert "revolutionary" in keys
    assert "new-arrivals" in keys
    assert "continue" not in keys
    assert "for-you" not in keys
    assert r.json()["user"] == {"name": None}


@pytest.mark.asyncio
async def test_signed_in_feed_has_continue_and_for_you(client, db):
    from app.models.library import Shelf, ShelfItem, ReadingProgress
    from app.models.review import Review
    u = await _make_user(db)
    token = await _login(client)

    shelved = await _make_book(db, "Shelved Banned", tags=["Suppressed Classics"], source_id="f1")
    candidate = await _make_book(db, "Also Banned", tags=["Suppressed Classics"], source_id="f2")
    liked = await _make_book(db, "Liked African", tags=["African Literature"], source_id="f3")
    in_progress = await _make_book(db, "Half Read", tags=["Suppressed Classics"], source_id="f4")

    shelf = Shelf(user_id=u.id, name="Saved", is_default=True)
    db.add(shelf)
    await db.commit()
    db.add(ShelfItem(shelf_id=shelf.id, book_id=shelved.id))
    db.add(ReadingProgress(user_id=u.id, book_id=in_progress.id, percent=0.5, position="c1:p:2"))
    db.add(Review(user_id=u.id, book_id=liked.id, rating=5, title="great", body="loved it"))
    await db.commit()

    r = await client.get("/api/v1/home/feed", headers=_h(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["name"] is not None
    keys = [s["key"] for s in body["sections"]]
    assert "continue" in keys
    assert "for-you" in keys

    cont = next(s for s in body["sections"] if s["key"] == "continue")
    assert [b["id"] for b in cont["items"]] == [in_progress.id]
    assert cont["items"][0]["percent"] == 0.5

    fyu = next(s for s in body["sections"] if s["key"] == "for-you")
    ids = [b["id"] for b in fyu["items"]]
    # Candidate matches the top taste tag; already-touched books never repeat.
    assert candidate.id in ids
    assert shelved.id not in ids and in_progress.id not in ids and liked.id not in ids


@pytest.mark.asyncio
async def test_library_requires_auth_401(client, db):
    r = await client.get("/api/v1/library")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_prefs_still_anonymous_friendly(client, db):
    r = await client.get("/api/v1/library/prefs")
    assert r.status_code == 200
    assert r.json()["anonymous"] is True


@pytest.mark.asyncio
async def test_bulk_approve_gate_skips_unverified(client, db):
    from app.models.book import Book, BookStatus
    await _make_user(db, email="admin-home@example.com", admin=True)
    token = await _login(client, email="admin-home@example.com")
    ok = await _make_book(db, "Verified Book", source_id="v1", verified=True)
    ko = await _make_book(db, "Unverified Book", source_id="v2", verified=False)

    r = await client.post("/api/v1/admin/books/bulk",
                          json={"action": "approve", "book_ids": [ok.id, ko.id]},
                          headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["affected"] == 1
    assert r.json()["skipped_unverified"] == 1
    await db.refresh(ok)
    await db.refresh(ko)
    assert ok.status == BookStatus.APPROVED
    assert ko.status != BookStatus.APPROVED


@pytest.mark.asyncio
async def test_approve_all_only_licence_verified(client, db):
    from app.models.book import Book, BookStatus
    await _make_user(db, email="admin-home2@example.com", admin=True)
    token = await _login(client, email="admin-home2@example.com")
    ok = await _make_book(db, "Good", source_id="g1", verified=True, pending=True)
    ko = await _make_book(db, "Bad", source_id="g2", verified=False)

    r = await client.post("/api/v1/admin/books/approve-all", headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["affected"] == 1
    assert r.json()["still_pending_unverified"] == 1
    await db.refresh(ok)
    await db.refresh(ko)
    assert ok.status == BookStatus.APPROVED
    assert ko.status == BookStatus.PENDING