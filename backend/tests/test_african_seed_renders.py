"""The shipped African seed data must actually render in the archive.

The endpoint tests in test_banned_records_api.py use synthetic fixtures, so
they would stay green while the real seed data broke the archive -- a record
left unverified, a missing ban_reason, a two-letter country code that is not
two letters, a duplicate that collapses on the second run. The user-visible
symptom for all of those is the same: the African section is empty and nothing
in the suite objects.

So this seeds the actual RECORDS from the script through the real endpoint.

The script is imported rather than re-listed here, which means the script had
to stop calling asyncio.run() at module scope; that is deliberate, since a
module that runs on import cannot be tested.
"""
import importlib

import pytest
from sqlalchemy import select

from app.models.censorship import CensorshipRecord

seed = importlib.import_module("app.scripts.seed_censorship_africa")
RECORDS = seed.RECORDS


async def _seed_from_script(db):
    """Insert the script's own rows, the way main() does."""
    for (title, author, year, cc, cname, status, since, reason, note) in RECORDS:
        db.add(CensorshipRecord(
            book_id=None, work_title=title, work_author=author, work_year=year,
            country_code=cc, country_name=cname, status=status, ban_reason=reason,
            banned_since=since, verified=True, verified_by="seed",
        ))
    await db.commit()


# ── The data itself ────────────────────────────────────────────────────────

def test_every_seeded_record_has_the_fields_the_archive_renders():
    """The archive row is built from these; a blank one renders as a blank line."""
    for r in RECORDS:
        title, author, year, cc, cname, status, since, reason, note = r
        where = f"{title!r} ({cc})"
        assert title and title.strip(), f"blank work_title: {where}"
        assert author and author.strip(), f"blank work_author: {where}"
        assert reason and len(reason.strip()) > 40, f"ban_reason too thin to render: {where}"
        assert cc and len(cc) == 2 and cc.isalpha() and cc.isupper(), \
            f"country_code must be a 2-letter uppercase code, got {cc!r} in {where}"
        assert cname and cname.strip(), f"blank country_name: {where}"
        assert status, f"blank status: {where}"
        assert year and str(year).strip(), f"blank work_year: {where}"


def test_seeded_titles_are_unique_per_country():
    """The seed's own idempotency key is (title, country); a duplicate would
    collapse on re-run and the archive would show one row where two belong."""
    keys = [(r[0].lower().strip(), r[3]) for r in RECORDS]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"duplicate (title, country) keys would collapse on re-run: {dupes}"


def test_seed_covers_the_african_countries_it_claims():
    from collections import Counter
    counts = Counter(r[4] for r in RECORDS)
    assert counts["Kenya"] >= 5, f"Kenya is thin: {dict(counts)}"
    assert counts["Nigeria"] >= 5, f"Nigeria is thin: {dict(counts)}"
    assert counts["South Africa"] >= 5, f"South Africa is thin: {dict(counts)}"
    assert counts["Ghana"] >= 3, f"Ghana is thin: {dict(counts)}"
    # Southern Africa beyond South Africa, so the section is not Anglophone-only.
    assert any("Zimbabwe" in c for c in counts), f"no Zimbabwe/Rhodesia row: {dict(counts)}"


# ── The data through the real endpoint ──────────────────────────────────────

@pytest.mark.asyncio
async def test_seeded_records_surface_through_the_archive_endpoint(client, db):
    """The whole point: after seeding, the archive is not empty."""
    await _seed_from_script(db)

    r = await client.get("/api/v1/banned/records")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == len(RECORDS), (
        f"expected all {len(RECORDS)} seeded records, got {body['total']}")
    assert all(i["book"] is None for i in body["items"]), \
        "archive-only seed rows must not claim a carried edition"


@pytest.mark.asyncio
async def test_archive_renders_every_seeded_country(client, db):
    await _seed_from_script(db)
    items = (await client.get("/api/v1/banned/records")).json()["items"]
    titles = {i["work_title"] for i in items}
    for (title, *_rest) in RECORDS:
        assert title in titles, f"seeded work missing from the archive: {title!r}"


@pytest.mark.asyncio
@pytest.mark.parametrize("cc,cname", sorted({(r[3], r[4]) for r in RECORDS}))
async def test_each_seeded_country_is_filterable(client, db, cc, cname):
    """The archive groups by country; a country that cannot be filtered is
    invisible in the UI even though the rows exist."""
    await _seed_from_script(db)
    body = (await client.get("/api/v1/banned/records", params={"country": cc})).json()
    assert body["total"] >= 1, f"country={cc} ({cname}) returns nothing"
    assert all(i["country_code"] == cc for i in body["items"])
    assert all(i["country_name"] == cname for i in body["items"])


@pytest.mark.asyncio
async def test_every_seeded_work_is_searchable_by_title(client, db):
    """Readers look for a specific book. Each seeded title must be findable by
    a distinctive fragment of its own title."""
    await _seed_from_script(db)
    for (title, *_rest) in RECORDS:
        # The longest word is the most distinctive one available; short titles
        # like "The Man Died" have nothing longer than four characters.
        words = [w for w in title.replace(":", " ").split() if len(w) >= 3]
        assert words, f"no searchable fragment in {title!r}"
        term = max(words, key=len)
        body = (await client.get("/api/v1/banned/records", params={"q": term})).json()
        assert any(i["work_title"] == title for i in body["items"]), \
            f"{title!r} is not findable by {term!r}"


@pytest.mark.asyncio
async def test_reseeding_does_not_duplicate(client, db):
    """Idempotency is the reason the fix was safe to run against production."""
    await _seed_from_script(db)
    first = (await client.get("/api/v1/banned/records")).json()["total"]
    # Re-run exactly as main() would: it skips keys it already recorded.
    existing = {(r[0].lower().strip(), r[3]) for r in RECORDS}
    pending = [r for r in RECORDS if (r[0].lower().strip(), r[3]) not in existing]
    assert pending == [], "the script would try to re-insert rows it already wrote"

    count = (await db.execute(select(CensorshipRecord))).scalars().all()
    assert len(count) == first == len(RECORDS)
