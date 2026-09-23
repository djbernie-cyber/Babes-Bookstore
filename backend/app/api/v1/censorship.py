"""Banned-books-by-country engine: the 'Illegal Books Catalog' data layer.

Public endpoints explain *why* works are banned and let readers flag new
candidates; super-admins verify flags into records. Books themselves are
never withheld — censorship records exist to inform the reader's decision.

Search matches the public books API so records only surface for approved,
licence-verified books that are actually on the shelves.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from .deps import get_db, get_current_user, require_superadmin
from ...models.book import Book, BookStatus
from ...models.censorship import CensorshipRecord, CensorshipStatus
from ...models.user import User
from ...services.audit import log_action

router = APIRouter(prefix="/banned", tags=["banned"])
admin_router = APIRouter(prefix="/admin/banned-records", tags=["banned"])


def _record_dict(r: CensorshipRecord) -> dict:
    return {
        "id": r.id,
        "book_id": r.book_id,
        "country_code": r.country_code,
        "country_name": r.country_name or r.country_code,
        "status": r.status,
        "ban_reason": r.ban_reason,
        "banned_since": r.banned_since,
        "source_url": r.source_url,
        "verified": r.verified,
    }


def _book_dict(b: Book) -> dict:
    return {
        "id": b.id,
        "title": b.title,
        "author": b.author,
        "cover_url": b.cover_path if (b.cover_path and b.cover_path.startswith("http")) else None,
        "category": b.category,
        "publication_year": b.publication_year,
        "tags": b.tags or [],
    }


class FlagRequest(BaseModel):
    reason: str = Field(min_length=4, max_length=1000)
    country_code: str = Field(min_length=2, max_length=2)
    status: str = CensorshipStatus.BANNED


@router.get("/records")
async def banned_records(
    country: str = "",
    q: str = "",
    status: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Books with censorship records, joined to their 'why banned' stories.

    Filters: country (alpha-2), text query (title/author), record status.
    Only verified records for approved books are listed.
    """
    stmt = (select(CensorshipRecord, Book)
            .join(Book, Book.id == CensorshipRecord.book_id)
            .where(Book.status == BookStatus.APPROVED, Book.license_verified.is_(True),
                   CensorshipRecord.verified.is_(True)))
    if country:
        stmt = stmt.where(CensorshipRecord.country_code == country.upper())
    if status:
        stmt = stmt.where(CensorshipRecord.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(func.lower(Book.title).like(like.lower()),
                              func.lower(Book.author).like(like.lower())))
    rows = (await db.execute(stmt.order_by(CensorshipRecord.country_code, Book.title))).all()

    items = [{
        **_record_dict(r),
        "book": _book_dict(b),
    } for r, b in rows]
    return {"total": len(items), "items": items}


@router.get("/countries")
async def banned_countries(db: AsyncSession = Depends(get_db)):
    """Per-country rollups of banned/restricted/contested works."""
    rows = (await db.execute(
        select(CensorshipRecord.country_code,
               func.max(CensorshipRecord.country_name),
               CensorshipRecord.status,
               func.count(CensorshipRecord.id))
        .where(CensorshipRecord.verified.is_(True))
        .group_by(CensorshipRecord.country_code, CensorshipRecord.status)
    )).all()
    buckets: dict[str, dict] = {}
    for code, name, st, count in rows:
        bucket = buckets.setdefault(code, {"country_code": code, "country_name": name or code, "counts": {}})
        bucket["counts"][st] = count
        bucket["total"] = sum(bucket["counts"].values())
    return {"items": sorted(buckets.values(), key=lambda b: -b["total"])}


@router.get("/books/{book_id}")
async def book_banned_records(book_id: int, db: AsyncSession = Depends(get_db)):
    """Every censorship record attached to one book."""
    rows = (await db.execute(
        select(CensorshipRecord).where(
            CensorshipRecord.book_id == book_id,
            CensorshipRecord.verified.is_(True),
        ).order_by(CensorshipRecord.country_code)
    )).scalars().all()
    return {"book_id": book_id, "items": [_record_dict(r) for r in rows]}


@router.post("/books/{book_id}/flag")
async def flag_book(
    book_id: int,
    body: FlagRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Users propose a book for the catalog when they know where it is
    banned. Lands unverified in a super-admin review queue."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Login required to flag a book")
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    dup = (await db.execute(
        select(CensorshipRecord.id).where(
            CensorshipRecord.book_id == book_id,
            CensorshipRecord.country_code == body.country_code.upper(),
            CensorshipRecord.verified.is_(True),
        )
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="That country/ban is already on file")

    record = CensorshipRecord(
        book_id=book_id,
        country_code=body.country_code.upper(),
        status=body.status if body.status in (CensorshipStatus.BANNED, CensorshipStatus.RESTRICTED, CensorshipStatus.CONTESTED) else CensorshipStatus.BANNED,
        ban_reason=body.reason,
        verified=False,
        verified_by="user_flag",
        proposed_by=current_user.id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {**_record_dict(record), "pending_review": True}


@admin_router.get("")
async def admin_list_flags(
    db: AsyncSession = Depends(get_db),
    _super=Depends(require_superadmin),
    pending_only: bool = Query(True),
):
    rows = (await db.execute(
        select(CensorshipRecord, Book)
        .join(Book, Book.id == CensorshipRecord.book_id)
        .where((CensorshipRecord.verified.is_(False)) if pending_only else (CensorshipRecord.verified.is_(True) | CensorshipRecord.verified.is_(False)))
        .order_by(CensorshipRecord.created_at.desc())
    )).all()
    return {"items": [{**_record_dict(r), "book": _book_dict(b), "proposed_by": r.proposed_by} for r, b in rows]}


class ReviewFlag(BaseModel):
    action: str  # verify | reject
    ban_reason: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    status: str | None = None
    banned_since: str | None = None
    source_url: str | None = None


@admin_router.post("/{record_id}/review")
async def review_flag(
    record_id: int,
    body: ReviewFlag,
    db: AsyncSession = Depends(get_db),
    super: User = Depends(require_superadmin),
):
    record = await db.get(CensorshipRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if body.action not in ("verify", "reject"):
        raise HTTPException(status_code=422, detail="action must be verify or reject")

    if body.action == "reject":
        await db.delete(record)
        await db.commit()
        return {"ok": True, "deleted": True}

    if body.ban_reason is not None:
        record.ban_reason = body.ban_reason
    if body.country_code:
        record.country_code = body.country_code.upper()
    if body.country_name:
        record.country_name = body.country_name
    if body.status:
        record.status = body.status
    if body.banned_since:
        record.banned_since = body.banned_since
    if body.source_url:
        record.source_url = body.source_url
    record.verified = True
    record.verified_by = f"verified:{super.id}"
    record.proposed_by = None
    await db.commit()
    await db.refresh(record)
    await log_action(db, action="banned.verify", entity_type="censorship_record",
                     entity_id=record.id, user_id=super.id,
                     details={"country": record.country_code})
    return {**_record_dict(record), "verified": True}


@admin_router.delete("/{record_id}")
async def admin_delete_record(record_id: int, db: AsyncSession = Depends(get_db), super: User = Depends(require_superadmin)):
    record = await db.get(CensorshipRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    await db.delete(record)
    await db.commit()
    await log_action(db, action="banned.delete", entity_type="censorship_record",
                     entity_id=record_id, user_id=super.id, details={})
    return {"ok": True}