from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.orm import selectinload
from typing import Optional, List

from fastapi import status
import re

from .deps import get_db, get_current_user, require_admin
from ...models.bundle import Bundle, BundleBook
from ...models.book import Book, BookStatus
from ...models.user import User
from ...schemas.bundle import (
    BundleCreate,
    BundleUpdate,
    BundleResponse,
    BundleListResponse,
    BundleBookResponse,
)


def _serialize_books(bundle: Bundle) -> list[BundleBookResponse]:
    """Map a bundle's ordered books to response models."""
    return [
        BundleBookResponse(
            id=bb.book.id,
            title=bb.book.title,
            author=bb.book.author,
            cover_path=bb.book.cover_path,
        )
        for bb in bundle.bundle_books
        if bb.book is not None
    ]

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
    filters = []
    if active_only:
        filters.append(Bundle.active == True)
    if category:
        filters.append(Bundle.category == category)
    if featured is not None:
        filters.append(Bundle.featured == featured)

    count_stmt = select(func.count(Bundle.id))
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = select(Bundle).options(
        selectinload(Bundle.bundle_books).selectinload(BundleBook.book)
    )
    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.order_by(Bundle.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    bundles = result.scalars().unique().all()

    items = []
    for b in bundles:
        b_data = BundleResponse.model_validate(b)
        b_data.books = _serialize_books(b)
        items.append(b_data)

    return BundleListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{bundle_id_or_slug}", response_model=BundleResponse)
async def get_bundle(bundle_id_or_slug: str, db: AsyncSession = Depends(get_db)):
    ref = bundle_id_or_slug.strip()
    if ref.isdigit():
        # Guard against values outside a signed 64-bit integer, which would
        # otherwise raise an OverflowError inside the database driver.
        value = int(ref)
        if value > 2**63 - 1:
            raise HTTPException(status_code=404, detail="Bundle not found")
        criterion = Bundle.id == value
    else:
        criterion = Bundle.slug == ref

    stmt = select(Bundle).options(
        selectinload(Bundle.bundle_books).selectinload(BundleBook.book)
    ).where(criterion)
    bundle = (await db.execute(stmt)).unique().scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")

    b_data = BundleResponse.model_validate(bundle)
    b_data.books = _serialize_books(bundle)
    return b_data


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s) or "bundle"


@router.post("/custom", response_model=BundleResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_bundle(
    bundle_in: BundleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """Create a user-curated custom bundle (no admin required).

    Authenticated users get a persistent bundle; anonymous users may still
    create a one-off custom bundle that is immediately purchasable.
    Custom bundles are always priced at the standard price and marked
    bundle_type='custom'.
    """
    from ...config import settings as _settings

    if not bundle_in.book_ids or len(bundle_in.book_ids) < 3:
        raise HTTPException(status_code=400, detail="Pick at least 3 books")
    if len(bundle_in.book_ids) > 40:
        raise HTTPException(status_code=400, detail="Custom bundles are limited to 40 books")

    # Normalise slug and ensure uniqueness
    base = _slugify(bundle_in.slug or bundle_in.name)
    slug = base
    suffix = 2
    while (await db.execute(select(Bundle).where(Bundle.slug == slug))).scalar_one_or_none():
        slug = f"{base}-{suffix}"
        suffix += 1

    bundle = Bundle(
        name=bundle_in.name.strip()[:200],
        slug=slug,
        description=bundle_in.description,
        long_description=bundle_in.long_description,
        price_cents=_settings.STANDARD_PRICE_PENCE,
        currency=_settings.CURRENCY,
        cover_image_path=bundle_in.cover_image_path,
        category=bundle_in.category or "Custom",
        tags=bundle_in.tags,
        bundle_type="custom",
        meta_title=bundle_in.meta_title,
        meta_description=bundle_in.meta_description,
        active=True,
        featured=False,
    )
    db.add(bundle)
    await db.flush()

    for i, book_id in enumerate(bundle_in.book_ids[:40]):
        book = await db.get(Book, book_id)
        if not book:
            continue
        db.add(BundleBook(bundle_id=bundle.id, book_id=book_id, sort_order=i))

    await db.commit()
    await db.refresh(bundle, ["bundle_books"])

    reloaded = (
        await db.execute(
            select(Bundle)
            .options(selectinload(Bundle.bundle_books).selectinload(BundleBook.book))
            .where(Bundle.id == bundle.id)
            .execution_options(populate_existing=True)
        )
    ).unique().scalar_one()

    b_data = BundleResponse.model_validate(reloaded)
    b_data.books = _serialize_books(reloaded)
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
        currency=bundle_in.currency,
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
    await db.refresh(bundle, ["bundle_books"])

    reloaded = (await db.execute(
        select(Bundle).options(
            selectinload(Bundle.bundle_books).selectinload(BundleBook.book)
        ).where(Bundle.id == bundle.id).execution_options(populate_existing=True)
    )).unique().scalar_one()

    b_data = BundleResponse.model_validate(reloaded)
    b_data.books = _serialize_books(reloaded)
    return b_data


@router.patch("/{bundle_id}", response_model=BundleResponse)
async def update_bundle(
    bundle_id: int,
    update: BundleUpdate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    bundle = (await db.execute(
        select(Bundle).options(selectinload(Bundle.bundle_books)).where(Bundle.id == bundle_id)
    )).unique().scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")

    data = update.model_dump(exclude_unset=True)
    book_ids = data.pop("book_ids", None)

    for k, v in data.items():
        setattr(bundle, k, v)

    if book_ids is not None:
        # Bulk-delete via the Core API: ORM session.delete() would lazily load
        # BundleBook.book outside the async context (MissingGreenlet).
        await db.execute(sa_delete(BundleBook).where(BundleBook.bundle_id == bundle_id))
        await db.flush()
        for i, book_id in enumerate(book_ids):
            book = await db.get(Book, book_id)
            if not book:
                continue
            db.add(BundleBook(bundle_id=bundle.id, book_id=book_id, sort_order=i))

    await db.commit()

    reloaded = (await db.execute(
        select(Bundle).options(
            selectinload(Bundle.bundle_books).selectinload(BundleBook.book)
        ).where(Bundle.id == bundle_id).execution_options(populate_existing=True)
    )).unique().scalar_one()

    b_data = BundleResponse.model_validate(reloaded)
    b_data.books = _serialize_books(reloaded)
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