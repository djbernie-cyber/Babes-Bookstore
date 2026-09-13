"""Backfill the 'Suppressed Classics' tag on books already in the catalogue.

Books ingested via the normal Gutenberg harvester before the Suppressed
Classics source existed lack the tag. This script iterates every entry in
SUPPRESSED_CANON, finds the matching ``source='gutenberg'`` book by
``source_id``, and appends the tag when missing. Run inside the API container:

    cd /app && PYTHONPATH=/app python /tmp/backfill_suppressed_tag.py

Idempotent — safe to re-run at any time.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models.book import Book
from app.sources.suppressed import SUPPRESSED_CLASSICS_TAG, SUPPRESSED_CANON


async def main():
    total = 0
    updated = 0
    skipped = 0

    async with AsyncSessionLocal() as db:
        # Map gutenberg_id (string) → book.id for fast lookup.
        stmt = select(Book.id, Book.source_id, Book.tags).where(
            Book.source == "gutenberg",
            Book.source_id.isnot(None),
        )
        rows = (await db.execute(stmt)).all()
        book_map = {r[1]: (r[0], r[2] or []) for r in rows}

        for entry in SUPPRESSED_CANON:
            gid = str(entry.get("gutenberg_id", ""))
            total += 1
            if gid not in book_map:
                skipped += 1
                continue

            book_id, tags = book_map[gid]
            if SUPPRESSED_CLASSICS_TAG in tags:
                skipped += 1
                continue

            new_tags = list(dict.fromkeys(tags + [SUPPRESSED_CLASSICS_TAG]))
            await db.execute(
                update(Book).where(Book.id == book_id).values(tags=new_tags)
            )
            book_map[gid] = (book_id, new_tags)
            updated += 1

        await db.commit()

    print(f"Suppressed Classics backfill: {total} canon entries, "
          f"{updated} updated, {skipped} skipped (missing or already tagged).")


asyncio.run(main())
