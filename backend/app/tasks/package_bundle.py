import asyncio
import logging
from datetime import datetime, timedelta

from ..celery_app import celery_app
from ..config import settings
from ..database import AsyncSessionLocal
from ..models.book import Book, BookStatus
from ..models.bundle import Bundle, BundleBook
from ..models.purchase import Purchase, PurchaseStatus
from ..services.packaging import packaging
from sqlalchemy import select

logger = logging.getLogger(__name__)


@celery_app.task(name="package.bundle")
def package_bundle_task(purchase_id: int) -> dict:
    """Package a bundle ZIP for a purchase."""
    return asyncio.run(_package_bundle_async(purchase_id))


@celery_app.task(name="package.rebuild_bundle")
def rebuild_bundle_task(bundle_id: int) -> dict:
    """Regenerate a bundle's ZIP from current contents (no purchase needed).

    Produces a fresh archive under a timestamped key. Because individual book
    files are now cached, rebuilds are fast and don't re-download the archive.
    Primarily used by admins after editing a bundle's book list or to refresh
    files that were previously unavailable.
    """
    return asyncio.run(_rebuild_bundle_async(bundle_id))


async def _rebuild_bundle_async(bundle_id: int) -> dict:
    from ..services.storage import storage

    async with AsyncSessionLocal() as session:
        from sqlalchemy.orm import selectinload
        bundle = (
            await session.execute(
                select(Bundle)
                .options(selectinload(Bundle.bundle_books).selectinload(BundleBook.book))
                .where(Bundle.id == bundle_id)
            )
        ).unique().scalar_one_or_none()
        if not bundle:
            return {"error": "Bundle not found"}
        books = [bb.book for bb in bundle.bundle_books if bb.book and bb.book.status == BookStatus.APPROVED]
        if not books:
            return {"error": "Bundle has no approved books"}
        try:
            zip_key = packaging.create_bundle_zip(bundle, books)
            from datetime import datetime
            from urllib.parse import quote
            base = (settings.PRODUCTION_URL or "").rstrip("/")
            url = storage.get_signed_url(zip_key, expires_in=3600)
            return {
                "bundle_id": bundle_id,
                "book_count": len(books),
                "zip_key": zip_key,
                "zip_url": url,
                "generated_at": datetime.utcnow().isoformat() + "Z",
            }
        except Exception as e:
            logger.error(f"Rebuild failed for bundle {bundle_id}: {e}")
            return {"error": str(e)}


async def _package_bundle_async(purchase_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        purchase = await session.get(Purchase, purchase_id)
        if not purchase:
            return {"error": "Purchase not found"}

        bundle = await session.get(Bundle, purchase.bundle_id)
        if not bundle:
            return {"error": "Bundle not found"}

        books = [bb.book for bb in bundle.bundle_books if bb.book.status == BookStatus.APPROVED]

        try:
            zip_key = packaging.create_bundle_zip(bundle, books)
            purchase.zip_path = zip_key
            purchase.status = PurchaseStatus.COMPLETED
            purchase.download_expires_at = datetime.utcnow() + timedelta(hours=settings.DOWNLOAD_WINDOW_HOURS)
            await session.commit()

            from ..services.email_service import email_service
            from ..services.storage import storage

            signed_url = storage.get_signed_url(zip_key, expires_in=settings.DOWNLOAD_WINDOW_HOURS * 3600)
            if purchase.customer_email and signed_url:
                email_service.send_purchase_confirmation(
                    to_email=purchase.customer_email,
                    bundle_name=bundle.name,
                    download_url=signed_url,
                )

            return {
                "purchase_id": purchase_id,
                "zip_path": zip_key,
                "book_count": len(books),
                "status": PurchaseStatus.COMPLETED,
            }
        except Exception as e:
            logger.error(f"Packaging failed for purchase {purchase_id}: {e}")
            purchase.status = PurchaseStatus.FAILED
            await session.commit()
            return {"error": str(e)}