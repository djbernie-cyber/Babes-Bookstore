"""African Literature adapter.

A dedicated, curated catalogue of African-authored and African-diaspora
literary works. Each entry is a canonical Project Gutenberg book (public
domain, English, licence-verified and downloadable), resolved through the
Gutenberg API so metadata, covers and EPUB/PDF files stay live.

The canon spans the continent and its diaspora: Olive Schreiner and Sol T.
Plaatje (South Africa), Olaudah Equiano (Igboland, Nigeria), Charles W.
Chesnutt and W.E.B. Du Bois (the United States diaspora), and more. Works
are tagged with `African Literature` so they can be browsed as a genre even
though they span many subject categories.
"""
import asyncio
import logging
from typing import List, Optional, Dict

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)

#: Curated canon: { gutenberg_id, title, author }. Resolved live via the
#: Gutenberg metadata endpoint which is public-domain, English and
#: downloadable — so these auto-approve and count toward the visible count.
AFRICAN_CANON: List[Dict] = [
    {"gutenberg_id": 1441, "title": "The Story of an African Farm", "author": "Olive Schreiner"},
    {"gutenberg_id": 1439, "title": "Dreams", "author": "Olive Schreiner"},
    {"gutenberg_id": 1440, "title": "Woman and Labour", "author": "Olive Schreiner"},
    {"gutenberg_id": 1458, "title": "Dream Life and Real Life: A Little African Story", "author": "Olive Schreiner"},
    {"gutenberg_id": 64520, "title": "Thoughts on South Africa", "author": "Olive Schreiner"},
    {"gutenberg_id": 1452, "title": "Native Life in South Africa: Before and Since the War", "author": "Sol T. Plaatje"},
    {"gutenberg_id": 15399, "title": "The Interesting Narrative of the Life of Olaudah Equiano", "author": "Olaudah Equiano"},
    {"gutenberg_id": 472, "title": "The House Behind the Cedars", "author": "Charles W. Chesnutt"},
    {"gutenberg_id": 11666, "title": "The Conjure Woman", "author": "Charles W. Chesnutt"},
    {"gutenberg_id": 11057, "title": "The Wife of his Youth and Other Stories", "author": "Charles W. Chesnutt"},
]

#: Public-domain African-diaspora authors / subjects we add on top of the
#: hand-curated canon during ingestion; matched against Gutenberg search.
AFRICAN_AUTHORS: List[str] = [
    "Olive Schreiner",
    "Solomon T. Plaatje",
    "Olaudah Equiano",
    "Charles W. Chesnutt",
    "W.E.B. Du Bois",
    "Booker T. Washington",
    "Pauline Hopkins",
    "Frederick Douglass",
]

AFRICAN_THEMES: List[str] = [
    "Africa",
    "South Africa",
    "Nigeria",
    "Egypt",
    "Ethiopia",
    "Kenya",
    "Ghana",
    "Senegal",
]

AFRICAN_LITERATURE_TAG = "African Literature"


class AfricanEbooksSource(BaseSource):
    """A curated, dedicated African-literature catalogue."""

    name = "african_ebooks"
    description = "African Literature — curated public-domain African & diaspora classics"
    license_type = "public_domain"
    rate_limit = 0.3

    GUTENBERG_API = "https://gutendex.com/books"

    async def list_popular(self, limit: int = 50, start_page: int = 1) -> List[BookMetadata]:
        """Resolve the curated canon into live BookMetadata."""
        books: List[BookMetadata] = []
        for entry in AFRICAN_CANON:
            meta = await self._resolve(entry)
            if meta:
                books.append(meta)
        return books

    async def search(self, query: str, limit: int = 20, start_page: int = 1) -> List[BookMetadata]:
        """Search the Gutenberg catalogue for African-authored titles."""
        q = (query or "").strip()
        target = q or "South Africa"
        try:
            await asyncio.sleep(self.rate_limit)
            response = await self.client.get(
                self.GUTENBERG_API, params={"search": target, "languages": "en"}
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            logger.warning("African search failed: %s", target, exc_info=True)
            return []
        out: List[BookMetadata] = []
        for raw in payload.get("results", []):
            meta = self._from_gutenberg(raw)
            if meta and (rand := self._is_african(meta)):
                meta.tags = list(dict.fromkeys((meta.tags or []) + [AFRICAN_LITERATURE_TAG]))
                out.append(meta)
            if len(out) >= limit:
                break
        return out

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        return await self._resolve_remote(source_id)

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        # Files are resolved and streamed from Gutenberg; individual book
        # downloads and bundle packaging use their own resolvers.
        return None

    async def _resolve(self, entry: Dict) -> Optional[BookMetadata]:
        meta = await self._resolve_remote(str(entry["gutenberg_id"]))
        if meta is None:
            return None
        meta.title = entry["title"]
        if entry.get("author"):
            meta.author = entry["author"]
        meta.source = self.name
        meta.source_id = str(entry["gutenberg_id"])
        src = f"https://www.gutenberg.org/ebooks/{entry['gutenberg_id']}"
        meta.source_url = src
        meta.tags = list(dict.fromkeys((meta.tags or []) + [AFRICAN_LITERATURE_TAG]))
        return meta

    async def _resolve_remote(self, gutenberg_id: str) -> Optional[BookMetadata]:
        try:
            await asyncio.sleep(self.rate_limit)
            response = await self.client.get(f"{self.GUTENBERG_API}/{gutenberg_id}")
            if response.status_code != 200:
                return None
            return self._from_gutenberg(response.json())
        except Exception:
            logger.warning("Gutenberg resolve failed for %s", gutenberg_id, exc_info=True)
            return None

    def _from_gutenberg(self, raw: Dict) -> Optional[BookMetadata]:
        book_id = raw.get("id")
        title = (raw.get("title") or "").strip()
        if not book_id or not title:
            return None
        if raw.get("copyright") is True:
            return None
        languages = raw.get("languages") or ["en"]
        if "en" not in languages:
            return None

        authors = [a.get("name") for a in raw.get("authors", []) if a.get("name")]
        formats: Dict[str, str] = raw.get("formats", {}) or {}

        def pick(*needles: str) -> Optional[str]:
            for mime, href in formats.items():
                if any(n in mime for n in needles) and not href.endswith(".zip"):
                    return href
            return None

        year = None
        for author in raw.get("authors", []):
            if author.get("death_year"):
                year = author["death_year"]
                break

        return BookMetadata(
            title=title[:500],
            author=", ".join(authors[:3]) or None,
            description=(raw.get("summaries") or [None])[0],
            source=self.name,
            source_id=str(book_id),
            source_url=f"https://www.gutenberg.org/ebooks/{book_id}",
            source_metadata={
                "download_count": raw.get("download_count"),
                "subjects": (raw.get("subjects") or [])[:8],
                "text_url": pick("text/plain"),
            },
            license_type="public_domain",
            license_url="https://www.gutenberg.org/policy/license.html",
            epub_url=pick("application/epub"),
            pdf_url=pick("application/pdf"),
            cover_url=pick("image/jpeg"),
            category="Classics",
            tags=list((raw.get("subjects") or [])[:5]),
            language="en",
            publication_year=year,
        )

    @staticmethod
    def _is_african(meta: BookMetadata) -> bool:
        hay = " ".join(filter(None, [meta.title, meta.author, meta.description]))
        hay_l = hay.lower()
        if any(a.lower() in hay_l for a in AFRICAN_AUTHORS):
            return True
        return any(t.lower() in hay_l for t in AFRICAN_THEMES)
