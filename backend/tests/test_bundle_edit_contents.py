"""Editing a bundle's contents through the admin picker.

The admin bundle form used to take hand-typed numeric IDs and had no way to
change an existing bundle's books at all. The picker now submits `book_ids` to
the same PATCH endpoint, which makes that endpoint's replace-the-whole-list
behaviour load-bearing for a routine admin task, so it gets its own tests:
order must follow the submitted array, removed books must actually disappear
rather than linger as orphans, and a non-admin must not be able to reach it.
"""
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api.v1.auth import create_access_token
from app.models.book import Book, BookStatus
from app.models.bundle import Bundle, BundleBook
from app.models.user import User


async def _admin_token(db):
    u = User(email="picker-admin@example.com", hashed_password="x", is_admin=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return create_access_token(u.id)


@pytest_asyncio.fixture
async def bundle(db):
    """A bundle holding two of three books, in a deliberate order."""
    ids = {}
    for n, title in enumerate(["Alpha", "Beta", "Gamma"]):
        b = Book(
            title=title, author=f"Author {n}", status=BookStatus.APPROVED,
            asset_verified=True, source="gutenberg", source_id=f"pick-{n}",
            license_type="public_domain", tags=[], category="Classics",
        )
        db.add(b)
        ids[title] = b
    await db.flush()
    bun = Bundle(name="Picker Test", slug="picker-test", price_cents=500, active=True)
    db.add(bun)
    await db.flush()
    # Gamma is deliberately absent: it is the "add it" case.
    for i, title in enumerate(["Alpha", "Beta"]):
        db.add(BundleBook(bundle_id=bun.id, book_id=ids[title].id, sort_order=i))
    await db.commit()
    return bun, {t: b.id for t, b in ids.items()}


@pytest.mark.asyncio
async def test_patch_replaces_contents_in_submitted_order(client, db, bundle):
    """Order is the admin's pick order, not database row order."""
    bun, ids = bundle
    token = await _admin_token(db)

    r = await client.patch(
        f"/api/v1/bundles/{bun.id}",
        json={"book_ids": [ids["Gamma"], ids["Alpha"], ids["Beta"]]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert [b["title"] for b in r.json()["books"]] == ["Gamma", "Alpha", "Beta"]


@pytest.mark.asyncio
async def test_patch_drops_books_that_were_unticked(client, db, bundle):
    """A removed book must vanish, not survive as an invisible BundleBook."""
    bun, ids = bundle
    token = await _admin_token(db)

    r = await client.patch(
        f"/api/v1/bundles/{bun.id}",
        json={"book_ids": [ids["Gamma"]]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert [b["title"] for b in r.json()["books"]] == ["Gamma"]

    rows = (await db.execute(
        select(BundleBook).where(BundleBook.bundle_id == bun.id)
    )).scalars().all()
    assert [row.book_id for row in rows] == [ids["Gamma"]]


@pytest.mark.asyncio
async def test_patch_does_not_duplicate_on_repeated_save(client, db, bundle):
    """Saving the same list twice must not append a second copy of each book."""
    bun, ids = bundle
    token = await _admin_token(db)
    payload = {"book_ids": [ids["Beta"], ids["Alpha"]]}

    for _ in range(2):
        r = await client.patch(f"/api/v1/bundles/{bun.id}", json=payload,
                               headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text

    rows = (await db.execute(
        select(BundleBook).where(BundleBook.bundle_id == bun.id)
    )).scalars().all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_patch_leaves_name_and_price_alone_when_only_contents_change(client, db, bundle):
    """The picker sends book_ids only; metadata must survive untouched."""
    bun, ids = bundle
    token = await _admin_token(db)

    r = await client.patch(
        f"/api/v1/bundles/{bun.id}",
        json={"book_ids": [ids["Gamma"]]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Picker Test"
    assert body["price_cents"] == 500
    assert body["slug"] == "picker-test"


@pytest.mark.asyncio
async def test_patch_ignores_unknown_book_ids_rather_than_500ing(client, db, bundle):
    """A stale id in the picker must not take the whole save down."""
    bun, ids = bundle
    token = await _admin_token(db)

    r = await client.patch(
        f"/api/v1/bundles/{bun.id}",
        json={"book_ids": [ids["Gamma"], 999_999_999]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert [b["title"] for b in r.json()["books"]] == ["Gamma"]


@pytest.mark.asyncio
async def test_patch_requires_admin(client, db, bundle):
    """Editing bundle contents is an admin capability, not a public one."""
    bun, ids = bundle

    anon = await client.patch(f"/api/v1/bundles/{bun.id}",
                              json={"book_ids": [ids["Gamma"]]})
    assert anon.status_code in (401, 403)

    reg = await client.post("/api/v1/auth/register", json={
        "email": "picker-reader@example.com", "password": "s3cret-pass", "name": "Reader",
    })
    token = reg.json()["access_token"]
    as_reader = await client.patch(
        f"/api/v1/bundles/{bun.id}", json={"book_ids": [ids["Gamma"]]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert as_reader.status_code == 403

    # And the rejection must not have mutated anything.
    books = (await client.get(f"/api/v1/bundles/{bun.id}")).json()["books"]
    assert [b["title"] for b in books] == ["Alpha", "Beta"]
