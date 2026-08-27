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
    """

    BUNDLE_ZIP_PREFIX = "bundles/"

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

    def _resolve_book_content(self, book: Book) -> Tuple[Optional[bytes], str]:
        """Return (bytes, extension) for the best available file for a book."""
        # 1. Try local/R2 cache if the path is not a URL
        for attr, ext in [(book.epub_path, "epub"), (book.pdf_path, "pdf"), (book.cover_path, "jpg")]:
            if attr and not attr.startswith("http"):
                data = self._try_local_r2(attr)
                if data:
                    return data, ext

        # 2. Try remote URLs in priority order
        candidates: List[Tuple[str, str]] = []
        if book.epub_path and book.epub_path.startswith("http"):
            candidates.append((book.epub_path, "epub"))
        if book.pdf_path and book.pdf_path.startswith("http"):
            candidates.append((book.pdf_path, "pdf"))
        # text_url is in source_metadata
        try:
            meta = book.source_metadata or {}
            text_url = meta.get("text_url") if isinstance(meta, dict) else None
            if text_url and isinstance(text_url, str) and text_url.startswith("http"):
                candidates.append((text_url, "txt"))
        except Exception:
            pass
        # cover as fallback content? prefer not to use cover as book content, but keep as extra
        # Gutenberg fallback URLs based on source_id
        if book.source == "gutenberg" and book.source_id and book.source_id.isdigit():
            gid = book.source_id
            candidates.append((f"https://www.gutenberg.org/ebooks/{gid}.txt.utf-8", "txt"))
            candidates.append((f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt", "txt"))
            candidates.append((f"https://www.gutenberg.org/files/{gid}/{gid}-0.txt", "txt"))
            candidates.append((f"https://www.gutenberg.org/ebooks/{gid}.epub3.images", "epub"))
            candidates.append((f"https://www.gutenberg.org/ebooks/{gid}.epub.images", "epub"))

        # Also try source_url if it's a direct file (unlikely but safe)
        # source_url is usually https://www.gutenberg.org/ebooks/<id> HTML page, not direct file, skip

        for url, ext in candidates:
            data = self._fetch_remote(url)
            if data and len(data) > 500:  # avoid tiny error pages
                return data, ext

        # 3. Last resort: try to fetch via Gutenberg HTML page and scrape? skip
        logger.warning("No downloadable file found for book %s (id=%s, source=%s/%s)", book.title, book.id, book.source, book.source_id)
        return None, "txt"

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
        # storage fallback writes locally even when R2 missing, so uploaded is still key
        if not uploaded:
            logger.error("Failed to store bundle zip for %s — even local fallback failed", bundle.slug)
            # As absolute last resort, write to /tmp so at least something exists
            try:
                fallback = f"/tmp/{bundle.slug}_{bundle.id}.zip"
                with open(fallback, "wb") as f:
                    f.write(data)
                logger.info("Wrote bundle zip to fallback %s", fallback)
                return fallback
            except Exception:
                pass
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
