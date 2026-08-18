import xml.etree.ElementTree as ET
from typing import List, Optional
import asyncio

from .base import BaseSource, BookMetadata


class GutenbergSource(BaseSource):
    """Project Gutenberg — public domain ebooks (70,000+)."""

    name = "gutenberg"
    description = "Project Gutenberg — public domain ebooks"
    license_type = "public_domain"
    rate_limit = 0.5

    CATALOG_URL = "https://www.gutenberg.org/cache/epub/feeds/today/books.rdf"
    OPENSEARCH_URL = "https://www.gutenberg.org/ebooks/search.opds"
    FILES_URL = "https://www.gutenberg.org/files/{id}/{id}-{file}.pdf"
    META_URL = "https://www.gutenberg.org/ebooks/{id}"

    async def search(self, query: str, limit: int = 20) -> List[BookMetadata]:
        params = {"query": query}
        response = await self.client.get(self.OPENSEARCH_URL, params=params)
        response.raise_for_status()
        return self._parse_opds(response.text, limit)

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        await asyncio.sleep(self.rate_limit)
        url = f"https://www.gutenberg.org/ebooks/{source_id}.rdf"
        try:
            response = await self.client.get(url)
            if response.status_code != 200:
                return None
            return self._parse_rdf(response.text, source_id)
        except Exception:
            return None

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        if not metadata.source_id:
            return None
        url = f"https://www.gutenberg.org/files/{metadata.source_id}/{metadata.source_id}-pdf.pdf"
        try:
            await asyncio.sleep(self.rate_limit)
            response = await self.client.get(url, follow_redirects=True)
            if response.status_code == 200 and "pdf" in response.headers.get("content-type", ""):
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
        return self._parse_rdf_catalog(response.text, limit)

    def _parse_opds(self, text: str, limit: int) -> List[BookMetadata]:
        books: List[BookMetadata] = []
        try:
            root = ET.fromstring(text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns)[:limit]:
                title_el = entry.find("atom:title", ns)
                title = title_el.text if title_el is not None else "Unknown"
                id_el = entry.find("atom:id", ns)
                source_id = id_el.text.split("/")[-1] if id_el is not None and id_el.text else None

                author = "Unknown"
                for author_el in entry.findall("atom:author", ns):
                    name_el = author_el.find("atom:name", ns)
                    if name_el is not None and name_el.text:
                        author = name_el.text
                        break

                if source_id and source_id.isdigit():
                    books.append(
                        BookMetadata(
                            title=title,
                            author=author,
                            source=self.name,
                            source_id=source_id,
                            source_url=f"https://www.gutenberg.org/ebooks/{source_id}",
                            license_type="public_domain",
                            license_url="https://www.gutenberg.org/policy/license.html",
                        )
                    )
        except ET.ParseError:
            pass
        return books

    def _parse_rdf(self, text: str, source_id: str) -> Optional[BookMetadata]:
        try:
            root = ET.fromstring(text)
            ns = {
                "dcterms": "http://purl.org/dc/terms/",
                "pg": "http://www.gutenberg.org/2009/pgterms/",
                "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            }

            title = "Unknown"
            title_el = root.find(".//dcterms:title", ns)
            if title_el is not None:
                title = title_el.text or title

            author = "Unknown"
            creator_el = root.find(".//dcterms:creator", ns)
            if creator_el is not None:
                name_el = creator_el.find("pg:name", ns)
                if name_el is not None:
                    author = name_el.text or author

            description_el = root.find(".//dcterms:description", ns)
            description = description_el.text if description_el is not None else None

            year_el = root.find(".//dcterms:issued", ns)
            year = int(year_el.text[:4]) if year_el is not None and year_el.text else None

            language_el = root.find(".//dcterms:language", ns)
            language = "en"
            if language_el is not None:
                lang_value = language_el.find("rdf:value", ns)
                if lang_value is not None and lang_value.text:
                    language = lang_value.text.split("/")[-1].lower()

            return BookMetadata(
                title=title,
                author=author,
                description=description,
                source=self.name,
                source_id=source_id,
                source_url=f"https://www.gutenberg.org/ebooks/{source_id}",
                license_type="public_domain",
                license_url="https://www.gutenberg.org/policy/license.html",
                pdf_url=f"https://www.gutenberg.org/files/{source_id}/{source_id}-pdf.pdf",
                language=language,
                publication_year=year,
            )
        except ET.ParseError:
            return None

    def _parse_rdf_catalog(self, text: str, limit: int) -> List[BookMetadata]:
        books: List[BookMetadata] = []
        try:
            root = ET.fromstring(text)
            ns = {
                "dcterms": "http://purl.org/dc/terms/",
                "pg": "http://www.gutenberg.org/2009/pgterms/",
            }
            for book_el in root.findall(".//pg:book", ns)[:limit]:
                ebook_id = book_el.get("rdf:about", "").rsplit("/", 1)[-1]
                title_el = book_el.find("dcterms:title", ns)
                title = title_el.text if title_el is not None and title_el.text else "Unknown"

                creator_el = book_el.find("dcterms:creator", ns)
                author = None
                if creator_el is not None:
                    author_el = creator_el.find("pg:name", ns)
                    if author_el is not None and author_el.text:
                        author = author_el.text

                if ebook_id and ebook_id.isdigit():
                    books.append(
                        BookMetadata(
                            title=title,
                            author=author,
                            source=self.name,
                            source_id=ebook_id,
                            source_url=f"https://www.gutenberg.org/ebooks/{ebook_id}",
                            license_type="public_domain",
                        )
                    )
        except ET.ParseError:
            pass
        return books