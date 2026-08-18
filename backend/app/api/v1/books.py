from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from typing import List, Optional

from .deps import get_db, require_admin, get_current_user
from ...models.book import Book, BookStatus
from ...schemas.book import BookResponse, BookListResponse, BookUpdate
from ...models.user import User

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", response_model=BookListResponse)
async def list_books(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    source: Optional[str] = None,
    license_type: Optional[str] = None,
    status_filter: Optional[BookStatus] = Query(None, alias="status"),
    search: Optional[str] = None,
    approved_only: bool = True,
    current_user: Optional[User] = Depends(get_current_user),
):
    """List books.

    The public catalogue only ever sees approved, licence-verified books.
    Viewing unapproved material (approved_only=false, or any explicit
    status filter) is an admin-only capability — previously anyone could
    enumerate pending and rejected books.
    """
    wants_unapproved = (approved_only is False) or (status_filter is not None)
    if wants_unapproved and (not current_user or not current_user.is_admin):
        raise HTTPException(status_code=403, detail="Admin required to list unapproved books")

    stmt = select(Book)

    # An explicit status filter wins over the approved_only default —
    # otherwise "?status=pending" would silently mean "approved only".
    if status_filter is not None:
        stmt = stmt.where(Book.status == status_filter)
    elif approved_only:
        stmt = stmt.where(Book.status == BookStatus.APPROVED, Book.license_verified == True)

    if category:
        stmt = stmt.where(Book.category == category)
    if source:
        stmt = stmt.where(Book.source == source)
    if license_type:
        stmt = stmt.where(Book.license_type == license_type)

    if search:
        search_filter = or_(
            Book.title.ilike(f"%{search}%"),
            Book.author.ilike(f"%{search}%"),
            Book.description.ilike(f"%{search}%"),
        )
        stmt = stmt.where(search_filter)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar() or 0

    stmt = stmt.order_by(Book.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    books = result.scalars().all()

    return BookListResponse(
        items=[BookResponse.model_validate(b) for b in books],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{book_id}", response_model=BookResponse)
async def get_book(book_id: int, db: AsyncSession = Depends(get_db)):
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return BookResponse.model_validate(book)


@router.patch("/{book_id}", response_model=BookResponse)
async def update_book(
    book_id: int,
    update: BookUpdate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    data = update.model_dump(exclude_unset=True)
    if "status" in data:
        data["status"] = BookStatus(data["status"])

    for k, v in data.items():
        setattr(book, k, v)

    await db.commit()
    await db.refresh(book)
    return BookResponse.model_validate(book)


@router.delete("/{book_id}")
async def delete_book(
    book_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    await db.delete(book)
    await db.commit()
    return {"deleted": True}


@router.post("/{book_id}/approve", response_model=BookResponse)
async def approve_book(
    book_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    book.status = BookStatus.APPROVED
    book.license_verified = True
    await db.commit()
    await db.refresh(book)
    return BookResponse.model_validate(book)


@router.post("/{book_id}/reject", response_model=BookResponse)
async def reject_book(
    book_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    book.status = BookStatus.REJECTED
    await db.commit()
    await db.refresh(book)
    return BookResponse.model_validate(book)