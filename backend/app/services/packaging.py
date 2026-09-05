import os
import io
import zipfile
import logging
from typing import List, Optional, Tuple
from datetime import datetime

import httpx

from ..models.book import Book
from ..models.bundle import Bundle
from .storage import storage

logger = logging.getLogger(__name__)


class PackagingService:
    """Generates ZIP bundles of books for delivery.

    Each book is fetched from its remote source URL (Gutenberg, etc) when
    not already cached in R2/local storage. The ZIP always contains a
    README and metadata.json even if some book downloads fail.

    To keep repeated packaging fast and rate-limit-safe, every fetched file
    is written to a per-book cache (keyed by source + source_id). A later
    package request reuses the cached bytes instead of hitting the archive
    again, so building the same bundle twice is near-instant.
    """

    BUNDLE_ZIP_PREFIX = "bundles/"
    BOOK_CACHE_PREFIX = "book-cache/"

    # Gutenberg blocks generic clients without a browser-like UA
    USER_AGENT = "Mozilla/5.0 (compatible; BabesBookstore/1.0; +https://babesbooks.store) bundle-packer"

    def _fetch_remote(self, url: str, timeout: float = 30.0) -> Optional[bytes]:
        try:
            with httpx.Client(follow_redirects=True, timeout=timeout, headers={"User-Agent": self.USER_AGENT, "Accept": "*/*"}) as client:
                resp = client.get(url)
                if resp.status_code == 200 and resp.content:
                    # Basic sanity: avoid HTML error pages masquerading as books
                    ctype = (resp.headers.get("content-type") or "").lower()
                    if "text/html" in ctype and len(resp.content) < 2000 and b"<html" in resp.content.lower():
                        logger.warning("Remote %s returned HTML (%s) — skipping", url, ctype)
                        return None
                    return resp.content
                logger.warning("Remote fetch %s -> %s", url, resp.status_code)
        except Exception as e:
            logger.warning("Remote fetch failed %s: %s", url, e)
        return None

    def _try_local_r2(self, key: str) -> Optional[bytes]:
        if not key or key.startswith("http"):
            return None
        # key looks like an R2 path, try storage
        try:
            data = storage.download_file(key)
            if data:
                return data
        except Exception as e:
            logger.debug("R2 download failed for %s: %s", key, e)
        return None

    def _cache_key(self, book: Book, ext: str) -> str:
        """Stable storage key for a single book's fetched file."""
        sid = book.source_id or str(book.id)
        return f"{self.BOOK_CACHE_PREFIX}{book.source}/{sid}.{ext}"

    def _resolve_book_content(self, book: Book) -> Tuple[Optional[bytes], str]:
        """Return (bytes, extension) for the best available file for a book.

        Order of preference:
          1. The per-book cache (persisted across runs) — makes repeat
             packaging near-instant and avoids hammering remote sources.
          2. A locally-stored path on the book record (legacy direct paths).
          3. A remote URL, which is fetched once and then cached.
        """
        # 1. Local/R2 cached copy first (covers both direct-stored and fetched)
        # Try the cache whenever we have a source identity.
        source_id = book.source_id or (str(book.id) if book.source else None)
        if book.source and source_id:
            for ext in ("epub", "pdf", "txt"):
                cached = self._try_local_r2(self._cache_key(book, ext))
                if cached:
                    return cached, ext

        # 2. Legacy direct-stored paths (R2 keys, not URLs)
        for attr, ext in [(book.epub_path, "epub"), (book.pdf_path, "pdf"), (book.cover_path, "jpg")]:
            if attr and not attr.startswith("http"):
                data = self._try_local_r2(attr)
                if data:
                    return data, ext

        # 3. Remote URLs in priority order (fetch once, then cache)
        candidates: List[Tuple[str, str]] = []
        if book.epub_path and book.epub_path.startswith("http"):
            candidates.append((book.epub_path, "epub"))
        if book.pdf_path and book.pdf_path.startswith("http"):
            candidates.append((book.pdf_path, "pdf"))
        try:
            meta = book.source_metadata or {}
            text_url = meta.get("text_url") if isinstance(meta, dict) else None
            if text_url and isinstance(text_url, str) and text_url.startswith("http"):
                candidates.append((text_url, "txt"))
        except Exception:
            pass
        # Gutenberg fallback URLs based on source_id
        if book.source == "gutenberg" and book.source_id and book.source_id.isdigit():
            gid = book.source_id
            candidates.append((f"https://www.gutenberg.org/ebooks/{gid}.txt.utf-8", "txt"))
            candidates.append((f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt", "txt"))
            candidates.append((f"https://www.gutenberg.org/files/{gid}/{gid}-0.txt", "txt"))
            candidates.append((f"https://www.gutenberg.org/ebooks/{gid}.epub3.images", "epub"))
            candidates.append((f"https://www.gutenberg.org/ebooks/{gid}.epub.images", "epub"))

        for url, ext in candidates:
            data = self._fetch_remote(url)
            if data and len(data) > 500:  # avoid tiny error pages
                self._cache_content(book, ext, data)
                return data, ext

        logger.warning("No downloadable file found for book %s (id=%s, source=%s/%s)", book.title, book.id, book.source, book.source_id)
        return None, "txt"

    def _cache_content(self, book: Book, ext: str, data: bytes) -> None:
        """Persist a fetched file to the per-book cache for future reuse."""
        if not book.source:
            return
        sid = book.source_id or str(book.id)
        key = self._cache_key(book, ext)
        try:
            storage.upload_bytes(key, data, "application/octet-stream")
            logger.debug("Cached %s for book %s", key, book.id)
        except Exception as e:
            logger.warning("Failed to cache %s for book %s: %s", key, book.id, e)

    def _resolve_book_text(self, book: Book) -> Optional[str]:
        """Return plain-text content for the in-browser reader (prefers txt).

        Order of preference (mirrors download logic but text-first):
          1. Cached plain text for this book.
          2. A ``text_url`` recorded in source metadata.
          3. Gutenberg .txt fallbacks derived from ``source_id``.
        Returns ``None`` when only binary formats (epub/pdf) exist — the caller
        can then fall back to the epub-centric resolver or the download URL.

        Truncates very large works so the reader stays responsive behind the
        Netlify /api proxy.
        """
        if not book.source:
            return None
        source_id = book.source_id or str(book.id)

        # 1. Cached .txt
        cached = self._try_local_r2(self._cache_key(book, "txt"))
        if cached:
            return self._human_text(cached)

        # 2. Remote URL from source metadata
        url: Optional[str] = None
        try:
            meta = book.source_metadata or {}
            candidate = meta.get("text_url") if isinstance(meta, dict) else None
            if candidate and isinstance(candidate, str) and candidate.startswith("http"):
                url = candidate
        except Exception:
            pass

        # 3. Gutenberg plain-text mirrors
        if book.source == "gutenberg" and source_id.isdigit():
            gid = source_id
            url = f"https://www.gutenberg.org/ebooks/{gid}.txt.utf-8"

        if not url:
            return None

        data = self._fetch_remote(url, timeout=60.0)
        if not data or len(data) < 500:
            return None
        self._cache_content(book, "txt", data)
        return self._human_text(data)

    def _human_text(self, data: bytes, cap: int = 1_500_000) -> str:
        """Decode reader-facing text, dropping the Gutenberg boilerplate header
        so the reader starts at the book proper, and cap oversized works."""
        import re
        text = data[:cap]
        for enc in ("utf-8", "utf-16", "latin-1"):
            try:
                text = text.decode(enc)
                break
            except (UnicodeDecodeError, ValueError):
                continue
        # Trim the standard "The Project Gutenberg eBook of ..." preamble, three
        # asterisk lines, and any licence block up to and including the release date.
        match = re.search(r"(?im)^\*{3}\s*START OF (THIS|THE) PROJECT GUTENBERG", text)
        if match:
            start = text.find("\n", match.end())
            text = text[start + 1:] if start != -1 else text
        return text.strip()

    def create_bundle_zip(self, bundle: Bundle, books: List[Book]) -> str:
        buffer = io.BytesIO()
        zip_filename = f"{bundle.slug}.zip"
        included = 0
        skipped = 0

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            metadata = self._build_metadata(bundle, books)
            zf.writestr("README.txt", self._build_readme(bundle, books))
            zf.writestr("metadata.json", metadata)

            for book in books:
                content, ext = self._resolve_book_content(book)
                if not content:
                    skipped += 1
                    # Still record that book was attempted; add a placeholder note
                    safe_title = self._sanitize_filename(book.title)
                    note = f"This book could not be downloaded automatically.\nTitle: {book.title}\nAuthor: {book.author or 'Unknown'}\nSource: {book.source_url or book.source}\nTry: https://www.gutenberg.org/ebooks/{book.source_id} if available.\n"
                    zf.writestr(f"books/{safe_title}.NOTE.txt", note)
                    continue

                safe_title = self._sanitize_filename(book.title)
                # Use extension from fetch; ensure reasonable filename
                arcname = f"books/{safe_title}.{ext}"
                # Avoid duplicate names in zip
                counter = 2
                while arcname in zf.namelist():
                    arcname = f"books/{safe_title}_{counter}.{ext}"
                    counter += 1
                try:
                    zf.writestr(arcname, content)
                    included += 1
                except Exception as e:
                    logger.warning("Zip write failed for %s: %s", arcname, e)
                    skipped += 1

            # Summary file for transparency
            summary = f"Bundle: {bundle.name}\nIncluded files: {included}\nUnavailable: {skipped}\nTotal in bundle: {len(books)}\nGenerated: {datetime.utcnow().isoformat()}Z\n"
            zf.writestr("SUMMARY.txt", summary)

        buffer.seek(0)
        data = buffer.getvalue()
        key = f"{self.BUNDLE_ZIP_PREFIX}{bundle.slug}/{bundle.id}-{int(datetime.utcnow().timestamp())}.zip"

        uploaded = storage.upload_bytes(key, data, "application/zip")
        if not uploaded:
            logger.error("Failed to store bundle zip for %s — even local fallback failed", bundle.slug)
            try:
                local = storage._local_path(key)
                os.makedirs(os.path.dirname(local), exist_ok=True)
                with open(local, "wb") as f:
                    f.write(data)
                logger.info("Wrote bundle zip to fallback local %s", local)
                return key
            except Exception as e:
                logger.error("Fallback local write failed for %s: %s", key, e)
            return key

        logger.info("Bundle %s packaged: %s books included=%s skipped=%s size=%s bytes -> %s", bundle.slug, len(books), included, skipped, len(data), key)
        return uploaded or key

    def _build_readme(self, bundle: Bundle, books: List[Book]) -> str:
        lines = [
            f"{bundle.name}",
            "=" * len(bundle.name),
            "",
            bundle.description or "",
            "",
            f"Books in this bundle ({len(books)}):",
            "",
        ]
        for i, book in enumerate(books, 1):
            author = book.author or "Unknown Author"
            lines.append(f"  {i}. {book.title} — {author}")
            if book.license_type:
                lines.append(f"     License: {book.license_type}")
        lines.append("")
        lines.append("All books in this bundle are in the public domain or licensed for")
        lines.append("commercial redistribution. Please check individual license terms.")
        lines.append("")
        lines.append("Files are provided as EPUB, PDF or plain text depending on what the")
        lines.append("source makes available. If a book shows as .NOTE.txt, the remote")
        lines.append("file was temporarily unavailable — you can download it directly from")
        lines.append("the source URL listed in metadata.json.")
        lines.append("")
        lines.append("© Babe's Bookstore — https://babesbooks.store")
        return "\n".join(lines)

    def _build_metadata(self, bundle: Bundle, books: List[Book]) -> str:
        import json
        data = {
            "bundle": {
                "id": bundle.id,
                "name": bundle.name,
                "slug": bundle.slug,
                "description": bundle.description,
            },
            "books": [
                {
                    "id": b.id,
                    "title": b.title,
                    "author": b.author,
                    "license": b.license_type,
                    "source": b.source,
                    "source_url": b.source_url,
                    "epub_url": b.epub_path if b.epub_path and b.epub_path.startswith("http") else None,
                    "pdf_url": b.pdf_path if b.pdf_path and b.pdf_path.startswith("http") else None,
                    "text_url": (b.source_metadata or {}).get("text_url") if isinstance(b.source_metadata, dict) else None,
                }
                for b in books
            ],
            "generated_at": datetime.utcnow().isoformat(),
        }
        return json.dumps(data, indent=2)

    def _sanitize_filename(self, name: str) -> str:
        safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_"))
        return safe[:100].strip() or "untitled"


packaging = PackagingService()
