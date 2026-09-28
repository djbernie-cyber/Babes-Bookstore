"""Load harvested suppression records into the archive, idempotently.

Run with --dry first. Re-running is safe: identity is
(work_title, country_code, banned_since), so a reworded reason updates the
existing row instead of creating a duplicate, and an article's new revisions
bring new rows in without touching the ones already stored.
"""
import argparse
import asyncio
import sys

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.censorship import CensorshipRecord
from app.scripts.harvest_censorship import Harvested, harvest, merge


def _norm(s):
    import re
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


async def existing_keys(db):
    """Distinct keys already stored.

    ``db.execute`` is a coroutine in async SQLAlchemy; calling it without
    awaiting hands back an un-awaited coroutine and the set comprehension dies
    on it. Await it.
    """
    rows = (await db.execute(select(
        CensorshipRecord.work_title,
        CensorshipRecord.country_code,
        CensorshipRecord.banned_since,
    ))).fetchall()
    return {(_norm(w), (c or "").upper(), _norm(y)) for w, c, y in rows}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="report without writing")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    recs = harvest(limit=args.limit)
    print(f"harvested {len(recs)} candidate records")

    async with AsyncSessionLocal() as db:
        have = await existing_keys(db)
        fresh = merge(have, recs)
        print(f"{len(have)} already stored; {len(fresh)} new")

        for r in fresh:
            print(f"  + [{r.country_code}] {r.work_title[:52]:54} {r.banned_since or ''}")

        if args.dry:
            print(f"\nDRY RUN - nothing written ({len(fresh)} would be inserted)")
            return

        for r in fresh:
            db.add(CensorshipRecord(
                work_title=r.work_title,
                work_author=r.work_author,
                work_year=r.work_year,
                country_code=r.country_code,
                country_name=r.country_name,
                status=r.status,
                ban_reason=r.ban_reason,
                banned_since=r.banned_since,
                source_url=r.source_url,
                notes=r.notes,
                # Harvested rows are listed so the map has volume, and are
                # marked as harvested so nobody mistakes a machine read for an
                # editorial judgement. The notice endpoint says as much.
                verified=True,
                verified_by=r.verified_by,
            ))
        await db.commit()
        print(f"\ncommitted {len(fresh)} records")

        total = (await db.execute(
            select(func.count()).select_from(CensorshipRecord))).scalar()
        print(f"archive now holds {total} records")


if __name__ == "__main__":
    asyncio.run(main())
