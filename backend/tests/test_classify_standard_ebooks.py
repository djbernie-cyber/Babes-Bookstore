"""Classification sets ``asset_verified`` from the publisher's own statement.

The bulk-approve button only touches asset-verified rows, so this is the code
that decides what the button is allowed to do. If it is wrong in the permissive
direction, "Approve all pending" puts in-copyright books on sale; if it is
wrong in the strict direction, a public-domain Nancy Drew from 1930 vanishes
from the queue for no reason.

Both directions are tested here, including the phrasing that a first attempt
missed: Neil Simon's Lost in Yonkers (1991) uses the death-date form of the
notice, not the published-date form, and keying on only the latter silently
treated it as cleared.
"""
import pytest

from app.sources.standard_ebooks import parse_standard_ebooks_copyright
from app.scripts.classify_standard_ebooks import SLUG, classify_one


PUBLISHED_DATE_NOTICE = (
    "This book was published in 1966, and will therefore enter the U.S. public "
    "domain in 36 years on January 1, 2062."
)
DEATH_DATE_NOTICE = (
    "This book was published in 1991, and will therefore enter the U.S. public "
    "domain 70 years after the author’s death."
)
PLAIN_PD_PAGE = (
    "The Richest Man in Babylon George S. Clason Standard Ebooks Following "
    "this link will ban your IP for 24 hours Ebooks About Newsletter"
)


class _Response:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class _Book:
    """Duck-typed stand-in: classify_one only touches these four attributes."""

    def __init__(self, source_id):
        self.source_id = source_id
        self.asset_verified = None
        self.license_type = "public_domain"
        self.rejected_reason = None
        self.publication_year = None


def _client(handler):
    class _C:
        async def get(self, url, **kw):
            return handler(url)
    return _C()


@pytest.mark.parametrize("html,expected_year", [
    (PUBLISHED_DATE_NOTICE, 1966),
    (DEATH_DATE_NOTICE, 1991),
])
def test_both_notice_phrasings_are_recognised(html, expected_year):
    verdict = parse_standard_ebooks_copyright(html)
    assert verdict["in_copyright"] is True
    assert verdict["publication_year"] == expected_year


def test_a_page_with_no_notice_is_not_in_copyright():
    """Frankenstein (1818) and Saki carry no notice; that absence is the
    publisher's implicit statement that the edition is already public domain."""
    assert parse_standard_ebooks_copyright(PLAIN_PD_PAGE)["in_copyright"] is False


class TestOutcomePerPage:
    @pytest.mark.asyncio
    async def test_confirmed_public_domain_becomes_asset_verified(self):
        book = _Book("george-s-clason/richest-man-in-babylon")
        client = _client(lambda url: _Response(200, PLAIN_PD_PAGE))
        assert await classify_one(client, book) == "verified"
        assert book.asset_verified is True
        assert book.rejected_reason is None

    @pytest.mark.asyncio
    async def test_in_copyright_is_held_with_its_date_recorded(self):
        """Death of a Salesman. Must not be asset-verified, and must say why."""
        book = _Book("arthur-miller/death-of-a-salesman")
        client = _client(lambda url: _Response(200, PUBLISHED_DATE_NOTICE))
        assert await classify_one(client, book) == "in_copyright"
        assert book.asset_verified is False
        assert book.license_type == "unknown"
        assert "In copyright" in book.rejected_reason
        assert book.publication_year == 1966

    @pytest.mark.asyncio
    async def test_death_date_phrasing_is_not_missed(self):
        """The regression that made this parser dangerous: keyed only on the
        published-date form, this page reads as cleared and Simon goes on sale."""
        book = _Book("neil-simon/lost-in-yonkers")
        client = _client(lambda url: _Response(200, DEATH_DATE_NOTICE))
        assert await classify_one(client, book) == "in_copyright"
        assert book.asset_verified is False
        assert book.publication_year == 1991

    @pytest.mark.asyncio
    async def test_404_is_flagged_not_verified(self):
        book = _Book("nobody/nothing-here")
        client = _client(lambda url: _Response(404))
        assert await classify_one(client, book) == "unreachable"
        assert book.asset_verified is False
        assert book.license_type == "unknown"
        assert "manual review" in book.rejected_reason

    @pytest.mark.asyncio
    async def test_transport_error_is_flagged_not_verified(self):
        book = _Book("some-author/some-book")

        def boom(url):
            raise TimeoutError("timed out")

        assert await classify_one(_client(boom), book) == "unreachable"
        assert book.asset_verified is False
        assert "TimeoutError" in book.rejected_reason

    @pytest.mark.asyncio
    async def test_malformed_slug_is_flagged_rather_than_skipped(self):
        """A co-author slug with an underscore is legitimate. Anything else
        still gets recorded, so it cannot quietly escape the check."""
        assert SLUG.match("william-craft_ellen-craft/a-book")
        book = _Book("not a slug")
        assert await classify_one(_client(lambda url: _Response(200, PLAIN_PD_PAGE)), book) == "malformed"
        assert book.asset_verified is False
