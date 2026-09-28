"""Classify pending Standard Ebooks editions against the publisher's own
public-domain statement, and set ``asset_verified`` from the result.

The licence audit used to treat an HTTP 200 from the source as proof that a
work was free to sell. That is not what a 200 means. It means a page exists.
The review queue filled up as a result: Death of a Salesman (1949), A
Streetcar Named Desire (1947), The Skin Of Our Teeth (1942) and The Time Of
Your Life (1939) were all labelled ``public_domain``, and four of them were
approved and went on sale.

Standard Ebooks states the answer on the book page itself, in one of two
phrasings:

    "This book was published in 1966, and will therefore enter the U.S.
     public domain in 36 years on January 1, 2062."

    "This book was published in 1991, and will therefore enter the U.S.
     public domain 70 years after the author's death."

A genuinely public-domain edition carries neither sentence. That is the
publisher asserting its own catalogue's status, which is better evidence than
anything we could infer, and it is what this script reads.

Outcomes per pending row:

* page states a future public-domain date -> ``asset_verified=False`` and
  ``license_type='unknown'``. The work is still in copyright. It stays
  PENDING with the reason recorded, because only a person should decide
  whether to sell a modern title.
* page carries no such statement       -> ``asset_verified=True``. The
  publisher says it is already public domain, so the row is eligible for
  "Approve all pending".
* page 404s, times out, or cannot be read -> ``asset_verified=False``,
  ``license_type='unknown'``, flagged for manual review. Unreachable is not
  evidence of infringement and is certainly not evidence of clearance, so the
  row is neither approved nor rejected.

This is what makes the bulk-approve button work without turning it into a
licence vacuum: it approves only what the publisher has confirmed.

    cd /app && PYTHONPATH=/app python /app/app/scripts/classify_standard_ebooks.py
    # add --dry-run to report without writing
    # add --limit N to classify a slice first
"""
import argparse
import asyncio
import logging
import re
import sys

import httpx
from sqlalchemy import select

sys.path.insert(0, "/app")

from app.database import AsyncSessionLocal
from app.models.book import Book, BookStatus
from app.sources.standard_ebooks import parse_standard_ebooks_copyright

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("classify_standard_ebooks")

BOOK_URL = "https://standardebooks.org/ebooks/{slug}"

# Standard Ebooks joins co-authors with an underscore in the slug directory,
# e.g. william-craft_ellen-craft/running-a-thousand-miles-for-freedom. An
# earlier pattern that allowed only [a-z0-9-] marked every one of those
# malformed and skipped it, which is how a title can escape a licence check
# without anybody noticing.
SLUG = re.compile(r"^[a-z0-9_-]+/[a-z0-9_-]+$")

IN_COPYRIGHT_REASON = (
    "In copyright: the publisher's page states this edition enters the U.S. "
    "public domain in {when}. Held pending for manual review."
)
UNREACHABLE_REASON = (
    "Source page could not be read ({note}). Not evidence of infringement "
    "and not evidence of clearance — flagged for manual review."
)


async def classify_one(client: httpx.AsyncClient, book: Book) -> str:
    """Return one of: verified, in_copyright, unreachable, malformed."""
    slug = book.source_id or ""
    if not SLUG.match(slug):
        book.asset_verified = False
        book.license_type = "unknown"
        book.rejected_reason = UNREACHABLE_REASON.format(note="malformed source id")
        return "malformed"

    note = "unreachable"
    for attempt in range(3):
        try:
            response = await client.get(BOOK_URL.format(slug=slug), timeout=30)
        except Exception as exc:
            note = type(exc).__name__
            await asyncio.sleep(1.5 * (attempt + 1))
            continue

        if response.status_code == 404:
            note = "page not found"
            break
        if response.status_code != 200:
            note = f"HTTP {response.status_code}"
            await asyncio.sleep(1.5 * (attempt + 1))
            continue

        verdict = parse_standard_ebooks_copyright(response.text)
        if verdict["in_copyright"]:
            book.asset_verified = False
            book.license_type = "unknown"
            when = (
                f"on January 1, {match}" if (match := re.search(
                    r"January 1,\s*(\d{4})", response.text)) else "later"
            )
            book.rejected_reason = IN_COPYRIGHT_REASON.format(when=when)
            if verdict["publication_year"]:
                book.publication_year = verdict["publication_year"]
            return "in_copyright"

        # No statement either way. The publisher does not flag this edition as
        # future-copyright, so treat it as cleared -- this is the same evidence
        # Standard Ebooks uses to decide what to publish at all.
        book.asset_verified = True
        book.rejected_reason = None
        if verdict["publication_year"]:
            book.publication_year = verdict["publication_year"]
        return "verified"

    book.asset_verified = False
    book.license_type = "unknown"
    book.rejected_reason = UNREACHABLE_REASON.format(note=note)
    return "unreachable"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        query = select(Book).where(
            Book.status == BookStatus.PENDING,
            Book.source == "standard_ebooks",
        )
        if args.limit:
            query = query.limit(args.limit)
        books = (await db.execute(query)).scalars().all()
        logger.info("classifying %d pending Standard Ebooks rows", len(books))

        tallies = {"verified": 0, "in_copyright": 0, "unreachable": 0, "malformed": 0}
        async with httpx.AsyncClient(
            headers={"User-Agent": "babes-bookstore-classifier/1.0"},
            follow_redirects=True,
            limits=httpx.Limits(max_connections=5),
            timeout=30,
        ) as client:
            for index, book in enumerate(books, 1):
                outcome = await classify_one(client, book)
                tallies[outcome] += 1
                if index % 50 == 0:
                    logger.info("  %d/%d %s", index, len(books), tallies)
                    if not args.dry_run:
                        await db.commit()

        if args.dry_run:
            await db.rollback()
            logger.info("dry run — nothing written")
        else:
            await db.commit()
        logger.info("result: %s", tallies)
        logger.info(
            "approve-all will now pick up %d row(s); %d held for manual review",
            tallies["verified"],
            tallies["in_copyright"] + tallies["unreachable"] + tallies["malformed"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
