"""Standard Ebooks adapter.

Standard Ebooks now returns 401 on its OPDS feeds to unauthenticated
clients, which made this source return zero books. We read the public
sitemap + HTML catalogue instead, which requires no credentials.

All Standard Ebooks titles are public domain, professionally typeset.
"""
import asyncio
import logging
import re
from typing import List, Optional

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)

BASE = "https://standardebooks.org"


class StandardEbooksSource(BaseSource):
    """Standard Ebooks — ~1,000 professionally formatted public domain ebooks."""

    name = "standard_ebooks"
    description = "Standard Ebooks — enhanced public domain ebooks"
    license_type = "public_domain"
    rate_limit = 0.5

    # Advertised in https://standardebooks.org/robots.txt (no file extension).
    SITEMAP_URL = f"{BASE}/sitemap"
    EBOOKS_URL = f"{BASE}/ebooks"

    async def search(self, query: str, limit: int = 20) -> List[BookMetadata]:
        books = await self._catalogue(limit=max(limit * 6, 120))
        if not query:
            return books[:limit]
        q = query.lower()
        return [b for b in books if q in b.title.lower() or q in (b.author or "").lower()][:limit]

    async def list_popular(self, limit: int = 50) -> List[BookMetadata]:
        return await self._catalogue(limit)

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        for book in await self._catalogue(limit=2000):
            if book.source_id == source_id:
                return book
        return None

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        for url in (metadata.epub_url, metadata.pdf_url):
            if not url:
                continue
            try:
                await asyncio.sleep(self.rate_limit)
                response = await self.client.get(url, follow_redirects=True)
                if response.status_code == 200 and response.content:
                    return response.content
            except Exception:
                logger.debug("Standard Ebooks download failed: %s", url, exc_info=True)
        return None

    async def _catalogue(self, limit: int) -> List[BookMetadata]:
        """Build the catalogue from the public sitemap (no auth required)."""
        slugs = await self._slugs(limit)
        return [self._from_slug(s) for s in slugs][:limit]

    async def _slugs(self, limit: int) -> List[str]:
        try:
            response = await self.client.get(self.SITEMAP_URL, follow_redirects=True)
            response.raise_for_status()
            text = response.text
        except Exception:
            logger.warning("Standard Ebooks sitemap fetch failed", exc_info=True)
            return []

        # Nested sitemap index -> fetch the ebook sitemap(s).
        if "<sitemapindex" in text:
            children = re.findall(r"<loc>\s*([^<]*ebook[^<]*)\s*</loc>", text)
            collected: List[str] = []
            for child in children:
                try:
                    await asyncio.sleep(self.rate_limit)
                    sub = await self.client.get(child, follow_redirects=True)
                    sub.raise_for_status()
                    collected += self._extract_slugs(sub.text)
                except Exception:
                    logger.debug("sitemap child failed: %s", child, exc_info=True)
                if len(collected) >= limit:
                    break
            return collected[:limit]

        return self._extract_slugs(text)[:limit]

    @staticmethod
    def _extract_slugs(xml: str) -> List[str]:
        """Pull 'author/title' slugs out of /ebooks/ URLs, preserving order."""
        found = re.findall(r"<loc>\s*https://standardebooks\.org/ebooks/([^<\s]+?)\s*</loc>", xml)
        slugs, seen = [], set()
        for slug in found:
            slug = slug.rstrip("/")
            # Real books are "author/title"; deeper paths are assets/sections.
            if slug.count("/") != 1 or slug in seen:
                continue
            seen.add(slug)
            slugs.append(slug)
        return slugs

    def _from_slug(self, slug: str) -> BookMetadata:
        author_slug, _, title_slug = slug.partition("/")

        def humanise(value: str) -> str:
            return re.sub(r"\s+", " ", value.replace("-", " ")).strip().title()

        flat = slug.replace("/", "_")
        return BookMetadata(
            title=humanise(title_slug)[:500],
            author=humanise(author_slug),
            source=self.name,
            source_id=slug,
            source_url=f"{self.EBOOKS_URL}/{slug}",
            license_type="public_domain",
            license_url=f"{BASE}/manual/the-standard-ebooks-manual-of-style",
            epub_url=f"{self.EBOOKS_URL}/{slug}/downloads/{flat}.epub",
            cover_url=f"{self.EBOOKS_URL}/{slug}/downloads/cover.jpg",
        )
