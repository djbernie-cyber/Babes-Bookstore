"""Re-randomise the membership of curated (system) bundles.

Called by the admin ``POST /admin/bundles/randomise`` endpoint. For each
active curated bundle it:

1.  Builds a **themed pool** of approved, licence-verified books that match
    the bundle's ``tags`` (any overlap) or ``category`` when no tags exist.
2.  Replaces the ``BundleBook`` rows with a fresh random subset of the same
    size (capped by pool size, floored at 1 when a pool exists).
3.  Flags the bundle for ZIP rebuild and audit-logs the mutation.

Custom (user-built) bundles are **never** touched.
"""

from __future__ import annotations

import logging
import random
from typing import Dict, List, Set, Tuple

from sqlalchemy import select, func, String, cast, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.book import Book, BookStatus
from ..models.bundle import Bundle, BundleBook

logger = logging.getLogger(__name__)

MIN_BUNDLE_SIZE = 3
MAX_BUNDLE_SIZE = 60


async def randomise_curated_bundles(db: AsyncSession) -> Dict:
    """Shuffle every active curated bundle's book membership in-place.

    Returns a summary dict ``{"updated": [...], "skipped": [...]}`` for
    the caller to audit-log and queue rebuilds.
    """
    # Load active curated bundles with their current books.
    stmt = (
        select(Bundle)
        .options(selectinload(Bundle.bundle_books))
        .where(Bundle.active == True, Bundle.bundle_type == "curated")
        .order_by(Bundle.id)
    )
    bundles = (await db.execute(stmt)).scalars().unique().all()

    if not bundles:
        return {"updated": [], "skipped": ["no active curated bundles"]}

    # Pre-load approved, licence-verified books once (pool used everywhere).
    approved_books: List[Dict] = [
        {
            "id": r[0],
            "author": r[1] or "",
            "tags": r[2] or [],
            "category": r[3] or "",
        }
        for r in (
            await db.execute(
                select(Book.id, Book.author, Book.tags, Book.category).where(
                    Book.status == BookStatus.APPROVED,
                    Book.license_verified == True,
                )
            )
        ).all()
    ]

    if not approved_books:
        return {"updated": [], "skipped": ["no approved books in catalogue"]}

    book_by_id = {b["id"]: b for b in approved_books}
    approved_ids = set(book_by_id.keys())

    updated: List[str] = []
    skipped: List[str] = []

    for bundle in bundles:
        current_size = len(bundle.bundle_books)
        if current_size == 0:
            skipped.append(f"{bundle.slug}: empty (no books)")
            continue

        tags = bundle.tags or []
        current_ids = {bb.book_id for bb in bundle.bundle_books}
        # Author canon: the original seeders picked many bundles by author
        # list (Twain, Dickens, Park…) whose catalogue entries don't all share
        # the bundle's tags. Keep their authors in the pool or the bundle
        # silently shrinks every time it is randomised.
        current_authors = {
            (book_by_id[i]["author"] or "").strip().lower()
            for i in current_ids if i in book_by_id
        } - {""}

        def _matches(book: Dict) -> bool:
            if tags and any(t in book["tags"] for t in tags):
                return True
            if not tags and bundle.category and book["category"] == bundle.category:
                return True
            inv = (book["author"] or "").strip().lower()
            if inv and inv in current_authors:
                return True
            return False

        pool = [b for b in approved_books if _matches(b)]

        # Fallback: if theme filter yields too few candidates, use full catalogue
        # (avoid degenerate tiny bundles).
        if len(pool) < MIN_BUNDLE_SIZE:
            pool = list(approved_books)

        # Remove any books currently in the bundle to encourage freshness
        fresh_pool = [b for b in pool if b["id"] not in current_ids]
        # If the fresh pool is smaller than target, re-include current books
        if len(fresh_pool) < MIN_BUNDLE_SIZE:
            fresh_pool = pool

        target = min(max(current_size, MIN_BUNDLE_SIZE), MAX_BUNDLE_SIZE, len(fresh_pool))
        # Sample-distinct: never duplicate a book inside its own bundle.
        chosen = random.sample(fresh_pool, target)
        final_ids = [b["id"] for b in chosen]

        # ── Replace membership (ORM delete keeps the identity map clean) ─
        for bb in list(bundle.bundle_books):
            await db.delete(bb)
        await db.flush()

        for i, book_id in enumerate(final_ids):
            db.add(BundleBook(bundle_id=bundle.id, book_id=book_id, sort_order=i))

        updated.append(
            f"{bundle.slug}: {current_size} → {len(final_ids)} books"
        )

    await db.commit()
    logger.info("Bundle randomise: %d updated, %d skipped", len(updated), len(skipped))
    return {"updated": updated, "skipped": skipped}
