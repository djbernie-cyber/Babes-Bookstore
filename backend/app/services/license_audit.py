"""Re-verify that approved books actually are public-domain / openly-licensed
at their declared source.

Fabricated source ids (e.g. a ``standard_ebooks`` slug for a book Standard
Ebooks does not publish — *Things Fall Apart*, *Nervous Conditions*, *Crispin*)
let modern, still-in-copyright novels be marked ``license_verified``. That is a
direct legal exposure. Any approved book whose declared source URL does not
resolve is a red flag: it either isn't the book it claims to be, or isn't a
real edition of it. Failures are rejected/hard-unapproved.

Checks every approved ``standard_ebooks`` / ``internet_archive`` book plus any
approved book carrying the African / Revolutionary tags — the modern-canon seam
where fabricated PD slips in. Gutenberg books are excluded because gutendex
already hard-filters unambiguously on its ``copyright=false`` flag.
"""
import asyncio
import logging
from typing import List, Optional, Tuple

import httpx
from sqlalchemy import String, cast, select

from ..models.book import Book, BookStatus
from ..sources.african_ebooks import (
    AFRICAN_CONTINENT_TAG,
    REVOLUTIONARY_TAG,
)

logger = logging.getLogger(__name__)

#: Author credits confirmed to be modern works being passed off as public
#: domain — hard-rejected wherever they surface.
KNOWN_NOT_PUBLIC_DOMAIN_IDS: set = {
    "chinua-achebe/things-fall-apart",
    "tsitsi-dangarembga/nervous-conditions",
    "avi/crispin",
}


async def _source_resolves(source_url: str) -> Tuple[bool, str]:
    url = (source_url or "").strip()
    if not url:
        return False, "missing source_url"
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "Babe's Bookstore/1.0 (license audit)"},
            )
        if response.status_code >= 400:
            return False, f"HTTP {response.status_code}"
        return True, f"HTTP {response.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, f"unreachable ({type(exc).__name__})"


async def audit_approved_books(
    session,
    source: Optional[str] = None,
    limit: int = 0,
) -> dict:
    """Re-check approved books against their declared source URL.

    Returns a report with ``checked``/``rejected``/``skipped``/``errors``.
    Rejects are committed to the database (status ``REJECTED``,
    ``license_verified=False``).
    """
    stmt = (
        select(Book)
        .where(
            Book.status == BookStatus.APPROVED,
            Book.license_verified == True,  # noqa: E712
        )
        .where(
            (Book.source.in_(["standard_ebooks", "internet_archive"]))
            | cast(Book.tags, String).ilike(f'%"{AFRICAN_CONTINENT_TAG}"%')
            | cast(Book.tags, String).ilike(f'%"{REVOLUTIONARY_TAG}"%')
        )
    )
    if source:
        stmt = stmt.where(Book.source == source)
    if limit:
        stmt = stmt.limit(limit)

    rows = (await session.execute(stmt)).scalars().all()

    report = {
        "checked": 0,
        "ok": 0,
        "rejected": 0,
        "skipped": 0,
        "errors": [],
        "rejected_titles": [],
    }
    if not rows:
        return report

    sem = asyncio.Semaphore(8)

    async def _check(book: Book) -> Optional[Tuple[Book, str]]:
        if book.source_id in KNOWN_NOT_PUBLIC_DOMAIN_IDS:
            return book, "known non-public-domain modern work"
        async with sem:
            ok, reason = await _source_resolves(book.source_url)
        if ok:
            return None
        return book, reason

    outcomes = await asyncio.gather(*(_check(b) for b in rows))
    for outcome in outcomes:
        if outcome is None:
            report["checked"] += 1
            report["ok"] += 1
            continue
        book, reason = outcome
        book.status = BookStatus.REJECTED
        book.license_verified = False
        report["checked"] += 1
        report["rejected"] += 1
        report["rejected_titles"].append(
            {"id": book.id, "title": book.title, "author": book.author, "reason": reason}
        )
        logger.warning(
            "License audit rejected book %s (%s) — %s", book.id, book.title, reason
        )

    await session.commit()
    report["errors"] = report["rejected_titles"]
    return report