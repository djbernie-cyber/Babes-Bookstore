from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from typing import Optional, List
from pydantic import BaseModel

from .deps import get_db, require_admin
from ...models.book import Book, BookStatus
from ...models.bundle import Bundle, BundleBook
from ...models.purchase import Purchase, PurchaseStatus
from ...models.user import User
from ...sources import source_registry

router = APIRouter(prefix="/admin", tags=["admin"])


class BulkBookAction(BaseModel):
    book_ids: List[int]
    action: str  # approve, reject, delete


class BulkStatusUpdate(BaseModel):
    status: str


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db), _admin=Depends(require_admin)):
    total_books = (await db.execute(select(func.count(Book.id)))).scalar() or 0
    approved_books = (
        await db.execute(select(func.count(Book.id)).where(Book.status == BookStatus.APPROVED))
    ).scalar() or 0
    pending_books = (
        await db.execute(select(func.count(Book.id)).where(Book.status == BookStatus.PENDING))
    ).scalar() or 0
    rejected_books = (
        await db.execute(select(func.count(Book.id)).where(Book.status == BookStatus.REJECTED))
    ).scalar() or 0

    total_bundles = (await db.execute(select(func.count(Bundle.id)))).scalar() or 0
    active_bundles = (
        await db.execute(select(func.count(Bundle.id)).where(Bundle.active == True))
    ).scalar() or 0

    total_purchases = (await db.execute(select(func.count(Purchase.id)))).scalar() or 0
    revenue_cents = (
        await db.execute(select(func.sum(Purchase.amount_cents)).where(Purchase.status == PurchaseStatus.COMPLETED))
    ).scalar() or 0

    return {
        "books": {
            "total": total_books,
            "approved": approved_books,
            "pending": pending_books,
            "rejected": rejected_books,
        },
        "bundles": {
            "total": total_bundles,
            "active": active_bundles,
        },
        "purchases": {
            "total": total_purchases,
            "revenue_cents": revenue_cents,
        },
    }


@router.post("/scrape/source/{source_name}")
async def trigger_source_scrape(
    source_name: str,
    query: str = "",
    limit: int = 20,
    start_page: int = 1,
    _admin=Depends(require_admin),
):
    if source_name not in source_registry.list_names():
        raise HTTPException(status_code=404, detail=f"Source '{source_name}' not found")

    from ...tasks.scrape import scrape_source_task
    task = scrape_source_task.delay(source_name, query, limit, start_page)
    return {"task_id": task.id, "source": source_name}


@router.post("/scrape/all")
async def trigger_all_scrape(
    query: str = "",
    limit_per_source: int = 50,
    _admin=Depends(require_admin),
):
    from ...tasks.scrape import scrape_all_sources_task
    task = scrape_all_sources_task.delay(query, limit_per_source)
    return {"task_id": task.id}


@router.post("/scrape/popular")
async def trigger_popular_scrape(
    limit_per_source: int = 50,
    _admin=Depends(require_admin),
):
    from ...tasks.scrape import scrape_popular_task
    task = scrape_popular_task.delay(limit_per_source)
    return {"task_id": task.id}


@router.post("/verify/licenses")
async def trigger_license_verification(_admin=Depends(require_admin)):
    from ...tasks.verify_licenses import verify_all_licenses_task
    task = verify_all_licenses_task.delay()
    return {"task_id": task.id}


@router.get("/sources")
async def list_sources(_admin=Depends(require_admin)):
    """Describe every registered source without opening HTTP clients."""
    return source_registry.describe()


@router.get("/purchases", response_model=None)
async def list_purchases(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List all purchases with pagination — for revenue auditing and refund handling."""
    stmt = select(Purchase).order_by(Purchase.created_at.desc())
    if status_filter:
        stmt = stmt.where(Purchase.status == status_filter)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    purchases = (await db.execute(stmt)).scalars().all()

    return {
        "items": [
            {
                "id": p.id,
                "bundle_id": p.bundle_id,
                "bundle_name": p.bundle.name if hasattr(p, 'bundle') and p.bundle else None,
                "user_id": p.user_id,
                "customer_email": p.customer_email,
                "customer_phone": p.customer_phone,
                "amount_cents": p.amount_cents,
                "currency": p.currency,
                "status": p.status.value if hasattr(p.status, 'value') else str(p.status),
                "payment_provider": p.payment_provider.value if p.payment_provider else None,
                "download_count": p.download_count,
                "max_downloads": p.max_downloads,
                "zip_path": p.zip_path,
                "created_at": p.created_at.isoformat(),
            }
            for p in purchases
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/books/bulk")
async def bulk_book_action(
    req: BulkBookAction,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Bulk approve, reject, or delete books."""
    if req.action not in ("approve", "reject", "delete"):
        raise HTTPException(status_code=400, detail="action must be approve/reject/delete")

    count = 0
    if req.action == "delete":
        for bid in req.book_ids:
            book = await db.get(Book, bid)
            if book:
                await db.delete(book)
        await db.commit()
        count = len(req.book_ids)
    else:
        target = BookStatus.APPROVED if req.action == "approve" else BookStatus.REJECTED
        for bid in req.book_ids:
            book = await db.get(Book, bid)
            if book:
                book.status = target
                if req.action == "approve":
                    book.license_verified = True
                count += 1
        await db.commit()

    return {"affected": count, "action": req.action}


@router.get("/bundles/{bundle_id}/books", response_model=None)
async def get_bundle_books(
    bundle_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List books in a bundle with pagination for the admin UI."""
    bundle = await db.get(Bundle, bundle_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")

    stmt = (
        select(Book.id, Book.title, Book.author, Book.source, Book.status)
        .join(BundleBook, Book.id == BundleBook.book_id)
        .where(BundleBook.bundle_id == bundle_id)
        .order_by(BundleBook.sort_order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0

    return {
        "items": [
            {"id": r[0], "title": r[1], "author": r[2], "source": r[3], "status": r[4]}
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/categories")
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """List all book categories and counts."""
    rows = (await db.execute(
        select(Book.category, func.count(Book.id).label("count"))
        .where(Book.status == BookStatus.APPROVED)
        .group_by(Book.category)
        .order_by(func.count(Book.id).desc())
    )).all()
    return [{"category": r[0], "count": r[1]} for r in rows if r[0]]