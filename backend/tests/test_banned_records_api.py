"""/api/v1/banned/records: the archive endpoint behind the suppression pages.

This endpoint is the only thing that makes the archive exist. When the African
suppression records were seeded but the archive rendered nothing, the cause was
a live API with no archive-only rows -- and nothing in the suite would have
noticed either way, because this endpoint had no tests at all.

The behaviour worth pinning is the outer join: a record for a work we do not
carry (still in copyright) must still be listed, with `book: null` and the
work identified by work_title/work_author. That is the whole point of the
archive. A record pointing at a book that is not approved must NOT be listed,
or the page would link to something a reader cannot open.
"""
import pytest

from app.models.book import Book, BookStatus
from app.models.censorship import CensorshipRecord, CensorshipStatus

ENDPOINT = "/api/v1/banned/records"


def _book(db, title, author, status=BookStatus.APPROVED, verified=True, n=0):
    b = Book(
        title=title, author=author, status=status, license_verified=verified,
        source="gutenberg", source_id=f"ban-{n}", license_type="public_domain",
        tags=[], category="Classics",
    )
    db.add(b)
    return b


def _record(db, work_title, work_author, country="KE", status=CensorshipStatus.BANNED,
            verified=True, book=None):
    db.add(CensorshipRecord(
        book_id=book.id if book is not None else None,
        work_title=work_title, work_author=work_author,
        country_code=country, country_name={"KE": "Kenya"}.get(country),
        status=status, ban_reason="Suppressed under the colonial-era publications ban.",
        banned_since="1952", verified=verified,
    ))


@pytest.mark.asyncio
async def test_archive_only_record_is_listed_with_a_null_book(client, db):
    """A work we cannot host is still documented. This is the archive."""
    _record(db, "Kill Me Quick, Kambithi", "Kenethula wa Mabgio")
    await db.commit()

    r = await client.get(ENDPOINT)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    it = items[0]
    assert it["book"] is None, "an archive-only record must not claim to be a book we carry"
    # The work is identified from the record itself, not from a joined book.
    assert it["work_title"] == "Kill Me Quick, Kambithi"
    assert it["work_author"] == "Kenethula wa Mabgio"
    assert it["country_name"] == "Kenya"
    assert it["country_code"] == "KE"
    assert it["ban_reason"]
    assert it["status"] == CensorshipStatus.BANNED


@pytest.mark.asyncio
async def test_record_for_an_approved_book_carries_that_book(client, db):
    b = _book(db, "Things Fall Apart", "Chinua Achebe")
    await db.flush()
    _record(db, "Things Fall Apart", "Chinua Achebe", book=b)
    await db.commit()

    it = (await client.get(ENDPOINT)).json()["items"][0]
    assert it["book"] is not None
    assert it["book"]["title"] == "Things Fall Apart"
    assert it["book"]["author"] == "Chinua Achebe"


@pytest.mark.asyncio
async def test_record_for_an_unapproved_book_is_not_listed(client, db):
    """Otherwise the page links to a book a reader cannot open."""
    b = _book(db, "Pending Draft", "Someone", status=BookStatus.PENDING)
    await db.flush()
    _record(db, "Pending Draft", "Someone", book=b)
    await db.commit()

    assert (await client.get(ENDPOINT)).json()["items"] == []


@pytest.mark.asyncio
async def test_record_for_an_unverified_licence_book_is_not_listed(client, db):
    b = _book(db, "Unlicensed Scan", "Someone", verified=False)
    await db.flush()
    _record(db, "Unlicensed Scan", "Someone", book=b)
    await db.commit()

    assert (await client.get(ENDPOINT)).json()["items"] == []


@pytest.mark.asyncio
async def test_unverified_records_are_hidden(client, db):
    """`verified` is the editorial gate; unverified rows must not publish."""
    _record(db, "Rumoured Ban", "Nobody", verified=False)
    _record(db, "Documented Ban", "Somebody", verified=True)
    await db.commit()

    items = (await client.get(ENDPOINT)).json()["items"]
    assert [i["work_title"] for i in items] == ["Documented Ban"]


@pytest.mark.asyncio
async def test_search_matches_an_archive_only_work_by_title(client, db):
    """The q filter reads Book.title too, which is NULL for archive-only rows.

    For an archive-only row the joined book is null, so a title search can only
    match via work_title. The search term here appears in the title and NOT in
    the author, so this fails if the work_title arm of the OR is ever dropped.
    """
    _record(db, "The Trial of Dedan Kimathi", "Waigwa Wachira", country="KE")
    _record(db, "How to Get a Taxi in Lagos", "Abolore K. A.", country="NG")
    await db.commit()

    r = await client.get(ENDPOINT, params={"q": "dedan"})
    assert r.status_code == 200
    titles = [i["work_title"] for i in r.json()["items"]]
    assert titles == ["The Trial of Dedan Kimathi"]


@pytest.mark.asyncio
async def test_search_matches_an_archive_only_work_by_author(client, db):
    """Same for the work_author arm, with a term that is only in the author."""
    _record(db, "Kikuyu Folktales", "Gakaara wa Wanjau", country="KE")
    _record(db, "How to Get a Taxi in Lagos", "Abolore K. A.", country="NG")
    await db.commit()

    r = await client.get(ENDPOINT, params={"q": "gakaara"})
    assert r.status_code == 200
    titles = [i["work_title"] for i in r.json()["items"]]
    assert titles == ["Kikuyu Folktales"]


@pytest.mark.asyncio
async def test_search_is_case_insensitive(client, db):
    """Documented intent, but only weakly enforced here.

    The endpoint lowercases `q` because Postgres LIKE is case-sensitive, while
    SQLite's LIKE is already case-insensitive for ASCII. So removing the
    `.lower()` still passes on this fixture -- verified by mutation. This test
    therefore guards against a search that stops matching altogether, not
    against the case-folding itself; that only becomes observable on Postgres.
    """
    _record(db, "The Trial of Dedan Kimathi", "Waigwa Wachira", country="KE")
    await db.commit()

    assert len((await client.get(ENDPOINT, params={"q": "DEDAN"})).json()["items"]) == 1
    assert len((await client.get(ENDPOINT, params={"q": "dedan"})).json()["items"]) == 1


@pytest.mark.asyncio
async def test_country_filter_finds_nothing_when_a_country_has_no_records(client, db):
    _record(db, "Kenyan Work", "A", country="KE")
    await db.commit()

    assert len((await client.get(ENDPOINT, params={"country": "ke"})).json()["items"]) == 1
    assert (await client.get(ENDPOINT, params={"country": "ZW"})).json()["items"] == []


@pytest.mark.asyncio
async def test_status_filter_and_response_shape(client, db):
    """The archive UI groups by status and reads these keys directly."""
    _record(db, "Banned Work", "A", status=CensorshipStatus.BANNED)
    _record(db, "Restricted Work", "B", status=CensorshipStatus.RESTRICTED)
    _record(db, "Contested Work", "C", status=CensorshipStatus.CONTESTED)
    await db.commit()

    body = (await client.get(ENDPOINT, params={"status": CensorshipStatus.CONTESTED})).json()
    assert body["total"] == 1
    it = body["items"][0]
    for key in ("id", "book_id", "work_title", "work_author", "work_year",
                "country_code", "country_name", "status", "ban_reason",
                "banned_since", "source_url", "verified", "book"):
        assert key in it, f"archive row is missing {key!r}, which the frontend reads"
