"""Project Gutenberg adapter.

Uses Gutendex (https://gutendex.com), the maintained JSON API over the
Gutenberg catalogue. The legacy `/ebooks/search.opds` endpoint now returns
403 to automated clients, which previously made this source return zero
books.

Everything on Gutenberg is public domain in the US.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)

LICENSE_URL = "https://www.gutenberg.org/policy/license.html"


class GutenbergSource(BaseSource):
    """Project Gutenberg — ~79,000 public domain ebooks."""

    name = "gutenberg"
    description = "Project Gutenberg — public domain ebooks"
    license_type = "public_domain"
    rate_limit = 0.3

    API_URL = "https://gutendex.com/books"
    PAGE_SIZE = 32  # Gutendex fixed page size

    #: Gutendex redirects books→books/ but the 301 costs ~1 RTT. Hit the
    #: canonical (trailing-slash) path directly to skip the redirect entirely.
    LIST_URL = "https://gutendex.com/books/"

    async def search(self, query: str, limit: int = 20, start_page: int = 1) -> List[BookMetadata]:
        return await self._collect({"search": query} if query else {}, limit, start_page)

    async def list_popular(self, limit: int = 50, start_page: int = 1) -> List[BookMetadata]:
        # Gutendex sorts by download count by default.
        return await self._collect({"sort": "popular", "languages": "en"}, limit, start_page)

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        try:
            response = await self.client.get(f"{self.API_URL}/{source_id}")
            if response.status_code != 200:
                return None
            return self._parse(response.json())
        except Exception:
            logger.warning("Gutenberg metadata fetch failed for %s", source_id, exc_info=True)
            return None

    async def harvest_catalogue(
        self,
        limit: Optional[int] = None,
        languages: str = "",
        batch_size: int = 8,
        max_concurrency: int = 8,
    ) -> List[BookMetadata]:
        """Fetch the full public-domain catalogue (Gutendex).

        Gutendex pages at a fixed 32 books/page. To scale to the full
        catalogue we discover the page count from the first request, then
        fetch pages concurrently through a semaphore-bounded gather so
        at most ``max_concurrency`` requests are in flight at once.

        Args:
            limit: Cap on total books returned; ``None`` for the whole
                catalogue.
            languages: ISO-639-2 language code(s) forwarded to Gutendex.
                Empty (default) means ALL languages. Pass ``"en"`` for the
                English-only subset.
            batch_size: Number of pages per wave (may be reduced by the
                semaphore if the wave is larger than max_concurrency).
            max_concurrency: Parallel page fetches allowed at once.
        """
        sem = asyncio.Semaphore(max_concurrency)
        query: dict = {"copyright": "false"}
        if languages:
            query["languages"] = languages

        async def _fetch(page_num: int) -> dict:
            async with sem:
                result = await self._get_page(query, page_num)
                await asyncio.sleep(self.rate_limit)
                return result

        first = await _fetch(1)
        total = (first.get("count") or 0)
        page_size = 32
        total_pages = -(-total // page_size)  # ceil

        pages_to_fetch = total_pages
        if limit is not None:
            pages_to_fetch = min(total_pages, -(-limit // page_size))

        logger.info(
            "Gutenberg full harvest: ~%d books across %d pages (conc=%d)",
            total, total_pages, max_concurrency,
        )

        books: List[BookMetadata] = []
        page = 1

        while page <= pages_to_fetch:
            wave = list(range(page, min(page + batch_size, pages_to_fetch) + 1))
            results = await asyncio.gather(
                *(_fetch(p) for p in wave),
                return_exceptions=True,
            )

            for payload in results:
                if isinstance(payload, BaseException):
                    logger.warning("Gutenberg page skipped: %s", payload)
                    continue
                for raw in payload.get("results", []):
                    book = self._parse(raw)
                    if book:
                        books.append(book)
                        if limit is not None and len(books) >= limit:
                            return books[:limit]

            page += len(wave)

        return books[:limit]

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        """Fetch the best available file, preferring EPUB then PDF then text."""
        candidates = [metadata.epub_url, metadata.pdf_url]
        candidates += [metadata.source_metadata.get("text_url")]

        for url in [u for u in candidates if u]:
            try:
                await asyncio.sleep(self.rate_limit)
                response = await self.client.get(url, follow_redirects=True)
                if response.status_code == 200 and response.content:
                    return response.content
            except Exception:
                logger.debug("Gutenberg download failed: %s", url, exc_info=True)
        return None

    async def _get_page(self, query: Dict[str, Any], page: int) -> dict:
        """Fetch a single results page, retrying on transient failures.

        Gutenberg rate-limits / occasionally drops connections under load, so a
        single failed request must not abort the whole import. We retry with
        exponential backoff and re-raise only after the budget is exhausted.
        """
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                response = await self.client.get(
                    self.LIST_URL, params={**query, "page": page}, follow_redirects=True
                )
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # noqa: BLE001 - retry regardless of cause
                last_exc = exc
                await asyncio.sleep(min(2 ** attempt, 16))
        logger.warning("Gutenberg page %s failed after retries", page)
        raise last_exc if last_exc else RuntimeError("unknown fetch error")

    async def _collect(
        self, params: Dict[str, Any], limit: int, start_page: int = 1
    ) -> List[BookMetadata]:
        """Page through the API until `limit` books are gathered.

        Starts at `start_page` so large imports can be resumed in batches
        without re-fetching earlier pages. A page that keeps failing is skipped
        rather than aborting the run, so a brief outage can't truncate the
        catalogue.
        """
        books: List[BookMetadata] = []
        query: Dict[str, Any] = {**params, "copyright": "false"}
        page = max(1, start_page)
        failures = 0

        while len(books) < limit:
            try:
                payload = await self._get_page(query, page)
            except Exception:
                failures += 1
                if failures >= 10:
                    logger.warning(
                        "Too many consecutive Gutenberg failures; stopping at page %s", page
                    )
                    break
                page += 1
                await asyncio.sleep(self.rate_limit * 2)
                continue

            failures = 0
            results = payload.get("results", [])
            for raw in results:
                book = self._parse(raw)
                if book:
                    books.append(book)
                    if len(books) >= limit:
                        break

            if not results or not payload.get("next"):
                break  # reached the end of the catalogue
            page += 1
            await asyncio.sleep(self.rate_limit)

        return books[:limit]

    @staticmethod
    def _categorise(bookshelves, subjects):
        """Best-effort genre from Gutenberg bookshelves / subjects."""
        hay = " ".join(bookshelves or []) + " " + " ".join(subjects or [])
        hay = hay.lower()
        rules = [
            ("mystery", "Mystery & Detective"),
            ("detective", "Mystery & Detective"),
            ("horror", "Gothic & Horror"),
            ("gothic", "Gothic & Horror"),
            ("ghost", "Gothic & Horror"),
            ("science fiction", "Science Fiction"),
            ("fantasy", "Fantasy"),
            ("fairy", "Children & Fairy Tales"),
            ("children", "Children & Fairy Tales"),
            ("adventure", "Adventure"),
            ("western", "Adventure"),
            ("romance", "Romance"),
            ("love", "Romance"),
            ("poetry", "Poetry"),
            ("drama", "Drama"),
            ("play", "Drama"),
            ("history", "History"),
            ("philosophy", "Philosophy"),
            ("religion", "Philosophy"),
            ("biography", "Biography"),
            ("cooking", "Non-Fiction"),
            ("art", "Non-Fiction"),
        ]
        for needle, label in rules:
            if needle in hay:
                return label
        if bookshelves:
            shelf = bookshelves[0].split(":")[-1].strip().title() if ":" in bookshelves[0] else bookshelves[0].strip().title()
            shelf = shelf.replace("Best Books Ever Listings", "Classics")
            shelf = shelf.replace("Banned Books From Anne Haight'S List", "Classics")
            shelf = shelf.replace("Bestsellers, American, 1895-1923", "Classics")
            shelf = shelf.replace("Best Books Ever List", "Classics")
            if shelf and shelf not in ("Category", ""):
                return shelf
        return "Classics"

    def _parse(self, raw: Dict[str, Any]) -> Optional[BookMetadata]:
        book_id = raw.get("id")
        title = (raw.get("title") or "").strip()
        if not book_id or not title:
            return None

        # Gutendex exposes `copyright: true` for the rare restricted item.
        if raw.get("copyright") is True:
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

        languages = raw.get("languages") or ["en"]
        if not languages:
            return None

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
                "languages": languages,
            },
            license_type="public_domain",
            license_url=LICENSE_URL,
            epub_url=pick("application/epub"),
            pdf_url=pick("application/pdf"),
            cover_url=pick("image/jpeg"),
            category=self._categorise(raw.get("bookshelves"), raw.get("subjects")),
            tags=[s for s in (raw.get("subjects") or [])[:5]],
            language=languages[0] if languages else "en",
            publication_year=year,
        )
