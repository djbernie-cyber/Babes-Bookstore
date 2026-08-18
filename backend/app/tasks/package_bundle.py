import asyncio
import logging
from datetime import datetime, timedelta

from ..celery_app import celery_app
from ..database import AsyncSessionLocal
from ..models.book import Book, BookStatus
from ..models.bundle import Bundle
from ..models.purchase import Purchase
from ..services.packaging import packaging
from sqlalchemy import select

logger = logging.getLogger(__name__)


@celery_app.task(name="package.bundle")
def package_bundle_task(purchase_id: int) -> dict:
    """Package a bundle ZIP for a purchase."""
    return asyncio.run(_package_bundle_async(purchase_id))


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
            purchase.status = "completed"
            purchase.download_expires_at = datetime.utcnow() + timedelta(hours=24)
            await session.commit()

            from ..services.email_service import email_service
            from ..services.storage import storage

            signed_url = storage.get_signed_url(zip_key, expires_in=86400)
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
                "status": "completed",
            }
        except Exception as e:
            logger.error(f"Packaging failed for purchase {purchase_id}: {e}")
            purchase.status = "failed"
            await session.commit()
            return {"error": str(e)}