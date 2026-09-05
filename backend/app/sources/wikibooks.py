"""Wikibooks adapter.

Wikibooks is a Wikimedia project hosting user-written, collaboratively
edited instructional books. Content is released CC BY-SA, so redistribution
is permitted with attribution. We drop transwiki/meta pages and subpages —
only top-level book pages are treated as works.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)

BASE = "https://en.wikibooks.org"


class WikibooksSource(BaseSource):
    """Wikibooks — CC BY-SA instructional books."""

    name = "wikibooks"
    description = "Wikibooks — open CC BY-SA textbooks and instructional works"
    license_type = "cc_by_sa_4.0"
    rate_limit = 0.35

    API_URL = f"{BASE}/w/api.php"
    LICENSE_URL = "https://en.wikibooks.org/wiki/Wikibooks:Copyright"
    CATEGORY = "Teaching & Education"

    def __init__(self):
        super().__init__()
        #: Opaque continuation token from the MediaWiki API, so a sequential
        #: ``start_page`` walk continues where the previous call stopped.
        self._ap_continue: Optional[str] = None

    async def search(self, query: str, limit: int = 20) -> List[BookMetadata]:
        if not query:
            return await self.list_popular(limit)
        try:
            response = await self.client.get(self.API_URL, params={
                "action": "query", "list": "search", "srsearch": query,
                "srnamespace": "0", "srlimit": min(limit, 50),
                "format": "json", "formatversion": "2",
            })
            response.raise_for_status()
            hits = response.json().get("query", {}).get("search", [])
        except Exception:
            logger.warning("Wikibooks search failed", exc_info=True)
            return []
        return [b for b in (self._parse(h.get("title")) for h in hits) if b][:limit]

    async def list_popular(self, limit: int = 50, start_page: int = 1) -> List[BookMetadata]:
        self._ap_continue = None  # a fresh walk always starts from the top
        books: List[BookMetadata] = []
        while len(books) < limit:
            params: Dict[str, Any] = {
                "action": "query", "list": "allpages",
                "apnamespace": "0", "apfilterredir": "nonredirects",
                "aplimit": min(limit - len(books) + 100, 500),
                "format": "json", "formatversion": "2",
            }
            if self._ap_continue:
                params["apcontinue"] = self._ap_continue
            try:
                response = await self.client.get(self.API_URL, params=params)
                response.raise_for_status()
                payload = response.json()
            except Exception:
                logger.warning("Wikibooks page list failed", exc_info=True)
                break
            for page in payload.get("query", {}).get("allpages", []):
                book = self._parse(page.get("title"))
                if book:
                    books.append(book)
                if len(books) >= limit:
                    break
            self._ap_continue = payload.get("continue", {}).get("apcontinue")
            if not self._ap_continue:
                break
            await asyncio.sleep(self.rate_limit)
        return books[:limit]

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        return self._parse(source_id.replace("_", " "))

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        """Render the book as HTML paragraphs for the reader."""
        if not metadata.source_id:
            return None
        try:
            await asyncio.sleep(self.rate_limit)
            response = await self.client.get(self.API_URL, params={
                "action": "parse", "page": metadata.source_id,
                "prop": "text", "format": "json", "formatversion": "2",
            }, timeout=90.0)
            response.raise_for_status()
            html = response.json().get("parse", {}).get("text", "")
            if not html:
                return None
            return html if isinstance(html, str) else (html.get("*") or "").encode("utf-8")
        except Exception:
            logger.debug("Wikibooks parse failed: %s", metadata.source_id, exc_info=True)
            return None

    def _parse(self, title: Optional[str]) -> Optional[BookMetadata]:
        if not title or not title.strip():
            return None
        title = title.strip()
        # Subpages ("Book/Chapter") are parts, and a few prefixes are meta pages.
        if "/" in title or title.startswith(("Wikibooks:", "Help:", "Cookbook/", "Template:")):
            return None
        slug = title.replace(" ", "_")
        return BookMetadata(
            title=title[:500],
            source=self.name,
            source_id=slug,
            source_url=f"{BASE}/wiki/{slug}",
            license_type=self.license_type,
            license_url=self.LICENSE_URL,
            category=self.CATEGORY,
            tags=[self.CATEGORY, "Non-Fiction"],
            language="en",
        )