from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, cast, String as SQLString
from typing import List

from .deps import get_db
from ...models.book import Book, BookStatus
from ...schemas.book import BookResponse, BookListResponse

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=BookListResponse)
async def search_books(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    search_filter = or_(
        Book.title.ilike(f"%{q}%"),
        Book.author.ilike(f"%{q}%"),
        Book.description.ilike(f"%{q}%"),
        # tags is a JSON column; cast to text so the LIKE works on both
        # Postgres (production) and SQLite (tests).
        cast(Book.tags, SQLString).ilike(f"%{q}%"),
    )
    stmt = select(Book).where(
        Book.status == BookStatus.APPROVED,
        Book.license_verified == True,
        search_filter,
    )

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar() or 0

    stmt = stmt.order_by(Book.title.asc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    books = result.scalars().all()

    return BookListResponse(
        items=[BookResponse.model_validate(b) for b in books],
        total=total,
        page=page,
        page_size=page_size,
    )