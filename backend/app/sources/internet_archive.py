from typing import List, Optional
import asyncio

from .base import BaseSource, BookMetadata, LICENSE_VERIFY_PER_ITEM


class InternetArchiveSource(BaseSource):
    """Internet Archive — license metadata available per-item."""

    name = "internet_archive"
    description = "Internet Archive (license-verified public domain only)"
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
            license_url = metadata.get("licenseurl", "")
            license_type = self._extract_license_type(license_url)

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
                pdf_url=self._find_pdf_url(metadata.get("files", [])),
            )
        except Exception:
            return None

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        if not metadata.pdf_url:
            return None
        try:
            await asyncio.sleep(self.rate_limit)
            response = await self.client.get(metadata.pdf_url, follow_redirects=True)
            if response.status_code == 200:
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

    def _find_pdf_url(self, files: list) -> Optional[str]:
        if not isinstance(files, list):
            return None
        for f in files:
            if isinstance(f, dict) and f.get("name", "").endswith(".pdf"):
                fmt = f.get("format", "").lower()
                if "pdf" in fmt or "text" in fmt:
                    name = f["name"]
                    return f"https://archive.org/download/{f.get('source','_ia')}/{name}"
        return None