from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from .deps import get_db
from ...models.book import Book, BookStatus

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
async def list_categories(db: AsyncSession = Depends(get_db)):
    """Public list of all categories with approved book counts."""
    rows = (await db.execute(
        select(Book.category, func.count(Book.id).label("count"))
        .where(Book.status == BookStatus.APPROVED, Book.license_verified == True)
        .where(Book.category.isnot(None))
        .group_by(Book.category)
        .order_by(func.count(Book.id).desc())
    )).all()
    return [{"slug": _slugify(r[0]), "name": r[0], "count": r[1]} for r in rows if r[0]]


def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
