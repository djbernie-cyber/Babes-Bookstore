from typing import List, Optional
import xml.etree.ElementTree as ET
import asyncio

from .base import BaseSource, BookMetadata


class DOABSource(BaseSource):
    """Directory of Open Access Books — verified CC licenses."""

    name = "doab"
    description = "Directory of Open Access Books (CC-licensed academic books)"
    license_type = "cc_by_4.0"
    rate_limit = 1.0

    OAI_URL = "https://directory.doabooks.org/oai/request"

    NAMESPACES = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    async def search(self, query: str, limit: int = 20) -> List[BookMetadata]:
        params = {
            "verb": "ListRecords",
            "metadataPrefix": "oai_dc",
            "set": "open_access",
        }
        try:
            response = await self.client.get(self.OAI_URL, params=params)
            response.raise_for_status()
        except Exception:
            return []
        return self._parse_oai(response.text, limit, query)

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
        books = self._parse_oai(response.text, 1, "")
        return books[0] if books else None

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        return None

    async def list_popular(self, limit: int = 50) -> List[BookMetadata]:
        return await self.search("", limit)

    def _parse_oai(self, text: str, limit: int, query: str) -> List[BookMetadata]:
        books: List[BookMetadata] = []
        try:
            root = ET.fromstring(text)
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

                if query and query.lower() not in title.lower():
                    continue

                license_type = self._parse_license(rights)

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

                if len(books) >= limit:
                    break
        except ET.ParseError:
            pass
        return books

    def _get_text(self, parent, tag: str) -> Optional[str]:
        el = parent.find(tag, self.NAMESPACES)
        return el.text if el is not None and el.text else None

    def _parse_license(self, rights: Optional[str]) -> str:
        if not rights:
            return "unknown"
        r = rights.lower()
        if "public domain" in r or "publicdomain" in r:
            return "public_domain"
        if "cc by-sa" in r or "cc-by-sa" in r:
            return "cc_by_sa_4.0"
        if "cc by" in r or "cc-by" in r:
            if "nc" in r:
                return "cc_by_nc"
            return "cc_by_4.0"
        if "cc0" in r:
            return "cc0_1.0"
        return "unknown"