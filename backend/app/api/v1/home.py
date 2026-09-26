"""Personalized home feed — the landing page's row-by-row shelf layout.

One endpoint (:meth:`GET /api/v1/home/feed`) returns the whole Netflix-style
home screen: what to continue reading, a deterministic "picked for you" row
built from the reader's own shelves/progress/reviews, a set of always-on
curated rows, and an optional seasonal band orchestrated by the admin's
site-config furniture. Anonymous readers get the curated rows.

Nothing here hits the network; every row is a query against the approved,
licence-verified catalogue, so the feed is honest and fast.
"""
import json
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, cast, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from .deps import get_db, get_optional_user
from ...models.book import Book, BookStatus
from ...models.library import ReadingProgress, Shelf, ShelfItem
from ...models.review import Review
from ...models.seasonal_theme import SiteConfig
from ...models.user import User

router = APIRouter(prefix="/home", tags=["home"])


def _book(b: Book) -> dict:
    return {
        "id": b.id,
        "title": b.title,
        "author": b.author,
        "cover_url": b.cover_path if (b.cover_path and b.cover_path.startswith("http")) else None,
        "category": b.category,
        "tags": b.tags or [],
        "publication_year": b.publication_year,
    }


def _approved_where():
    return (Book.status == BookStatus.APPROVED, Book.license_verified == True)


def _dedupe(rows: list[dict], shown: set[int], limit: int) -> list[dict]:
    """Prefer books no earlier shelf has used, but never render an empty row.

    Every row used to be ordered by created_at desc, so "Start with the
    classics" and "New arrivals" returned the *same* eight ids and the two
    Marx shelves mirrored each other. Specialised shelves now claim their
    books first; the generic ones fill the gaps.
    """
    fresh = [r for r in rows if r["id"] not in shown]
    return (fresh or rows)[:limit]


async def _tag_row(db: AsyncSession, tag: str, limit: int, exclude_tags: tuple[str, ...] = ()) -> list:
    stmt = (
        select(Book)
        .where(*_approved_where(), cast(Book.tags, String).ilike(f'%"{tag}"%'))
        .order_by(Book.created_at.desc())
        .limit(limit * 4)
    )
    rows = [_book(b) for b in (await db.execute(stmt)).scalars()]
    if exclude_tags:
        # Stored tags are JSON, so filter in Python rather than with ILIKE.
        blocked = {t.lower() for t in exclude_tags}
        rows = [r for r in rows if not (blocked & {t.lower() for t in (r.get("tags") or [])})]
    return rows


async def _category_row(db: AsyncSession, category: str, limit: int) -> list:
    stmt = (
        select(Book)
        .where(*_approved_where(), Book.category == category)
        .order_by(Book.created_at.desc())
        .limit(limit * 4)
    )
    return [_book(b) for b in (await db.execute(stmt)).scalars()]


async def _recent_row(db: AsyncSession, limit: int) -> list:
    stmt = (
        select(Book)
        .where(*_approved_where())
        .order_by(Book.created_at.desc())
        .limit(limit * 4)
    )
    return [_book(b) for b in (await db.execute(stmt)).scalars()]


async def _continue_reading(db: AsyncSession, user: User, limit: int) -> list:
    rows = (
        await db.execute(
            select(Book, ReadingProgress.percent)
            .join(ReadingProgress, ReadingProgress.book_id == Book.id)
            .where(
                ReadingProgress.user_id == user.id,
                ReadingProgress.percent > 0.001,
                ReadingProgress.percent < 0.999,
            )
            .order_by(ReadingProgress.updated_at.desc())
            .limit(limit)
        )
    ).all()
    return [{**_book(b), "percent": p or 0.0} for b, p in rows]


async def _reader_signals(db: AsyncSession, user: User) -> list[int]:
    """Books the reader already interacts with: shelved, in progress, liked."""
    shelved = select(ShelfItem.book_id).join(Shelf, ShelfItem.shelf_id == Shelf.id).where(Shelf.user_id == user.id)
    in_progress = select(ReadingProgress.book_id).where(ReadingProgress.user_id == user.id)
    liked = select(Review.book_id).where(Review.user_id == user.id, Review.rating >= 4)
    rows = await db.execute(union(shelved, in_progress, liked))
    return [r[0] for r in rows.all()]


async def _for_you(db: AsyncSession, user: User, limit: int, exclude: list[int]) -> list:
    """Deterministic 'picked for you': the reader's own tag tastes.

    The top three tags across everything the reader shelved, started, or
    rated four-or-more stars become the recommendation palette. Books on
    those tags the reader hasn't already touched are surfaced newest first.
    No ML, no black box — the feed is explainable from the reader's library.
    """
    if not exclude:
        return []
    all_books = (
        await db.execute(select(Book).where(Book.id.in_(exclude)))
    ).scalars().all()
    counts: Counter = Counter()
    for b in all_books:
        for t in (b.tags or []):
            counts[t] += 1
    top = [t for t, _ in counts.most_common(3) if t]
    if not top:
        return []

    patterns = [cast(Book.tags, String).ilike(f'%"{t}"%') for t in top]
    stmt = (
        select(Book)
        .where(*_approved_where(), or_(*patterns), ~Book.id.in_(exclude))
        .order_by(Book.created_at.desc())
        .limit(limit)
    )
    return [_book(b) for b in (await db.execute(stmt)).scalars()]


@router.get("/feed")
async def home_feed(
    limit: int = Query(8, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """The row-by-row home screen, personalised for the signed-in reader."""
    sections: list[dict] = []
    shown: set[int] = set()

    def claim(cands: list[dict]) -> list[dict]:
        chosen = _dedupe(cands, shown, limit)
        for r in chosen:
            shown.add(r["id"])
        return chosen

    signals = await _reader_signals(db, current_user) if current_user else []

    if current_user:
        cont = await _continue_reading(db, current_user, min(limit, 12))
        if cont:
            sections.append({"key": "continue", "title": "Continue reading", "items": claim(cont)})

    if current_user:
        for_you = await _for_you(db, current_user, limit, signals)
        if for_you:
            sections.append({"key": "for-you", "title": "Picked for you", "items": claim(for_you)})

    # Specialised shelves claim first so the catch-all rows below cannot
    # swallow every book they were meant to showcase.
    #
    # The African shelf excludes "Colonial Sauce". The retag pass gives
    # COLONIAL_AUTHORS (Henty, Doyle, Kipling, Haggard, Conrad, Marryat) the
    # African Literature tag on purpose, so empire-framing Africa-adventure
    # stays findable; leading the shelf with them buried the actual African
    # and diaspora canon behind 1,900 titles of Victorian adventure fiction.
    # The colonial works keep their own tag and their own shelf.
    suppressed = claim(await _tag_row(db, "Suppressed Classics", limit))
    african = claim(await _tag_row(db, "African Literature", limit, exclude_tags=("Colonial Sauce",)))
    revolutionary = claim(await _tag_row(db, "Revolutionary", limit))

    classic = claim(await _category_row(db, "Classics", limit)) if not current_user else []
    recent = claim(await _recent_row(db, limit))

    if classic:
        sections.append({"key": "start-here", "title": "Start with the classics", "items": classic})
    if suppressed:
        sections.append({"key": "suppressed", "title": "Banned & suppressed classics", "items": suppressed})
    if african:
        sections.append({"key": "african", "title": "African literature", "items": african})
    if revolutionary:
        sections.append({"key": "revolutionary", "title": "The revolutionary shelf", "items": revolutionary})
    if recent:
        sections.append({"key": "new-arrivals", "title": "New arrivals", "items": recent})

    furniture: dict = {}
    cfg = (await db.execute(select(SiteConfig).where(SiteConfig.id == 1))).scalar_one_or_none()
    if cfg:
        try:
            furniture = json.loads(cfg.furniture) if cfg.furniture else {}
        except Exception:
            furniture = {}
    season = furniture.get("seasonal") if isinstance(furniture, dict) else None
    if isinstance(season, dict) and season.get("title"):
        sections.append({
            "key": "season",
            "title": season.get("title", ""),
            "body": season.get("body", ""),
            "href": season.get("href", ""),
            "emoji": season.get("emoji", ""),
            "items": [],
        })

    return {
        "user": {"name": (current_user.name or current_user.email) if current_user else None},
        "sections": sections,
    }