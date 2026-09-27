"""The admin bundle form must stay a book picker, not an ID textbox.

Regression guards for the change that replaced the "Book IDs (comma-separated)"
free-text input with a catalogue search + tick list. The failure mode these
prevent is quiet: a hand-rolled picker that still renders, still submits, and
still passes a class audit while being as unusable as the textbox it replaced.
So these assert the specific affordances, not merely that an id exists.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HTML = ROOT / "frontend" / "admin" / "bundles.html"
JS = ROOT / "frontend" / "js" / "admin-bundles.js"


@pytest.fixture(scope="module")
def html():
    return HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js():
    return JS.read_text(encoding="utf-8")


def test_picker_offers_catalogue_search_not_id_typing(html):
    """An admin must be able to find a book by its name."""
    assert 'id="bundle-book-search"' in html, "no catalogue search box in the bundle form"
    assert 'id="bundle-book-results"' in html, "search has nowhere to render results"
    # The search box must not be a bare number field.
    search_tag = re.search(r'<input[^>]*id="bundle-book-search"[^>]*>', html).group(0)
    assert 'type="search"' in search_tag, "search box should be type=search (clearable, mobile keyboard)"


def test_picked_list_shows_books_and_keeps_its_order(html, js):
    """Order follows pick order, so the UI has to show a position per row."""
    assert 'id="bundle-book-picked"' in html
    assert "<ol" in html, "picked books should be an ordered list"
    # renderPicked must number the rows, and pick() must append.
    assert re.search(r"\$\{i \+ 1\}", js), "picked rows are not numbered, so order is invisible"
    assert re.search(r"order\.push\(b\.id\)", js), "pick() does not append to the order array"


def test_book_ids_field_is_hidden_not_typed_into(html):
    """book_ids stays the submitted field, but must not invite manual IDs."""
    tag = re.search(r'<input[^>]*id="bundle-book-ids"[^>]*>', html).group(0)
    assert 'type="hidden"' in tag, "book-ids must be hidden; the picker writes it"
    assert "comma-separated" not in html.lower(), "the old hand-typed ID prompt is back"


def test_books_are_addable_and_removable(js):
    assert "data-pick" in js and "data-unpick" in js
    assert re.search(r"function pick\(", js) and re.search(r"function unpick\(", js)


def test_existing_bundles_can_have_their_contents_edited(js, html):
    """A picker that can only build new bundles still strands every old one."""
    assert 'data-action="editBundle"' in js, "no per-bundle Edit control"
    assert re.search(r"function editBundle\(", js)
    assert "editingId" in js, "no create-vs-edit state, so edits would create duplicates"
    # Edit must repopulate the picker from the bundle's current books.
    assert re.search(r"\(b\.books \|\| \[\]\)\.forEach", js), "edit does not preload existing books"


def test_submit_uses_patch_when_editing(js, html):
    assert 'data-submit="submitBundle"' in html
    assert re.search(r"function submitBundle\(", js)
    body = re.search(r"const payload = \{(.*?)\n            \};", js, re.S)
    assert body, "no payload built for submission"
    assert "book_ids" in body.group(1), "picked books are not sent to the API"
    assert re.search(r"editing \? '/api/v1/bundles/' \+ editingId : '/api/v1/bundles'", js), \
        "edit must PATCH the existing bundle, not POST a new one"


def test_slug_is_not_sent_on_edit(js):
    """BundleUpdate has no slug field; sending one is a silent no-op that implies it worked."""
    body = re.search(r"const payload = \{(.*?)\n            \};", js, re.S).group(1)
    assert "slug" not in body, "slug is in the shared payload, so edits send it too"
    # It must be attached afterwards, and only when creating.
    assert re.search(r"if \(!editing\) payload\.slug = ", js), \
        "slug must be attached create-only"


def test_escaping_is_applied_to_every_interpolated_book_field(js):
    """Book titles come from scraped catalogues; one unescaped quote breaks the page."""
    found = 0
    for fn in ("renderPicked", "searchBooks"):
        block = re.search(rf"function {fn}\(.*?\n        \}}", js, re.S).group(0)
        # Every `${...}` interpolation in the block that reads a title or author.
        for expr in re.findall(r"\$\{(.*?)\}", block, re.S):
            if not re.search(r"\.title|\.author", expr):
                continue
            found += 1
            assert expr.strip().startswith("escapeHtml("), \
                f"{fn} interpolates a book field unescaped: ${{{expr}}}"
    # Guard against the check silently matching nothing in a future refactor.
    assert found >= 4, f"only found {found} title/author interpolations; the check may be stale"
