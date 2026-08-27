import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from .deps import get_db, get_current_user
from ...models.bundle import Bundle
from ...models.purchase import Purchase, PurchaseStatus
from ...models.user import User
from ...config import settings
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/purchases", tags=["purchases"])


class PurchaseListItem(BaseModel):
    id: int
    bundle_id: int
    bundle_name: str
    bundle_slug: str
    amount_cents: int
    currency: str
    status: str
    download_available: bool
    download_token: str
    download_expires_at: Optional[datetime] = None
    created_at: datetime


def _download_available(purchase: Purchase) -> bool:
    return (
        purchase.status == PurchaseStatus.COMPLETED
        and bool(purchase.zip_path)
        and purchase.download_expires_at is not None
        and purchase.download_count < purchase.max_downloads
    )


@router.get("", response_model=list[PurchaseListItem])
async def list_my_purchases(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    stmt = (
        select(Purchase, Bundle)
        .join(Bundle, Purchase.bundle_id == Bundle.id)
        .where(Purchase.user_id == current_user.id)
        .order_by(Purchase.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        PurchaseListItem(
            id=p.id,
            bundle_id=b.id,
            bundle_name=b.name,
            bundle_slug=b.slug,
            amount_cents=p.amount_cents,
            currency=p.currency,
            status=p.status,
            download_available=_download_available(p),
            download_token=p.download_token,
            download_expires_at=p.download_expires_at,
            created_at=p.created_at,
        )
        for p, b in rows
    ]


@router.get("/storage/{key:path}")
async def serve_storage_file(key: str):
    """Serve a bundle ZIP from local filesystem fallback (when R2 not configured).

    The key is obscured (bundle id + timestamp) and download availability is
    still gated by the purchase token at /{purchase_id}/download, so this
    endpoint can be public.
    """
    from ..services.storage import storage

    # Prevent traversal
    if ".." in key or key.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid key")
    local = storage._local_path(key)
    if not os.path.exists(local):
        raise HTTPException(status_code=404, detail="File not found — bundle may still be packaging, try again in 30s")
    return FileResponse(local, filename=os.path.basename(local), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{os.path.basename(local)}"'})


@router.get("/{purchase_id}/download")
async def get_download_link(
    purchase_id: int,
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    purchase = await db.get(Purchase, purchase_id)
    if not purchase or purchase.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Purchase not found")
    if token != purchase.download_token:
        raise HTTPException(status_code=403, detail="Invalid download token")
    # On-demand packaging for old purchases created before the fix or
    # when the async worker was blocked — ensures same-device download
    # works even if zip_path is missing.
    if not _download_available(purchase):
        # Attempt to package now if the purchase is completed but zip missing/expired
        if purchase.status == PurchaseStatus.COMPLETED and purchase.download_count < purchase.max_downloads:
            try:
                from sqlalchemy.orm import selectinload
                from ..models.bundle import BundleBook
                from ..services.packaging import packaging
                from datetime import timedelta
                bundle = await db.get(Bundle, purchase.bundle_id)
                if bundle:
                    await db.refresh(bundle, ["bundle_books"])
                    # Ensure books are loaded
                    stmt = select(Bundle).options(selectinload(Bundle.bundle_books).selectinload(BundleBook.book)).where(Bundle.id == bundle.id)
                    bundle = (await db.execute(stmt)).unique().scalar_one()
                    books = [bb.book for bb in bundle.bundle_books if bb.book and bb.book.status.value == "approved"]
                    if books:
                        key = packaging.create_bundle_zip(bundle, books)
                        if key:
                            purchase.zip_path = key
                            purchase.download_expires_at = datetime.utcnow() + timedelta(hours=settings.DOWNLOAD_WINDOW_HOURS)
                            await db.commit()
                            await db.refresh(purchase)
            except Exception as e:
                import logging; logging.getLogger(__name__).warning("On-demand packaging failed for purchase %s: %s", purchase_id, e)
        if not _download_available(purchase):
            raise HTTPException(status_code=403, detail="Download not available — bundle is still packaging, try again in 30s")

    from ..services.storage import storage

    url = storage.get_signed_url(
        purchase.zip_path, expires_in=settings.DOWNLOAD_WINDOW_HOURS * 3600
    )
    if not url:
        raise HTTPException(status_code=503, detail="Download storage is not configured")

    purchase.download_count += 1
    await db.commit()
    return {"url": url, "expires_at": purchase.download_expires_at}
