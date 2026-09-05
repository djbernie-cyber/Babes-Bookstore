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
from ..sources.african_ebooks import (
    AFRICAN_LITERATURE_TAG,
    AFRICAN_CONTINENT_TAG,
    COLONIAL_SOURCE_TAG,
    REVOLUTIONARY_TAG,
    AFRICAN_AUTHORS,
    AFRICAN_CONTINENT_AUTHORS,
    COLONIAL_AUTHORS,
    COLONIAL_COLLABORATORS,
    CONDEMNED_REVOLUTIONARY_AUTHORS,
    AFRICAN_THEMES,
)

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
    skipped_dupe: int = 0
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
            "skipped_dupe": self.skipped_dupe,
            "errors": self.errors[:5],
        }


def _normalize_title(title: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _status_for(result) -> BookStatus:
    """Map a licence verdict onto a moderation status."""
    if result.status == LicenseStatus.APPROVED:
        return BookStatus.APPROVED
    return BookStatus.PENDING


async def _ingest(source_name: str, items: Sequence[BookMetadata], chunk_size: int = 500) -> IngestReport:
    """Upsert scraped metadata, enforcing licence rules. Idempotent.

    To scale to ~90k records without a single huge transaction, items are
    processed in bounded chunks and each chunk is committed independently.
    All the report counters are accumulated across chunks.
    """
    report = IngestReport(source=source_name, found=len(items))
    if not items:
        return report

    # Prefetch the set of already-known titles *for this source* so dupe
    # detection works across the whole batch even though we commit in chunks.
    known_titles: set[str] = set()
    async with AsyncSessionLocal() as session:
        for (t,) in (await session.execute(
            select(Book.title).where(Book.source == source_name)
        )).all():
            known_titles.add(_normalize_title(t))

    for start in range(0, len(items), chunk_size):
        chunk = items[start:start + chunk_size]
        await _ingest_chunk(source_name, chunk, report, known_titles)

    return report


async def _ingest_chunk(
    source_name: str,
    items: Sequence[BookMetadata],
    report: IngestReport,
    known_titles: set[str],
) -> None:
    """Commit one bounded chunk of items within its own transaction."""
    if not items:
        return

    async with AsyncSessionLocal() as session:
        try:
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

                norm_title = _normalize_title(metadata.title)

                tags = list(metadata.tags or [])
                from ..sources.african_ebooks import AfricanEbooksSource
                if (AfricanEbooksSource._is_african_author(metadata.author)
                        or AfricanEbooksSource._is_colonial_author(metadata.author)):
                    tiers = [AFRICAN_LITERATURE_TAG]
                    if AfricanEbooksSource._is_continent_african(metadata.author):
                        tiers.append(AFRICAN_CONTINENT_TAG)
                    if AfricanEbooksSource._is_colonial_author(metadata.author):
                        tiers.append(COLONIAL_SOURCE_TAG)
                    for t in tiers:
                        if t not in tags:
                            tags.append(t)
                if AfricanEbooksSource._is_revolutionary_author(metadata.author):
                    if REVOLUTIONARY_TAG not in tags:
                        tags.append(REVOLUTIONARY_TAG)

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
                    "tags": tags,
                    "language": metadata.language or "en",
                    "publication_year": metadata.publication_year,
                    "status": status,
                    "license_verified": approved,
                    "isbn": metadata.isbn,
                    "page_count": metadata.page_count,
                    "cover_path": metadata.cover_url,
                    "epub_path": metadata.epub_url,
                    "pdf_path": metadata.pdf_url,
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
                elif norm_title in known_titles:
                    report.skipped_dupe += 1
                else:
                    session.add(Book(**payload, verified_at=datetime.utcnow()))
                    report.created += 1
                    known_titles.add(norm_title)

            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.exception("Failed to commit ingest chunk for %s", source_name)
            report.errors.append(f"commit failed: {exc}")


async def _scrape_source(source_name: str, query: str, limit: int, start_page: int = 1) -> dict:
    # Celery invokes each task via asyncio.run(), which spins up a fresh
    # event loop every time. The module-level async engine's connection pool
    # is bound to whichever loop first opened a connection, so reusing it from
    # a new loop raises "attached to a different loop". Dispose and let the
    # pool rebuild against the current loop.
    from ..database import engine

    try:
        await engine.dispose()
    except Exception:
        pass

    try:
        source = source_registry.get(source_name)
    except KeyError:
        return IngestReport(source=source_name, errors=[f"unknown source '{source_name}'"]).as_dict()

    try:
        if query:
            items = await source.search(query, limit=limit, start_page=start_page)
        else:
            try:
                items = await source.list_popular(limit, start_page=start_page)
            except TypeError:
                # Some sources don't support pagination (start_page).
                items = await source.list_popular(limit)
    except Exception as exc:
        logger.exception("Fetch failed for %s", source_name)
        return IngestReport(source=source_name, errors=[f"fetch failed: {exc}"]).as_dict()
    finally:
        await source.close()

    report = await _ingest(source_name, items)

    # Close pooled connections on the loop we just used so they aren't torn
    # down (and logged as errors) when asyncio.run() closes the loop.
    try:
        await engine.dispose()
    except Exception:
        pass

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
def scrape_source_task(source_name: str, query: str = "", limit: int = 20, start_page: int = 1) -> dict:
    logger.info("Scraping %s (query=%r, limit=%s, start_page=%s)", source_name, query, limit, start_page)
    result = asyncio.run(_scrape_source(source_name, query, limit, start_page))
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


@celery_app.task(name="scrape.gutenberg_full")
def scrape_gutenberg_full_task(limit: int | None = None, start_page: int = 1) -> dict:
    """Harvest the full English public-domain Gutenberg catalogue.

    Uses concurrent paging to scale to ~74k English books. Because the whole
    set is large, this is processed through :func:`_ingest` which commits in
    bounded chunks so a single huge transaction never ties up the DB. Optional
    ``start_page`` lets the operator resume a long harvest.
    """
    from ..sources.gutenberg import GutenbergSource

    async def _run() -> dict:
        from ..database import engine
        try:
            await engine.dispose()
        except Exception:
            pass

        source = GutenbergSource()
        try:
            items = await source.harvest_catalogue(limit=limit)
        finally:
            await source.close()

        report = await _ingest("gutenberg", items)

        try:
            await engine.dispose()
        except Exception:
            pass
        return report.as_dict()

    logger.info("Running full Gutenberg catalogue harvest (limit=%s)", limit)
    return asyncio.run(_run())


@celery_app.task(name="scrape.african_full")
def scrape_african_full_task(limit: int | None = None) -> dict:
    """Harvest the full African-themed Gutenberg catalogue (~low thousands).

    Expands the African Literature shelf from the hand-curated canon to every
    public-domain, English, Africa-themed work Gutendex exposes, tagging each
    ``African Literature``. Result is ingested in chunks exactly like the full
    Gutenberg harvest so memory stays bounded.
    """
    from ..sources.african_ebooks import AfricanEbooksSource

    async def _run() -> dict:
        from ..database import engine
        try:
            await engine.dispose()
        except Exception:
            pass

        source = AfricanEbooksSource()
        try:
            items = await source.harvest_african(limit=limit)
        finally:
            await source.close()

        report = await _ingest("african_ebooks", items)

        try:
            await engine.dispose()
        except Exception:
            pass
        return report.as_dict()

    logger.info("Running full African Literature harvest (limit=%s)", limit)
    return asyncio.run(_run())


def _sources_with_pagination() -> List[str]:
    """Sources that accept ``start_page`` so they can be walked in full."""
    out: List[str] = []
    for name in source_registry.list_names():
        if name in ("gutenberg", "african_ebooks"):
            continue  # handled by their dedicated full-catalogue harvesters
        try:
            source = source_registry.get(name)
        except KeyError:
            continue
        if hasattr(source, "list_popular"):
            try:
                import inspect
                if "start_page" in inspect.signature(source.list_popular).parameters:
                    out.append(name)
            except Exception:
                continue
    return out


@celery_app.task(name="scrape.full_catalogue")
def scrape_full_catalogue_task(pages_per_source: int = 60) -> dict:
    """Bull path to ~90k: run the full Gutenberg catalogue, the full African
    Literature shelf, and multi-page walks of every other public source in
    parallel, so total curated volume reaches its honest ceiling.

    Gutenberg (English, public-domain) is ~74k after dedupe; Standard Ebooks,
    Wikisource, OpenStax, Internet Archive, DOAB, OAPEN and Open Library each
    add hundreds to a few thousand licensed titles. The combined, deduped total
    is reported honestly — it lands in the high-seventies to mid-eighties
    thousands, not a guaranteed flat 90,000, because the licensed public-domain
    English corpus simply does not contain 90k unique works.
    """
    from ..database import engine

    async def _run() -> dict:
        try:
            await engine.dispose()
        except Exception:
            pass

        reports: dict = {}
        exceptions: List[str] = []

        async def _run_full_gutenberg() -> None:
            from ..sources.gutenberg import GutenbergSource
            src = GutenbergSource()
            try:
                items = await src.harvest_catalogue(limit=None)
            finally:
                await src.close()
            try:
                await engine.dispose()
            except Exception:
                pass
            reports["gutenberg"] = (await _ingest("gutenberg", items)).as_dict()

        async def _run_full_african() -> None:
            from ..sources.african_ebooks import AfricanEbooksSource
            src = AfricanEbooksSource()
            try:
                items = await src.harvest_african(limit=None)
            finally:
                await src.close()
            try:
                await engine.dispose()
            except Exception:
                pass
            reports["african_ebooks"] = (await _ingest("african_ebooks", items)).as_dict()

        async def _run_source(name: str, pages: int) -> None:
            from ..database import engine as _engine
            src = source_registry.get(name)
            collected: List[BookMetadata] = []
            for page in range(1, pages + 1):
                try:
                    page_items = await src.list_popular(limit=50, start_page=page)
                except Exception:
                    break
                if not page_items:
                    break
                collected.extend(page_items)
            try:
                await src.close()
            except Exception:
                pass
            try:
                await _engine.dispose()
            except Exception:
                pass
            reports[name] = (await _ingest(name, collected)).as_dict()

        async def _run_sources() -> None:
            await asyncio.gather(
                *(_run_source(n, pages_per_source) for n in _sources_with_pagination()),
                return_exceptions=True,
            )

        # Kick off the two heavy harvesters first, then walk the others.
        await asyncio.gather(_run_full_gutenberg(), _run_full_african(), return_exceptions=True)
        await _run_sources()

        try:
            await engine.dispose()
        except Exception:
            pass
        return {"reports": reports, "exceptions": exceptions}

    logger.info("Running ~90k full-catalogue harvest (pages/source=%s)", pages_per_source)
    return asyncio.run(_run())


@celery_app.task(name="retag.african_literature")
def retag_african_literature_task() -> dict:
    """Backfill the African Literature tag tiers over the whole approved shelf.

    Author-priority pass across every approved book:
      - African/diaspora author           -> ``African Literature``
      - Black African (continent) author  -> + ``African Author``
      - Colonial / collaborator author    -> + ``Colonial Sauce``

    Idempotent: only adds tags where missing, never downgrades or removes.
    This is the post-harvest pass that catches works surfaced by any source
    (not just the African harvester), so the full catalogue is correctly
    partitioned into African / diaspora / colonial-sauce tiers.
    """
    from ..database import AsyncSessionLocal

    async def _run() -> dict:
        from ..sources.african_ebooks import AfricanEbooksSource

        stats = {"scanned": 0, "african": 0, "continent": 0, "colonial": 0, "revolutionary": 0}
        async with AsyncSessionLocal() as session:
            stmt = select(Book).where(Book.status == BookStatus.APPROVED)
            result = await session.execute(stmt)
            for book in result.scalars():
                stats["scanned"] += 1
                tags = list(book.tags or [])
                changed = False

                if AfricanEbooksSource._is_african_author(book.author):
                    if AFRICAN_LITERATURE_TAG not in tags:
                        tags.insert(0, AFRICAN_LITERATURE_TAG)
                        changed = True
                    stats["african"] += 1
                    if AfricanEbooksSource._is_continent_african(book.author):
                        if AFRICAN_CONTINENT_TAG not in tags:
                            tags.insert(1, AFRICAN_CONTINENT_TAG)
                            changed = True
                        stats["continent"] += 1

                if AfricanEbooksSource._is_colonial_author(book.author):
                    if COLONIAL_SOURCE_TAG not in tags and AFRICAN_LITERATURE_TAG not in tags:
                        tags.insert(0, AFRICAN_LITERATURE_TAG)
                        changed = True
                    if COLONIAL_SOURCE_TAG not in tags:
                        tags.insert(1, COLONIAL_SOURCE_TAG)
                        changed = True
                    stats["colonial"] += 1

                if AfricanEbooksSource._is_revolutionary_author(book.author):
                    if REVOLUTIONARY_TAG not in tags:
                        tags.append(REVOLUTIONARY_TAG)
                        changed = True
                    stats["revolutionary"] += 1

                if changed:
                    book.tags = tags
            await session.commit()
        return stats

    logger.info("Backfilling African Literature tag tiers")
    return asyncio.run(_run())
