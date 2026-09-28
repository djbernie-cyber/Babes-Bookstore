"""Internet Archive file selection, and the URL it used to build wrong.

`_find_pdf_url` returned
``https://archive.org/download/{f.get("source", "_ia")}/{name}``. Entries in
the ``files`` list of a ``/metadata/`` response carry ``name``, ``format``,
``size`` and sometimes ``original``/``source`` -- and when ``source`` is absent
the fallback is the literal string ``"_ia"``. So every item the adapter
returned had a PDF URL under ``/download/_ia/``, which 404s. Nothing caught it
because the tests only ever checked that *a* URL came back, not that it
addressed the item.

The shapes below are trimmed from real ``/metadata/`` responses: the identifier
is on the top-level response, never on the file entry.
"""
import pytest

pytestmark = pytest.mark.asyncio

IDENT = "anarchistcookbookillustrated00"

# Two editions of the same scan: a page-image original and a small derived EPUB.
# A factory, not a constant: two of these tests strip keys off the list to model
# real responses, and a shared module-level dict let one test's mutation decide
# another's result.
def _files():
    return [
        {"name": "anarchistcookbook_scan.pdf", "format": "Text PDF",
         "size": "48211333", "original": True},
        {"name": "anarchistcookbook_meta.xml", "format": "Metadata"},
        {"name": "anarchistcookbook_jp2.zip", "format": "Single Page Processed JP2 ZIP",
         "size": "90112233", "original": True},
        {"name": "anarchistcookbook_djvu.txt", "format": "DjVuTXT", "size": "812344"},
        {"name": "anarchistcookbook_hocr_searchtext.epub", "format": "EPUB",
         "size": "412883", "source": IDENT},
    ]


def _src():
    from app.sources.internet_archive import InternetArchiveSource
    return InternetArchiveSource()


# --- the URL bug ------------------------------------------------------------

async def test_pdf_url_addresses_the_item_not_a_literal_underscore_ia():
    """The regression this file exists for."""
    url = _src()._find_pdf_url(_files(), IDENT)
    assert url is not None
    assert "_ia" not in url, f"still building the placeholder path: {url}"
    assert f"/download/{IDENT}/" in url
    assert url.endswith(".pdf")
    assert url.startswith("https://archive.org/download/")


async def test_epub_url_addresses_the_item_too():
    url = _src()._find_epub_url(_files(), IDENT)
    assert url == f"https://archive.org/download/{IDENT}/anarchistcookbook_hocr_searchtext.epub"


async def test_underscore_ia_never_appears_even_when_source_is_missing():
    """source is absent from almost every file entry, which is the trap."""
    files = _files()
    for f in files:
        f.pop("source", None)
    url = _src()._find_pdf_url(_files(), IDENT)
    assert url == f"https://archive.org/download/{IDENT}/anarchistcookbook_scan.pdf"


# --- choosing between derivatives -------------------------------------------

async def test_derived_epub_beats_the_page_image_original():
    src = _src()
    assert src._find_epub_url(_files(), IDENT).endswith("hocr_searchtext.epub")
    # For PDF there is only the original, and it must still be found.
    assert src._find_pdf_url(_files(), IDENT).endswith("anarchistcookbook_scan.pdf")


async def test_the_smallest_derived_file_wins():
    """A 41 MB derived EPUB is a worse EPUB than a 400 KB one."""
    files = [
        {"name": "huge.epub", "format": "EPUB", "size": "41000000", "source": IDENT},
        {"name": "small.epub", "format": "EPUB", "size": "400000", "source": IDENT},
    ]
    assert _src()._find_epub_url(files, IDENT).endswith("small.epub")


async def test_non_book_files_are_never_picked():
    """DjVuTXT and JP2 are not EPUBs, and a zip is not a PDF."""
    src = _src()
    epub = src._find_epub_url(_files(), IDENT)
    assert epub is not None
    assert not epub.endswith(".zip")
    # djvu.txt is neither: it is not an epub, and not a pdf either.
    assert src._find_pdf_url(_files(), IDENT).endswith(".pdf")


async def test_uppercase_extensions_still_match():
    files = [{"name": "Book.EPUB", "format": "EPUB", "size": "100", "source": IDENT}]
    assert _src()._find_epub_url(files, IDENT).endswith("Book.EPUB")


async def test_missing_or_junk_size_does_not_raise():
    files = [
        {"name": "a.epub", "format": "EPUB", "source": IDENT, "size": "unknown"},
        {"name": "b.epub", "format": "EPUB", "source": IDENT},
    ]
    assert _src()._find_epub_url(files, IDENT) is not None


async def test_filenames_with_spaces_are_percent_encoded():
    """Archive filenames contain spaces; the stored URL must be a real URL."""
    files = [{"name": "Sumerian Cuneiform English Dictionary 12013CT 28xii.epub",
              "format": "EPUB", "size": "1000", "source": IDENT}]
    url = _src()._find_epub_url(files, IDENT)
    assert " " not in url, f"unencoded space in a URL that gets stored: {url}"
    assert "%20" in url
    assert url.endswith("28xii.epub")


async def test_absent_or_malformed_files_list_is_handled():
    src = _src()
    for bad in (None, "not a list", [], [None, "x", 5]):
        assert src._find_pdf_url(bad, IDENT) is None
        assert src._find_epub_url(bad, IDENT) is None


# --- metadata wiring --------------------------------------------------------

async def test_get_metadata_populates_both_formats(monkeypatch):
    src = _src()
    payload = {
        "metadata": {"title": "The Anarchist Cookbook", "creator": "Powell",
                     "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/",
                     "date": "1971", "mediatype": "texts"},
        "files": _files(),
    }

    class R:
        status_code = 200

        def json(self):
            return payload

    monkeypatch.setattr(src.client, "get", lambda *a, **k: _coro(R()))
    src.rate_limit = 0

    md = await src.get_metadata(IDENT)
    assert md is not None
    assert md.pdf_url and md.epub_url
    assert f"/download/{IDENT}/" in md.pdf_url
    assert f"/download/{IDENT}/" in md.epub_url
    assert md.publication_year == 1971


def _coro(value):
    async def _inner():
        return value
    return _inner()



    @staticmethod
    def _cls():
        from app.sources.internet_archive import InternetArchiveSource
        return InternetArchiveSource

    """`mediatype:texts` is necessary but nowhere near sufficient.

    A PlayStation 2 BIOS dump and a Minecraft skin are both text files on the
    Internet Archive, and both can carry a public-domain licence field. Five
    such uploads reached the review queue labelled `public_domain`: the
    mediatype and licenceurl filters the adapter already had let them through.
    """

    @staticmethod
    def _md(**kw):
        base = {"title": "A Book", "mediatype": "texts"}
        base.update(kw)
        return base

    async def test_bios_dump_is_not_a_book(self):
        md = TestNotABookFilter._md(title="Play Station 2 Bios", collection=["community", "opensource_media"])
        assert self._cls()._is_book_item(md, ["community", "opensource_media"]) is False

    async def test_flash_exploit_is_not_a_book(self):
        for ident in ("script.video.F4mProxy", "plugin.video.f4mTester"):
            md = TestNotABookFilter._md(title=ident, identifier=ident)
            assert self._cls()._is_book_item(md, ["community"]) is False, ident

    async def test_minecraft_skin_is_not_a_book(self):
        md = TestNotABookFilter._md(title="skin-mr-bean", identifier="link-skin-mr-bean")
        assert self._cls()._is_book_item(md, ["opensource", "community"]) is False

    async def test_community_only_upload_is_rejected_even_with_no_bad_title(self):
        """scospoof has a harmless-looking title; the collection is the tell."""
        md = TestNotABookFilter._md(title="scospoof", collection=["opensource_media", "community"])
        assert self._cls()._is_book_item(md, ["opensource_media", "community"]) is False

    async def test_curated_collection_is_kept(self):
        md = TestNotABookFilter._md(title="Frankenstein", collection=["library", "gutenberg"])
        assert self._cls()._is_book_item(md, ["library", "gutenberg"]) is True

    async def test_mixed_collection_with_a_curated_one_is_kept(self):
        """Being in a community collection too is not disqualifying on its own."""
        md = TestNotABookFilter._md(title="Frankenstein", collection=["library", "community"])
        assert self._cls()._is_book_item(md, ["library", "community"]) is True

    async def test_a_real_book_with_no_collection_data_is_not_discarded(self):
        """Absent metadata is not evidence of junk; do not throw the title away."""
        md = TestNotABookFilter._md(title="Middlemarch")
        assert self._cls()._is_book_item(md, []) is True

    async def test_sheet_music_is_not_caught_by_the_title_patterns(self):
        """Cantorion sheet music is a real defect but not one this filter can
        judge from a title, so it must not be silently dropped as junk."""
        md = TestNotABookFilter._md(title="Cantorion sheet music collection 4")
        assert self._cls()._is_book_item(md, []) is True


class TestCommunityUploadIsReviewOnly:
    """The Art of War and a BIOS dump share a collection, so a community-only
    upload is demoted to `unknown` rather than dropped: returning None from
    get_metadata would delist an already-approved title."""

    @staticmethod
    def _cls():
        from app.sources.internet_archive import InternetArchiveSource
        return InternetArchiveSource

    async def test_art_of_war_in_community_collections_is_not_dropped(self):
        """The false positive that forced this design: a real PD book."""
        md = {"title": "The Art Of War By Sun Tzu", "identifier": "TheArtOfWarBySunTzu"}
        assert self._cls()._is_definitely_not_a_book(md) is False
        assert self._cls()._is_community_upload(md, ["opensource", "community"]) is True

    async def test_curated_collection_is_not_a_community_upload(self):
        md = {"title": "Frankenstein"}
        assert self._cls()._is_community_upload(md, ["library", "gutenberg"]) is False

    async def test_absent_collections_is_not_treated_as_an_upload(self):
        assert self._cls()._is_community_upload({"title": "Middlemarch"}, []) is False
class TestNotABookFilter:
    """`mediatype:texts` is necessary but nowhere near sufficient.

    A PlayStation 2 BIOS dump and a Minecraft skin are both text files on the
    Internet Archive, and both can carry a public-domain licence field. Seven
    such uploads reached the review queue labelled `public_domain`: the
    mediatype and licenceurl checks the adapter already had let them through.
    """

    @staticmethod
    def _cls():
        from app.sources.internet_archive import InternetArchiveSource
        return InternetArchiveSource

    @staticmethod
    def _md(**kw):
        base = {"title": "A Book", "mediatype": "texts"}
        base.update(kw)
        return base

    # --- hard drops: identifiers that cannot be a book -------------------

    async def test_bios_dump_is_dropped(self):
        md = self._md(title="Play Station 2 Bios", identifier="PlayStation2Bios")
        assert self._cls()._is_definitely_not_a_book(md) is True

    async def test_flash_exploits_are_dropped(self):
        for ident in ("script.video.F4mProxy", "plugin.video.f4mTester"):
            md = self._md(title=ident, identifier=ident)
            assert self._cls()._is_definitely_not_a_book(md) is True, ident

    async def test_minecraft_skin_is_dropped(self):
        md = self._md(title="skin-mr-bean", identifier="link-skin-mr-bean")
        assert self._cls()._is_definitely_not_a_book(md) is True

    # --- not hard drops: demoted to `unknown` instead --------------------

    async def test_harmless_titled_community_upload_is_flagged_not_dropped(self):
        """scospoof has no tell in its name; the collection is the only signal,
        which is not enough to discard a title, so it must reach review."""
        md = self._md(title="scospoof")
        assert self._cls()._is_definitely_not_a_book(md) is False
        assert self._cls()._is_community_upload(md, ["opensource_media", "community"]) is True

    # --- genuine books must survive --------------------------------------

    async def test_curated_collection_is_left_alone(self):
        md = self._md(title="Frankenstein")
        assert self._cls()._is_definitely_not_a_book(md) is False
        assert self._cls()._is_community_upload(md, ["library", "gutenberg"]) is False

    async def test_mixed_collection_with_a_curated_one_is_left_alone(self):
        md = self._md(title="Frankenstein")
        assert self._cls()._is_community_upload(md, ["library", "community"]) is False

    async def test_missing_collection_data_is_not_read_as_junk(self):
        """Absent metadata is not evidence of anything; do not discard."""
        md = self._md(title="Middlemarch")
        assert self._cls()._is_community_upload(md, []) is False

    async def test_sheet_music_is_not_judged_by_title_alone(self):
        """Cantorion sheet music is a real defect in the approved pile, but not
        one this filter can judge, so it must not be silently dropped."""
        md = self._md(title="Cantorion sheet music collection 4")
        assert self._cls()._is_definitely_not_a_book(md) is False


class TestCommunityUploadIsReviewOnly:
    @staticmethod
    def _cls():
        from app.sources.internet_archive import InternetArchiveSource
        return InternetArchiveSource

    async def test_art_of_war_shares_a_collection_with_the_junk(self):
        """The false positive that forced this design: a real PD book."""
        md = {"title": "The Art Of War By Sun Tzu", "identifier": "TheArtOfWarBySunTzu"}
        assert self._cls()._is_definitely_not_a_book(md) is False
        assert self._cls()._is_community_upload(md, ["opensource", "community"]) is True
