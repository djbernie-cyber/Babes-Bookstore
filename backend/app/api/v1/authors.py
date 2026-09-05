from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, String, cast, case
from typing import Optional

from .deps import get_db
from ...models.book import Book, BookStatus
from ...schemas.book import BookResponse, BookListResponse
from ...sources.african_ebooks import (
    AFRICAN_LITERATURE_TAG,
    AFRICAN_CONTINENT_TAG,
    COLONIAL_SOURCE_TAG,
)

router = APIRouter(prefix="/authors", tags=["authors"])


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

    stmt = (
        select(Book.author, func.count(Book.id).label("book_count"))
        .where(
            Book.status == BookStatus.APPROVED,
            Book.license_verified == True,
            Book.author.isnot(None),
            Book.author != "",
            tag_filter,
            colonial_filter,
        )
        .group_by(Book.author)
        .order_by(
            case((continent_filter, 0), else_=1),
            func.count(Book.id).desc(),
        )
    )

    if search:
        stmt = stmt.where(Book.author.ilike(f"%{search}%"))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    continent_stmt = (
        select(Book.author, func.count(Book.id).label("book_count"))
        .where(
            Book.status == BookStatus.APPROVED,
            Book.license_verified == True,
            Book.author.isnot(None),
            Book.author != "",
            tag_filter,
            colonial_filter,
            continent_filter,
        )
        .group_by(Book.author)
        .order_by(func.count(Book.id).desc())
    )
    if search:
        continent_stmt = continent_stmt.where(Book.author.ilike(f"%{search}%"))

    result = await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    rows = result.all()

    items = [{"name": r[0], "book_count": r[1], "slug": _slugify(r[0])} for r in rows]

    # Featured: lead with continent (Black African) authors.
    continent_result = await db.execute(continent_stmt.limit(5))
    continent_rows = continent_result.all()
    featured = [{"name": r[0], "book_count": r[1], "slug": _slugify(r[0])} for r in continent_rows]
    if not featured:
        featured = items[:5]

    return {
        "items": items,
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
