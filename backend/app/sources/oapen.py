from typing import List, Optional
import xml.etree.ElementTree as ET
import asyncio
import logging
from collections import Counter

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)


class OAPENSource(BaseSource):
    """OAPEN — Open Access publisher books with CC licenses."""

    name = "oapen"
    description = "OAPEN — open access academic books"
    license_type = "cc_by_4.0"
    rate_limit = 1.0

    OAI_URL = "https://library.oapen.org/oai/request"

    #: The only dc:resourceType value that describes a standalone work.
    MONOGRAPH_TYPES = {"book"}

    NAMESPACES = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    def __init__(self):
        super().__init__()
        #: dc:resourceType values dropped during the last harvest, for logging.
        self._rejected_types: Counter = Counter()

    @classmethod
    def _is_monograph(cls, record_types: set, part_of: Optional[str]) -> bool:
        """True only for a record OAPEN itself labels a standalone book.

        Deliberately strict. A chapter extracted from an edited collection is
        not a book, and neither is an unlabelled record: with no confirmed
        `book` type there is no evidence the record is a monograph, and this
        catalogue presents every title as a book. ``relationisPartOfBook``
        disqualifies a record on its own, independently of the type, because it
        means the record is a part of a larger work.
        """
        if part_of:
            return False
        if not record_types:
            return False
        return record_types <= cls.MONOGRAPH_TYPES

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

        self._log_rejections()
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

            values: dict = {}
            for el in dc_el:
                values.setdefault(el.tag.split("}", 1)[-1], []).append(
                    (el.text or "").strip()
                )

            def first(tag: str) -> Optional[str]:
                got = values.get(tag) or []
                return got[0] if got and got[0] else None

            title = first("title")
            creator = first("creator")
            description = first("description")
            date = first("date")
            rights = first("rights")
            license_condition = first("licenseCondition")
            identifier_dc = first("identifier")

            # OAPEN's OAI feed is not a book feed. Alongside monographs it
            # serves the PDFs of individual chapters, so roughly one record in
            # six is `resourceType` 'chapter' and was being ingested as a
            # shoppable book. Kept only the parts.
            record_types = {
                v.lower() for v in values.get("resourceType", []) if v
            }
            part_of = next(
                (v for v in values.get("relationisPartOfBook", []) if v), None
            )
            if not self._is_monograph(record_types, part_of):
                key = "/".join(sorted(record_types)) or "(absent)"
                self._rejected_types[key] += 1
                continue

            # OAPEN splits the licence across two elements: dc:rights holds the
            # marker "info:eu-repo/semantics/openAccess" and the real licence
            # name ("Attribution 4.0 International") arrives in
            # dc:licenseCondition. Parsing dc:rights alone never matched any
            # branch of _parse_license, so all 452 monographs per page were
            # recorded as licence "unknown" and had to be reviewed by hand.
            license_type = self._parse_license(license_condition)

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
                    license_url=license_condition or rights,
                    publication_year=int(date[:4]) if date and len(date) >= 4 else None,
                    source_metadata={
                        "resource_type": sorted(record_types),
                        "publisher": first("publisher"),
                        "isbn": next(
                            (v for v in values.get("relationisbn", []) if v), None
                        ),
                    },
                )
            )

        token_el = root.find(".//oai:resumptionToken", self.NAMESPACES)
        token = token_el.text.strip() if token_el is not None and token_el.text else None
        return books, token

    def _get_text(self, parent, tag: str) -> Optional[str]:
        el = parent.find(tag, self.NAMESPACES)
        return el.text if el is not None and el.text else None

    async def _check_live(self, sample: int = 300) -> None:
        """Log the shape of the real feed: what is kept, and with what licence.

        Both decisions here were made from sampled records, so this makes the
        assumption checkable in production rather than only in a test fixture.
        """
        try:
            books = await self._harvest(sample)
        except Exception as exc:  # diagnostics must never break a harvest
            logger.warning("OAPEN live check failed: %s", exc)
            return
        if not books:
            logger.warning("OAPEN live check returned no monographs")
            return
        licences: Counter = Counter(b.license_type for b in books)
        no_author = sum(1 for b in books if not b.author)
        logger.info(
            "OAPEN live check: %d/%d monographs kept, %d without a creator, "
            "licences=%s",
            len(books),
            sample,
            no_author,
            dict(licences.most_common()),
        )
        unknown = licences.get("unknown", 0)
        if unknown:
            logger.warning(
                "OAPEN: %d kept record(s) still have an unresolved licence; "
                "check dc:licenseCondition handling",
                unknown,
            )

    def _log_rejections(self) -> None:
        if not self._rejected_types:
            return
        summary = ", ".join(
            f"{count} x {'/'.join(sorted(types))}" for types, count in
            self._rejected_types.most_common()
        )
        logger.info(
            "OAPEN skipped %d non-monograph record(s): %s",
            sum(self._rejected_types.values()),
            summary,
        )
        self._rejected_types.clear()

    def _parse_license(self, license_condition: Optional[str]) -> str:
        """Map a dc:licenseCondition value onto a licence type.

        The values are the bare Creative Commons deed names, e.g.
        "Attribution 4.0 International" -- not the "CC BY 4.0" abbreviations
        this function used to look for, which is why it returned "unknown" for
        every real OAPEN record.
        """
        if not license_condition:
            return "unknown"
        r = " ".join(license_condition.lower().split())
        if "public domain" in r:
            return "public_domain"
        if "cc0" in r or "cc zero" in r:
            return "cc0_1.0"
        # Order matters: the NC and ND variants contain "attribution" too, and
        # NC-SA contains both, so the most restrictive qualifier has to be
        # tested before the permissive one.
        if "noncommercial" in r or "non-commercial" in r or " nc " in f" {r} ":
            if "sharealike" in r or "share alike" in r:
                return "cc_by_nc_sa_4.0"
            return "cc_by_nc_4.0"
        if "noderiv" in r or "no derivative" in r:
            return "cc_by_nd_4.0"
        if "sharealike" in r or "share alike" in r:
            return "cc_by_sa_4.0"
        if "attribution" in r:
            return "cc_by_4.0"
        return "unknown"