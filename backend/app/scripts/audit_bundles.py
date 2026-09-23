"""Audit download-ability of the catalogue and repair what is derivable.

Runs inside the API container against the live DB. Read-only audit by
default; pass --fix to repair.

    python /app/app/scripts/audit_bundles.py            # bundles only
    python /app/app/scripts/audit_bundles.py --all      # entire approved catalogue
    python /app/app/scripts/audit_bundles.py --all --fix

"Downloadable" mirrors the resolver's candidate logic
(packaging._resolve_book_content): a book yields bytes when —
  * epub_path / pdf_path are set on the record (R2 key or http), or
  * source == "gutenberg" with a numeric source_id (http fallbacks), or
  * source_metadata.text_url is set (http)
Anything else has nothing to fetch.

Repairs applied by --fix, in order:
  1. gutenberg records with a numeric id derivable from their source_url get
     source_id backfilled;
  2. standard_ebooks records get epub_path derived from their source slug;
  3. any remaining un-downloadable book is dropped from bundles and its
     status moved to REJECTED so it never surfaces as a purchasable title.
"""
import asyncio
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select, delete as sa_delete

from app.database import AsyncSessionLocal
from app.models.book import Book, BookStatus
from app.models.bundle import Bundle, BundleBook

GUTENBERG_EBOOK_RE = re.compile(r"gutenberg\.org/(?:ebooks|files|cache/epub)/(\d+)")
SE_SLUG_RE = re.compile(r"standardebooks\.org/ebooks/([a-z0-9-]+/[a-z0-9-]+)", re.I)


def _gid_from_url(url: str) -> str | None:
    if not url:
        return None
    m = GUTENBERG_EBOOK_RE.search(url)
    return m.group(1) if m else None


def _se_epub_from_url(url: str) -> str | None:
    if not url:
        return None
    m = SE_SLUG_RE.search(url)
    if not m:
        return None
    slug = m.group(1).replace("/", "-")
    return f"https://standardebooks.org/ebooks/{m.group(1)}/downloads/{slug}.epub"


def _resolve(book: Book) -> tuple[bool, str]:
    if book.status != BookStatus.APPROVED or not book.license_verified:
        return False, "not download-eligible (status/licence gate)"
    if book.epub_path or book.pdf_path:
        return True, "epub/pdf path set"
    try:
        meta = book.source_metadata or {}
        if isinstance(meta, dict) and meta.get("text_url"):
            return True, "source_metadata.text_url"
    except Exception:
        pass
    if book.source == "gutenberg":
        if book.source_id and book.source_id.isdigit():
            return True, "gutenberg source_id"
        gid = _gid_from_url(book.source_url or "")
        if gid:
            return True, f"gutenberg source_url -> {gid}"
        return False, "gutenberg w/o numeric source_id"
    if book.source == "standard_ebooks":
        if _se_epub_from_url(book.source_url or ""):
            return True, "standardebooks slug derivable"
        return False, "standardebooks w/o slug url"
    return False, f"{book.source} w/o direct file"


async def audit(fix: bool, all_catalog: bool) -> None:
    async with AsyncSessionLocal() as db:
        bundles = (await db.execute(select(Bundle))).scalars().all()
        bundle_links: dict[int, list[str]] = {}
        for b in bundles:
            rows = (await db.execute(
                select(BundleBook.book_id).where(BundleBook.bundle_id == b.id)
            )).scalars().all()
            for bid in rows:
                bundle_links.setdefault(bid, []).append(b.slug)

        if all_catalog:
            books = {bk.id: bk for bk in (await db.execute(
                select(Book).where(Book.status == BookStatus.APPROVED)
            )).scalars().all()}
            targets = list(books.values())
        else:
            ids = list(bundle_links.keys())
            books = {bk.id: bk for bk in (await db.execute(
                select(Book).where(Book.id.in_(ids or [0])))).scalars().all()}
            targets = list(books.values())

        broken: list[dict] = []
        derived: list[dict] = []
        for bk in targets:
            ok, why = _resolve(bk)
            if ok:
                continue
            rec = dict(id=bk.id, title=bk.title, author=bk.author or "",
                       source=bk.source or "", source_id=bk.source_id or "",
                       source_url=bk.source_url or "", why=why,
                       bundles=",".join(bundle_links.get(bk.id, [])) or "-")
            if bk.source == "gutenberg" and not (bk.source_id and bk.source_id.isdigit()):
                gid = _gid_from_url(bk.source_url or "")
                if gid:
                    if fix:
                        bk.source_id = gid
                        derived.append({**rec, "fixed": f"source_id={gid}"})
                    else:
                        broken.append(rec)
                    continue
            if bk.source == "standard_ebooks":
                epub = _se_epub_from_url(bk.source_url or "")
                if epub:
                    if fix:
                        bk.epub_path = epub
                        derived.append({**rec, "fixed": f"epub_path={epub}"})
                    else:
                        broken.append(rec)
                    continue
            broken.append(rec)

        by_source: dict[str, int] = {}
        for bk in targets:
            by_source[bk.source or "?"] = by_source.get(bk.source or "?", 0) + 1

        print(f"SOURCE DISTRIBUTION: {len(targets)} books")
        for s, n in sorted(by_source.items(), key=lambda kv: -kv[1]):
            print(f"  {s: <18} {n}")

        if fix:
            print(f"\nDERIVED ({len(derived)}):")
            for each in derived:
                print(f"  + #{each['id']} {each['title'][:64]!r}: {each['fixed']}")

        print(f"\nUNAVAILABLE ({len(broken)}):")
        for r in broken:
            print(f"  - #{r['id']} [{r['source']}] {r['title'][:64]!r} "
                  f"bundles={r['bundles']} :: {r['why']}")

        if fix:
            rejected = 0
            for r in broken:
                await db.execute(sa_delete(BundleBook).where(BundleBook.book_id == r["id"]))
                bk = books.get(r["id"])
                if bk is not None:
                    bk.status = BookStatus.REJECTED
                    rejected += 1
            await db.commit()
            print(f"\nFIXED: {len(derived)} derived, {rejected} rejected/re-pruned.")
        elif not broken:
            print("\nAll books are downloadable.")
        else:
            print("\n(no changes made — re-run with --fix to repair)")


if __name__ == "__main__":
    all_catalog = "--all" in sys.argv
    fix = "--fix" in sys.argv
    asyncio.run(audit(fix=fix, all_catalog=all_catalog))