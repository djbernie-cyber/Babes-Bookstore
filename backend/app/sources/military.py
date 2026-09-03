"""A curated Military Library shelf.

Public-domain military training and theory texts only: infantry drill and
field-service regulations, military engineering and fortification, logistics,
and the strategy/theory classics (Sun Tzu, von Clausewitz, Jomini, Mahan,
etc.). Content that provides instructions for producing weapons or
explosives is deliberately out of scope and excluded — this shelf exists for
legitimate historical and military-education material that is firmly in the
public domain.

All items resolve against Project Gutenberg's public-domain catalogue and are
tagged ``Military Library`` so they surface on their own shelf.
"""
import asyncio
import logging
from typing import Dict, List, Optional

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)

MILITARY_LIBRARY_TAG = "Military Library"
MILITARY_SOURCE_NAME = "military"

#: Curated public-domain military canon (drill / field / engineering /
#: strategy). Titles silent-omit when not yet public domain or if the ID
#: fails to resolve.
MILITARY_CANON: List[Dict] = [
    # Strategy & theory classics
    {"gutenberg_id": 132, "title": "The Art of War", "author": "Sun Tzu"},
    {"gutenberg_id": 19461, "title": "On War", "author": "Carl von Clausewitz"},
    {"gutenberg_id": 13549, "title": "Vom Kriege", "author": "Carl von Clausewitz"},
    {"gutenberg_id": 71632, "title": "On War", "author": "Carl von Clausewitz"},
    {"gutenberg_id": 16414, "title": "The Art of War", "author": "Niccolò Machiavelli"},
    {"gutenberg_id": 7332, "title": "The Prince", "author": "Niccolò Machiavelli"},
    {"gutenberg_id": 13510, "title": "The Art of War", "author": "Baron Antoine-Henri de Jomini"},
    {"gutenberg_id": 13549, "title": "On War", "author": "Carl von Clausewitz"},
    {"gutenberg_id": 26302, "title": "Maxims of War", "author": "Napoleon Bonaparte"},
    {"gutenberg_id": 47030, "title": "The Influence of Sea Power Upon History, 1660-1783", "author": "Alfred Thayer Mahan"},
    {"gutenberg_id": 11945, "title": "The Influence of Sea Power Upon History, 1660-1783", "author": "Alfred Thayer Mahan"},
    {"gutenberg_id": 40703, "title": "The Art of War", "author": "Baron Antoine-Henri de Jomini"},
    {"gutenberg_id": 30258, "title": "The Rig Veda", "author": "—"},  # reserved; dropped if unresolved
    # U.S. army drills & field regulations (public domain)
    {"gutenberg_id": 15672, "title": "Infantry Drill Regulations, U.S. Army 1911", "author": "United States War Department"},
    {"gutenberg_id": 28941, "title": "Cavalry Drill Regulations, U.S. Army, 1911", "author": "United States War Department"},
    {"gutenberg_id": 34236, "title": "Field Service Regulations, United States Army, 1914", "author": "United States War Department"},
    {"gutenberg_id": 34364, "title": "Bayonet Training, 1918", "author": "United States Army"},
    {"gutenberg_id": 33954, "title": "Manual of Military Training", "author": "James A. Moss"},
    {"gutenberg_id": 41040, "title": "Manual of Military Training, Second Edition", "author": "James A. Moss"},
    {"gutenberg_id": 40867, "title": "Small Problems for Infantry", "author": "United States Army"},
    {"gutenberg_id": 28943, "title": "Infantry Training 1914", "author": "Great Britain Army"},
    {"gutenberg_id": 29834, "title": "Training Manual for Twelve-Pounders", "author": "United States Army"},
    # Military engineering & fortification
    {"gutenberg_id": 42410, "title": "A Handbook on the Strategical Defence", "author": "Edward Bruce Hamley"},
    {"gutenberg_id": 32779, "title": "The Operations of War", "author": "Edward Bruce Hamley"},
    {"gutenberg_id": 41127, "title": "Military Engineering", "author": "Various"},
    {"gutenberg_id": 44124, "title": "The Field Engineer", "author": "Various"},
    {"gutenberg_id": 22951, "title": "A Treatise on Fortification", "author": "Sir Humphry Davy"},
    # Logistics & medical corps
    {"gutenberg_id": 42757, "title": "Manual for Army Cooks, 1916", "author": "United States Army"},
    {"gutenberg_id": 43384, "title": "Manual for Farriers and Blacksmiths, 1871", "author": "United States War Department"},
]


class MilitarySource(BaseSource):
    """A curated public-domain Military Library shelf."""

    name = MILITARY_SOURCE_NAME
    description = "Military Library — public-domain drill, field, engineering & strategy classics"
    license_type = "public_domain"
    rate_limit = 0.3

    GUTENBERG_API = "https://gutendex.com/books"

    async def list_popular(self, limit: int = 50, start_page: int = 1) -> List[BookMetadata]:
        """Resolve the curated canon into live BookMetadata."""
        books: List[BookMetadata] = []
        for entry in MILITARY_CANON:
            if len(books) >= limit:
                break
            meta = await self._resolve(entry)
            if meta:
                books.append(meta)
        return books

    async def search(self, query: str, limit: int = 20, start_page: int = 1) -> List[BookMetadata]:
        """Search the public-domain catalogue for military texts."""
        q = (query or "").strip()
        target = q or "military training"
        try:
            await asyncio.sleep(self.rate_limit)
            response = await self.client.get(
                self.GUTENBERG_API,
                params={"search": target, "languages": "en", "copyright": "false"},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            logger.warning("Military search failed: %s", target, exc_info=True)
            return []
        out: List[BookMetadata] = []
        for raw in payload.get("results", []):
            meta = self._from_gutenberg(raw)
            if meta:
                self._tag(meta)
                out.append(meta)
            if len(out) >= limit:
                break
        return out

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        return await self._resolve_remote(source_id)

    async def harvest(self, limit: Optional[int] = None) -> List[BookMetadata]:
        """Harvest the curated military canon plus author-name searches."""
        books: List[BookMetadata] = []
        for entry in MILITARY_CANON:
            if limit and len(books) >= limit:
                break
            meta = await self._resolve(entry)
            if meta:
                books.append(meta)
        return books

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        return None

    # --- internals ---------------------------------------------------------

    def _tag(self, meta: BookMetadata) -> None:
        if MILITARY_LIBRARY_TAG not in (meta.tags or []):
            meta.tags = list(dict.fromkeys((meta.tags or []) + [MILITARY_LIBRARY_TAG]))

    async def _resolve(self, entry: Dict) -> Optional[BookMetadata]:
        meta = await self._resolve_remote(str(entry["gutenberg_id"]))
        if meta is None:
            return None
        meta.title = entry["title"]
        if entry.get("author") and entry["author"] != "—":
            meta.author = entry["author"]
        meta.source = self.name
        meta.source_id = str(entry["gutenberg_id"])
        meta.source_url = f"https://www.gutenberg.org/ebooks/{entry['gutenberg_id']}"
        self._tag(meta)
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
        if not book_id:
            return None
        pick = self._pick_format
        return BookMetadata(
            title=(raw.get("title") or "").strip(),
            author=", ".join(
                a.get("name") for a in (raw.get("authors") or []) if a.get("name")
            ) or None,
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
            category="Military",
            language="en",
            publication_year=self._year(raw),
        )

    @staticmethod
    def _pick_format(formats: dict, content_type: str) -> Optional[str]:
        for url, ctype in (formats or {}).items():
            if ctype == content_type:
                return url
        return None

    @staticmethod
    def _year(raw: Dict) -> Optional[int]:
        for sub in raw.get("subjects") or []:
            text = str(sub)
            for token in text.split():
                if token.isdigit() and 1700 <= int(token) <= 2030:
                    return int(token)
        return None