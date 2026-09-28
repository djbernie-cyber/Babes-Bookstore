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
