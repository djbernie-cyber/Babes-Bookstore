"""A reader's collection is theirs, not catalogue stock.

POST /bundles/custom is how you group books you already have. It wrote into
the same `bundles` table the storefront lists, searches, prices and sells
from, with no owner recorded. So every reader's personal grouping became a
globally visible, standard-priced, purchasable product -- and because
PATCH and DELETE both required admin, not even the person who made it could
rename or remove it.

These are the invariants that fix has to hold. Each one is a way the previous
behaviour leaked, so each is pinned rather than assumed:

* creating while signed in produces a personal bundle, not a product;
* creating anonymously still produces the one-off basket checkout needs, or
  the checkout path would lose its input entirely;
* personal bundles stay out of the public listing and out of everyone else's
  view, including admins;
* the owner can rename and delete their own, but cannot reach the fields
  that would turn their collection into stock;
* checkout refuses a personal bundle at the one choke point every provider
  goes through.
"""
import pytest
from app.services.security import hash_password

pytestmark = pytest.mark.asyncio


async def _reader(db, email, is_admin=False):
    from app.models.user import User
    user = User(email=email, hashed_password=hash_password("pw"),
                is_admin=is_admin, is_active=True)
    db.add(user)
    await db.commit()
    return user


async def _login(client, email, password="pw"):
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _books(db, n=3):
    from app.models.book import Book, BookStatus
    out = []
    for i in range(n):
        b = Book(title=f"Owned Book {i}", author="A. Reader", source="gutenberg",
                 source_id=f"own-{i}", license_type="public_domain",
                 status=BookStatus.APPROVED)
        db.add(b)
        out.append(b)
    # commit, not flush: the `client` fixture opens its own session against the
    # same file, so flushed-but-uncommitted rows are invisible to the request
    # and the bundle comes back with silently no books.
    await db.commit()
    return out


async def _custom(client, headers, books, name="My Shelf"):
    # slug and price_cents are required by BundleCreate but then discarded --
    # the handler derives its own slug and forces the standard price. A wart in
    # the request schema, not something these tests should change, so they send
    # the fields the endpoint insists on.
    body = {
        "name": name,
        "slug": name.lower().replace(" ", "-"),
        "price_cents": 1000,
        "book_ids": [b.id for b in books],
    }
    return await client.post("/api/v1/bundles/custom", json=body, headers=headers)


# --- creating ---------------------------------------------------------------

async def test_signed_in_creation_is_personal_not_a_product(client, db):
    await _reader(db, "owner2@example.com")
    headers = await _login(client, "owner2@example.com")
    books = await _books(db)

    r = await _custom(client, headers, books)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_personal"] is True

    from app.models.bundle import Bundle
    from sqlalchemy import select
    row = (await db.execute(select(Bundle))).scalars().one()
    assert row.owner_id is not None, "no owner recorded -- the original defect"
    assert row.bundle_type == "personal"


async def test_anonymous_creation_stays_a_purchasable_one_off(client, db):
    """Checkout's input must keep working: no user, no owner, still a product."""
    books = await _books(db)

    r = await _custom(client, {}, books, name="One-off Basket")
    assert r.status_code == 201, r.text
    assert r.json()["is_personal"] is False

    from app.models.bundle import Bundle
    from sqlalchemy import select
    row = (await db.execute(select(Bundle))).scalars().one()
    assert row.owner_id is None
    assert row.bundle_type == "custom"
    assert row.active is True, "the one-off still has to be checkable out"


# --- visibility -------------------------------------------------------------

async def test_personal_bundles_are_absent_from_the_public_listing(client, db):
    reader = await _reader(db, "owner2@example.com")
    headers = await _login(client, "owner2@example.com")
    books = await _books(db)
    await _custom(client, headers, books)

    r = await client.get("/api/v1/bundles")
    assert r.status_code == 200
    assert r.json()["total"] == 0, \
        "a reader's collection is showing up in the storefront bundle list"
    assert all(not i["is_personal"] for i in r.json()["items"])

    from app.models.bundle import Bundle
    from sqlalchemy import select
    assert (await db.execute(select(Bundle))).scalars().one().owner_id == reader.id


async def test_products_and_personal_coexist_in_the_listing(client, db, seeded):
    """The filter must hide personal bundles without hiding the catalogue."""
    await _reader(db, "owner2@example.com")
    headers = await _login(client, "owner2@example.com")
    await _custom(client, headers, await _books(db))

    r = await client.get("/api/v1/bundles")
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["name"] == "Classic Literature"


async def test_another_reader_cannot_fetch_someone_elses_bundle(client, db):
    await _reader(db, "owner@example.com")
    owner_headers = await _login(client, "owner@example.com")
    made = await _custom(client, owner_headers, await _books(db))
    bundle_id = made.json()["id"]

    await _reader(db, "nosy@example.com")
    nosy = await _login(client, "nosy@example.com")

    r = await client.get(f"/api/v1/bundles/{bundle_id}", headers=nosy)
    assert r.status_code == 404, "another reader can read a private collection"
    assert "not found" in r.json()["detail"].lower(), \
        "should be 404, not 403 -- 403 confirms the bundle exists"


async def test_even_an_admin_cannot_read_another_readers_collection(client, db):
    """The point of 'owned'. Admin reach is how shared stock starts again."""
    await _reader(db, "owner@example.com")
    owner_headers = await _login(client, "owner@example.com")
    made = await _custom(client, owner_headers, await _books(db))
    bundle_id = made.json()["id"]

    await _reader(db, "boss@example.com", is_admin=True)
    boss = await _login(client, "boss@example.com")

    r = await client.get(f"/api/v1/bundles/{bundle_id}", headers=boss)
    assert r.status_code == 404


async def test_the_owner_can_fetch_their_own_by_id_and_by_slug(client, db):
    await _reader(db, "owner@example.com")
    headers = await _login(client, "owner@example.com")
    made = await _custom(client, headers, await _books(db))
    body = made.json()

    by_id = await client.get(f"/api/v1/bundles/{body['id']}", headers=headers)
    assert by_id.status_code == 200
    assert len(by_id.json()["books"]) == 3

    by_slug = await client.get(f"/api/v1/bundles/{body['slug']}", headers=headers)
    assert by_slug.status_code == 200


async def test_mine_returns_only_the_callers_collections(client, db):
    await _reader(db, "one@example.com")
    await _reader(db, "two@example.com")
    h1 = await _login(client, "one@example.com")
    h2 = await _login(client, "two@example.com")

    books = await _books(db, 6)
    a = await _custom(client, h1, books[:3], name="Reader One A")
    b = await _custom(client, h1, books[3:], name="Reader One B")
    await _custom(client, h2, books[:3], name="Reader Two")

    r = await client.get("/api/v1/bundles/mine", headers=h1)
    assert r.status_code == 200, r.text
    mine = r.json()
    assert mine["total"] == 2
    assert {i["name"] for i in mine["items"]} == {"Reader One A", "Reader One B"}
    assert {i["id"] for i in mine["items"]} == {a.json()["id"], b.json()["id"]}
    assert all(i["is_personal"] for i in mine["items"])


async def test_mine_requires_a_token(client, db):
    r = await client.get("/api/v1/bundles/mine")
    assert r.status_code in (401, 403)


# --- editing ----------------------------------------------------------------

async def test_owner_can_rename_their_own_bundle(client, db):
    await _reader(db, "owner@example.com")
    headers = await _login(client, "owner@example.com")
    made = await _custom(client, headers, await _books(db))
    bundle_id = made.json()["id"]

    r = await client.patch(f"/api/v1/bundles/{bundle_id}",
                           json={"name": "Renamed Shelf"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed Shelf"


async def test_another_reader_cannot_rename_it(client, db):
    await _reader(db, "owner@example.com")
    owner = await _login(client, "owner@example.com")
    bundle_id = (await _custom(client, owner, await _books(db))).json()["id"]

    await _reader(db, "nosy@example.com")
    nosy = await _login(client, "nosy@example.com")

    r = await client.patch(f"/api/v1/bundles/{bundle_id}",
                           json={"name": "Mine Now"}, headers=nosy)
    assert r.status_code in (403, 404)


async def test_owner_cannot_price_or_publish_their_own_collection(client, db):
    """The fields that make a product sellable stay out of a reader's hands."""
    await _reader(db, "owner@example.com")
    headers = await _login(client, "owner@example.com")
    bundle_id = (await _custom(client, headers, await _books(db))).json()["id"]

    for field, value in [("price_cents", 0), ("active", False),
                         ("featured", True), ("currency", "usd")]:
        r = await client.patch(f"/api/v1/bundles/{bundle_id}",
                               json={field: value}, headers=headers)
        assert r.status_code == 400, \
            f"owner was allowed to set {field}={value!r} on a personal bundle"


async def test_owner_can_reorder_the_books_in_their_own_bundle(client, db):
    await _reader(db, "owner@example.com")
    headers = await _login(client, "owner@example.com")
    books = await _books(db, 4)
    bundle_id = (await _custom(client, headers, books)).json()["id"]

    reordered = [b.id for b in reversed(books)]
    r = await client.patch(f"/api/v1/bundles/{bundle_id}",
                           json={"book_ids": reordered}, headers=headers)
    assert r.status_code == 200, r.text
    assert [b["id"] for b in r.json()["books"]] == reordered


async def test_owner_can_delete_their_own_bundle(client, db):
    await _reader(db, "owner@example.com")
    headers = await _login(client, "owner@example.com")
    bundle_id = (await _custom(client, headers, await _books(db))).json()["id"]

    r = await client.delete(f"/api/v1/bundles/{bundle_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert (await client.get(f"/api/v1/bundles/{bundle_id}", headers=headers)).status_code == 404


async def test_another_reader_cannot_delete_it(client, db):
    await _reader(db, "owner@example.com")
    owner = await _login(client, "owner@example.com")
    bundle_id = (await _custom(client, owner, await _books(db))).json()["id"]

    await _reader(db, "nosy@example.com")
    nosy = await _login(client, "nosy@example.com")

    r = await client.delete(f"/api/v1/bundles/{bundle_id}", headers=nosy)
    assert r.status_code in (403, 404)
    assert (await client.get(f"/api/v1/bundles/{bundle_id}", headers=owner)).status_code == 200


# --- checkout ---------------------------------------------------------------

@pytest.mark.parametrize("provider", ["stripe", "paypal", "square", "free", "mpesa"])
async def test_no_provider_will_sell_a_personal_bundle(client, db, provider):
    """All seven checkout call sites funnel through one resolver.

    Testing each provider individually would only prove today's five; the
    point is that a *new* provider inherits the refusal.
    """
    await _reader(db, "owner@example.com")
    headers = await _login(client, "owner@example.com")
    made = await _custom(client, headers, await _books(db))
    bundle_id = made.json()["id"]

    payload = {"bundle_id": bundle_id, "email": "owner@example.com"}
    if provider == "mpesa":
        payload["phone"] = "254712345678"
    r = await client.post(f"/api/v1/webhooks/{provider}/checkout", json=payload,
                          headers=headers)
    assert r.status_code in (404, 400), \
        f"{provider} accepted a personal bundle for sale: {r.status_code} {r.text}"


# --- model-level ------------------------------------------------------------

async def test_visible_to_covers_every_combination():
    """The whole visibility rule, with no database and no HTTP.

    async only because the module-level pytestmark is asyncio_mode=strict, and
    adding a per-test marker to the other twenty to keep one of them sync is
    the worse trade.
    """
    from app.models.bundle import Bundle

    class U:
        def __init__(self, id):
            self.id = id

    product = Bundle(owner_id=None)
    assert product.is_personal is False
    assert product.visible_to(None) is True
    assert product.visible_to(U(1)) is True

    mine = Bundle(owner_id=7)
    assert mine.is_personal is True
    assert mine.visible_to(U(7)) is True
    assert mine.visible_to(U(8)) is False
    assert mine.visible_to(None) is False
