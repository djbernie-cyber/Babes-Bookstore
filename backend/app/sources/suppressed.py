"""A curated Suppressed Classics shelf.

Public-domain literary and historical works that have been banned, burned,
or censored — famous precisely for the fact that authority tried to erase
them. This shelf treats them as the art and documents they are, the way a
public library does: Ovid, Boccaccio, Petronius, the Kama Sutra, the
Arabian Nights, Sappho, Rabelais, and the other canonical "banned books."
All items resolve against Project Gutenberg's public-domain catalogue and
are tagged ``Suppressed Classics``.

Note: this shelf explicitly does NOT carry instructions for producing
weapons or explosives. Censored *literature and ideas* are the shelf's
subject; manufacturing manuals are something else entirely.
"""
import asyncio
import logging
from typing import Dict, List, Optional

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)

SUPPRESSED_CLASSICS_TAG = "Suppressed Classics"
SUPPRESSED_SOURCE_NAME = "suppressed"

#: Curated public-domain suppressed / banned literary classics.
#: Entries for texts still in copyright (or not on Gutenberg) simply
#: fail to resolve and are silently omitted.
SUPPRESSED_CANON: List[Dict] = [
    # Classical world — sex & satire banned by antiquity
    {"gutenberg_id": 3315, "title": "The Kama Sutra of Vatsyayana", "author": "Vatsyayana"},
    {"gutenberg_id": 7899, "title": "The Kama Sutra", "author": "Vatsyayana"},
    {"gutenberg_id": 23639, "title": "Kama Sutra (veadur)", "author": "Vatsyayana"},
    {"gutenberg_id": 3726, "title": "The Decameron", "author": "Giovanni Boccaccio"},
    {"gutenberg_id": 5218, "title": "The Decameron", "author": "Giovanni Boccaccio"},
    {"gutenberg_id": 5225, "title": "The Satyricon", "author": "Petronius Arbiter"},
    {"gutenberg_id": 8583, "title": "The Satyricon", "author": "Petronius Arbiter"},
    {"gutenberg_id": 3435, "title": "The Book of the Thousand Nights and a Night (Vol. 1)", "author": "Richard F. Burton"},
    {"gutenberg_id": 3437, "title": "The Book of the Thousand Nights and a Night (Vol. 3)", "author": "Richard F. Burton"},
    {"gutenberg_id": 57343, "title": "Sappho: One Hundred Lyrics", "author": "Sappho"},
    {"gutenberg_id": 20922, "title": "The Poems of Sappho", "author": "Sappho"},
    {"gutenberg_id": 1200, "title": "Gargantua and Pantagruel", "author": "François Rabelais"},
    {"gutenberg_id": 23337, "title": "Gargantua and Pantagruel (Wellcome)", "author": "François Rabelais"},
    # The turn-of-the-century sexual classics
    {"gutenberg_id": 25305, "title": "Fanny Hill: Memoirs of a Woman of Pleasure", "author": "John Cleland"},
    {"gutenberg_id": 25306, "title": "Fanny Hill (Part II)", "author": "John Cleland"},
    {"gutenberg_id": 10555, "title": "The Perfumed Garden of the Cheikh Nefzaoui", "author": "Cheikh Nefzaoui"},
    {"gutenberg_id": 2480, "title": "Ananga Ranga", "author": "Kalyana Malla"},
    {"gutenberg_id": 10989, "title": "The Book of Pleasure: Love Letters", "author": "Various"},
    # Aretino & the Renaissance satirists
    {"gutenberg_id": 1332, "title": "Ragionamenti", "author": "Pietro Aretino"},
    {"gutenberg_id": 27339, "title": "The Works of Aretino", "author": "Pietro Aretino"},
    # Banned moderns (public-domain translations)
    {"gutenberg_id": 17462, "title": "Justine Part (Sade, public domain English ed.)", "author": "Marquis de Sade"},
    {"gutenberg_id": 1231, "title": "The Complete Memoirs of Jacques Casanova de Seingalt", "author": "Giacomo Casanova"},
    {"gutenberg_id": 63908, "title": "The Memoirs of Jacques Casanova de Seingalt (Seingalt-Ed.)", "author": "Giacomo Casanova"},
    # Philosophy / satire suppressed for politics & religion
    {"gutenberg_id": 19942, "title": "The Social Contract", "author": "Jean-Jacques Rousseau"},
    {"gutenberg_id": 5427, "title": "Émile", "author": "Jean-Jacques Rousseau"},
    {"gutenberg_id": 71632, "title": "On War", "author": "Carl von Clausewitz"},
]


class SuppressedClassicsSource(BaseSource):
    """A curated public-domain Suppressed Classics shelf."""

    name = SUPPRESSED_SOURCE_NAME
    description = "Suppressed Classics — banned, burned and censored literary & historical canon"
    license_type = "public_domain"
    rate_limit = 0.3

    GUTENBERG_API = "https://gutendex.com/books"

    async def list_popular(self, limit: int = 50, start_page: int = 1) -> List[BookMetadata]:
        books: List[BookMetadata] = []
        for entry in SUPPRESSED_CANON:
            if limit and len(books) >= limit:
                break
            meta = await self._resolve(entry)
            if meta:
                books.append(meta)
        return books

    async def search(self, query: str, limit: int = 20, start_page: int = 1) -> List[BookMetadata]:
        q = (query or "").strip()
        target = q or "banned classics"
        try:
            await asyncio.sleep(self.rate_limit)
            response = await self.client.get(
                self.GUTENBERG_API,
                params={"search": target, "languages": "en", "copyright": "false"},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            logger.warning("Suppressed search failed: %s", target, exc_info=True)
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
        books: List[BookMetadata] = []
        for entry in SUPPRESSED_CANON:
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
        if SUPPRESSED_CLASSICS_TAG not in (meta.tags or []):
            meta.tags = list(dict.fromkeys((meta.tags or []) + [SUPPRESSED_CLASSICS_TAG]))

    async def _resolve(self, entry: Dict) -> Optional[BookMetadata]:
        meta = await self._resolve_remote(str(entry["gutenberg_id"]))
        if meta is None:
            return None
        meta.title = entry["title"]
        if entry.get("author"):
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
            category="Classics",
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