"""Directory of Open Access Books (DOAB) adapter.

Fixes applied:
- Dropped `set=open_access`, which the OAI endpoint answers with
  `noRecordsMatch` (this made the source return zero books).
- Added resumption-token paging so more than one page is reachable.
- Licence detection now reads dc:rights *and* dc:license, and maps
  NonCommercial/NoDerivatives correctly so they get rejected upstream.
"""
import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import List, Optional

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)

NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


class DOABSource(BaseSource):
    """Directory of Open Access Books — CC-licensed academic books."""

    name = "doab"
    description = "Directory of Open Access Books (CC-licensed academic books)"
    license_type = "cc_by_4.0"
    rate_limit = 1.0

    OAI_URL = "https://directory.doabooks.org/oai/request"

    async def search(self, query: str, limit: int = 20) -> List[BookMetadata]:
        # OAI-PMH has no free-text search; fetch a window and filter locally.
        books = await self._harvest(limit if not query else max(limit * 8, 200))
        if not query:
            return books[:limit]
        q = query.lower()
        return [
            b for b in books
            if q in b.title.lower()
            or q in (b.author or "").lower()
            or q in (b.description or "").lower()
        ][:limit]

    async def list_popular(self, limit: int = 50, start_page: int = 1) -> List[BookMetadata]:
        return await self._harvest(limit)

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        try:
            response = await self.client.get(self.OAI_URL, params={
                "verb": "GetRecord", "metadataPrefix": "oai_dc", "identifier": source_id,
            }, follow_redirects=True)
            response.raise_for_status()
        except Exception:
            logger.warning("DOAB GetRecord failed for %s", source_id, exc_info=True)
            return None
        records, _ = self._parse(response.text)
        return records[0] if records else None

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        if not metadata.pdf_url:
            return None
        try:
            await asyncio.sleep(self.rate_limit)
            response = await self.client.get(metadata.pdf_url, follow_redirects=True)
            if response.status_code == 200 and response.content[:4] == b"%PDF":
                return response.content
        except Exception:
            logger.debug("DOAB download failed: %s", metadata.pdf_url, exc_info=True)
        return None

    async def _harvest(self, limit: int) -> List[BookMetadata]:
        """Harvest records, following resumption tokens until `limit` is met."""
        books: List[BookMetadata] = []
        params = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}

        while len(books) < limit:
            try:
                response = await self.client.get(self.OAI_URL, params=params, follow_redirects=True)
                response.raise_for_status()
            except Exception:
                logger.warning("DOAB harvest failed", exc_info=True)
                break

            batch, token = self._parse(response.text)
            if not batch and not token:
                break
            books.extend(batch)

            if not token:
                break
            # Per the spec, resumptionToken must be sent alone.
            params = {"verb": "ListRecords", "resumptionToken": token}
            await asyncio.sleep(self.rate_limit)

        return books[:limit]

    def _parse(self, xml: str) -> tuple[List[BookMetadata], Optional[str]]:
        books: List[BookMetadata] = []
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            logger.warning("DOAB returned malformed XML")
            return books, None

        error = root.find(".//oai:error", NS)
        if error is not None:
            logger.warning("DOAB OAI error: %s", (error.text or error.get("code")))
            return books, None

        for record in root.findall(".//oai:record", NS):
            header = record.find("oai:header", NS)
            if header is None or header.get("status") == "deleted":
                continue

            dc = record.find(".//oai_dc:dc", NS)
            if dc is None:
                continue

            title = self._text(dc, "dc:title")
            identifier = self._text(header, "oai:identifier")
            if not title or not identifier:
                continue

            rights = [e.text for e in dc.findall("dc:rights", NS) if e.text]
            rights += [e.text for e in dc.findall("dc:license", NS) if e.text]
            urls = [e.text for e in dc.findall("dc:identifier", NS) if e.text]
            authors = [e.text for e in dc.findall("dc:creator", NS) if e.text]
            subjects = [e.text for e in dc.findall("dc:subject", NS) if e.text]
            date = self._text(dc, "dc:date")

            licence, licence_url = self._licence(rights)

            books.append(BookMetadata(
                title=title.strip()[:500],
                author=", ".join(authors[:3]) or None,
                description=self._text(dc, "dc:description"),
                source=self.name,
                source_id=identifier,
                source_url=next((u for u in urls if u.startswith("http")), None),
                source_metadata={"publisher": self._text(dc, "dc:publisher")},
                license_type=licence,
                license_url=licence_url,
                pdf_url=next((u for u in urls if u.lower().endswith(".pdf")), None),
                tags=subjects[:5],
                language=self._text(dc, "dc:language") or "en",
                publication_year=self._year(date),
            ))

        token_el = root.find(".//oai:resumptionToken", NS)
        token = token_el.text.strip() if token_el is not None and token_el.text else None
        return books, token

    @staticmethod
    def _text(parent, tag: str) -> Optional[str]:
        if parent is None:
            return None
        el = parent.find(tag, NS)
        return el.text.strip() if el is not None and el.text else None

    @staticmethod
    def _year(value: Optional[str]) -> Optional[int]:
        if not value or len(value) < 4 or not value[:4].isdigit():
            return None
        year = int(value[:4])
        return year if 1000 <= year <= 2100 else None

    @staticmethod
    def _licence(values: List[str]) -> tuple[str, Optional[str]]:
        """Map dc:rights/dc:license text onto a canonical licence id."""
        url = next((v for v in values if v and v.startswith("http")), None)
        blob = " ".join(v.lower() for v in values if v)

        if not blob:
            return "unknown", url
        if "publicdomain" in blob or "public domain" in blob or "cc0" in blob:
            return ("cc0_1.0" if "cc0" in blob else "public_domain"), url
        if "by-nc-nd" in blob or ("nc" in blob and "nd" in blob):
            return "cc_by_nc_nd", url
        if "by-nc-sa" in blob:
            return "cc_by_nc_sa", url
        if "by-nc" in blob or "noncommercial" in blob or "non-commercial" in blob:
            return "cc_by_nc", url
        if "by-nd" in blob or "noderiv" in blob:
            return "cc_by_nd", url
        if "by-sa" in blob or "sharealike" in blob:
            return "cc_by_sa_4.0", url
        if "cc-by" in blob or "cc by" in blob or "creativecommons.org/licenses/by/" in blob:
            return "cc_by_4.0", url
        # "open access" alone is not a redistribution licence -> manual review.
        return "unknown", url
