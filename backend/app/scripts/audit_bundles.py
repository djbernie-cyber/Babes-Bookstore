"""Audit download-ability of the catalogue and repair what is derivable.

Runs inside the API container against the live DB. Read-only audit by
default; pass --fix to repair.

    python /app/app/scripts/audit_bundles.py            # bundles only
    python /app/app/scripts/audit_bundles.py --all      # entire approved catalogue
    python /app/app/scripts/audit_bundles.py --all --fix

"Downloadable" mirrors the resolver's candidate logic
(packaging._resolve_book_content / _gutenberg_gid): a book yields bytes when —
  * epub_path / pdf_path are set (R2 key or http), or
  * source_metadata.text_url is set, or
  * a numeric Gutenberg id is reachable (source_id or gutenberg.org URL)

Repairs applied by --fix, in order:
  1. Gutenberg ids / URLs → num; source-id free records get gutenberg epub_path
     backfilled (suppressed / military buckets that were scraped from PG);
  2. standard_ebooks → epub_path derived from the slug;
  3. open_library with a known free edition → gutenberg epub_path;
  4. internet_archive → pdf/text_url derived from archive.org metadata when the
     item is not access-restricted;
  5. oapen / doab → pdf_path derived from the OAI handle page;
  6. wikibooks → text_url from the MediaWiki raw export;
  anything still un-downloadable is dropped from bundles and its status moves
  to REJECTED so it never surfaces as a purchasable title.
"""
import asyncio
import re
import sys
from urllib.parse import quote

sys.path.insert(0, "/app")

import httpx

from sqlalchemy import select, delete as sa_delete

from app.database import AsyncSessionLocal
from app.models.book import Book, BookStatus
from app.models.bundle import Bundle, BundleBook

GUTENBERG_URL_RE = re.compile(r"gutenberg\.org/(?:ebooks|files|cache/epub)/(\d+)")
SE_SLUG_RE = re.compile(r"standardebooks\.org/ebooks/([a-z0-9-]+/[a-z0-9-]+)", re.I)
OAI_HANDLE_RE = re.compile(r"oai:[^:]+:(\d+\.\d+\.\d+/\d+)")
HANDLE_URL_RE = re.compile(r"/(?:handle|bitstream)/?(20\.\d+\.\d+/\d+)")
ARCHIVE_ITEM_RE = re.compile(r"archive\.org/details/([^/?#]+)")

UA = "Mozilla/5.0 (compatible; BabesBookstore/1.0; +https://babesbooks.store) audit"

# Known free Gutenberg editions for works we only hold as Open Library records.
OL_KNOWN = {
    "OL138052W": "11",   # Alice's Adventures in Wonderland
}


def _gid_from_url(url: str) -> str | None:
    m = GUTENBERG_URL_RE.search(url or "")
    return m.group(1) if m else None


def _se_epub_from_url(url: str) -> str | None:
    m = SE_SLUG_RE.search(url or "")
    if not m:
        return None
    slug = m.group(1).replace("/", "_")
    return f"https://standardebooks.org/ebooks/{m.group(1)}/downloads/{slug}.epub"


def _shape_ok(data: bytes, ext: str) -> bool:
    head = data[:32]
    if ext == "epub":
        return head.startswith(b"PK")
    if ext == "pdf":
        return head.startswith((b"%PDF", b"%\xE2\xE3\xCF\xD3"))
    if ext == "txt":
        s = data.lstrip(b"\xef\xbb\xbf \t\r\n")
        return not s.startswith((b"<!DOCTYPE", b"<html", b"<?xml", b"<meta"))
    return True


async def _url_alive(url: str, ext: str = "epub") -> bool:
    """Verify a source file by content shape, not just status code. Error
    pages (HTML/XML stubs served with 200) would pass a HEAD check, so read a
    small preview and confirm the container/format magic bytes. Transient
    errors (429/5xx/network) are treated as alive so flaky sources can never
    mass-reject otherwise healthy titles."""

    def _do(pattern: str) -> bool:
        try:
            r = httpx.get(url, timeout=25, headers={"User-Agent": UA,
                          "Range": "bytes=0-2048"}, follow_redirects=True)
            if r.status_code in (404, 410):
                return False
            if r.status_code >= 400:
                return True if (r.status_code == 429 or r.status_code >= 500) else False
            if not r.content:
                return False
            return _shape_ok(r.content[:2048], ext)
        except Exception:
            return True

    return await asyncio.to_thread(_do, "")


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
        gid = _gid_from_url(book.source_url or "")
        if book.source_id and book.source_id.isdigit():
            return True, "gutenberg source_id"
        if gid:
            return True, f"gutenberg url -> {gid}"
        return False, "gutenberg w/o numeric source_id"
    if book.source == "standard_ebooks":
        if book.epub_path:
            return True, "standardebooks epub set"
        if _se_epub_from_url(book.source_url or ""):
            return False, "standardebooks slug — needs epub backfill"
        return False, "standardebooks w/o slug url"
    if book.source == "open_library":
        gid = OL_KNOWN.get((book.source_id or "").strip())
        if gid and book.epub_path:
            return True, f"open_library known edition ({gid})"
        if gid:
            return False, f"open_library known edition ({gid}) needs epub backfill"
        return False, "open_library w/o known free edition"
    if book.source in ("suppressed", "military", "banned", "african_ebooks"):
        gid = _gid_from_url(book.source_url or "")
        if gid or (book.source_id and book.source_id.isdigit()):
            return True, f"pg-scraped bucket w/ gutenberg {gid or book.source_id}"
        return False, f"{book.source} w/o gutenberg linkage"
    if book.source == "internet_archive":
        if ARCHIVE_ITEM_RE.search(book.source_url or ""):
            return False, "internet_archive item — derivable in --fix"
        return False, "internet_archive w/o item"
    return False, f"{book.source} w/o direct file"


async def audit(fix: bool, all_catalog: bool, verify_se: bool) -> None:
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
        for bk in targets:
            ok, why = _resolve(bk)
            if not ok:
                broken.append(dict(id=bk.id, title=bk.title, author=bk.author or "",
                                   source=bk.source or "", source_id=bk.source_id or "",
                                   source_url=bk.source_url or "", why=why,
                                   bundles=",".join(bundle_links.get(bk.id, [])) or "-"))

        se_updates: list[dict] = []
        if verify_se:
            se_targets = [bk for bk in targets if bk.source == "standard_ebooks"]
            print(f"\nVerifying {len(se_targets)} standardebooks epub urls (concurrent HEAD)...")
            sem = asyncio.Semaphore(16)

            async def _one(bk: Book):
                async with sem:
                    cands = []
                    if bk.epub_path:
                        cands.append(bk.epub_path)
                    d = _se_epub_from_url(bk.source_url or "")
                    if d and d not in cands:
                        cands.append(d)
                    if not cands:
                        return
                    for u in cands:
                        if await _url_alive(u, "epub"):
                            return u
                    return

            results = await asyncio.gather(*(_one(bk) for bk in se_targets))
            dead_ids = 0
            for bk, url in zip(se_targets, results):
                if url is None:
                    if bk.epub_path:  # had a path but every candidate is dead
                        dead_ids += 1
                        if not any(r["id"] == bk.id for r in broken):
                            broken.append(dict(id=bk.id, title=bk.title,
                                               author=bk.author or "", source=bk.source or "",
                                               source_id=bk.source_id or "",
                                               source_url=bk.source_url or "",
                                               why="standardebooks epub dead (404/410)",
                                               bundles=",".join(bundle_links.get(bk.id, [])) or "-", dead=True))
                    continue
                if bk.epub_path != url:
                    se_updates.append(dict(id=bk.id, title=bk.title,
                                           author=bk.author or "", source=bk.source or "",
                                           source_id=bk.source_id or "",
                                           source_url=bk.source_url or "",
                                           why="stale standardebooks path", url=url,
                                           bundles=",".join(bundle_links.get(bk.id, [])) or "-"))
            print(f"  live={len(se_targets)} dead={dead_ids} stale_path_to_rewrite={len(se_updates)}")

        by_source: dict[str, int] = {}
        for bk in targets:
            by_source[bk.source or "?"] = by_source.get(bk.source or "?", 0) + 1

        print(f"SOURCE DISTRIBUTION: {len(targets)} books")
        for s, n in sorted(by_source.items(), key=lambda kv: -kv[1]):
            print(f"  {s: <18} {n}")

        print(f"\nUNAVAILABLE ({len(broken)}):")
        for r in broken:
            print(f"  - #{r['id']} [{r['source']}] {r['title'][:64]!r} "
                  f"bundles={r['bundles']} :: {r['why']}")

        if not fix:
            print("\n(no changes made — re-run with --fix to repair)")
            return

        fixed: list[dict] = []
        rejected: list[dict] = []

        def _mark_fixed(r, how):
            fixed.append({**r, "fixed": how})

        def _gutenberg_epub(book, gid):
            book.epub_path = f"https://www.gutenberg.org/ebooks/{gid}.epub3.images"

        for r in se_updates:
            bk = books.get(r["id"])
            if bk is None:
                continue
            bk.epub_path = r["url"]
            _mark_fixed(r, f"epub_path={r['url']} (rewrote stale path)")

        for r in broken:
            bk = books.get(r["id"])
            if bk is None:
                rejected.append(r)
                continue

            if r.get("dead"):
                rejected.append({**r, "why": "standardebooks epub dead (404/410)"})
                continue

            # 1. PG-scraped buckets (suppressed / military / african_ebooks…) → epub path
            gid = _gid_from_url(bk.source_url or "")
            if not gid and bk.source_id and bk.source_id.isdigit() and "gutenberg.org" in (bk.source_url or ""):
                gid = bk.source_id
            if gid and bk.source in ("suppressed", "military", "banned", "african_ebooks"):
                _gutenberg_epub(bk, gid)
                _mark_fixed(r, f"epub_path={bk.epub_path}")
                continue

            if bk.source == "gutenberg":
                _gutenberg_epub(bk, bk.source_id)
                _mark_fixed(r, f"epub_path={bk.epub_path}")
                continue

            # 2. standard_ebooks (verify before trusting a derived URL)
            epub = _se_epub_from_url(bk.source_url or "")
            if epub:
                if await _url_alive(epub, "epub"):
                    bk.epub_path = epub
                    _mark_fixed(r, f"epub_path={epub}")
                else:
                    rejected.append({**r, "why": "standardebooks epub dead (404/410)"})
                continue

            # 3. open_library known editions
            ok = OL_KNOWN.get((bk.source_id or "").strip())
            if ok:
                _gutenberg_epub(bk, ok)
                _mark_fixed(r, f"epub_path={bk.epub_path} (OL->PG {ok})")
                continue

            # 4. internet_archive item → pdf or text from metadata
            if bk.source == "internet_archive":
                im = ARCHIVE_ITEM_RE.search(bk.source_url or "")
                if im:
                    ident = im.group(1)
                    try:
                        meta = httpx.get(f"https://archive.org/metadata/{ident}",
                                         timeout=25, headers={"User-Agent": UA}).json()
                        restricted = (meta.get("metadata", {}).get("access-restricted-item") or "") == "true"
                        pdf = next((f["name"] for f in meta.get("files", [])
                                    if f.get("name", "").endswith(".pdf")
                                    and "_encrypted" not in f["name"] and "_lcp" not in f["name"]), None)
                        txt = next((f["name"] for f in meta.get("files", [])
                                    if f.get("name", "").endswith("_djvu.txt")), None)
                        if not restricted and pdf:
                            bk.pdf_path = f"https://archive.org/download/{ident}/{pdf}"
                            _mark_fixed(r, f"pdf_path={bk.pdf_path}")
                            continue
                        if not restricted and txt:
                            md = dict(bk.source_metadata or {})
                            md["text_url"] = f"https://archive.org/download/{ident}/{txt}"
                            bk.source_metadata = md
                            _mark_fixed(r, f"text_url={md['text_url']}")
                            continue
                        if restricted:
                            rejected.append({**r, "why": "archive item is loan-restricted"})
                            continue
                    except Exception as e:
                        rejected.append({**r, "why": f"archive metadata error: {e}"})
                        continue

            # 5. oapen / doab → pdf from the OAI handle page
            if bk.source in ("oapen", "doab"):
                src_url = bk.source_url or ""
                handle = None
                moai = OAI_HANDLE_RE.search((bk.source_id or "") + "|" + src_url)
                if moai:
                    handle = moai.group(1)
                else:
                    murl = HANDLE_URL_RE.search(src_url)
                    if murl:
                        handle = murl.group(1)
                if handle:
                    base = "library.oapen.org" if bk.source == "oapen" else "directory.doabooks.org"
                    try:
                        res = httpx.get(f"https://{base}/handle/{handle}",
                                        timeout=25, headers={"User-Agent": UA})
                        href = re.search(r'href="/?(bitstream/handle/[^"]+?\.pdf)"', res.text)
                        if href and "oapen.org" in href.group(1):
                            base_o = "https://library.oapen.org"
                        elif href:
                            base_o = f"https://{base}"
                        else:
                            raise ValueError("no bitstream pdf href")
                        url = base_o + "/" + href.group(1).lstrip("/")
                        if url and url.startswith("https://"):
                            bk.pdf_path = url
                            _mark_fixed(r, f"pdf_path={url}")
                            continue
                        raise ValueError("unusable pdf url")
                    except Exception as e:
                        rejected.append({**r, "why": f"{bk.source} handle scrape failed: {e}"})
                        continue

            # 6. wikibooks → MediaWiki raw text
            if bk.source == "wikibooks" and "/wiki/" in (bk.source_url or ""):
                title = bk.source_url.rsplit("/wiki/", 1)[-1]
                md = dict(bk.source_metadata or {})
                md["text_url"] = f"https://en.wikibooks.org/w/index.php?title={quote(title)}&action=raw"
                bk.source_metadata = md
                _mark_fixed(r, f"text_url={md['text_url']}")
                continue

            rejected.append(r)

        print(f"\nFIXED ({len(fixed)}):")
        for each in fixed:
            print(f"  + #{each['id']} {each['title'][:64]!r}: {each['fixed']}")

        print(f"\nREJECTED ({len(rejected)}):")
        for r in rejected:
            print(f"  - #{r['id']} [{r['source']}] {r['title'][:64]!r} "
                  f"bundles={r['bundles']} :: {r['why']}")

        for r in rejected:
            await db.execute(sa_delete(BundleBook).where(BundleBook.book_id == r["id"]))
            bk = books.get(r["id"])
            if bk is not None:
                bk.status = BookStatus.REJECTED

        await db.commit()
        print(f"\nDONE: {len(fixed)} derived/fixed, {len(rejected)} rejected + bundle-pruned.")


if __name__ == "__main__":
    all_catalog = "--all" in sys.argv
    fix = "--fix" in sys.argv
    verify_se = "--verify-se" in sys.argv
    asyncio.run(audit(fix=fix, all_catalog=all_catalog, verify_se=verify_se))