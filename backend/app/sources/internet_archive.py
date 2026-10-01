from typing import List, Optional
import asyncio
import logging
import re
from urllib.parse import quote

from .base import BaseSource, BookMetadata, LICENSE_VERIFY_PER_ITEM

logger = logging.getLogger(__name__)


class InternetArchiveSource(BaseSource):
    """Internet Archive — license metadata available per-item."""

    name = "internet_archive"
    description = "Internet Archive (asset-verified public domain only)"
    license_type = LICENSE_VERIFY_PER_ITEM
    rate_limit = 1.0

    SEARCH_URL = "https://archive.org/advancedsearch.php"
    METADATA_URL = "https://archive.org/metadata/{identifier}"
    DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"

    async def search(self, query: str, limit: int = 20) -> List[BookMetadata]:
        params = {
            "q": f'({query}) AND mediatype:accessrepresentative OR mediatype:texts AND licenseurl:*',
            "fl[]": "identifier,title,creator,date,licenseurl,mediatype",
            "rows": limit,
            "page": 1,
            "output": "json",
        }
        try:
            response = await self.client.get(self.SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception:
            return []

        books: List[BookMetadata] = []
        for doc in data.get("response", {}).get("docs", []):
            license_url = doc.get("licenseurl", "")
            license_type = self._extract_license_type(license_url)

            books.append(
                BookMetadata(
                    title=doc.get("title", "Unknown"),
                    author=doc.get("creator"),
                    source=self.name,
                    source_id=doc.get("identifier"),
                    source_url=f"https://archive.org/details/{doc.get('identifier')}",
                    license_type=license_type,
                    license_url=license_url,
                    publication_year=self._extract_year(doc.get("date")),
                )
            )
        return books

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        await asyncio.sleep(self.rate_limit)
        try:
            response = await self.client.get(self.METADATA_URL.format(identifier=source_id))
            if response.status_code != 200:
                return None
            data = response.json()

            metadata = data.get("metadata", {})
            collections = metadata.get("collection") or []
            if self._is_definitely_not_a_book(metadata):
                logger.info(
                    "Internet Archive: dropping %s (%s) — not a book",
                    source_id, metadata.get("title"),
                )
                return None

            license_url = metadata.get("licenseurl", "")
            license_type = self._extract_license_type(license_url)

            # An upload-only collection is not proof of infringement, but it
            # is proof nobody curated this. Demote to `unknown` so the licence
            # gate holds and a person has to look, rather than letting the
            # item's own licenceurl field vouch for itself.
            community_upload = self._is_community_upload(metadata, collections)
            if community_upload:
                license_type = "unknown"

            # ``files`` is a sibling of ``metadata`` in the /metadata/ response,
            # not a key inside it. Reading it off the inner dict -- as this did
            # -- always yielded [], so the adapter returned a null pdf_url for
            # every item it had ever seen.
            files = data.get("files", [])
            return BookMetadata(
                title=metadata.get("title", "Unknown"),
                author=metadata.get("creator"),
                description=metadata.get("description"),
                source=self.name,
                source_id=source_id,
                source_url=f"https://archive.org/details/{source_id}",
                license_type=license_type,
                license_url=license_url,
                publication_year=self._extract_year(metadata.get("date")),
                pdf_url=self._find_pdf_url(files, source_id),
                # Internet Archive is one of the few sources here that can offer
                # both formats for the same item: many scans have both a
                # derived EPUB and a page-image PDF, so a reader can choose
                # either without us pairing two different editions.
                epub_url=self._find_epub_url(files, source_id),
                source_metadata={
                    "mediatype": metadata.get("mediatype", ""),
                    "community_upload": community_upload,
                    "collections": collections[:5] if isinstance(collections, list) else [],
                },
            )
        except Exception:
            return None

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        """Fetch the best available file, preferring EPUB then PDF.

        Matches the preference the other both-format sources use, so an item
        that *has* an EPUB stops shipping as a scan-derived PDF.
        """
        for url in (metadata.epub_url, metadata.pdf_url):
            if not url:
                continue
            try:
                await asyncio.sleep(self.rate_limit)
                response = await self.client.get(url, follow_redirects=True)
                if response.status_code == 200 and response.content:
                    return response.content
            except Exception:
                pass
        return None

    async def list_popular(self, limit: int = 50, start_page: int = 1) -> List[BookMetadata]:
        # Solr pages at 50 rows; ``start_page`` requests a later page so
        # multi-page walks of this source surface genuinely new books.
        params = {
            "q": 'mediatype:texts AND licenseurl:*publicdomain*',
            "fl[]": "identifier,title,creator,date,licenseurl",
            "rows": 50,
            "page": max(1, start_page),
            "sort[]": "downloads desc",
            "output": "json",
        }
        try:
            response = await self.client.get(self.SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception:
            return []

        books: List[BookMetadata] = []
        for doc in data.get("response", {}).get("docs", [])[:limit]:
            books.append(
                BookMetadata(
                    title=doc.get("title", "Unknown"),
                    author=doc.get("creator"),
                    source=self.name,
                    source_id=doc.get("identifier"),
                    source_url=f"https://archive.org/details/{doc.get('identifier')}",
                    license_type="public_domain",
                    license_url=doc.get("licenseurl"),
                    publication_year=self._extract_year(doc.get("date")),
                )
            )
        return books

    #: Collections holding arbitrary user uploads. Everything an anonymous user
    #: has ever attached to a file, which is not a curated shelf of books:
    #: console BIOS dumps, Flash ActionScript exploits, Minecraft skins. All of
    #: these are ``mediatype:texts`` and several carry a public-domain licence
    #: field, so mediatype and licenceurl alone cannot separate them from a
    #: real book.
    COMMUNITY_COLLECTIONS: frozenset = frozenset({
        "community", "opensource", "opensource_media", "opensourcecode",
        "opensource_music", "opensource_software", "opensource_images",
        "softwarelibrary", "softwarelibrary_msdos_games",
    })

    #: Title/identifier fragments that are never a book. Kept deliberately
    #: narrow: a false positive here discards a real title, so each entry is
    #: something that cannot plausibly be the name of a book.
    NON_BOOK_PATTERNS: tuple = (
        r"^script\.video\.", r"^plugin\.video\.", r"^link-skin-", r"-skin-",
        r"\bbios\b", r"\bfirmware\b", r"\bflash\s+exploit\b",
    )

    @classmethod
    def _is_definitely_not_a_book(cls, metadata: dict) -> bool:
        """True only for identifiers that cannot be a book at all.

        Hard-dropping is reserved for these. Everything else -- including a
        community-only upload, which is suspicious but not decisive -- takes
        the softer route below, because a false positive here does not merely
        fail to import: returning ``None`` from ``get_metadata`` makes an
        already-approved book unverifiable and delists it. The Art of War
        (``TheArtOfWarBySunTzu``) lives in ``['opensource', 'community']``
        alongside the junk, so collection membership cannot be a hard filter.
        """
        haystack = " ".join(
            str(metadata.get(k) or "") for k in ("title", "identifier", "subject")
        ).lower()
        return any(re.search(p, haystack) for p in cls.NON_BOOK_PATTERNS)

    @classmethod
    def _is_community_upload(cls, metadata: dict, collections) -> bool:
        """True for items that sit *only* in arbitrary-user-upload collections.

        This is a review signal, not a rejection: the collection is the only
        thing separating ``scospoof`` from the Art of War, and it is not
        enough evidence to discard a title. Such items are forced to
        ``unknown`` so they cannot be approved without a human reading them.
        """
        collections = set(collections) if isinstance(collections, (list, tuple)) else set()
        return bool(collections) and collections <= cls.COMMUNITY_COLLECTIONS

    def _extract_license_type(self, license_url: str) -> str:
        if not license_url:
            return "unknown"
        url = license_url.lower()
        if "publicdomain" in url or "pd" in url:
            return "public_domain"
        if "creativecommons.org/licenses/by/" in url:
            return "cc_by_4.0"
        if "creativecommons.org/licenses/by-sa/" in url:
            return "cc_by_sa_4.0"
        if "creativecommons.org/publicdomain/zero" in url:
            return "cc0_1.0"
        return "unknown"

    def _extract_year(self, date) -> Optional[int]:
        if isinstance(date, str) and len(date) >= 4:
            try:
                return int(date[:4])
            except ValueError:
                pass
        elif isinstance(date, list) and date:
            return self._extract_year(date[0])
        return None

    def _find_file_url(self, files: list, source_id: str, extension: str,
                       formats: tuple) -> Optional[str]:
        """Best {extension} derivative for an item, as a real download URL.

        The URL used to be built from ``f.get("source", "_ia")``, which is the
        only key the method could ever get wrong: entries in ``files`` carry
        ``name``/``format``/``size`` and no ``source``, so every item produced
        https://archive.org/download/_ia/<name> -- a 404 for every book the
        adapter had ever returned. The identifier has to come from the caller,
        which is what DOWNLOAD_URL has always been for.

        Derived files (the EPUB or PDF generated *from* a scanned original) win
        over uploads, because IA marks those with ``source: <identifier>`` while
        originals set ``original: true``. For a scan, the derived EPUB is the
        reflowable text and the original PDF is the page images.
        """
        if not isinstance(files, list):
            return None
        candidates = []
        for f in files:
            if not isinstance(f, dict):
                continue
            name = f.get("name", "")
            if not name.lower().endswith(extension):
                continue
            fmt = (f.get("format") or "").lower()
            if formats and not any(k in fmt for k in formats):
                continue
            is_original = bool(f.get("original"))
            derived = f.get("source") == source_id
            try:
                size = int(f.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            # Sort key: derived first, then smallest, since a 40 MB scan-derived
            # PDF is a worse EPUB than a 400 KB one.
            candidates.append((0 if derived and not is_original else 1, size, name))

        if not candidates:
            return None
        name = min(candidates)[2]
        # Archive filenames routinely contain spaces ("Sumerian Cuneiform
        # English Dictionary 12013CT 28xii.epub"). These URLs are stored on the
        # book row and handed to browsers, not just to httpx, which would
        # normalise the spaces for us. Percent-encode here so the stored value
        # is a URL rather than something that merely works when we fetch it.
        return self.DOWNLOAD_URL.format(
            identifier=quote(source_id, safe=""), filename=quote(name, safe="")
        )

    def _find_pdf_url(self, files: list, source_id: str) -> Optional[str]:
        return self._find_file_url(files, source_id, ".pdf", ("pdf", "text"))

    def _find_epub_url(self, files: list, source_id: str) -> Optional[str]:
        return self._find_file_url(files, source_id, ".epub", ("epub", "electronic"))