from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List

from .deps import get_db
from ...models.book import Book, BookStatus
from ...schemas.book import BookResponse, BookListResponse
from ...services.search_filters import book_match_filter

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=BookListResponse)
async def search_books(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    match, score = book_match_filter(Book, q)
    stmt = select(Book).where(
        Book.status == BookStatus.APPROVED,
        Book.license_verified == True,
    )
    if match is not None:
        stmt = stmt.where(match)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar() or 0

    if score is not None:
        stmt = stmt.order_by(score.desc(), Book.title.asc())
    else:
        stmt = stmt.order_by(Book.title.asc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    books = result.scalars().all()

    return BookListResponse(
        items=[BookResponse.model_validate(b) for b in books],
        total=total,
        page=page,
        page_size=page_size,
    )