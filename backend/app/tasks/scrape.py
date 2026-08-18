import asyncio
import logging
from typing import List
from datetime import datetime

from ..celery_app import celery_app
from ..sources import source_registry
from ..sources.base import BookMetadata
from ..services.license_verifier import license_verifier, LicenseStatus
from ..models.book import Book, BookStatus
from ..database import AsyncSessionLocal
from ..services.storage import storage
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def _scrape_source_async(source_name: str, query: str, limit: int) -> dict:
    source = source_registry.get(source_name)
    try:
        results: List[BookMetadata] = await source.search(query, limit=limit)
        new_count = 0
        updated_count = 0
        rejected_count = 0
        pending_count = 0

        async with AsyncSessionLocal() as session:
            for metadata in results:
                license_result = license_verifier.verify(
                    metadata.license_type,
                    metadata.license_url,
                )

                stmt = select(Book).where(
                    Book.source == source_name,
                    Book.source_id == metadata.source_id,
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()

                status = BookStatus.REJECTED
                if license_result.status == LicenseStatus.APPROVED:
                    status = BookStatus.PENDING
                elif license_result.status == LicenseStatus.PENDING:
                    status = BookStatus.PENDING

                if license_result.status == LicenseStatus.REJECTED:
                    rejected_count += 1
                    continue
                elif license_result.status == LicenseStatus.PENDING:
                    pending_count += 1
                else:
                    pass

                book_data = {
                    "title": metadata.title,
                    "author": metadata.author,
                    "description": metadata.description,
                    "source": metadata.source,
                    "source_id": metadata.source_id,
                    "source_url": metadata.source_url,
                    "source_metadata": metadata.source_metadata,
                    "license_type": metadata.license_type,
                    "license_url": metadata.license_url,
                    "category": metadata.category,
                    "tags": metadata.tags or [],
                    "language": metadata.language,
                    "publication_year": metadata.publication_year,
                    "status": status,
                    "license_verified": license_result.status == LicenseStatus.APPROVED,
                }

                if existing:
                    for k, v in book_data.items():
                        setattr(existing, k, v)
                    existing.verified_at = datetime.utcnow()
                    updated_count += 1
                else:
                    book = Book(**book_data, verified_at=datetime.utcnow())
                    session.add(book)
                    new_count += 1

            await session.commit()

        return {
            "source": source_name,
            "query": query,
            "found": len(results),
            "new": new_count,
            "updated": updated_count,
            "rejected": rejected_count,
            "pending": pending_count,
        }
    finally:
        await source.close()


@celery_app.task(name="scrape.source")
def scrape_source_task(source_name: str, query: str = "", limit: int = 20) -> dict:
    """Scrape a single source for books matching query."""
    logger.info(f"Scraping {source_name} for '{query}'")
    result = asyncio.run(_scrape_source_async(source_name, query, limit))
    logger.info(f"Scrape complete: {result}")
    return result


@celery_app.task(name="scrape.all_sources")
def scrape_all_sources_task(query: str = "", limit_per_source: int = 50) -> List[dict]:
    """Scrape all registered sources."""
    results = []
    for name in source_registry.list_names():
        try:
            result = scrape_source_task(name, query, limit_per_source)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to scrape {name}: {e}")
            results.append({"source": name, "error": str(e)})
    return results


@celery_app.task(name="scrape.popular")
def scrape_popular_task(limit_per_source: int = 50) -> List[dict]:
    """Scrape popular/recent books from all sources."""
    results = []
    for name in source_registry.list_names():
        try:
            source = source_registry.get(name)
            popular = asyncio.run(source.list_popular(limit_per_source))
            asyncio.run(source.close())

            new_count = 0
            async with AsyncSessionLocal() as session:
                for metadata in popular:
                    license_result = license_verifier.verify(metadata.license_type, metadata.license_url)
                    if license_result.status == LicenseStatus.REJECTED:
                        continue

                    stmt = select(Book).where(
                        Book.source == name,
                        Book.source_id == metadata.source_id,
                    )
                    existing = (await session.execute(stmt)).scalar_one_or_none()

                    status = BookStatus.PENDING if license_result.status == LicenseStatus.APPROVED else BookStatus.PENDING

                    if existing:
                        existing.title = metadata.title
                        existing.author = metadata.author
                        existing.license_type = metadata.license_type
                        existing.license_url = metadata.license_url
                        existing.license_verified = license_result.status == LicenseStatus.APPROVED
                        existing.verified_at = datetime.utcnow()
                        existing.status = status
                    else:
                        book = Book(
                            title=metadata.title,
                            author=metadata.author,
                            source=name,
                            source_id=metadata.source_id,
                            source_url=metadata.source_url,
                            license_type=metadata.license_type,
                            license_url=metadata.license_url,
                            status=status,
                            license_verified=license_result.status == LicenseStatus.APPROVED,
                            verified_at=datetime.utcnow(),
                        )
                        session.add(book)
                        new_count += 1

                await session.commit()

            results.append({"source": name, "popular_count": len(popular), "new": new_count})
        except Exception as e:
            logger.error(f"Failed popular scrape for {name}: {e}")
            results.append({"source": name, "error": str(e)})
    return results