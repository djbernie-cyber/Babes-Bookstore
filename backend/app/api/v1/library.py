"""User library API: named shelves, shelf items, reading progress, prefs.

The wishlist is modelled as a user's default shelf, so existing clients keep
working while users gain multiple named shelves and per-book reading progress.
All endpoints live under /api/v1/library and require a logged-in user.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete as sa_delete, or_

from .deps import get_db, get_current_user, get_optional_user
from ...models.book import Book, BookStatus
from ...models.bundle import Bundle
from ...models.user import User
from ...models.library import Shelf, ShelfItem, ReadingProgress
from ...models.review import Review

router = APIRouter(prefix="/library", tags=["library"])

DEFAULT_SHELF = "Saved"
VALID_THEMES = ("light", "dark", "sepia")
VALID_FONT_SIZES = ("s", "m", "l", "xl")


class ShelfCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ShelfRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProgressSave(BaseModel):
    percent: float = Field(ge=0.0, le=1.0)
    position: str = Field("", max_length=500)


class PrefsSave(BaseModel):
    theme: str | None = None
    reader_font_size: str | None = None


def _require(user: User | None) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Login required for your library")
    return user


async def _default_shelf(db: AsyncSession, user_id: int) -> Shelf:
    """Return the user's default shelf, creating it on first use."""
    shelf = (await db.execute(
        select(Shelf).where(Shelf.user_id == user_id, Shelf.is_default.is_(True))
    )).scalar_one_or_none()
    if shelf:
        return shelf
    shelf = Shelf(user_id=user_id, name=DEFAULT_SHELF, is_default=True)
    db.add(shelf)
    await db.commit()
    return shelf


def _book_payload(b: Book) -> dict:
    cover = b.cover_path if (b.cover_path and b.cover_path.startswith("http")) else None
    return {
        "id": b.id,
        "title": b.title,
        "author": b.author,
        "cover_url": cover,
        "category": b.category,
    }


# --------------------------------------------------------------------------
# Shelves
# --------------------------------------------------------------------------

@router.get("")
async def list_shelves(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the user's shelves with per-shelf book counts."""
    user = _require(current_user)
    await _default_shelf(db, user.id)

    rows = (await db.execute(
        select(Shelf, func.count(ShelfItem.id))
        .outerjoin(ShelfItem, ShelfItem.shelf_id == Shelf.id)
        .where(Shelf.user_id == user.id)
        .group_by(Shelf.id)
        .order_by(Shelf.is_default.desc(), Shelf.created_at.asc())
    )).all()

    return {
        "items": [
            {"id": s.id, "name": s.name, "is_default": s.is_default, "book_count": count}
            for s, count in rows
        ]
    }


@router.post("")
async def create_shelf(
    payload: ShelfCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new named shelf."""
    user = _require(current_user)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Shelf name cannot be blank")

    existing = (await db.execute(
        select(Shelf).where(Shelf.user_id == user.id, Shelf.name == name)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Shelf '{name}' already exists")

    shelf = Shelf(user_id=user.id, name=name)
    db.add(shelf)
    await db.commit()
    await db.refresh(shelf)
    return {"id": shelf.id, "name": shelf.name, "is_default": False, "book_count": 0}


@router.patch("/{shelf_id}")
async def rename_shelf(
    shelf_id: int,
    payload: ShelfRename,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rename one of the user's shelves."""
    user = _require(current_user)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Shelf name cannot be blank")

    shelf = await db.get(Shelf, shelf_id)
    if not shelf or shelf.user_id != user.id:
        raise HTTPException(status_code=404, detail="Shelf not found")
    if shelf.is_default:
        raise HTTPException(status_code=400, detail="The default shelf cannot be renamed")

    clash = (await db.execute(
        select(Shelf.id).where(Shelf.user_id == user.id, Shelf.name == name)
    )).scalar_one_or_none()
    if clash:
        raise HTTPException(status_code=409, detail=f"Shelf '{name}' already exists")

    old = shelf.name
    shelf.name = name
    await db.commit()
    return {"id": shelf.id, "name": shelf.name, "renamed_from": old}


@router.delete("/{shelf_id}")
async def delete_shelf(
    shelf_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a shelf (books are not deleted, only the collection)."""
    user = _require(current_user)
    shelf = await db.get(Shelf, shelf_id)
    if not shelf or shelf.user_id != user.id:
        raise HTTPException(status_code=404, detail="Shelf not found")
    if shelf.is_default:
        raise HTTPException(status_code=400, detail="The default shelf cannot be deleted")

    await db.execute(sa_delete(ShelfItem).where(ShelfItem.shelf_id == shelf.id))
    await db.delete(shelf)
    await db.commit()
    return {"deleted": True}


# --------------------------------------------------------------------------
# Shelf items
# --------------------------------------------------------------------------

@router.get("/{shelf_id}/books")
async def list_shelf_books(
    shelf_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=100),
):
    """List the books on a shelf (newest first)."""
    user = _require(current_user)
    shelf = await db.get(Shelf, shelf_id)
    if not shelf or shelf.user_id != user.id:
        raise HTTPException(status_code=404, detail="Shelf not found")

    total = (await db.execute(
        select(func.count()).select_from(ShelfItem).where(ShelfItem.shelf_id == shelf.id)
    )).scalar() or 0

    rows = (await db.execute(
        select(Book)
        .join(ShelfItem, ShelfItem.book_id == Book.id)
        .where(ShelfItem.shelf_id == shelf.id)
        .order_by(ShelfItem.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    return {
        "id": shelf.id,
        "name": shelf.name,
        "is_default": shelf.is_default,
        "items": [_book_payload(b) for b in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/{shelf_id}/books/{book_id}")
async def add_to_shelf(
    shelf_id: int,
    book_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a book to a shelf. Idempotent."""
    user = _require(current_user)
    shelf = await db.get(Shelf, shelf_id)
    if not shelf or shelf.user_id != user.id:
        raise HTTPException(status_code=404, detail="Shelf not found")
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    existing = (await db.execute(
        select(ShelfItem.id).where(
            ShelfItem.shelf_id == shelf.id, ShelfItem.book_id == book.id
        )
    )).scalar_one_or_none()
    if existing:
        return {"shelf_id": shelf.id, "book_id": book.id, "added": False, "already": True}

    db.add(ShelfItem(shelf_id=shelf.id, book_id=book.id))
    await db.commit()
    return {"shelf_id": shelf.id, "book_id": book.id, "added": True, "already": False}


@router.delete("/{shelf_id}/books/{book_id}")
async def remove_from_shelf(
    shelf_id: int,
    book_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a book from a shelf."""
    user = _require(current_user)
    shelf = await db.get(Shelf, shelf_id)
    if not shelf or shelf.user_id != user.id:
        raise HTTPException(status_code=404, detail="Shelf not found")

    result = await db.execute(
        sa_delete(ShelfItem).where(
            ShelfItem.shelf_id == shelf.id, ShelfItem.book_id == book_id
        )
    )
    await db.commit()
    return {"removed": result.rowcount > 0}


# --------------------------------------------------------------------------
# Reading progress
# --------------------------------------------------------------------------

@router.put("/progress/{book_id}")
async def save_progress(
    book_id: int,
    payload: ProgressSave,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save reading progress for a book (percent 0-1 + anchor)."""
    user = _require(current_user)
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    row = (await db.execute(
        select(ReadingProgress).where(
            ReadingProgress.user_id == user.id, ReadingProgress.book_id == book.id
        )
    )).scalar_one_or_none()
    if not row:
        row = ReadingProgress(user_id=user.id, book_id=book.id)
        db.add(row)
    row.percent = payload.percent
    row.position = payload.position
    await db.commit()
    return {"book_id": book.id, "percent": row.percent}


@router.get("/progress/{book_id}")
async def get_progress(
    book_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Return the current user's reading progress for a book."""
    if not current_user:
        return {"book_id": book_id, "percent": 0.0, "position": "", "progressed": False}
    row = (await db.execute(
        select(ReadingProgress).where(
            ReadingProgress.user_id == current_user.id,
            ReadingProgress.book_id == book_id,
        )
    )).scalar_one_or_none()
    if not row:
        return {"book_id": book_id, "percent": 0.0, "position": "", "progressed": False}
    return {
        "book_id": book_id,
        "percent": row.percent or 0.0,
        "position": row.position or "",
        "progressed": row.percent is not None and row.percent > 0.001,
    }


@router.get("/continue-reading")
async def continue_reading(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(8, ge=1, le=24),
):
    """Return in-progress books sorted by most recently read."""
    user = _require(current_user)
    rows = (await db.execute(
        select(Book, ReadingProgress.percent, ReadingProgress.updated_at)
        .join(ReadingProgress, ReadingProgress.book_id == Book.id)
        .where(
            ReadingProgress.user_id == user.id,
            ReadingProgress.percent > 0.001,
            ReadingProgress.percent < 0.999,
        )
        .order_by(ReadingProgress.updated_at.desc())
        .limit(limit)
    )).all()

    return {
        "items": [
            {
                **_book_payload(b),
                "percent": percent or 0.0,
                "percent_label": f"{round(percent * 100) if percent else 0}%",
                "last_read_at": updated.isoformat() if updated else None,
            }
            for b, percent, updated in rows
        ]
    }


# --------------------------------------------------------------------------
# Preferences (theme / font size)
# --------------------------------------------------------------------------

@router.get("/prefs")
async def get_prefs(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Return the user's saved theme / reader preferences."""
    if not current_user:
        return {"theme": None, "reader_font_size": None, "anonymous": True}
    return {
        "theme": current_user.theme or "sepia",
        "reader_font_size": current_user.reader_font_size or "m",
        "anonymous": False,
    }


@router.put("/prefs")
async def save_prefs(
    payload: PrefsSave,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save theme / reader preferences to the account so they follow the user."""
    user = _require(current_user)
    if payload.theme is not None:
        if payload.theme not in VALID_THEMES:
            raise HTTPException(status_code=422, detail="theme must be light, dark or sepia")
        user.theme = payload.theme
    if payload.reader_font_size is not None:
        if payload.reader_font_size not in VALID_FONT_SIZES:
            raise HTTPException(status_code=422, detail="reader_font_size must be s, m, l or xl")
        user.reader_font_size = payload.reader_font_size
    await db.commit()
    return {
        "theme": user.theme or "sepia",
        "reader_font_size": user.reader_font_size or "m",
        "anonymous": False,
    }


# --------------------------------------------------------------------------
# Library summary (live counts, no hardcoded numbers)
# --------------------------------------------------------------------------

@router.get("/summary")
async def library_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Live account-page numbers: catalogue total, shelf counts, in progress."""
    user = _require(current_user)
    await _default_shelf(db, user.id)

    catalogue_total = (await db.execute(
        select(func.count()).select_from(Book).where(
            Book.status == BookStatus.APPROVED, Book.license_verified.is_(True)
        )
    )).scalar() or 0

    shelves = (await db.execute(
        select(Shelf, func.count(ShelfItem.id))
        .outerjoin(ShelfItem, ShelfItem.shelf_id == Shelf.id)
        .where(Shelf.user_id == user.id)
        .group_by(Shelf.id)
        .order_by(Shelf.is_default.desc(), Shelf.created_at.asc())
    )).all()

    in_progress = (await db.execute(
        select(func.count()).select_from(ReadingProgress).where(
            ReadingProgress.user_id == user.id,
            ReadingProgress.percent > 0.001,
            ReadingProgress.percent < 0.999,
        )
    )).scalar() or 0

    bundle_count = (await db.execute(
        select(func.count()).select_from(Bundle)
    )).scalar() or 0

    return {
        "catalogue_total": catalogue_total,
        "bundle_count": bundle_count,
        "in_progress": in_progress,
        "total_saved": sum(count for _, count in shelves),
        "shelves": [
            {"id": s.id, "name": s.name, "is_default": s.is_default, "book_count": count}
            for s, count in shelves
        ],
    }

@router.get("/my-reviews")
async def my_reviews(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    """The current user's own reviews, joined with their book."""
    user = _require(current_user)

    count_stmt = select(func.count()).select_from(Review).where(Review.user_id == user.id)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Review, Book)
        .join(Book, Review.book_id == Book.id)
        .where(Review.user_id == user.id)
        .order_by(Review.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()

    return {
        "items": [
            {
                "id": rev.id,
                "rating": rev.rating,
                "title": rev.title,
                "body": rev.body,
                "created_at": rev.created_at.isoformat() if rev.created_at else None,
                "book": _book_payload(book),
            }
            for rev, book in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
