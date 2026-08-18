import asyncio
import logging
from datetime import datetime

from ..celery_app import celery_app
from ..database import AsyncSessionLocal
from ..models.book import Book, BookStatus
from ..services.license_verifier import license_verifier, LicenseStatus
from sqlalchemy import select

logger = logging.getLogger(__name__)


@celery_app.task(name="verify.licenses.all")
def verify_all_licenses_task() -> dict:
    """Re-verify licenses for all pending books."""
    return asyncio.run(_verify_all_async())


async def _verify_all_async() -> dict:
    approved = 0
    rejected = 0
    pending = 0

    async with AsyncSessionLocal() as session:
        stmt = select(Book).where(Book.status == BookStatus.PENDING)
        books = (await session.execute(stmt)).scalars().all()

        for book in books:
            result = license_verifier.verify(book.license_type, book.license_url)
            book.verified_at = datetime.utcnow()

            if result.status == LicenseStatus.APPROVED:
                book.license_verified = True
                approved += 1
            elif result.status == LicenseStatus.REJECTED:
                book.status = BookStatus.REJECTED
                rejected += 1
            else:
                pending += 1

        await session.commit()

    return {"approved": approved, "rejected": rejected, "pending": pending}


@celery_app.task(name="verify.license.single")
def verify_single_book_task(book_id: int) -> dict:
    """Verify license for a single book."""
    return asyncio.run(_verify_single_async(book_id))


async def _verify_single_async(book_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        book = await session.get(Book, book_id)
        if not book:
            return {"error": "Book not found"}

        result = license_verifier.verify(book.license_type, book.license_url)
        book.verified_at = datetime.utcnow()

        if result.status == LicenseStatus.APPROVED:
            book.license_verified = True
            book.status = BookStatus.PENDING
        elif result.status == LicenseStatus.REJECTED:
            book.status = BookStatus.REJECTED

        await session.commit()

        return {
            "book_id": book.id,
            "status": result.status.value,
            "license_type": result.license_type,
            "reason": result.reason,
        }