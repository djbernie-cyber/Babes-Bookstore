"""Biodiversity Heritage Library adapter.

BHL digitises public-domain biodiversity and natural-history literature
(books, articles, serials). Core content is pre-1928 and public domain, so
items are included directly. The BHL API requires a free key (BHL_API_KEY);
without it the adapter reports itself and yields nothing.
"""
import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)

BASE = "https://www.biodiversitylibrary.org/api3"


class BiodiversitySource(BaseSource):
    """BHL - public-domain biodiversity and natural-history literature."""

    name = "biodiversity"
    description = "Biodiversity Heritage Library - public-domain natural history"
    license_type = "public_domain"
    rate_limit = 1.0
    requires_api_key = True

    LICENSE_URL = "https://www.biodiversitylibrary.org/about"
    CATEGORY = "Nature/Gardening/Animals"

    def __init__(self):
        super().__init__()
        self.api_key: Optional[str] = os.environ.get("BHL_API_KEY")

    def _params(self, **extra: Any) -> Dict[str, Any]:
        params: Dict[str, Any] = {"format": "json", "apikey": self.api_key or ""}
        params.update(extra)
        return params

    async def _get(self, op: str, **params: Any) -> List[Dict[str, Any]]:
        if not self.api_key:
            logger.info("BHL API key not configured; skipping %s", op)
            return []
        await asyncio.sleep(self.rate_limit)
        try:
            response = await self.client.get(BASE, params=self._params(op=op, **params))
            response.raise_for_status()
            return response.json().get("Result") or []
        except Exception:
            logger.warning("BHL %s failed", op, exc_info=True)
            return []

    async def search(self, query: str, limit: int = 20) -> List[BookMetadata]:
        if not query:
            return await self.list_popular(limit)
        rows = await self._get(
            "GetSearchResults", searchtable="Book",
            searchterm=query, numitems=min(limit, 100),
        )
        books: List[BookMetadata] = []
        for row in rows:
            source_id = (
                row.get("TitleId") or row.get("TitleID")
                or row.get("GoToTitleMetadataIdentifier")
            )
            title = row.get("FullTitle") or row.get("ShortTitle") or row.get("TitleUrl")
            if source_id and title:
                books.append(self._parse(str(source_id), title))
            if len(books) >= limit:
                break
        return books

    async def list_popular(self, limit: int = 50, start_page: int = 1) -> List[BookMetadata]:
        rows = await self._get("GetTopLevelTitles", limit=min(limit, 100), page=start_page)
        books: List[BookMetadata] = []
        for row in rows:
            source_id = row.get("TitleMetadataId") or row.get("TitleMetadataID")
            title = row.get("FullTitle") or row.get("ShortTitle") or row.get("TitleTitle")
            if source_id and title:
                books.append(self._parse(str(source_id), title))
        return books[:limit]

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        rows = await self._get("GetTitleMetadata", titleid=source_id, items="title")
        if not rows:
            return None
        title = rows[0].get("FullTitle") or rows[0].get("ShortTitle") or "BHL title"
        return self._parse(source_id, title)

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        """Return OCR text for the first item of a title, when a key is set."""
        if not metadata.source_id or not self.api_key:
            return None
        rows = await self._get("GetTitleMetadata", titleid=metadata.source_id, items="full")
        if not rows:
            return None
        items = rows[0].get("Items") or []
        if not items:
            return None
        item_id = items[0].get("ItemID") or items[0].get("ItemId")
        if not item_id:
            return None
        await asyncio.sleep(self.rate_limit)
        try:
            response = await self.client.get(
                BASE, params=self._params(op="GetItemText", itemid=item_id)
            )
            response.raise_for_status()
            data = response.json().get("ItemText")
            text = data.get("Text") if isinstance(data, dict) else None
            if text:
                return text.encode("utf-8")
        except Exception:
            logger.debug("BHL text fetch failed for %s", metadata.source_id, exc_info=True)
        return None

    def _parse(self, source_id: str, title: str) -> BookMetadata:
        return BookMetadata(
            title=title[:500],
            source=self.name,
            source_id=source_id,
            source_url=f"https://www.biodiversitylibrary.org/bibliography/{source_id}",
            license_type=self.license_type,
            license_url=self.LICENSE_URL,
            category=self.CATEGORY,
            tags=[self.CATEGORY],
            language="en",
        )