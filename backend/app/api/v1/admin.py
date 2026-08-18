from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from .deps import get_db, require_admin
from ...models.book import Book, BookStatus
from ...models.bundle import Bundle
from ...models.purchase import Purchase
from ...models.user import User
from ...sources import source_registry

router = APIRouter(prefix="/admin", tags=["admin"])


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
        await db.execute(select(func.sum(Purchase.amount_cents)).where(Purchase.status == "completed"))
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
    _admin=Depends(require_admin),
):
    if source_name not in source_registry.list_names():
        raise HTTPException(status_code=404, detail=f"Source '{source_name}' not found")

    from ...tasks.scrape import scrape_source_task
    task = scrape_source_task.delay(source_name, query, limit)
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