from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List

from ..deps import get_db, require_admin
from ...models.bundle import Bundle, BundleBook
from ...models.book import Book, BookStatus
from ...schemas.bundle import (
    BundleCreate,
    BundleUpdate,
    BundleResponse,
    BundleListResponse,
)

router = APIRouter(prefix="/bundles", tags=["bundles"])


@router.get("", response_model=BundleListResponse)
async def list_bundles(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    featured: Optional[bool] = None,
    active_only: bool = True,
):
    stmt = select(Bundle)
    if active_only:
        stmt = stmt.where(Bundle.active == True)
    if category:
        stmt = stmt.where(Bundle.category == category)
    if featured is not None:
        stmt = stmt.where(Bundle.featured == featured)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar() or 0

    stmt = stmt.order_by(Bundle.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    bundles = result.scalars().all()

    items = []
    for b in bundles:
        b_data = BundleResponse.model_validate(b)
        b_data.books = [
            {
                "id": bb.book.id,
                "title": bb.book.title,
                "author": bb.book.author,
                "cover_path": bb.book.cover_path,
            }
            for bb in b.bundle_books
        ]
        items.append(b_data)

    return BundleListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{bundle_id_or_slug}", response_model=BundleResponse)
async def get_bundle(bundle_id_or_slug: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Bundle).where(
        (Bundle.id == int(bundle_id_or_slug)) if bundle_id_or_slug.isdigit() else (Bundle.slug == bundle_id_or_slug)
    )
    bundle = (await db.execute(stmt)).scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")

    b_data = BundleResponse.model_validate(bundle)
    b_data.books = [
        {
            "id": bb.book.id,
            "title": bb.book.title,
            "author": bb.book.author,
            "cover_path": bb.book.cover_path,
        }
        for bb in bundle.bundle_books
    ]
    return b_data


@router.post("", response_model=BundleResponse)
async def create_bundle(
    bundle_in: BundleCreate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    existing = await db.execute(select(Bundle).where(Bundle.slug == bundle_in.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Slug already exists")

    bundle = Bundle(
        name=bundle_in.name,
        slug=bundle_in.slug,
        description=bundle_in.description,
        long_description=bundle_in.long_description,
        price_cents=bundle_in.price_cents,
        cover_image_path=bundle_in.cover_image_path,
        category=bundle_in.category,
        tags=bundle_in.tags,
        bundle_type=bundle_in.bundle_type,
        meta_title=bundle_in.meta_title,
        meta_description=bundle_in.meta_description,
    )
    db.add(bundle)
    await db.flush()

    for i, book_id in enumerate(bundle_in.book_ids):
        book = await db.get(Book, book_id)
        if not book:
            continue
        bb = BundleBook(bundle_id=bundle.id, book_id=book_id, sort_order=i)
        db.add(bb)

    await db.commit()
    await db.refresh(bundle)

    b_data = BundleResponse.model_validate(bundle)
    b_data.books = [
        {
            "id": bb.book.id,
            "title": bb.book.title,
            "author": bb.book.author,
            "cover_path": bb.book.cover_path,
        }
        for bb in bundle.bundle_books
    ]
    return b_data


@router.patch("/{bundle_id}", response_model=BundleResponse)
async def update_bundle(
    bundle_id: int,
    update: BundleUpdate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    bundle = await db.get(Bundle, bundle_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")

    data = update.model_dump(exclude_unset=True)
    book_ids = data.pop("book_ids", None)

    for k, v in data.items():
        setattr(bundle, k, v)

    if book_ids is not None:
        for bb in bundle.bundle_books:
            await db.delete(bb)
        await db.flush()
        for i, book_id in enumerate(book_ids):
            bb = BundleBook(bundle_id=bundle.id, book_id=book_id, sort_order=i)
            db.add(bb)

    await db.commit()
    await db.refresh(bundle)

    b_data = BundleResponse.model_validate(bundle)
    b_data.books = [
        {
            "id": bb.book.id,
            "title": bb.book.title,
            "author": bb.book.author,
            "cover_path": bb.book.cover_path,
        }
        for bb in bundle.bundle_books
    ]
    return b_data


@router.delete("/{bundle_id}")
async def delete_bundle(
    bundle_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    bundle = await db.get(Bundle, bundle_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    await db.delete(bundle)
    await db.commit()
    return {"deleted": True}