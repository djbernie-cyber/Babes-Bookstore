from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, String, cast, case
from typing import Optional
import re

from .deps import get_db
from ...models.book import Book, BookStatus
from ...schemas.book import BookResponse, BookListResponse
from ...sources.african_ebooks import (
    AFRICAN_LITERATURE_TAG,
    AFRICAN_CONTINENT_TAG,
    COLONIAL_SOURCE_TAG,
    CONDEMNED_REVOLUTIONARY_AUTHORS,
)

router = APIRouter(prefix="/authors", tags=["authors"])

_AGGREGATE_CREDITS: list[str] = ["Various", "Anonymous", "Unknown"]

#: Revolutionary writers explicitly banned/imprisoned by their own states —
#: surfaced with a badge so readers can find the political canon.
_banned_lookup = {n.strip().lower(): n for n in CONDEMNED_REVOLUTIONARY_AUTHORS}


def _display_name(name: str) -> str:
    """``"Surname, Given (alias)"`` -> ``"Given Surname"``; others unchanged."""
    part = (name or "").split("(")[0].strip()
    if "," in part:
        head, _, tail = part.partition(",")
        head, tail = head.strip(), tail.strip()
        if head and tail and not any(ch.isdigit() for ch in head):
            return f"{tail} {head}"
    return part


def _author_key(name: str) -> str:
    """Normalised merge key so ``"Equiano, Olaudah"`` and ``"Olaudah Equiano"``
    collapse onto the same shelf entry."""
    return re.sub(r"[^a-z0-9]+", "", _display_name(name).lower())


def _identifiable_author(name: str) -> bool:
    """Skip initials-only and lone-single-token credits that can never identify
    a real author (stale auto-tags from anonymous Gutenberg records)."""
    tokens = re.findall(r"[a-z0-9]+", (name or "").lower())
    if not tokens or all(len(t) == 1 for t in tokens):
        return False
    if len(tokens) == 1:
        return False
    return True


def _banned(name: str) -> bool:
    """True when ``name`` matches a condemned revolutionary writer.

    Author strings appear in the catalogue in both "First Last" and
    "Last, First" forms, so compare against every word ordering.
    """
    if not name:
        return False
    clean = " ".join((name or "").strip().lower().split())
    if clean in _banned_lookup:
        return True
    # Re-order "Last, First" → "First Last".
    if "," in clean:
        parts = [p.strip() for p in clean.split(",")]
        if len(parts) == 2 and parts[0] and parts[1]:
            reordered = f"{parts[1]} {parts[0]}".strip()
            if reordered in _banned_lookup:
                return True
    return False


@router.get("")
async def list_authors(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str = Query("", alias="q"),
):
    """List all authors with their book counts. Paginated."""
    # Get distinct authors with counts from approved books
    stmt = (
        select(Book.author, func.count(Book.id).label("book_count"))
        .where(
            Book.status == BookStatus.APPROVED,
            Book.license_verified == True,
            Book.author.isnot(None),
            Book.author != "",
            Book.author.notin_(_AGGREGATE_CREDITS),
        )
        .group_by(Book.author)
        .order_by(func.count(Book.id).desc())
    )

    if search:
        stmt = stmt.where(Book.author.ilike(f"%{search}%"))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    result = await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    rows = result.all()

    return {
        "items": [{"name": r[0], "book_count": r[1], "slug": _slugify(r[0])} for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/african", response_model=dict)
async def list_african_authors(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str = Query("", alias="q"),
):
    """List authors whose approved works carry the African Literature tag,
    excluding colonial-sauce (coloniser) works.

    Returns featured/large collections first along with every author and
    their African-tagged book count, so the African Authors page can show
    a spotlight + full browsable list in one call. Black African (continent)
    authors are ordered ahead of the diaspora canon.
    """
    tag_filter = cast(Book.tags, String).ilike(f'%"{AFRICAN_LITERATURE_TAG}"%')
    colonial_filter = ~cast(Book.tags, String).ilike(f'%"{COLONIAL_SOURCE_TAG}"%')
    continent_filter = cast(Book.tags, String).ilike(f'%"{AFRICAN_CONTINENT_TAG}"%')

    base = (
        select(Book.author, func.count(Book.id).label("book_count"))
        .where(
            Book.status == BookStatus.APPROVED,
            Book.license_verified == True,
            Book.author.isnot(None),
            Book.author != "",
            Book.author.notin_(_AGGREGATE_CREDITS),
            tag_filter,
            colonial_filter,
        )
        .group_by(Book.author)
    )

    rows = (await db.execute(base.order_by(func.count(Book.id).desc()))).all()
    if search:
        like = f"%{search.lower()}%"
        rows = [r for r in rows if like in r[0].lower() or like in _author_key(r[0])]

    # Merge duplicated name spellings, drop degenerate credits.
    merged: dict = {}
    continent_keys: set = set()
    continent_rows = (await db.execute(
        base.where(continent_filter).order_by(func.count(Book.id).desc())
    )).all()
    for r in continent_rows:
        continent_keys.add(_author_key(r[0]))

    for name, count in rows:
        if not _identifiable_author(name):
            continue
        key = _author_key(name)
        entry = merged.get(key)
        display = _display_name(name)
        if entry is None:
            merged[key] = {"name": display, "slug": _slugify(display), "book_count": count, "banned": _banned(name)}
        else:
            entry["book_count"] += count
            if len(re.sub(r"[^a-z]+", "", display)) > len(re.sub(r"[^a-z]+", "", entry["name"])):
                entry["name"] = display
            entry["banned"] = entry["banned"] or _banned(name)

    ordered = sorted(
        merged.values(),
        key=lambda a: (
            _author_key(a["name"]) not in continent_keys,
            -a["book_count"],
            a["name"].lower(),
        ),
    )
    total = len(ordered)
    paged = ordered[(page - 1) * page_size: page * page_size]

    featured = [a for a in ordered if _author_key(a["name"]) in continent_keys][:5]
    if not featured:
        featured = ordered[:5]

    continent_total = sum(
        1 for r in continent_rows if _identifiable_author(r[0]) and len(_author_key(r[0])) > 2
    )

    return {
        "items": paged,
        "featured": featured,
        "total_african_books": (await db.execute(
            select(func.count(Book.id)).where(
                Book.status == BookStatus.APPROVED,
                Book.license_verified == True,
                tag_filter,
                colonial_filter,
            )
        )).scalar() or 0,
        "total_continent_books": (await db.execute(
            select(func.count(Book.id)).where(
                Book.status == BookStatus.APPROVED,
                Book.license_verified == True,
                tag_filter,
                colonial_filter,
                continent_filter,
            )
        )).scalar() or 0,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{author_slug}", response_model=BookListResponse)
async def get_author_books(
    author_slug: str,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    tag: Optional[str] = None,
):
    """Get books by a specific author (matched by slug).

    Pass ``?tag=African Literature`` (URL-encoded) to restrict to a tag so
    an author's dedicated page can show only their African-tagged works.
    """
    # Find the author whose slug matches
    author_name = author_slug.replace("-", " ")

    # Try exact match first, then fuzzy
    stmt = select(Book).where(
        Book.status == BookStatus.APPROVED,
        Book.license_verified == True,
    )

    # Try matching by normalized name
    stmt = stmt.where(
        func.lower(func.replace(func.replace(Book.author, " ", ""), "-", "")) ==
        func.lower(func.replace(func.replace(author_name, " ", ""), "-", ""))
    )

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar() or 0

    if total == 0:
        # Fuzzy: try ilike
        stmt = select(Book).where(
            Book.status == BookStatus.APPROVED,
            Book.license_verified == True,
            Book.author.ilike(f"%{author_name}%"),
        )
        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(total_stmt)).scalar() or 0

    if total == 0:
        raise HTTPException(status_code=404, detail="Author not found")

    if tag:
        tag_filter = cast(Book.tags, String).ilike(f'%"{tag}"%')
        stmt = stmt.where(tag_filter)
        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(total_stmt)).scalar() or 0

    stmt = stmt.order_by(Book.publication_year.asc().nullslast(), Book.title.asc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    books = result.scalars().all()

    return BookListResponse(
        items=[BookResponse.model_validate(b) for b in books],
        total=total,
        page=page,
        page_size=page_size,
    )


def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
