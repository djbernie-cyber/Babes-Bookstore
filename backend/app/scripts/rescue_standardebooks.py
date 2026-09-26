"""Re-source the rejected Standard Ebooks records, and keep the rest rejected.

Runs inside the API container against the live DB.

    python /app/app/scripts/rescue_standardebooks.py --dry-run
    python /app/app/scripts/rescue_standardebooks.py
    python /app/app/scripts/rescue_standardebooks.py --limit 200

For every REJECTED standard_ebooks book, in order:

  1. SE direct download — derive the real ``?source=download`` epub url and keep
     the title only if that url serves actual epub bytes (ranged GET + magic).
     This restores the titles an earlier sweep wrongly rejected because it
     probed the HTML funnel instead of the file.
  2. Gutenberg — match the title against a licence-verified, downloadable
     Gutenberg-sourced book we already hold, re-point the record at that
     edition and record the original Standard Ebooks url as provenance.
  3. Otherwise the book stays REJECTED and is reported with its reason.

Nothing is approved on a title match alone: the replacement file is fetched and
shape-checked before the record is flipped, and a rescue is skipped whenever
the author is known and disagrees.
"""
import asyncio
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.book import Book, BookStatus
from app.scripts.audit_bundles import (
    GUTENBERG_URL_RE,
    _se_epub_from_url,
    _url_alive,
)

# Records we are willing to serve a Gutenberg file for.
PG_SOURCES = ("gutenberg", "suppressed", "military", "banned", "african_ebooks")

ARTICLES = ("the", "a", "an")


def _norm(s: str | None) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
    toks = [t for t in s.split() if t not in ARTICLES]
    return " ".join(toks)


def _surname(author: str | None) -> str:
    # Project Gutenberg catalogues authors as "Wells, H. G." (surname first),
    # while the SE scraper stores "H. G. Wells". Handle both.
    raw = (author or "").strip()
    if "," in raw:
        toks = _norm(raw.split(",")[0]).split()
        if toks:
            return toks[-1]
    toks = _norm(raw).split()
    return toks[-1] if toks else ""


def _title_match(a: str, b: str) -> bool:
    """Deliberately strict: an exact normalised title, or one title being a
    clean prefix of the other (catches 'X' vs 'X: A Subtitle')."""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) < len(b) else (b, a)
    return len(short) >= 8 and long.startswith(short + " ")


def _author_ok(a: str | None, b: str | None) -> bool:
    """Unknown authors are permissive; two known authors must agree on the
    family name so we never graft one author's book onto another's."""
    sa, sb = _surname(a), _surname(b)
    if not sa or not sb:
        return True
    if sa == sb:
        return True
    return len(sa) >= 5 and len(sb) >= 5 and (sa in sb or sb in sa)


def _pg_file(cand: Book) -> tuple[str, str] | None:
    """The verified file we can point a rescued record at."""
    gid = None
    m = GUTENBERG_URL_RE.search(cand.source_url or "")
    if m:
        gid = m.group(1)
    if not gid and (cand.source_id or "").isdigit():
        gid = cand.source_id
    if gid:
        return gid, f"https://www.gutenberg.org/ebooks/{gid}.epub3.images"
    if cand.epub_path and cand.epub_path.startswith("http"):
        return "", cand.epub_path
    return None


async def _apply(restored: list[dict], rescued: list[dict]) -> tuple[int, int]:
    """Write the flips in a fresh session and then prove they landed.

    The probe phase deliberately runs outside any session (it is slow and
    network-bound), so the Book instances it started from are detached by
    then and mutating them would commit nothing. Re-fetch the rows by id,
    and re-read the statuses afterwards rather than trusting the commit.
    """
    ids = [r["id"] for r in restored + rescued]
    if not ids:
        return 0, 0

    async with AsyncSessionLocal() as db:
        books = (await db.execute(
            select(Book).where(Book.id.in_(ids))
        )).scalars().all()
        by_id = {b.id: b for b in books}
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

        for r in restored:
            bk = by_id.get(r["id"])
            if bk is None:
                continue
            bk.epub_path = r["url"]
            bk.status = BookStatus.APPROVED

        for r in rescued:
            bk = by_id.get(r["id"])
            if bk is None:
                continue
            # Keep the record's standard_ebooks identity and just point it at a
            # verified Gutenberg file. Re-pointing source/source_id would
            # collide with the UNIQUE(source, source_id) index as soon as two
            # SE records rescue onto the same Gutenberg edition, aborting the
            # whole sweep; the provenance lives in source_metadata instead.
            bk.epub_path = r["url"]
            bk.status = BookStatus.APPROVED
            meta = dict(bk.source_metadata or {})
            meta.update({
                "rescued_from": "standard_ebooks",
                "served_from": "gutenberg",
                "gutenberg_gid": r["gid"] or None,
                "rescued_from_title": r["from_title"],
                "rescued_from_author": r["from_author"],
                "rescued_at": stamp,
            })
            bk.source_metadata = meta

        await db.commit()

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Book.status).where(Book.id.in_(ids))
        )).scalars().all()
        approved = sum(1 for st in rows if st == BookStatus.APPROVED)
    return len(ids), approved


async def run(limit: int | None = None, dry_run: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        stmt = select(Book).where(
            Book.status == BookStatus.REJECTED,
            Book.source == "standard_ebooks",
        ).order_by(Book.id)
        if limit:
            stmt = stmt.limit(limit)
        targets = (await db.execute(stmt)).scalars().all()

        pool = (await db.execute(select(Book).where(
            Book.status == BookStatus.APPROVED,
            Book.license_verified.is_(True),
            Book.source.in_(PG_SOURCES),
        ))).scalars().all()

    index: dict[str, list[Book]] = {}
    for cand in pool:
        if _pg_file(cand):
            index.setdefault(_norm(cand.title), []).append(cand)
    print(f"rescue candidates: {len(targets)} rejected standard_ebooks")
    print(f"gutenberg pool:    {sum(len(v) for v in index.values())} verified across "
          f"{len(index)} distinct titles\n")

    verified: dict[str, bool] = {}
    sem = asyncio.Semaphore(16)

    async def alive(url: str) -> bool:
        if url not in verified:
            async with sem:
                if url not in verified:
                    verified[url] = await _url_alive(url, "epub")
        return verified[url]

    async def probe(book: Book) -> dict:
        row = {"id": book.id, "title": book.title, "author": book.author, "how": "", "url": ""}

        se_why = "no standard ebooks url"
        epub = _se_epub_from_url(book.source_url or "")
        if epub:
            epub += "?source=download" if "?" not in epub else ""
            if await alive(epub):
                row.update(how="restored-se", url=epub)
                return row
            se_why = "standard ebooks epub not published"

        # Fall through to Gutenberg even when the SE url is unusable: a
        # re-sourced edition only needs the title and author to match.
        tnorm = _norm(book.title)
        for cand in index.get(tnorm, []):
            if not _author_ok(book.author, cand.author):
                continue
            hit = _pg_file(cand)
            if not hit:
                continue
            _gid, url = hit
            if not await alive(url):
                continue
            row.update(how="rescued-gutenberg", url=url,
                       gid=_gid, from_title=cand.title, from_author=cand.author)
            return row
        row["why"] = f"{se_why}; no verified gutenberg edition"
        return row

    results = await asyncio.gather(*(probe(b) for b in targets))

    restored = [r for r in results if r["how"] == "restored-se"]
    rescued = [r for r in results if r["how"] == "rescued-gutenberg"]
    kept = [r for r in results if not r["how"]]

    print(f"RESTORED FROM STANDARD EBOOKS ({len(restored)}):")
    for r in restored:
        print(f"  + #{r['id']} {r['title'][:64]!r}")
    print(f"\nRESCUED FROM GUTENBERG ({len(rescued)}):")
    for r in rescued:
        print(f"  + #{r['id']} {r['title'][:64]!r} <- {r['from_title'][:44]!r} gid={r['gid'] or '-'}")
    print(f"\nKEPT REJECTED ({len(kept)}):")
    for r in kept[:200]:
        print(f"  - #{r['id']} {r['title'][:64]!r} :: {r['why']}")
    if len(kept) > 200:
        print(f"  ... and {len(kept) - 200} more")

    if dry_run:
        print(f"\nDRY RUN — {len(restored)} restored, {len(rescued)} re-sourced, "
              f"{len(kept)} kept rejected. {len(verified)} urls verified.")
        return

    written, approved = await _apply(restored, rescued)
    print(f"\nDONE: {len(restored)} restored, {len(rescued)} re-sourced, "
          f"{len(kept)} kept rejected. {len(verified)} urls verified.")
    print(f"WRITE CHECK: {written} rows targeted, {approved} now APPROVED in the database.")
    if written != approved:
        print("!! WRITE CHECK FAILED — some rows did not flip; re-run before trusting counts.")


if __name__ == "__main__":
    asyncio.run(run(
        limit=int(sys.argv[sys.argv.index("--limit") + 1])
        if "--limit" in sys.argv else None,
        dry_run="--dry-run" in sys.argv,
    ))
