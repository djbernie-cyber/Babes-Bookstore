"""Re-verify that approved books actually are public-domain / openly-licensed
at their declared source.

Fabricated source ids (e.g. a ``standard_ebooks`` slug for a book Standard
Ebooks does not publish — *Things Fall Apart*, *Nervous Conditions*, *Crispin*)
let modern, still-in-copyright novels be marked ``asset_verified``. That is a
direct legal exposure. Any approved book whose declared source URL does not
resolve is a red flag: it either isn't the book it claims to be, or isn't a
real edition of it.

What that red flag is *worth* is the point this module was wrong about. It used
to treat an unresolved URL as sufficient to reject, and rejected 2,209 books
that way. But a 404, a timeout and a DNS failure look identical to a source
that moved, rate-limited or is briefly down, and none of them is evidence that a
book is in copyright. Withdrawing a genuine public-domain edition because
Standard Ebooks was briefly unreachable is a self-inflicted loss of stock.

So the outcomes are now split by what the evidence actually supports:

* **REJECTED** — a positively identified non-public-domain work, i.e. one of
  ``KNOWN_NOT_PUBLIC_DOMAIN_IDS``. Curated evidence, not a failed request. The
  fabricated-modern-novel case, which is what this audit exists to catch, still
  lands here.
* **PENDING** — the source could not be confirmed. Hidden from the catalogue
  until a human checks, but kept, and surfaced in the review queue rather than
  written off. A 5xx or timeout that clears later can be re-approved without
  re-scraping.
* **unchanged** — the source resolved.

Every outcome records ``rejected_reason`` so the review page can say why, which
it could not before: the 2,209 earlier rejections were explained only in a log
line, leaving the queue unreviewable.

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

#: Outcomes, so the caller does not infer intent from a status string.
REJECTED = "rejected"
PENDING = "pending"
OK = "ok"


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


def _classify(book: Book, resolves: bool, reason: str) -> str:
    """Decide what a failed check means for this particular book."""
    if book.source_id in KNOWN_NOT_PUBLIC_DOMAIN_IDS:
        return REJECTED
    if resolves:
        return OK
    return PENDING


async def audit_approved_books(
    session,
    source: Optional[str] = None,
    limit: int = 0,
) -> dict:
    """Re-check approved books against their declared source URL.

    Returns a report with ``checked``/``rejected``/``pending``/``ok``. Changes
    are committed: a book that cannot be confirmed moves to PENDING with
    ``asset_verified=False``, and only a known non-public-domain work is
    rejected. Both record ``rejected_reason``.
    """
    stmt = (
        select(Book)
        .where(
            Book.status == BookStatus.APPROVED,
            Book.asset_verified == True,  # noqa: E712
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
        "pending": 0,
        "skipped": 0,
        "errors": [],
        "rejected_titles": [],
        "pending_titles": [],
    }
    if not rows:
        return report

    sem = asyncio.Semaphore(8)

    async def _check(book: Book) -> Optional[Tuple[Book, str, bool]]:
        if book.source_id in KNOWN_NOT_PUBLIC_DOMAIN_IDS:
            return book, "known non-public-domain modern work", True
        async with sem:
            ok, reason = await _source_resolves(book.source_url)
        if ok:
            return None
        return book, reason, ok

    outcomes = await asyncio.gather(*(_check(b) for b in rows))
    for outcome in outcomes:
        if outcome is None:
            report["checked"] += 1
            report["ok"] += 1
            continue
        book, reason, resolves = outcome
        verdict = _classify(book, resolves, reason)
        report["checked"] += 1
        if verdict == REJECTED:
            book.status = BookStatus.REJECTED
            book.asset_verified = False
            book.rejected_reason = reason
            report["rejected"] += 1
            report["rejected_titles"].append(
                {"id": book.id, "title": book.title, "author": book.author, "reason": reason}
            )
            logger.warning(
                "License audit rejected book %s (%s) — %s", book.id, book.title, reason
            )
        else:
            # Unconfirmed, not discredited. Keep the record, lose the sale, and
            # put it in front of a person with the reason attached.
            book.status = BookStatus.PENDING
            book.asset_verified = False
            book.rejected_reason = f"source unconfirmed: {reason}"
            report["pending"] += 1
            report["pending_titles"].append(
                {"id": book.id, "title": book.title, "author": book.author, "reason": reason}
            )
            logger.info(
                "License audit moved book %s (%s) to pending — %s",
                book.id, book.title, reason,
            )

    await session.commit()
    report["errors"] = report["rejected_titles"]
    return report
