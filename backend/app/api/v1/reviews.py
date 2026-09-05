from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete as sa_delete

from .deps import get_db, get_current_user
from ...models.book import Book, BookStatus
from ...models.review import Review
from ...models.user import User

router = APIRouter(prefix="/books", tags=["reviews"])


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    title: str = Field("", max_length=200)
    body: str = Field("", max_length=2000)


class ReviewUpdate(BaseModel):
    rating: int = Field(ge=1, le=5)
    title: str = Field("", max_length=200)
    body: str = Field("", max_length=2000)


@router.get("/{book_id}/reviews")
async def list_reviews(
    book_id: int,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    """List public reviews for a book with rating summary."""
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Rating summary
    rating_stmt = (
        select(
            func.count(Review.id).label("count"),
            func.avg(Review.rating).label("avg"),
        )
        .where(Review.book_id == book_id)
    )
    row = (await db.execute(rating_stmt)).one()

    count_stmt = select(func.count()).select_from(Review).where(Review.book_id == book_id)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Review, User.name)
        .join(User, Review.user_id == User.id)
        .where(Review.book_id == book_id)
        .order_by(Review.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return {
        "items": [
            {
                "id": r.id,
                "rating": r.rating,
                "title": r.title,
                "body": r.body,
                "user_name": name,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r, name in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "summary": {
            "count": row.count or 0,
            "average": round(row.avg, 1) if row.avg else None,
        },
    }


@router.post("/{book_id}/reviews")
async def create_review(
    book_id: int,
    review: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a review for an approved book. Requires auth."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Login required to review")

    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.status != BookStatus.APPROVED:
        raise HTTPException(status_code=403, detail="Only approved books can be reviewed")

    # One review per user per book
    existing = (await db.execute(
        select(Review).where(Review.book_id == book_id, Review.user_id == current_user.id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="You have already reviewed this book")

    new_review = Review(
        book_id=book_id,
        user_id=current_user.id,
        rating=review.rating,
        title=review.title,
        body=review.body,
    )
    db.add(new_review)
    await db.commit()
    await db.refresh(new_review)
    return {"id": new_review.id, "rating": new_review.rating, "title": new_review.title}


@router.patch("/{book_id}/reviews/mine")
async def update_my_review(
    book_id: int,
    review: ReviewUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the current user's review for a book."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Login required")

    existing = (await db.execute(
        select(Review).where(Review.book_id == book_id, Review.user_id == current_user.id)
    )).scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="You haven't reviewed this book")

    existing.rating = review.rating
    existing.title = review.title
    existing.body = review.body
    await db.commit()
    await db.refresh(existing)
    return {"id": existing.id, "rating": existing.rating, "title": existing.title, "body": existing.body}


@router.delete("/{book_id}/reviews/mine")
async def delete_my_review(
    book_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete the current user's review for a book."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Login required")

    result = await db.execute(
        sa_delete(Review).where(Review.book_id == book_id, Review.user_id == current_user.id)
    )
    await db.commit()
    return {"deleted": result.rowcount > 0}
