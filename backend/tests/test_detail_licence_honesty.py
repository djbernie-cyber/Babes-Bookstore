"""The book detail page must not offer a file it cannot hand over.

The catalogue now lists approved titles whose licence is still being
confirmed, so the detail page can be reached for a book the backend will
refuse to download from. Three ways that could go wrong, and all three would
be a lie told to a reader on the page that matters most:

* the download button stays a live link, and clicking it 403s;
* the licence badge stays emerald, which reads as "checked and clear";
* nothing explains the silence, so the title looks simply broken.

These pin the fix. They are structural because there is no JS runtime in this
environment (no node); the behaviour itself is covered against the API in
test_visibility_split.py.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HTML_PATH = ROOT / "frontend" / "books" / "detail.html"
JS_PATH = ROOT / "frontend" / "js" / "book-detail.js"


@pytest.fixture(scope="module")
def html():
    return HTML_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js():
    return JS_PATH.read_text(encoding="utf-8")


def test_detail_page_has_an_asset_note_slot(html):
    assert 'id="asset-note"' in html, "no element to explain an unavailable file"
    assert 'id="asset-note"' in html and "hidden" in html.split('id="asset-note"')[1][:120]


def test_unverified_branch_exists_and_is_keyed_on_the_flag(js):
    assert "asset_verified === false" in js, \
        "the unconfirmed case is not detected at all"


def _unverified_branch(js):
    """The source between the unconfirmed check and the cleared-books path.

    Delimited on the verified path's own first statement rather than on
    ``return;`` -- the forEach guard is itself a ``return;`` and would
    truncate the branch before the interesting part.
    """
    tail = js.split("asset_verified === false", 1)[1]
    return tail.split("document.getElementById('download').href", 1)[0]


def test_unverified_books_lose_their_download_href(js):
    """The href is the promise. Removing it is what makes the button honest."""
    body = _unverified_branch(js)
    assert "removeAttribute('href')" in body, \
        "download link still points at an endpoint that will 403"
    assert "cursor-not-allowed" in body, "button still advertises itself as clickable"
    assert "aria-disabled" in body, "no accessible disabled state for screen readers"


def test_unverified_books_get_an_explanation(js):
    body = _unverified_branch(js)
    assert "asset-note" in body
    assert "still verifying this edition" in body, \
        "reader is told the file is gone but not why"


def test_cleared_books_still_get_real_links(js):
    """The relaxation must not cost the common case its download."""
    tail = js.split("asset_verified === false", 1)[1]
    assert "/download" in tail, "a verified book no longer gets a download link"
    assert "/read/" in tail, "a verified book no longer gets a reader link"


def test_green_cleared_badge_is_withheld_from_unverified_titles(js):
    """Emerald + licence_type reads as 'checked'. It must not show for unconfirmed."""
    m = re.search(r"let m = \"\"; if \(b\.license_type\)(.*?); if \(b\.category\)", js, re.S)
    assert m, "meta badge line not found"
    line = m.group(1)
    assert "b.asset_verified ? badge" in line, \
        "asset badge ignores the verified/unverified state"
    assert "asset check pending" in line, \
        "no wording distinguishes an edition that has not cleared its check"
