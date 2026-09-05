from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete as sa_delete

from .deps import get_db, get_current_user
from ...models.book import Book, BookStatus
from ...models.user import User
from ...models.wishlist import WishlistItem

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


def _require(user: User | None) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Login required to use your wishlist")
    return user


@router.get("")
async def list_wishlist(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List the current user's wishlisted books (newest first)."""
    user = _require(current_user)

    count_stmt = (
        select(func.count())
        .select_from(WishlistItem)
        .where(WishlistItem.user_id == user.id)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Book)
        .join(WishlistItem, WishlistItem.book_id == Book.id)
        .where(WishlistItem.user_id == user.id)
        .order_by(WishlistItem.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return {
        "items": [
            {
                "id": b.id,
                "title": b.title,
                "author": b.author,
                "cover_url": b.cover_path,
                "category": b.category,
            }
            for b in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/{book_id}")
async def add_to_wishlist(
    book_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a book to the current user's wishlist. Idempotent."""
    user = _require(current_user)

    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    existing = (await db.execute(
        select(WishlistItem).where(
            WishlistItem.user_id == user.id,
            WishlistItem.book_id == book_id,
        )
    )).scalar_one_or_none()
    if existing:
        return {"wishlisted": True, "already": True}

    db.add(WishlistItem(user_id=user.id, book_id=book_id))
    await db.commit()
    return {"wishlisted": True, "already": False}


@router.delete("/{book_id}")
async def remove_from_wishlist(
    book_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a book from the current user's wishlist."""
    user = _require(current_user)

    result = await db.execute(
        sa_delete(WishlistItem).where(
            WishlistItem.user_id == user.id,
            WishlistItem.book_id == book_id,
        )
    )
    await db.commit()
    return {"wishlisted": False, "removed": result.rowcount > 0}


@router.get("/status/{book_id}")
async def wishlist_status(
    book_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Report whether the current user has a given book wishlisted."""
    if not current_user:
        return {"wishlisted": False, "anonymous": True}

    existing = (await db.execute(
        select(WishlistItem.id).where(
            WishlistItem.user_id == current_user.id,
            WishlistItem.book_id == book_id,
        )
    )).scalar_one_or_none()
    return {"wishlisted": existing is not None, "anonymous": False}
