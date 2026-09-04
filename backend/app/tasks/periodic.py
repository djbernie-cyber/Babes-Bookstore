"""Celery Beat periodic tasks — cleanup, maintenance, and housekeeping."""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from ..celery_app import celery_app
from ..database import AsyncSessionLocal
from ..models.purchase import Purchase, PurchaseStatus

logger = logging.getLogger(__name__)


@celery_app.task(name="periodic.cleanup_expired")
def cleanup_expired_task():
    """Mark purchases with expired download windows as EXPIRED."""
    return asyncio.run(_cleanup_expired_async())


async def _cleanup_expired_async() -> dict:
    expired_count = 0
    async with AsyncSessionLocal() as session:
        cutoff = datetime.utcnow()
        stmt = select(Purchase).where(
            Purchase.status == PurchaseStatus.COMPLETED,
            Purchase.download_expires_at.isnot(None),
            Purchase.download_expires_at < cutoff,
        )
        result = await session.execute(stmt)
        purchases = result.scalars().all()

        for purchase in purchases:
            purchase.status = PurchaseStatus.EXPIRED
            expired_count += 1

        if expired_count:
            await session.commit()
            logger.info("Expired %d purchase download links", expired_count)

    return {"expired": expired_count}
