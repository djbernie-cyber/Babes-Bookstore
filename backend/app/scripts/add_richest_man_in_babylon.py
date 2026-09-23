"""Add 'The Richest Man in Babylon' (George S. Clason) to the catalogue.

1926 US first publication -> public domain in the US since 2022. Open Library
does not flag this scan as public_scan_b so the auto-harvest quietly skips it;
insert it directly, with its cover and a per-item manual licence verification.

Run inside the API container:
    cd /app && PYTHONPATH=/app python /tmp/add_richest.py
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.book import Book, BookStatus, VerificationMethod
from app.models.bundle import Bundle, BundleBook

TITLE = "The Richest Man in Babylon"
AUTHOR = "Clason, George S."
SOURCE_ID = "OL8165007W"
COVER = "https://archive.org/services/img/richestmaninbaby00clas"


async def main():
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(
            select(Book).where(Book.source == "open_library", Book.source_id == SOURCE_ID)
        )).scalar_one_or_none()

        if existing:
            print(f"already present id={existing.id}; ensuring approved+cover")
            existing.status = BookStatus.APPROVED
            existing.license_verified = True
            existing.verified_by = VerificationMethod.MANUAL.value
            existing.cover_path = existing.cover_path or COVER
            existing.tags = list(dict.fromkeys((existing.tags or []) + ["Classics", "Bestsellers", "Self-Help"]))
            db.add(existing)
            await db.flush()
            book_id = existing.id
        else:
            row = Book(
                title=TITLE, author=AUTHOR,
                description="The parable of wealth and discipline that taught a generation "
                    "to pay themselves first, keep thyself out of debt and make gold work for "
                    "you — Babylonia's ancient money wisdom, modern finance's quiet bible.",
                source="open_library", source_id=SOURCE_ID,
                source_url="https://openlibrary.org/works/OL8165007W",
                license_type="public_domain",
                license_url="https://openlibrary.org/works/OL8165007W",
                license_verified=True,
                verified_by=VerificationMethod.MANUAL.value,
                category="Self-Help",
                tags=["Classics", "Bestsellers", "Self-Help"],
                language="en", publication_year=1926,
                status=BookStatus.APPROVED,
                cover_path=COVER,
            )
            db.add(row)
            await db.flush()
            book_id = row.id

        # Drop into any existing bundle that should carry it
        want = ["foie-gras-best-sellers", "classics-canon"]
        for slug in want:
            b = (await db.execute(select(Bundle).where(Bundle.slug == slug))).scalar_one_or_none()
            if not b:
                print(f"bundle {slug}: not present yet — skipped")
                continue
            inside = (await db.execute(
                select(BundleBook).where(BundleBook.bundle_id == b.id, BundleBook.book_id == book_id)
            )).scalar_one_or_none()
            if not inside:
                maxorder = (await db.execute(
                    select(func.coalesce(func.max(BundleBook.sort_order), 0)).where(BundleBook.bundle_id == b.id)
                )).scalar() or 0
                db.add(BundleBook(bundle_id=b.id, book_id=book_id, sort_order=maxorder + 1))
                print(f"bundle {slug}: added book id={book_id}")
            else:
                print(f"bundle {slug}: already included")

        await db.commit()
        print(f"done. book id={book_id}")


asyncio.run(main())