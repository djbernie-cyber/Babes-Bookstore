from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, AsyncIterator
import httpx


@dataclass
class BookMetadata:
    """Standardized book metadata from any source."""
    title: str
    author: Optional[str] = None
    description: Optional[str] = None
    isbn: Optional[str] = None

    source: str = ""
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    source_metadata: Dict[str, Any] = field(default_factory=dict)

    license_type: str = ""
    license_url: Optional[str] = None

    pdf_url: Optional[str] = None
    epub_url: Optional[str] = None
    cover_url: Optional[str] = None

    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    language: str = "en"
    page_count: Optional[int] = None
    publication_year: Optional[int] = None


class BaseSource(ABC):
    """Base class for book source adapters."""

    name: str = ""
    description: str = ""
    license_type: str = "public_domain"
    rate_limit: float = 1.0  # seconds between requests
    requires_api_key: bool = False

    #: Some providers (Gutenberg, Standard Ebooks) reject unfamiliar agents
    #: with 403/401, so present a conventional UA plus a contact URL.
    USER_AGENT = (
        "Mozilla/5.0 (compatible; BabesBookstore/1.0; "
        "+https://babes-bookstore.netlify.app) public-domain-aggregator"
    )

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
            },
        )

    async def close(self):
        await self.client.aclose()

    @abstractmethod
    async def search(self, query: str, limit: int = 20) -> List[BookMetadata]:
        """Search for books matching query."""
        pass

    @abstractmethod
    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        """Get detailed metadata for a specific book."""
        pass

    @abstractmethod
    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        """Download book content (PDF/EPUB)."""
        pass

    @abstractmethod
    async def list_popular(self, limit: int = 50) -> List[BookMetadata]:
        """List popular/recent books from this source."""
        pass

    def is_known_license(self, license_type: Optional[str]) -> bool:
        return license_type in ("public_domain", "cc0_1.0", "cc_by_4.0", "cc_by_sa_4.0")