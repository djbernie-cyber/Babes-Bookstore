from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from typing import Optional, List
from pydantic import BaseModel
import time

from .deps import get_db, require_admin
from ...models.book import Book, BookStatus
from ...models.bundle import Bundle, BundleBook
from ...models.purchase import Purchase, PurchaseStatus
from ...models.refund import Refund, RefundStatus
from ...models.user import User
from ...models.audit import AuditLog
from ...sources import source_registry
from ...services.audit import log_action
from ...services import mpesa_b2c

router = APIRouter(prefix="/admin", tags=["admin"])


def _task_in_flight(name: str, first_arg: str | None = None) -> str | None:
    """Return the id of a worker task that is active or queued (reserved).

    Guards against stacking duplicate scraping/retag jobs from repeated
    dashboard clicks while a run is still in progress. Best-effort: if the
    broker is unreachable we err on the side of allowing the enqueue.
    """
    try:
        from celery import current_app as _celery
        insp = _celery.control.inspect()
        for bucket in (insp.active(), insp.reserved()):
            if not bucket:
                continue
            for _worker, tasks in bucket.items():
                for t in tasks or []:
                    if t.get("name") != name:
                        continue
                    if first_arg is not None:
                        args = t.get("args") or []
                        if not args or args[0] != first_arg:
                            continue
                    return t.get("id")
    except Exception:
        return None
    return None


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


@router.post("/backfill/covers")
async def trigger_cover_backfill(
    limit: int = Query(2000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Fill missing book covers from Open Library in the background.

    Scans approved books with ``cover_path IS NULL`` and stores a cover URL
    for each (bounded, batched, with backoff). Idempotent: books already
    covered (or sentineled) are skipped.
    """
    from ...tasks.backfill_covers import backfill_covers_task
    existing = _task_in_flight("covers.backfill")
    if existing:
        return {"task_id": existing, "already_running": True}
    task = backfill_covers_task.delay(limit)
    await log_action(
        db, action="backfill.covers", entity_type="book",
        user_id=admin.id, details={"limit": limit},
    )
    return {"task_id": task.id, "limit": limit}


@router.post("/scrape/source/{source_name}")
async def trigger_source_scrape(
    source_name: str,
    query: str = "",
    limit: int = 20,
    start_page: int = 1,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if source_name not in source_registry.list_names():
        raise HTTPException(status_code=404, detail=f"Source '{source_name}' not found")

    from ...tasks.scrape import scrape_source_task
    existing = _task_in_flight("scrape.source", source_name)
    if existing:
        return {"task_id": existing, "source": source_name, "already_running": True}
    task = scrape_source_task.delay(source_name, query, limit, start_page)
    await log_action(
        db, action="scrape.source", entity_type="source",
        user_id=admin.id, details={"source": source_name, "query": query, "limit": limit},
    )
    return {"task_id": task.id, "source": source_name}


@router.post("/scrape/all")
async def trigger_all_scrape(
    query: str = "",
    limit_per_source: int = 50,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from ...tasks.scrape import scrape_all_sources_task
    existing = _task_in_flight("scrape.all_sources")
    if existing:
        return {"task_id": existing, "already_running": True}
    task = scrape_all_sources_task.delay(query, limit_per_source)
    await log_action(
        db, action="scrape.all", entity_type="source",
        user_id=admin.id, details={"query": query, "limit_per_source": limit_per_source},
    )
    return {"task_id": task.id}


@router.post("/scrape/popular")
async def trigger_popular_scrape(
    limit_per_source: int = 50,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from ...tasks.scrape import scrape_popular_task
    existing = _task_in_flight("scrape.popular")
    if existing:
        return {"task_id": existing, "already_running": True}
    task = scrape_popular_task.delay(limit_per_source)
    await log_action(
        db, action="scrape.popular", entity_type="source",
        user_id=admin.id, details={"limit_per_source": limit_per_source},
    )
    return {"task_id": task.id}


@router.post("/scrape/gutenberg-full")
async def trigger_gutenberg_full(
    limit: Optional[int] = Query(None, ge=1, description="Total books to harvest (omit for the full catalogue)"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Kick off a full English public-domain Gutenberg catalogue harvest.

    With no ``limit`` this ingests the whole ~74k English set, committed in
    bounded chunks by the task. Use with caution; prefer a ``limit`` when
    testing.
    """
    from ...tasks.scrape import scrape_gutenberg_full_task
    existing = _task_in_flight("scrape.gutenberg_full")
    if existing:
        return {"task_id": existing, "already_running": True}
    task = scrape_gutenberg_full_task.delay(limit)
    await log_action(
        db, action="scrape.gutenberg_full", entity_type="source",
        user_id=admin.id, details={"limit": limit},
    )
    return {"task_id": task.id, "full_catalogue": limit is None}


@router.post("/scrape/african-full")
async def trigger_african_full(
    limit: Optional[int] = Query(None, ge=1, description="Total African books to harvest (omit for the full African set)"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Expand the African Literature shelf from the curated canon to the full
    set of English public-domain Africa-themed Gutenberg works."""
    from ...tasks.scrape import scrape_african_full_task
    existing = _task_in_flight("scrape.african_full")
    if existing:
        return {"task_id": existing, "already_running": True}
    task = scrape_african_full_task.delay(limit)
    await log_action(
        db, action="scrape.african_full", entity_type="source",
        user_id=admin.id, details={"limit": limit},
    )
    return {"task_id": task.id, "full_catalogue": limit is None}


@router.post("/scrape/suppressed-full")
async def trigger_suppressed_full(
    limit: Optional[int] = Query(None, ge=1, description="Total suppressed books to harvest (omit for the full banned-books set)"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Expand the Suppressed Classics shelf to every public-domain banned book
    by the banned/condemned author canon (author-priority Gutenberg sweep)."""
    from ...tasks.scrape import scrape_suppressed_full_task
    existing = _task_in_flight("scrape.suppressed_full")
    if existing:
        return {"task_id": existing, "already_running": True}
    task = scrape_suppressed_full_task.delay(limit)
    await log_action(
        db, action="scrape.suppressed_full", entity_type="source",
        user_id=admin.id, details={"limit": limit},
    )
    return {"task_id": task.id, "full_catalogue": limit is None}


@router.post("/scrape/full")
async def trigger_full_catalogue(
    pages_per_source: int = Query(60, ge=1, le=500, description="Pages walked per non-Gutenberg source"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Bull path toward 90k: run the full English Gutenberg catalogue, the full
    African Literature shelf (author-priority), and multi-page walks of every
    other public source in parallel. The combined, deduped result is reported
    honestly — the licensed public-domain English corpus tops out in the high
    seventies to mid-eighties thousands, not a guaranteed flat 90,000."""
    from ...tasks.scrape import scrape_full_catalogue_task
    existing = _task_in_flight("scrape.full_catalogue")
    if existing:
        return {"task_id": existing, "already_running": True}
    task = scrape_full_catalogue_task.delay(pages_per_source=pages_per_source)
    await log_action(
        db, action="scrape.full", entity_type="source",
        user_id=admin.id, details={"pages_per_source": pages_per_source},
    )
    return {"task_id": task.id, "full_catalogue": True}


@router.post("/verify/licenses")
async def trigger_license_verification(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from ...tasks.verify_licenses import verify_all_licenses_task
    existing = _task_in_flight("verify.licenses.all")
    if existing:
        return {"task_id": existing, "already_running": True}
    task = verify_all_licenses_task.delay()
    await log_action(db, action="verify.licenses", entity_type="book", user_id=admin.id)
    return {"task_id": task.id}


@router.post("/audit/license-sources")
async def trigger_license_source_audit(
    source: Optional[str] = Query(None, description="Restrict to one source, e.g. standard_ebooks"),
    limit: int = Query(200, ge=1, le=5000, description="Max books to re-check in this pass"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Re-verify approved books against their declared source URL.

    Fabricated source ids (modern novels passed off as public domain) fail the
    check and are hard-rejected. Runs synchronously for the bounded ``limit``;
    the full sweep is run from the prod container script.
    """
    from ...services.license_audit import audit_approved_books
    report = await audit_approved_books(db, source=source, limit=limit)
    await log_action(
        db, action="audit.license_sources", entity_type="book",
        user_id=admin.id, details={"source": source, "limit": limit, **report},
    )
    return report


@router.post("/retag/african-literature")
async def trigger_african_retag(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Backfill 'African Literature' tags on existing approved books."""
    from ...tasks.scrape import retag_african_literature_task
    existing = _task_in_flight("retag.african_literature")
    if existing:
        return {"task_id": existing, "already_running": True}
    task = retag_african_literature_task.delay()
    await log_action(db, action="retag.african_literature", entity_type="book", user_id=admin.id)
    return {"task_id": task.id}


@router.get("/reviews")
async def list_all_reviews(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    book_id: Optional[int] = Query(None),
):
    """List reviews for moderation — optionally filter by book_id."""
    from ...models.review import Review
    from ...models.book import Book

    stmt = select(Review, User.name, Book.title).join(User, Review.user_id == User.id).join(Book, Review.book_id == Book.id)
    if book_id:
        stmt = stmt.where(Review.book_id == book_id)
    stmt = stmt.order_by(Review.created_at.desc())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0
    result = await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    rows = result.all()

    return {
        "items": [
            {
                "id": r.id,
                "book_id": r.book_id,
                "book_title": title,
                "user_id": r.user_id,
                "user_name": name,
                "rating": r.rating,
                "title": r.title,
                "body": r.body,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r, name, title in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.delete("/reviews/{review_id}")
async def delete_review_admin(
    review_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Delete any review (admin moderation)."""
    from ...models.review import Review
    review = await db.get(Review, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    await db.delete(review)
    await db.commit()
    await log_action(
        db, action="review.delete", entity_type="review",
        user_id=admin.id, details={"review_id": review_id, "book_id": review.book_id},
    )
    return {"deleted": True, "review_id": review_id}


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
    stmt = select(Purchase, Bundle).outerjoin(Bundle, Purchase.bundle_id == Bundle.id).order_by(Purchase.created_at.desc())
    count_stmt = select(func.count(Purchase.id))
    if status_filter:
        stmt = stmt.where(Purchase.status == status_filter)
        count_stmt = count_stmt.where(Purchase.status == status_filter)
    total = (await db.execute(count_stmt)).scalar() or 0
    result = await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    rows = result.all()

    return {
        "items": [
            {
                "id": p.id,
                "bundle_id": p.bundle_id,
                "bundle_name": b.name if b else None,
                "user_id": p.user_id,
                "customer_email": p.customer_email,
                "customer_phone": p.customer_phone,
                "amount_cents": p.amount_cents,
                "currency": p.currency,
                "status": p.status.value if hasattr(p.status, 'value') else str(p.status),
                "payment_provider": p.payment_provider.value if hasattr(p.payment_provider, 'value') else p.payment_provider,
                "download_count": p.download_count,
                "max_downloads": p.max_downloads,
                "zip_path": p.zip_path,
                "created_at": p.created_at.isoformat(),
            }
            for p, b in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/books/bulk")
async def bulk_book_action(
    req: BulkBookAction,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
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
                count += 1
        await db.commit()
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

    await log_action(
        db,
        action=f"book.bulk_{req.action}",
        entity_type="book",
        user_id=admin.id,
        details={"book_ids": req.book_ids, "affected": count},
    )
    await db.commit()
    return {"affected": count, "action": req.action}


@router.post("/books/approve-all")
async def approve_all_pending_books(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Approve every pending book in a single pass."""
    result = await db.execute(
        update(Book)
        .where(Book.status == BookStatus.PENDING)
        .values(status=BookStatus.APPROVED, license_verified=True)
    )
    count = result.rowcount or 0
    await log_action(
        db,
        action="book.approve_all",
        entity_type="book",
        user_id=admin.id,
        details={"affected": count},
    )
    await db.commit()
    return {"affected": count, "action": "approve"}


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


@router.post("/bundles/{bundle_id}/rebuild")
async def rebuild_bundle(
    bundle_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Regenerate a bundle's ZIP from its current contents in the background.

    Individual book files are served from the per-book cache where present, so
    the rebuild is fast and doesn't re-download the source archive. Use after
    editing a bundle's book list or to refresh files that were unavailable.
    """
    bundle = await db.get(Bundle, bundle_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")

    from ...tasks.package_bundle import rebuild_bundle_task
    task = rebuild_bundle_task.delay(bundle_id)
    await log_action(
        db, action="bundle.rebuild", entity_type="bundle",
        entity_id=bundle_id, user_id=admin.id,
        details={"bundle_slug": bundle.slug},
    )
    return {"task_id": task.id, "bundle_id": bundle_id, "slug": bundle.slug, "status": "queued"}


@router.post("/bundles/randomise")
async def randomise_bundles(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Re-randomise the membership of every active curated (system) bundle.

    Each curated bundle is re-picked from the approved, licence-verified
    catalogue, preferring books whose tags/category match the bundle's theme,
    then the affected ZIPs are rebuilt in the background. Custom bundles are
    never touched. Single in-flight guard prevents stacking redundant runs.
    """
    from ...tasks.bundle_randomise import randomise_system_bundles_task

    task = _task_in_flight("services.randomise_system_bundles")
    if task:
        raise HTTPException(status_code=409, detail=f"Randomisation already in progress ({task}")

    t = randomise_system_bundles_task.delay()
    await log_action(
        db, action="bundle.randomise", entity_type="bundle",
        entity_id=None, user_id=admin.id,
        details={"status": "queued", "task_id": t.id},
    )
    return {"task_id": t.id, "status": "queued"}


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


@router.get("/books/bulk")
async def list_books_bulk(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
    category: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
):
    """Return a flat list of book IDs + titles for bulk bundle assignment."""
    stmt = select(Book.id, Book.title, Book.author, Book.category, Book.source).where(Book.status == BookStatus.APPROVED)
    if category:
        stmt = stmt.where(Book.category == category)
    stmt = stmt.order_by(Book.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).all()
    return [
        {"id": r[0], "title": r[1], "author": r[2], "category": r[3], "source": r[4]}
        for r in rows
    ]


@router.get("/bundle-categories")
async def get_bundle_categories(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """List distinct bundle categories for filtering."""
    rows = (await db.execute(
        select(Bundle.category, func.count(Bundle.id).label("count"))
        .where(Bundle.category.isnot(None), Bundle.active == True)
        .group_by(Bundle.category)
        .order_by(func.count(Bundle.id).desc())
    )).all()
    return [{"category": r[0], "count": r[1]} for r in rows if r[0]]


@router.get("/audit-log")
async def list_audit_log(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action_filter: Optional[str] = Query(None, alias="action"),
    entity_filter: Optional[str] = Query(None, alias="entity"),
):
    """List audit log entries with pagination and optional filters."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    count_stmt = select(func.count()).select_from(AuditLog)

    if action_filter:
        stmt = stmt.where(AuditLog.action == action_filter)
        count_stmt = count_stmt.where(AuditLog.action == action_filter)
    if entity_filter:
        stmt = stmt.where(AuditLog.entity_type == entity_filter)
        count_stmt = count_stmt.where(AuditLog.entity_type == entity_filter)

    total = (await db.execute(count_stmt)).scalar() or 0
    result = await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    rows = result.scalars().all()

    return {
        "items": [
            {
                "id": r.id,
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "user_id": r.user_id,
                "details": r.details,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ─── M-Pesa B2Pochi refunds ─────────────────────────────────────────────


def _normalise_ke_phone(raw: str | None) -> str | None:
    p = (raw or "").strip().replace(" ", "").replace("-", "")
    if not p:
        return None
    if p.startswith("+"):
        p = p[1:]
    if p.startswith("0"):
        p = "254" + p[1:]
    if p.startswith("7") and len(p) == 9:
        p = "254" + p
    return p if (p.startswith("254") and len(p) == 12) else None


def _refund_dict(r: Refund) -> dict:
    return {
        "id": r.id,
        "purchase_id": r.purchase_id,
        "amount": r.amount_cents,
        "currency": r.currency,
        "status": r.status,
        "originator_conversation_id": r.originator_conversation_id,
        "conversation_id": r.conversation_id,
        "transaction_id": r.transaction_id,
        "result_code": r.result_code,
        "result_desc": r.result_desc,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/refunds")
async def list_refunds(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    total = (await db.execute(select(func.count(Refund.id)))).scalar() or 0
    rows = (await db.execute(
        select(Refund).order_by(Refund.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {"items": [_refund_dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/purchases/{purchase_id}/refund")
async def refund_purchase(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Refund a paid M-Pesa purchase to the customer's Pochi wallet.

    Creates a Refund record keyed by a unique OriginatorConversationID
    (Daraja's idempotency key) then submits a B2Pochi payout. The final
    outcome arrives on the b2pochi webhook; this call returns the
    accepted-but-unsettled refund.
    """
    purchase = await db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    if (purchase.payment_provider or "").lower() != "mpesa":
        raise HTTPException(status_code=400, detail="Only M-Pesa purchases can be refunded via B2Pochi")
    if purchase.status not in (PurchaseStatus.PAID, PurchaseStatus.COMPLETED):
        raise HTTPException(status_code=400, detail="Only paid purchases can be refunded")

    phone = _normalise_ke_phone(purchase.customer_phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Purchase has no valid M-Pesa phone on record")

    existing = (await db.execute(
        select(Refund).where(
            Refund.purchase_id == purchase_id,
            Refund.status.in_([RefundStatus.PENDING, RefundStatus.PROCESSING, RefundStatus.SUCCEEDED]),
        )
    )).scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Refund already {existing.status} for this purchase")

    # KES shillings (no cents). Matches the STK conversion rate (1 GBP ≈ 170 KES).
    kes_amount = max(10, int(round((purchase.amount_cents / 100) * 170)))

    refund = Refund(
        purchase_id=purchase.id,
        amount_cents=kes_amount,
        currency="kes",
        customer_phone=phone,
        status=RefundStatus.PENDING,
        originator_conversation_id=f"BBREF-{purchase.id}-{int(time.time())}",
    )
    db.add(refund)
    await db.commit()
    await db.refresh(refund)

    ack = await mpesa_b2c.submit_b2pochi(refund, phone)
    response_code = str(ack.get("ResponseCode", "")).strip()
    refund.conversation_id = ack.get("ConversationID") or refund.conversation_id
    if response_code == "0":
        refund.status = RefundStatus.PROCESSING
        refund.result_desc = ack.get("ResponseDescription")
    else:
        refund.status = RefundStatus.FAILED
        refund.result_code = response_code or "ERR"
        refund.result_desc = ack.get("ResponseDescription") or ack.get("errorMessage") or "Rejected by Daraja"
    await db.commit()
    await db.refresh(refund)

    await log_action(
        db,
        action="refund_mpesa",
        entity_type="purchase",
        entity_id=purchase.id,
        user_id=admin.id,
        details={"refund_id": refund.id, "amount": kes_amount, "status": refund.status},
    )
    return _refund_dict(refund)