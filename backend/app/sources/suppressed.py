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

Beyond the hand-curated canon, :meth:`harvest_banned` expands the shelf to
every public-domain English work Gutendex surfaces for a large list of
banned, censored or condemned authors (BANNED_AUTHORS), so the shelf
reflects the full universe of public-domain "banned books" rather than a
fixed list.
"""
import asyncio
import logging
from typing import Dict, List, Optional

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)

SUPPRESSED_CLASSICS_TAG = "Suppressed Classics"
REVOLUTIONARY_TAG = "Revolutionary"
SUPPRESSED_SOURCE_NAME = "suppressed"

#: Curated public-domain suppressed / banned literary classics.
#: Gutenberg IDs verified against the PG catalogue (wrong IDs would otherwise
#: ingest a *different* book under the canon's title). Entries for texts not
#: public-domain (or not on Gutenberg) simply fail to resolve and are
#: silently omitted.
SUPPRESSED_CANON: List[Dict] = [
    # ── Classical world — sex & satire banned by antiquity ───────────
    {"gutenberg_id": 27827, "title": "The Kama Sutra of Vatsyayana", "author": "Vatsyayana"},
    {"gutenberg_id": 3726, "title": "The Decameron (Vol. I)", "author": "Giovanni Boccaccio"},
    {"gutenberg_id": 5225, "title": "The Satyricon — Complete", "author": "Petronius Arbiter"},
    {"gutenberg_id": 3435, "title": "The Book of the Thousand Nights and a Night (Vol. 1)", "author": "Richard F. Burton"},
    {"gutenberg_id": 3437, "title": "The Book of the Thousand Nights and a Night (Vol. 3)", "author": "Richard F. Burton"},
    {"gutenberg_id": 21765, "title": "The Metamorphoses of Ovid, Books I–VII", "author": "Ovid"},
    {"gutenberg_id": 1200, "title": "Gargantua and Pantagruel", "author": "François Rabelais"},
    # ── The turn-of-the-century sexual classics ──────────────────────
    {"gutenberg_id": 25305, "title": "Fanny Hill: Memoirs of a Woman of Pleasure", "author": "John Cleland"},
    # ── Banned moderns (public-domain translations) ──────────────────
    {"gutenberg_id": 4300, "title": "Ulysses", "author": "James Joyce"},
    {"gutenberg_id": 2814, "title": "Dubliners", "author": "James Joyce"},
    {"gutenberg_id": 73144, "title": "Lady Chatterley's Lover", "author": "D. H. Lawrence"},
    {"gutenberg_id": 28948, "title": "The Rainbow", "author": "D. H. Lawrence"},
    {"gutenberg_id": 217, "title": "Sons and Lovers", "author": "D. H. Lawrence"},
    {"gutenberg_id": 4240, "title": "Women in Love", "author": "D. H. Lawrence"},
    {"gutenberg_id": 2413, "title": "Madame Bovary", "author": "Gustave Flaubert"},
    {"gutenberg_id": 5250, "title": "Nana", "author": "Émile Zola"},
    {"gutenberg_id": 56528, "title": "Germinal", "author": "Émile Zola"},
    # ── Philosophy / satire suppressed for politics & religion ───────
    {"gutenberg_id": 46333, "title": "The Social Contract", "author": "Jean-Jacques Rousseau"},
    {"gutenberg_id": 5427, "title": "Émile", "author": "Jean-Jacques Rousseau"},
    {"gutenberg_id": 3913, "title": "The Confessions of Jean-Jacques Rousseau", "author": "Jean-Jacques Rousseau"},
    {"gutenberg_id": 19942, "title": "Candide", "author": "Voltaire"},
    # ── Banned literature & classics suppressed in their own countries ──
    {"gutenberg_id": 174, "title": "The Picture of Dorian Gray", "author": "Oscar Wilde"},
    {"gutenberg_id": 76, "title": "The Adventures of Huckleberry Finn", "author": "Mark Twain"},
    {"gutenberg_id": 140, "title": "The Jungle", "author": "Upton Sinclair"},
    {"gutenberg_id": 5267, "title": "Sister Carrie", "author": "Theodore Dreiser"},
    {"gutenberg_id": 31824, "title": "The \"Genius\"", "author": "Theodore Dreiser"},
    {"gutenberg_id": 8771, "title": "Jurgen: A Comedy of Justice", "author": "James Branch Cabell"},
    {"gutenberg_id": 1228, "title": "On the Origin of Species", "author": "Charles Darwin"},
    {"gutenberg_id": 203, "title": "Uncle Tom's Cabin", "author": "Harriet Beecher Stowe"},
    {"gutenberg_id": 370, "title": "Moll Flanders", "author": "Daniel Defoe"},
    {"gutenberg_id": 601, "title": "The Monk: A Romance", "author": "M. G. Lewis"},
    {"gutenberg_id": 2162, "title": "Anarchism and Other Essays", "author": "Emma Goldman"},
    {"gutenberg_id": 408, "title": "The Souls of Black Folk", "author": "W. E. B. Du Bois"},
    {"gutenberg_id": 8660, "title": "Woman and the New Race", "author": "Margaret Sanger"},
    {"gutenberg_id": 689, "title": "The Kreutzer Sonata and Other Stories", "author": "Leo Tolstoy"},
    {"gutenberg_id": 61, "title": "Manifesto of the Communist Party", "author": "Karl Marx"},
    {"gutenberg_id": 23428, "title": "The Conquest of Bread", "author": "Peter Kropotkin"},
    {"gutenberg_id": 4341, "title": "Mutual Aid: A Factor of Evolution", "author": "Peter Kropotkin"},
    {"gutenberg_id": 147, "title": "Common Sense", "author": "Thomas Paine"},
    {"gutenberg_id": 2981, "title": "The Memoirs of Jacques Casanova de Seingalt", "author": "Giacomo Casanova"},
]

#: Authors whose works have been banned, burned, censored or condemned by a
#: government, church or other authority. Public-domain authors only (anyone
#: still in copyright simply fails to resolve and is skipped). Used by
#: :meth:`harvest_banned` to expand the shelf well beyond the canon, plus an
#: author-priority sweep mirroring the African Literature harvest.
BANNED_AUTHORS: List[str] = [
    # Classical & Renaissance writers suppressed for sex, satire or religion
    "Vatsyayana",
    "Ovid",
    "Petronius Arbiter",
    "Sappho",
    "Giovanni Boccaccio",
    "François Rabelais",
    "Pietro Aretino",
    "Kalyana Malla",
    "Cheikh Nefzaoui",
    "John Cleland",
    "Giacomo Casanova",
    "Marquis de Sade",
    "Donatien Alphonse François de Sade",
    # Enlightenment & philosophies condemned by church and crown
    "Voltaire",
    "Jean-Jacques Rousseau",
    "Denis Diderot",
    "Thomas Paine",
    "Baron d'Holbach",
    "François-Marie Arouet",
    # 19th-century novelists tried and convicted for obscenity or blasphemy
    "Gustave Flaubert",
    "Émile Zola",
    "Charles Baudelaire",
    "Anatole France",
    "Guy de Maupassant",
    "M. G. Lewis",
    "Matthew Gregory Lewis",
    "Jeremy Bentham",
    # Victorian & early-modern banned classics
    "Oscar Wilde",
    "Mark Twain",
    "Upton Sinclair",
    "Theodore Dreiser",
    "James Branch Cabell",
    "D. H. Lawrence",
    "James Joyce",
    "Walt Whitman",
    "Radclyffe Hall",
    "Margaret Sanger",
    "Havelock Ellis",
    "Marie Stopes",
    "W. E. B. Du Bois",
    "Langston Hughes",
    "Richard Wright",
    "Sutton E. Griggs",
    # Anarchist, socialist & labour classics burned by states
    "Karl Marx",
    "Friedrich Engels",
    "Peter Kropotkin",
    "Pyotr Kropotkin",
    "Mikhail Bakunin",
    "Emma Goldman",
    "Alexander Berkman",
    "Maxim Gorky",
    "Upton Sinclair",
    "Jack London",
    "Leo Tolstoy",
    "Nikolai Chernyshevsky",
    "Clara Zetkin",
    # Colonial censors & anti-imperial classics
    "James Stephen",
    "J. A. Hobson",
    "Scott Nearing",
    "Victor Serge",
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

    async def harvest_banned(
        self,
        limit: Optional[int] = None,
        max_concurrency: int = 6,
        batch_size: int = 6,
    ) -> List[BookMetadata]:
        """Harvest the full public-domain banned / suppressed shelf.

        Author-priority: for every name in BANNED_AUTHORS (plus the condemned
        revolutionary authors already curated on the Revolutionary shelf) we
        search Gutenberg and take every public-domain English work it
        surfaces, tagging it ``Suppressed Classics`` (and ``Revolutionary``
        where the author is a condemned revolutionary). Deduped by Gutenberg
        id so a work surfaced through multiple authors is ingested once.

        The result is the honest ceiling of the shelf: every public-domain
        "banned book" the corpus actually contains.
        """
        import asyncio as _aio

        from .african_ebooks import CONDEMNED_REVOLUTIONARY_AUTHORS, AfricanEbooksSource

        authors: List[str] = []
        for name in list(BANNED_AUTHORS) + list(CONDEMNED_REVOLUTIONARY_AUTHORS):
            if name not in authors:
                authors.append(name)

        sem = _aio.Semaphore(max_concurrency)
        seen: set[int] = set()
        books: List[BookMetadata] = []

        async def _fetch_page(query: str, page_num: int) -> dict:
            async with sem:
                try:
                    await _aio.sleep(self.rate_limit)
                    resp = await self.client.get(
                        self.GUTENBERG_API,
                        params={
                            "search": query,
                            "languages": "en",
                            "copyright": "false",
                            "page": page_num,
                        },
                    )
                    resp.raise_for_status()
                    return resp.json()
                except Exception:
                    logger.warning("Banned harvest search query failed: %s (page %s)", query, page_num)
                    return {}

        for query in authors:
            page_num = 1
            pages_to_fetch = 1
            while page_num <= pages_to_fetch:
                wave_pages = list(range(page_num, min(page_num + batch_size, pages_to_fetch) + 1))
                payloads = await _aio.gather(
                    *(_fetch_page(query, p) for p in wave_pages),
                    return_exceptions=True,
                )
                for payload in payloads:
                    if isinstance(payload, BaseException) or not payload:
                        continue
                    total = payload.get("count") or 0
                    pages_to_fetch = -(-total // 32)  # Gutendex fixed page size
                    for raw in payload.get("results", []):
                        bid = raw.get("id")
                        if bid is None or bid in seen:
                            continue
                        meta = self._from_gutenberg(raw)
                        if not meta:
                            continue
                        # Author-priority: only take the work when one of its
                        # credited authors is on the banned/condemned canon.
                        if not self._is_banned_author(meta.author):
                            continue
                        seen.add(bid)
                        self._tag(meta)
                        books.append(meta)
                        if limit is not None and len(books) >= limit:
                            return books[:limit]
                page_num += len(wave_pages)

        return books[:limit]

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        return None

    # --- internals ---------------------------------------------------------

    @staticmethod
    def _is_banned_author(author: Optional[str]) -> bool:
        """True when a credited author matches the banned/condemned canon.

        Reuses the strict name matcher from the African shelf (initials and
        lone short names can never false-positive onto full names) so the
        author-priority harvest only surfaces genuinely banned writers.
        """
        from .african_ebooks import (
            AfricanEbooksSource,
            CONDEMNED_REVOLUTIONARY_AUTHORS,
        )

        if not author:
            return False
        for candidate in list(BANNED_AUTHORS) + list(CONDEMNED_REVOLUTIONARY_AUTHORS):
            if (AfricanEbooksSource._name_matches(author, candidate)
                    or AfricanEbooksSource._name_matches(candidate, author)):
                return True
        return False

    def _tag(self, meta: BookMetadata) -> None:
        tags = list(dict.fromkeys((meta.tags or []) + [SUPPRESSED_CLASSICS_TAG]))
        # Authors condemned by their own governments also carry the
        # Revolutionary tag so both shelves surface them.
        from .african_ebooks import AfricanEbooksSource
        if AfricanEbooksSource._is_revolutionary_author(meta.author):
            if REVOLUTIONARY_TAG not in tags:
                tags.append(REVOLUTIONARY_TAG)
        meta.tags = tags

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
        formats: Dict[str, str] = raw.get("formats", {}) or {}
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
                "text_url": pick(formats, "text/plain"),
            },
            license_type="public_domain",
            license_url="https://www.gutenberg.org/policy/license.html",
            epub_url=pick(formats, "application/epub"),
            pdf_url=pick(formats, "application/pdf"),
            cover_url=pick(formats, "image/jpeg"),
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