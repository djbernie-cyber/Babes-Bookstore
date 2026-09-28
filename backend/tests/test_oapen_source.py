"""OAPEN feeds whole PDFs, not just books.

OAPEN's OAI-PMH endpoint serves the extracted chapter PDFs of edited
collections alongside standalone monographs. In 536 sampled records, 84 (15.7%)
were `dc:resourceType` 'chapter' and 39 of those also carried
`dc:relationisPartOfBook`. Before the filter in oapen.OAPENSource those
chapters were ingested as shoppable books, which is how a title like
"Chapter Solar and Chthonic Deities in Ancient Anatolia" reached the review
queue as if it were a book by Charles Wayne Steitler.

These tests pin the classification rules to the shapes OAPEN actually returns.
"""

import pytest

from app.config import get_settings as _get_settings
from app.sources.oapen import OAPENSource

settings = _get_settings()

NS = (
    'xmlns:oai="http://www.openarchives.org/OAI/2.0/" '
    'xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/"'
)


def record(
    title: str = "A Standalone Monograph",
    resource_type: str = "book",
    part_of: str = None,
    creator: str = "Some Author",
    rights: str = "info:eu-repo/semantics/openAccess",
    license_condition: str = "Attribution 4.0 International",
) -> str:
    type_el = f"<dc:type>{resource_type}</dc:type>" if resource_type else ""
    part_el = (
        f"<dc:relationisPartOfBook>{part_of}</dc:relationisPartOfBook>"
        if part_of
        else ""
    )
    creator_el = f"<dc:creator>{creator}</dc:creator>" if creator else ""
    cond_el = (
        f"<dc:licenseCondition>{license_condition}</dc:licenseCondition>"
        if license_condition
        else ""
    )
    # OAPEN splits the licence in two: dc:rights carries the
    # info:eu-repo/semantics/openAccess marker, while the actual licence text
    # ("Attribution 4.0 International") arrives in dc:licenseCondition. Reading
    # rights alone is why every harvested book shows licence "unknown" and lands
    # in the manual review queue with an unresolved licence.
    return f"""
    <oai:record>
      <oai:header><oai:identifier>oai:library.oapen.org:12345</oai:identifier></oai:header>
      <oai:metadata>
        <oai_dc:dc>
          <dc:title>{title}</dc:title>
          {creator_el}
          <dc:resourceType>{resource_type}</dc:resourceType>{type_el}
          {part_el}
          <dc:rights>{rights}</dc:rights>
          {cond_el}
          <dc:date>2021</dc:date>
          <dc:publisher>Some Press</dc:publisher>
        </oai_dc:dc>
      </oai:metadata>
    </oai:record>
    """


def parse(*records: str):
    xml = f'<?xml version="1.0"?><OAI-PMH {NS}>{"".join(records)}</OAI-PMH>'
    books, token = OAPENSource()._parse(xml)
    return books


class TestOapenTypeFilter:
    def test_monograph_is_kept(self):
        books = parse(record())
        assert len(books) == 1
        assert books[0].title == "A Standalone Monograph"
        assert books[0].license_type == "cc_by_4.0"

    def test_chapter_is_dropped(self):
        """The bug: a chapter from an edited volume is not a book."""
        assert parse(record(
            title="Chapter Solar and Chthonic Deities in Ancient Anatolia",
            resource_type="chapter",
        )) == []

    def test_record_that_is_part_of_a_book_is_dropped(self):
        """A chapter-numbered title alone is ambiguous; the parent link is not."""
        assert parse(record(
            title="Chapter 1 Introduction",
            resource_type="book",
            part_of="5b1b1a20-1111-2222-3333-444455556666",
        )) == []

    def test_unlabelled_record_is_dropped(self):
        """No resourceType means no evidence it is a monograph."""
        assert parse(record(resource_type="")) == []

    def test_unknown_type_is_not_treated_as_a_book(self):
        assert parse(record(resource_type="dataset")) == []

    def test_mixed_types_are_dropped_even_when_book_is_present(self):
        xml = f"""<?xml version="1.0"?><OAI-PMH {NS}>
        <oai:record>
          <oai:header><oai:identifier>oai:library.oapen.org:999</oai:identifier></oai:header>
          <oai:metadata><oai_dc:dc>
            <dc:title>Book containing a dataset</dc:title>
            <dc:resourceType>book</dc:resourceType>
            <dc:resourceType>dataset</dc:resourceType>
          </oai_dc:dc></oai:metadata>
        </oai:record>
        </OAI-PMH>"""
        assert OAPENSource()._parse(xml)[0] == []

    def test_case_is_ignored(self):
        """OAPEN is not consistent about casing, so compare lowercased."""
        assert parse(record(resource_type="Chapter")) == []
        assert len(parse(record(resource_type="BOOK"))) == 1

    def test_deleted_records_are_ignored(self):
        xml = f'<?xml version="1.0"?><OAI-PMH {NS}><oai:record><oai:header>' \
              f'<oai:identifier>oai:x:1</oai:identifier><oai:deleted/></oai:header>' \
              f'</oai:record></OAI-PMH>'
        assert OAPENSource()._parse(xml)[0] == []


class TestOapenMetadata:
    def test_kept_records_record_their_type_for_audit(self):
        """Provenance so a reviewer can see why a record passed the filter."""
        book = parse(record())[0]
        assert book.source_metadata["resource_type"] == ["book"]
        assert book.source_metadata["publisher"] == "Some Press"

    def test_missing_creator_is_tolerated_not_faked(self):
        """35.6% of real records have no dc:creator. Do not invent one."""
        book = parse(record(creator=""))[0]
        assert book.author is None

    def test_licence_is_read_from_license_condition(self):
        """The real bug behind '100 books waiting for review, licence unknown'.

        OAPEN puts the openAccess marker in dc:rights and the actual licence
        name in dc:licenseCondition. Only the latter names a licence.
        """
        assert parse(record())[0].license_type == "cc_by_4.0"

    def test_licence_url_is_the_condition_not_the_marker(self):
        book = parse(record())[0]
        assert book.license_url == "Attribution 4.0 International"

    @pytest.mark.parametrize(
        "condition,expected",
        [
            ("Attribution 4.0 International", "cc_by_4.0"),
            ("Attribution-ShareAlike 4.0 International", "cc_by_sa_4.0"),
            ("Attribution-NonCommercial 4.0 International", "cc_by_nc_4.0"),
            (
                "Attribution-NonCommercial-ShareAlike 4.0 International",
                "cc_by_nc_sa_4.0",
            ),
            ("Attribution-NoDerivatives 4.0 International", "cc_by_nd_4.0"),
            ("CC0 1.0 Universal", "cc0_1.0"),
            ("Public Domain Dedication", "public_domain"),
            ("Some Future Licence", "unknown"),
            ("", "unknown"),
        ],
    )
    def test_licence_mapping(self, condition, expected):
        assert OAPENSource()._parse_license(condition) == expected

    def test_noncommercial_is_not_mistaken_for_permissive_by(self):
        """NC contains 'nc' inside another word; order must not hide it."""
        got = OAPENSource()._parse_license("Attribution-NonCommercial 4.0 International")
        assert got == "cc_by_nc_4.0"
        assert got in settings.BLOCKED_LICENSES, "an NC book must be refused"

    def test_blocked_licences_cover_the_spelling_adapters_emit(self):
        """Guards the BLOCKED_LICENSES gap that let NC/SA through unblocked."""
        for lic in (
            "cc_by_nc_4.0",
            "cc_by_nc_sa_4.0",
            "cc_by_nd_4.0",
        ):
            assert lic in settings.BLOCKED_LICENSES
        for lic in settings.ALLOWED_LICENSES:
            assert lic not in settings.BLOCKED_LICENSES, (
                f"{lic} is both allowed and blocked"
            )

    def test_is_monograph_helper_is_strict(self):
        assert OAPENSource._is_monograph({"book"}, None) is True
        assert OAPENSource._is_monograph({"chapter"}, None) is False
        assert OAPENSource._is_monograph(set(), None) is False
        assert OAPENSource._is_monograph({"book"}, "parent-id") is False
