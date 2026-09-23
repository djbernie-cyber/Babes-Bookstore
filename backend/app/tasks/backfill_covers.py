"""Backfill missing book covers.

Two passes, in order:

1. **Gutenberg derivation.** Most storefront books are Gutenberg-backed, but
   Gutendex only advertises ``image/jpeg`` in ``formats`` when it has cached a
   cover itself — so books ingested straight from Gutendex can land with a
   ``NULL`` cover even though Gutenberg serves one at its standard cache path.
   We build that URL from ``source_id``, verify it with a HEAD, and store it.
   Newest-first so freshly harvested shelves fill immediately.

2. **Open Library search** for the non-Gutenberg remainder (keyed by
   ``cover_i`` via ``covers.openlibrary.org``).

Idempotent: books that already have a cover are skipped, and Open Library
misses are marked with an empty-string sentinel so we never hammer it twice.
"""
import asyncio
import logging

import httpx
from sqlalchemy import select

from ..celery_app import celery_app
from ..celery_db import SessionLocal as AsyncSessionLocal
from ..models.book import Book, BookStatus
from ..config import settings
from ..sources.gutenberg import GUTENBERG_ID_SOURCES, gutenberg_cache_cover

logger = logging.getLogger(__name__)

COVER_URL = "{cover_i}-M.jpg"
COVER_TMPL = "https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"
OL_SEARCH = "https://openlibrary.org/search.json"

#: Light pause between Gutenberg HEADs — they're cheap but we still pace them.
GUTENBERG_HEAD_DELAY = 0.08

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


async def _head_ok(client: httpx.AsyncClient, url: str):
    """Probe a derived Gutenberg cover URL.

    Returns ``True`` when it's a live image, ``False`` on a definite miss
    (404/410), and ``None`` on a transient condition (429/5xx/conn error) so
    the caller leaves the book untouched for a later run.
    """
    try:
        resp = await client.head(url, follow_redirects=True, timeout=12.0)
    except (httpx.TransportError, httpx.HTTPStatusError):
        return None
    if resp.status_code == 200:
        return (resp.headers.get("content-type", "") or "").startswith("image")
    if resp.status_code in (404, 410):
        return False
    return None


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
    """Fill missing covers: Gutenberg derivation first (newest-first), then OL."""
    processed = filled = 0
    g_filled = g_miss = g_transient = 0
    ol_filled = ol_missed = 0
    async with AsyncSessionLocal() as db:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=15.0
        ) as client:
            # ── Pass 1: Gutenberg-derived covers (fast, HEAD-verified) ─────
            # Newest-first so freshly harvested shelves (Military, Socialist,
            # Suppressed) fill immediately instead of waiting behind ~80k
            # older titles when ordering by id.
            g_stmt = (
                select(Book)
                .where(Book.status == BookStatus.APPROVED)
                .where(Book.cover_path.is_(None))
                .where(Book.source.in_(GUTENBERG_ID_SOURCES))
                .order_by(Book.id.desc())
                .limit(limit)
            )
            g_books = (await db.execute(g_stmt)).scalars().all()
            for book in g_books:
                url = gutenberg_cache_cover(book.source, book.source_id)
                if url:
                    ok = await _head_ok(client, url)
                    if ok is True:
                        book.cover_path = url
                        g_filled += 1
                        filled += 1
                    elif ok is False:
                        g_miss += 1
                    else:
                        g_transient += 1
                    processed += 1
                if GUTENBERG_HEAD_DELAY > 0:
                    await asyncio.sleep(GUTENBERG_HEAD_DELAY)
                if processed and processed % 250 == 0:
                    await db.commit()
                    logger.info(
                        "gutenberg cover pass: %s/%s (filled %s)",
                        processed, len(g_books), g_filled,
                    )
            await db.commit()
            logger.info(
                "gutenberg cover pass done: tried=%s filled=%s miss=%s transient=%s",
                len(g_books), g_filled, g_miss, g_transient,
            )

            # ── Pass 2: Open Library search for non-Gutenberg titles ───────
            ol_stmt = (
                select(Book)
                .where(Book.status == BookStatus.APPROVED)
                .where(Book.cover_path.is_(None))
                .where(Book.source.notin_(GUTENBERG_ID_SOURCES))
                .order_by(Book.id)
                .limit(limit)
            )
            ol_books = (await db.execute(ol_stmt)).scalars().all()
            for book in ol_books:
                url = await _fetch_one(client, book)
                if url is None:
                    logger.warning(
                        "OL unreachable for book %s — stopped before sentinel",
                        book.id,
                    )
                    break
                if url:
                    book.cover_path = url
                    ol_filled += 1
                    filled += 1
                else:
                    book.cover_path = ""  # sentinel: known miss
                    ol_missed += 1
                processed += 1
                if delay > 0:
                    await asyncio.sleep(delay)
            await db.commit()
            logger.info("open library pass: tried=%s filled=%s missed=%s",
                        len(ol_books), ol_filled, ol_missed)

    logger.info("cover backfill done: processed=%s filled=%s missed=%s",
                processed, filled, ol_missed)
    return {
        "processed": processed,
        "filled": filled,
        "missed": ol_missed,
        "gutenberg_filled": g_filled,
        "gutenberg_miss": g_miss,
        "gutenberg_transient": g_transient,
        "ol_filled": ol_filled,
        "total": processed,
    }


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