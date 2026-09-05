from typing import List, Optional
import xml.etree.ElementTree as ET
import asyncio
import logging

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)


class OAPENSource(BaseSource):
    """OAPEN — Open Access publisher books with CC licenses."""

    name = "oapen"
    description = "OAPEN — open access academic books"
    license_type = "cc_by_4.0"
    rate_limit = 1.0

    OAI_URL = "https://library.oapen.org/oai/request"

    NAMESPACES = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    async def search(self, query: str, limit: int = 20) -> List[BookMetadata]:
        if not query:
            return await self.list_popular(limit)
        # OAI-PMH has no free-text search; harvest a window and filter locally.
        books = await self._harvest(max(limit * 8, 200))
        q = query.lower()
        return [
            b for b in books
            if q in b.title.lower()
            or q in (b.author or "").lower()
            or q in (b.description or "").lower()
        ][:limit]

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        params = {
            "verb": "GetRecord",
            "metadataPrefix": "oai_dc",
            "identifier": source_id,
        }
        try:
            response = await self.client.get(self.OAI_URL, params=params)
            response.raise_for_status()
        except Exception:
            return None
        books, _token = self._parse(response.text)
        return books[0] if books else None

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        return None

    async def list_popular(self, limit: int = 50, start_page: int = 1) -> List[BookMetadata]:
        return await self._harvest(limit, start_page=start_page)

    async def _harvest(self, limit: int, start_page: int = 1) -> List[BookMetadata]:
        """Harvest records, following resumption tokens until `limit` is met.

        OAPEN's OAI endpoint returns resumption tokens that may be long-lived
        (a UUID) or opaque decimal. Each page must be requested with the token
        alone. We retry transient failures, skip earlier records for
        ``start_page``, and stop cleanly either when the limit is reached or
        the endpoint reports no further token.
        """
        books: List[BookMetadata] = []
        params = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
        consecutive_failures = 0
        skip = max(0, (start_page - 1) * max(limit, 1))

        while len(books) < limit:
            try:
                response = await self.client.get(self.OAI_URL, params=params)
                response.raise_for_status()
            except Exception:
                consecutive_failures += 1
                if consecutive_failures >= 5:
                    logger.warning("OAPEN harvest failed repeatedly; stopping")
                    break
                await asyncio.sleep(self.rate_limit * 3)
                continue

            consecutive_failures = 0
            batch, token = self._parse(response.text)

            if self._error(response.text):
                logger.warning("OAPEN OAI error halting harvest")
                break

            if not batch and not token:
                break

            carried = skip
            for b in batch:
                if carried > 0:
                    carried -= 1
                    continue
                books.append(b)
                if len(books) >= limit:
                    break
            skip = 0
            if len(books) >= limit:
                break

            if not token:
                break
            params = {"verb": "ListRecords", "resumptionToken": token}
            await asyncio.sleep(self.rate_limit)

        return books[:limit]

    def _error(self, text: str) -> Optional[str]:
        try:
            root = ET.fromstring(text)
            err = root.find("oai:error", self.NAMESPACES)
            return err.get("code") if err is not None else None
        except ET.ParseError:
            return "parse"

    def _parse(self, text: str) -> tuple[List[BookMetadata], Optional[str]]:
        books: List[BookMetadata] = []
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            logger.warning("OAPEN returned malformed XML")
            return books, None

        records = root.findall(".//oai:record", self.NAMESPACES)

        for record in records:
            header = record.find("oai:header", self.NAMESPACES)
            if header is not None and header.find("oai:deleted", self.NAMESPACES) is not None:
                continue

            identifier_el = header.find("oai:identifier", self.NAMESPACES) if header is not None else None
            identifier = identifier_el.text if identifier_el is not None else None

            metadata_el = record.find("oai:metadata", self.NAMESPACES)
            if metadata_el is None:
                continue

            dc_el = metadata_el.find("oai_dc:dc", self.NAMESPACES)
            if dc_el is None:
                continue

            title = self._get_text(dc_el, "dc:title")
            creator = self._get_text(dc_el, "dc:creator")
            description = self._get_text(dc_el, "dc:description")
            date = self._get_text(dc_el, "dc:date")
            rights = self._get_text(dc_el, "dc:rights")
            identifier_dc = self._get_text(dc_el, "dc:identifier")

            license_type = self._parse_license(rights)

            if not title and not identifier:
                continue

            books.append(
                BookMetadata(
                    title=title or "Unknown",
                    author=creator,
                    description=description,
                    source=self.name,
                    source_id=identifier,
                    source_url=identifier_dc,
                    license_type=license_type,
                    license_url=rights,
                    publication_year=int(date[:4]) if date and len(date) >= 4 else None,
                )
            )

        token_el = root.find(".//oai:resumptionToken", self.NAMESPACES)
        token = token_el.text.strip() if token_el is not None and token_el.text else None
        return books, token

    def _get_text(self, parent, tag: str) -> Optional[str]:
        el = parent.find(tag, self.NAMESPACES)
        return el.text if el is not None and el.text else None

    def _parse_license(self, rights: Optional[str]) -> str:
        if not rights:
            return "unknown"
        r = rights.lower()
        if "public domain" in r:
            return "public_domain"
        if "cc by-sa" in r or "cc-by-sa" in r:
            return "cc_by_sa_4.0"
        if "cc by" in r:
            if "nc" in r:
                return "cc_by_nc"
            return "cc_by_4.0"
        if "cc0" in r:
            return "cc0_1.0"
        return "unknown"