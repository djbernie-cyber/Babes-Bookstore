"""Backfill missing book covers from Open Library's public cover service.

Open Library returns cover images via `covers.openlibrary.org` which are keyed
by its internal `cover_i`. We query `/search.json` by title, accept the first
result whose author name overlaps ours, and store the cover URL. Idempotent:
books that already have a cover are skipped, and misses are marked with an
empty-string sentinel so we never hammer Open Library twice for the same book.
"""
import asyncio
import logging

import httpx
from sqlalchemy import select

from ..celery_app import celery_app
from ..celery_db import SessionLocal as AsyncSessionLocal
from ..models.book import Book, BookStatus
from ..config import settings

logger = logging.getLogger(__name__)

COVER_URL = "{cover_i}-M.jpg"
COVER_TMPL = "https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"
OL_SEARCH = "https://openlibrary.org/search.json"

USER_AGENT = "BabeBookstore/{0} (+https://babesbooks.store)".format(
    getattr(settings, "APP_VERSION", "0.1")
)


def _author_overlap(book_author: str, candidate_authors) -> bool:
    if not book_author:
        return True
    tokens = {t.lower() for t in book_author.split() if len(t) >= 3}
    if not tokens:
        return True
    haystack = " ".join(candidate_authors or []).lower()
    return any(t in haystack for t in tokens)


async def _fetch_one(client: httpx.AsyncClient, book) -> str:
    title = (book.title or "").strip()
    if not title:
        return ""
    params = {
        "q": title,
        "fields": "title,author_name,cover_i",
        "limit": 10,
    }
    try:
        resp = await client.get(OL_SEARCH, params=params)
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
    except (httpx.HTTPStatusError, httpx.TransportError) as e:
        # Transient blip — 429/5xx/conn reset. Back off briefly and retry once.
        await asyncio.sleep(2.5)
        try:
            resp = await client.get(OL_SEARCH, params=params)
            resp.raise_for_status()
            docs = resp.json().get("docs", [])
        except Exception as e2:
            logger.warning("OL lookup failed for %r (retried): %s", title, e2)
            return None
    except Exception as e:  # unexpected — skip, don't sentinel
        logger.warning("OL lookup failed for %r: %s", title, e)
        return None
    for doc in docs:
        if not doc.get("cover_i"):
            continue
        if _author_overlap(book.author, doc.get("author_name")):  # type: ignore[arg-type]
            return COVER_TMPL.format(cover_i=doc["cover_i"])
    return ""


async def backfill_covers(limit: int = 2000, delay: float = 0.22) -> dict:
    """Scan approved books without a cover and try to fill them from OL."""
    processed = 0
    filled = 0
    missed = 0
    async with AsyncSessionLocal() as db:
        stmt = (
            select(Book)
            .where(Book.status == BookStatus.APPROVED)
            .where(Book.cover_path.is_(None))
            .order_by(Book.id)
            .limit(limit)
        )
        books = (await db.execute(stmt)).scalars().all()
        total = len(books)
        if not total:
            return {"processed": 0, "filled": 0, "missed": 0, "total": 0}

        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=15.0
        ) as client:
            for book in books:
                url = await _fetch_one(client, book)
                if url is None:
                    logger.warning(
                        "OL unreachable for book %s — stopped before sentinel",
                        book.id,
                    )
                    break
                if url:
                    book.cover_path = url
                    filled += 1
                else:
                    book.cover_path = ""  # sentinel: known miss
                    missed += 1
                processed += 1
                if delay > 0:
                    await asyncio.sleep(delay)
                if processed % 250 == 0:
                    await db.commit()
                    logger.info(
                        "cover backfill progress: %s/%s (filled %s)",
                        processed,
                        total,
                        filled,
                    )
        await db.commit()

    logger.info("cover backfill done: processed=%s filled=%s missed=%s", processed, filled, missed)
    return {"processed": processed, "filled": filled, "missed": missed, "total": total}


def run_backfill(limit: int = 2000, delay: float = 0.22) -> dict:
    return asyncio.run(backfill_covers(limit=limit, delay=delay))


@celery_app.task(name="covers.backfill")
def backfill_covers_task(limit: int = 2000, delay: float = 0.22) -> dict:
    """Celery wrapper: fill missing book covers from Open Library (batched)."""
    return run_backfill(limit=limit, delay=delay)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--delay", type=float, default=0.22)
    args = parser.parse_args()
    print(json.dumps(run_backfill(limit=args.limit, delay=args.delay)))