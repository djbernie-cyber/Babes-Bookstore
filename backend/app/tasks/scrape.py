"""Celery tasks for ingesting books from external sources.

Design notes:
- Each task wraps a single `asyncio.run(...)` call. Mixing `await` into a
  synchronous Celery task raises SyntaxError/RuntimeError at runtime.
- Ingestion is idempotent and keyed on (source, source_id).
- Books whose licence is on the allow-list are auto-approved so they are
  immediately visible in the storefront; anything uncertain stays PENDING
  for manual review, and blocked licences are never stored.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Sequence

from sqlalchemy import select

from ..celery_app import celery_app
from ..database import AsyncSessionLocal
from ..models.book import Book, BookStatus
from ..services.license_verifier import license_verifier, LicenseStatus
from ..sources import source_registry
from ..sources.base import BookMetadata

logger = logging.getLogger(__name__)


@dataclass
class IngestReport:
    source: str
    found: int = 0
    created: int = 0
    updated: int = 0
    approved: int = 0
    pending: int = 0
    rejected: int = 0
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "found": self.found,
            "created": self.created,
            "updated": self.updated,
            "approved": self.approved,
            "pending": self.pending,
            "rejected": self.rejected,
            "errors": self.errors[:5],
        }


def _status_for(result) -> BookStatus:
    """Map a licence verdict onto a moderation status."""
    if result.status == LicenseStatus.APPROVED:
        return BookStatus.APPROVED
    return BookStatus.PENDING


async def _ingest(source_name: str, items: Sequence[BookMetadata]) -> IngestReport:
    """Upsert scraped metadata, enforcing licence rules. Idempotent."""
    report = IngestReport(source=source_name, found=len(items))
    if not items:
        return report

    async with AsyncSessionLocal() as session:
        for metadata in items:
            if not metadata.source_id or not metadata.title:
                report.errors.append("skipped record missing source_id/title")
                continue

            verdict = license_verifier.verify(metadata.license_type, metadata.license_url)
            if verdict.status == LicenseStatus.REJECTED:
                report.rejected += 1
                continue

            status = _status_for(verdict)
            approved = status == BookStatus.APPROVED
            if approved:
                report.approved += 1
            else:
                report.pending += 1

            payload = {
                "title": metadata.title[:500],
                "author": metadata.author,
                "description": metadata.description,
                "source": source_name,
                "source_id": str(metadata.source_id),
                "source_url": metadata.source_url,
                "source_metadata": metadata.source_metadata,
                "license_type": metadata.license_type,
                "license_url": metadata.license_url,
                "category": metadata.category,
                "tags": metadata.tags or [],
                "language": metadata.language or "en",
                "publication_year": metadata.publication_year,
                "status": status,
                "license_verified": approved,
            }

            existing = (await session.execute(
                select(Book).where(
                    Book.source == source_name,
                    Book.source_id == str(metadata.source_id),
                )
            )).scalar_one_or_none()

            if existing:
                for key, value in payload.items():
                    # Never overwrite good data with nulls from a partial record.
                    if value is not None or key in ("description", "author"):
                        setattr(existing, key, value)
                existing.verified_at = datetime.utcnow()
                report.updated += 1
            else:
                session.add(Book(**payload, verified_at=datetime.utcnow()))
                report.created += 1

        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.exception("Failed to commit ingest for %s", source_name)
            report.errors.append(f"commit failed: {exc}")

    return report


async def _scrape_source(source_name: str, query: str, limit: int) -> dict:
    try:
        source = source_registry.get(source_name)
    except KeyError:
        return IngestReport(source=source_name, errors=[f"unknown source '{source_name}'"]).as_dict()

    try:
        items = await source.search(query, limit=limit) if query else await source.list_popular(limit)
    except Exception as exc:
        logger.exception("Fetch failed for %s", source_name)
        return IngestReport(source=source_name, errors=[f"fetch failed: {exc}"]).as_dict()
    finally:
        await source.close()

    report = await _ingest(source_name, items)
    return report.as_dict()


async def _scrape_many(source_names: Sequence[str], query: str, limit: int) -> List[dict]:
    """Fetch sources concurrently; a failure in one never aborts the rest."""
    results = await asyncio.gather(
        *(_scrape_source(name, query, limit) for name in source_names),
        return_exceptions=True,
    )
    out: List[dict] = []
    for name, result in zip(source_names, results):
        if isinstance(result, BaseException):
            logger.exception("Scrape task failed for %s", name)
            out.append(IngestReport(source=name, errors=[str(result)]).as_dict())
        else:
            out.append(result)
    return out


@celery_app.task(name="scrape.source")
def scrape_source_task(source_name: str, query: str = "", limit: int = 20) -> dict:
    logger.info("Scraping %s (query=%r, limit=%s)", source_name, query, limit)
    result = asyncio.run(_scrape_source(source_name, query, limit))
    logger.info("Scrape finished: %s", result)
    return result


@celery_app.task(name="scrape.all_sources")
def scrape_all_sources_task(query: str = "", limit_per_source: int = 50) -> List[dict]:
    names = source_registry.list_names()
    logger.info("Scraping %d sources (query=%r)", len(names), query)
    return asyncio.run(_scrape_many(names, query, limit_per_source))


@celery_app.task(name="scrape.popular")
def scrape_popular_task(limit_per_source: int = 50) -> List[dict]:
    """Populate the catalogue with each source's popular/recent titles."""
    names = source_registry.list_names()
    logger.info("Scraping popular titles from %d sources", len(names))
    return asyncio.run(_scrape_many(names, "", limit_per_source))
