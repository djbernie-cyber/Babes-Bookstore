"""Listing cards must not render a download that the API will refuse.

Relaxing the catalogue to show approved-but-unconfirmed titles means every
page that lists books can now display a record the download endpoint rejects.
The failure mode is quiet and specific: the card renders fine, the button
looks normal, and the reader gets a 403 only after clicking.

So the decision lives in exactly one place -- window.downloadCta in app.js --
and this asserts both halves: that the helper exists and branches on the
flag, and that no listing script has grown its own private copy of the link
that would drift from it.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
JS = ROOT / "frontend" / "js"

# Every page that renders a book card. Each must load app.js BEFORE its own
# script, or downloadCta is undefined at call time.
LISTING_SCRIPTS = ["search.js", "category.js", "author-detail.js",
                   "african-literature.js", "banned-works.js"]
LISTING_PAGES = ["books/search.html", "categories/category.html",
                 "categories/revolutionary.html", "authors/detail.html",
                 "categories/african-literature.html", "banned-works.html"]


@pytest.fixture(scope="module")
def app_js():
    return (JS / "app.js").read_text(encoding="utf-8")


def test_helper_is_defined_once_in_app_js(app_js):
    assert "window.downloadCta" in app_js, "no shared decision point for the download CTA"
    assert app_js.count("window.downloadCta =") == 1, \
        "a second definition would silently win depending on load order"


def test_helper_branches_on_the_flag(app_js):
    assert "b.license_verified === false" in app_js, \
        "helper renders a download link for unconfirmed titles"
    pending = app_js.split("b.license_verified === false", 1)[1][:400]
    assert "Licence pending" in pending, "no alternative offer for an unconfirmed title"
    assert "/books/" in pending, "unconfirmed title should lead somewhere, not nowhere"


def test_helper_keeps_the_real_download_for_confirmed_books(app_js):
    tail = app_js.split("b.license_verified === false", 1)[1]
    assert "/api/v1/books/" in tail and "/download" in tail, \
        "confirmed books lost their download link"


def test_helper_serves_both_themes(app_js):
    """The archive listing is dark; a light-pill button is invisible there."""
    assert "bg-stone-100" in app_js, "dark-theme variant removed"
    assert "bg-[#0b0b0c]" in app_js, "light-theme variant removed"


@pytest.mark.parametrize("name", LISTING_SCRIPTS)
def test_no_listing_script_hardcodes_its_own_download_link(name):
    src = (JS / name).read_text(encoding="utf-8")
    # Any remaining hand-built /download link in a listing is a bug, because
    # it cannot know about the flag.
    leaked = re.findall(r"['\"][^'\"]*books/(?:\' \+ b\.id \+ |\$\{b\.id\})/download", src)
    assert not leaked, \
        f"{name} builds its own download link ({leaked}); use downloadCta(b)"


@pytest.mark.parametrize("name", LISTING_SCRIPTS)
def test_listing_scripts_actually_use_the_helper(name):
    src = (JS / name).read_text(encoding="utf-8")
    assert "downloadCta(b" in src, f"{name} lists books but never calls the helper"


@pytest.mark.parametrize("page", LISTING_PAGES)
def test_helper_is_loaded_before_the_page_script(page):
    html = (ROOT / "frontend" / page).read_text(encoding="utf-8")
    scripts = re.findall(r'src="/js/([^"]+)"', html)
    assert "app.js" in scripts, f"{page} does not load app.js, so downloadCta is undefined"
    page_script = [s for s in scripts if s in LISTING_SCRIPTS]
    assert page_script, f"{page} loads no listing script?"
    for s in page_script:
        assert scripts.index("app.js") < scripts.index(s), \
            f"{page} loads {s} before app.js -- helper would be undefined"
