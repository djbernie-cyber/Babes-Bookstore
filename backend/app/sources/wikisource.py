"""Wikisource adapter.

Wikisource hosts transcribed, proofread public domain texts. We prefer the
"Validated texts" category (two-pass proofread) for quality, and fall back
to "Proofread texts".

Text is CC BY-SA 4.0 at minimum, and the underlying works are public
domain, so redistribution is permitted with attribution.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)

BASE = "https://en.wikisource.org"


class WikisourceSource(BaseSource):
    """Wikisource — community-proofread public domain texts."""

    name = "wikisource"
    description = "Wikisource — proofread public domain transcriptions"
    license_type = "public_domain"
    rate_limit = 0.4

    API_URL = f"{BASE}/w/api.php"
    QUALITY_CATEGORIES = ("Category:Validated texts", "Category:Proofread texts")

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
            logger.warning("Wikisource search failed", exc_info=True)
            return []
        return [b for b in (self._parse(h.get("title")) for h in hits) if b][:limit]

    async def list_popular(self, limit: int = 50, start_page: int = 1) -> List[BookMetadata]:
        books: List[BookMetadata] = []
        for category in self.QUALITY_CATEGORIES:
            if len(books) >= limit:
                break
            books.extend(await self._category(category, limit - len(books)))
            await asyncio.sleep(self.rate_limit)
        return books[:limit]

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        return self._parse(source_id.replace("_", " "))

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        """Wikisource exposes EPUB via the wsexport service."""
        if not metadata.epub_url:
            return None
        try:
            await asyncio.sleep(self.rate_limit)
            response = await self.client.get(metadata.epub_url, timeout=60.0)
            if response.status_code == 200 and response.content:
                return response.content
        except Exception:
            logger.debug("Wikisource export failed: %s", metadata.epub_url, exc_info=True)
        return None

    async def _category(self, category: str, limit: int) -> List[BookMetadata]:
        books: List[BookMetadata] = []
        cont: Optional[str] = None

        while len(books) < limit:
            params: Dict[str, Any] = {
                "action": "query", "list": "categorymembers",
                "cmtitle": category, "cmnamespace": "0",
                "cmlimit": min(limit - len(books), 500),
                "format": "json", "formatversion": "2",
            }
            if cont:
                params["cmcontinue"] = cont

            try:
                response = await self.client.get(self.API_URL, params=params)
                response.raise_for_status()
                payload = response.json()
            except Exception:
                logger.warning("Wikisource category fetch failed (%s)", category, exc_info=True)
                break

            for member in payload.get("query", {}).get("categorymembers", []):
                book = self._parse(member.get("title"))
                if book:
                    books.append(book)

            cont = payload.get("continue", {}).get("cmcontinue")
            if not cont:
                break
            await asyncio.sleep(self.rate_limit)

        return books[:limit]

    def _parse(self, title: Optional[str]) -> Optional[BookMetadata]:
        if not title or not title.strip():
            return None
        title = title.strip()

        # Subpages ("Book/Chapter 1") are parts, not whole works.
        if "/" in title or title.startswith(("Page:", "Index:", "Wikisource:")):
            return None

        slug = title.replace(" ", "_")
        export = (
            "https://ws-export.wmcloud.org/?format=epub&lang=en&page=" + slug
        )
        return BookMetadata(
            title=title[:500],
            source=self.name,
            source_id=slug,
            source_url=f"{BASE}/wiki/{slug}",
            license_type="public_domain",
            license_url="https://en.wikisource.org/wiki/Wikisource:Copyright_policy",
            epub_url=export,
            language="en",
        )
