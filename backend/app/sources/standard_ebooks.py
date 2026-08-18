from typing import List, Optional
import asyncio

from .base import BaseSource, BookMetadata


class StandardEbooksSource(BaseSource):
    """Standard Ebooks — professionally formatted public domain ebooks."""

    name = "standard_ebooks"
    description = "Standard Ebooks — enhanced public domain ebooks"
    license_type = "public_domain"
    rate_limit = 1.0

    CATALOG_URL = "https://standardebooks.org/opds/all"
    BASE_URL = "https://standardebooks.org"

    async def search(self, query: str, limit: int = 20) -> List[BookMetadata]:
        params = {"query": query}
        try:
            response = await self.client.get(self.CATALOG_URL, params=params)
            response.raise_for_status()
        except Exception:
            return []
        return self._parse_opds(response.text, limit)

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        await asyncio.sleep(self.rate_limit)
        url = f"{self.BASE_URL}/opds/{source_id}"
        try:
            response = await self.client.get(url)
            if response.status_code != 200:
                return None
            return self._parse_entry(response.text, source_id)
        except Exception:
            return None

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        if not metadata.pdf_url:
            return None
        try:
            await asyncio.sleep(self.rate_limit)
            response = await self.client.get(metadata.pdf_url)
            if response.status_code == 200:
                return response.content
        except Exception:
            pass
        return None

    async def list_popular(self, limit: int = 50) -> List[BookMetadata]:
        try:
            response = await self.client.get(self.CATALOG_URL)
            response.raise_for_status()
        except Exception:
            return []
        return self._parse_opds(response.text, limit)

    def _parse_opds(self, text: str, limit: int) -> List[BookMetadata]:
        books: List[BookMetadata] = []
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns)[:limit]:
                title_el = entry.find("atom:title", ns)
                title = title_el.text if title_el is not None else "Unknown"

                id_el = entry.find("atom:id", ns)
                source_id = None
                if id_el is not None and id_el.text:
                    source_id = id_el.text.split("/")[-1]

                author = "Unknown"
                for author_el in entry.findall("atom:author", ns):
                    name_el = author_el.find("atom:name", ns)
                    if name_el is not None and name_el.text:
                        author = name_el.text
                        break

                summary_el = entry.find("atom:summary", ns)
                description = summary_el.text if summary_el is not None else None

                pdf_url = None
                for link in entry.findall("atom:link", ns):
                    href = link.get("href")
                    if href and href.endswith(".pdf"):
                        pdf_url = href
                        break

                cover_url = None
                for link in entry.findall("atom:link", ns):
                    if link.get("rel") == "http://opds-spec.org/image/thumbnail":
                        cover_url = link.get("href")
                        break

                if source_id:
                    books.append(
                        BookMetadata(
                            title=title,
                            author=author,
                            description=description,
                            source=self.name,
                            source_id=source_id,
                            source_url=f"{self.BASE_URL}/ebooks/{source_id}",
                            license_type="public_domain",
                            license_url="https://standardebooks.org/about",
                            pdf_url=pdf_url,
                            cover_url=cover_url,
                        )
                    )
        except Exception:
            pass
        return books

    def _parse_entry(self, text: str, source_id: str) -> Optional[BookMetadata]:
        return self._parse_opds(text, 1)[0] if self._parse_opds(text, 1) else None