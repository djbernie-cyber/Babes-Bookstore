"""Full production license + data-quality sweep.

Run inside the API container:
    cd /app && PYTHONPATH=/app python /app/app/scripts/audit_licenses.py

1. Re-verifies every approved standard_ebooks / internet_archive book plus all
   African/Revolutionary-tagged books against their declared source URL.
   Fabricated public-domain claims (modern novels) are hard-rejected.
2. Strips the bogus ``African Author`` continent tag from degenerate
   initials/lone-short-name credits left by the old loose matcher.
"""
import asyncio
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import String, cast, select

from app.database import AsyncSessionLocal
from app.models.book import Book
from app.services.license_audit import audit_approved_books
from app.sources.african_ebooks import AFRICAN_CONTINENT_TAG


def _degenerate_author(name) -> bool:
    tokens = re.findall(r"[a-z0-9]+", (name or "").lower())
    if not tokens:
        return True
    if all(len(t) == 1 for t in tokens):
        return True
    if len(tokens) == 1:
        return True
    return False


async def main() -> None:
    async with AsyncSessionLocal() as session:
        report = await audit_approved_books(session)
        print(
            f"[audit] checked={report['checked']} ok={report['ok']} "
            f"rejected={report['rejected']}"
        )
        for item in report["rejected_titles"]:
            print(
                f"[audit] REJECTED {item['id']} | {item['title'][:60]} | "
                f"{item['author']} | {item['reason']}"
            )

        tagged = (
            await session.execute(
                select(Book).where(cast(Book.tags, String).ilike(f'%"{AFRICAN_CONTINENT_TAG}"%'))
            )
        ).scalars().all()
        removed = 0
        for book in tagged:
            if not _degenerate_author(book.author):
                continue
            tags = [t for t in (book.tags or []) if t != AFRICAN_CONTINENT_TAG]
            if len(tags) != len(book.tags or []):
                book.tags = tags
                removed += 1
        await session.commit()
        print(f"[tags] stripped 'African Author' from {removed} degenerate-author books")
    print("[done]")


asyncio.run(main())