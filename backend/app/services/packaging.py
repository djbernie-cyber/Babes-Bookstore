import os
import io
import zipfile
import logging
from typing import List
from datetime import datetime

from ..models.book import Book
from ..models.bundle import Bundle
from .storage import storage

logger = logging.getLogger(__name__)


class PackagingService:
    """Generates ZIP bundles of books for delivery."""

    BUNDLE_ZIP_PREFIX = "bundles/"

    def create_bundle_zip(self, bundle: Bundle, books: List[Book]) -> str:
        buffer = io.BytesIO()
        zip_filename = f"{bundle.slug}.zip"

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            metadata = self._build_metadata(bundle, books)
            zf.writestr("README.txt", self._build_readme(bundle, books))
            zf.writestr("metadata.json", metadata)

            for book in books:
                if not book.pdf_path:
                    continue
                content = storage.download_file(book.pdf_path)
                if content:
                    safe_title = self._sanitize_filename(book.title)
                    arcname = f"books/{safe_title}.pdf"
                    zf.writestr(arcname, content)

        buffer.seek(0)
        key = f"{self.BUNDLE_ZIP_PREFIX}{bundle.slug}/{bundle.id}-{int(datetime.utcnow().timestamp())}.zip"

        uploaded = storage.upload_bytes(key, buffer.getvalue(), "application/zip")
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
        lines.append("© Babe's Bookstore")
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