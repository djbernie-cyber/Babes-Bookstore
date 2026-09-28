"""Backfill African Literature / African Author tags across the whole catalogue.

The African tag pipeline only ran at ingest time, and only for books the
African source happened to produce. Result on the live catalogue: the
``/categories/african-literature`` shelf — linked from the nav, the footer,
the home page and /authors/african — was backed by **six** rows that were in
fact just two distinct works (Equiano and Plaatje) ingested three times each
under conflicting categories. Olive Schreiner, who is four of the ten
hand-curated canon entries, had 23 books in the catalogue and not one of them
carried an African tag.

This script re-applies the existing author classifiers to every approved,
licence-verified book and writes the missing tags. It adds tags only; it
never invents a book, never touches ``category``, and never marks anything
licence-verified. Idempotent — safe to re-run.

    cd /app && PYTHONPATH=/app python /tmp/backfill_african_tags.py
    # add --dry-run to report without writing
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.book import Book, BookStatus
from app.sources.african_ebooks import (
    AFRICAN_LITERATURE_TAG,
    AFRICAN_CONTINENT_TAG,
    COLONIAL_SOURCE_TAG,
    REVOLUTIONARY_TAG,
    AfricanEbooksSource,
)

DRY_RUN = "--dry-run" in sys.argv


def tags_for(author: str) -> list[str]:
    """The tag set the ingest-time _apply_african_tags would have produced."""
    out: list[str] = []
    if AfricanEbooksSource._is_african_author(author) or AfricanEbooksSource._is_colonial_author(author):
        out.append(AFRICAN_LITERATURE_TAG)
    if AfricanEbooksSource._is_continent_african(author):
        out.append(AFRICAN_CONTINENT_TAG)
    if AfricanEbooksSource._is_colonial_author(author):
        out.append(COLONIAL_SOURCE_TAG)
    if AfricanEbooksSource._is_revolutionary_author(author):
        out.append(REVOLUTIONARY_TAG)
    return out


async def main():
    changed = 0
    shelf: set[str] = set()      # authors on the African Literature shelf
    continent: set[str] = set()  # ...that are Black African from the continent

    async with AsyncSessionLocal() as db:
        books = (await db.execute(
            select(Book).where(
                Book.status == BookStatus.APPROVED,
                Book.asset_verified.is_(True),
            )
        )).scalars().all()

        for b in books:
            wanted = tags_for(b.author or "")
            if not wanted:
                continue
            have = list(b.tags or [])
            missing = [t for t in wanted if t not in have]
            if not missing:
                shelf.add(b.author)
                if AFRICAN_CONTINENT_TAG in wanted:
                    continent.add(b.author)
                continue

            b.tags = list(dict.fromkeys(have + wanted))
            changed += 1
            shelf.add(b.author)
            if AFRICAN_CONTINENT_TAG in wanted:
                continent.add(b.author)
            print(f"+{','.join(missing):40} {str(b.author)[:30]:30} | {str(b.title)[:44]}")

        if not DRY_RUN:
            await db.commit()

    print()
    print(f"{'DRY RUN — nothing written' if DRY_RUN else 'committed'}: {changed} books updated")
    print(f"African Literature shelf : {len(shelf)} distinct authors")
    print(f"  of which Black African from the continent : {len(continent)}")


asyncio.run(main())
