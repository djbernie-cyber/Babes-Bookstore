"""Every shelf the site links to must actually resolve to books.

`/categories/<slug>` has two possible backends: a *tag* (the political and
thematic shelves) or the `category` column (the subject shelves). The slug
table in `js/category.js` decides which. A slug that is in neither renders a
category page that silently returns zero books.

That is not hypothetical: `african-literature` was missing from TAG_CATS while
being linked from the nav, the footer, the home page and /authors/african, so
the most prominent Black-African surface on the site resolved to nothing. This
test fails if that ever recurs.
"""
import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
CATEGORY_JS = FRONTEND / "js" / "category.js"


def _js_object(src: str, name: str) -> dict[str, str]:
    """Pull a flat `var NAME = { 'k': 'v', ... }` map out of JS."""
    m = re.search(rf"var\s+{name}\s*=\s*\{{(.*?)\n\}};", src, re.S)
    assert m, f"{name} not found in {CATEGORY_JS.name}"
    return dict(re.findall(r"'([^']+)'\s*:\s*'([^']*)'", m.group(1)))


@pytest.fixture(scope="module")
def category_js() -> str:
    return CATEGORY_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def descs(category_js: str) -> dict[str, str]:
    return _js_object(category_js, "CATEGORY_DESCS")


@pytest.fixture(scope="module")
def tag_cats(category_js: str) -> dict[str, str]:
    return _js_object(category_js, "TAG_CATS")


def _linked_slugs() -> set[str]:
    slugs: set[str] = set()
    for page in FRONTEND.rglob("*.html"):
        for href in re.findall(r'href="/categories/([^"?#]+)"', page.read_text(encoding="utf-8")):
            slugs.add(href.strip("/").lower())
    return slugs


def test_category_slugs_are_linked_anywhere():
    """Sanity check on the guard itself — a silently empty set would pass."""
    assert len(_linked_slugs()) >= 5, "expected the site to link several category shelves"


def test_every_linked_shelf_has_a_backend(tag_cats, descs):
    """The regression: no linked shelf may fall through to a non-existent column."""
    orphans = sorted(s for s in _linked_slugs() if s not in tag_cats and s not in descs)
    assert not orphans, (
        "Shelves linked in the frontend but absent from both TAG_CATS and "
        f"CATEGORY_DESCS in category.js — these will render zero books: {orphans}"
    )


def test_african_literature_shelf_resolves(tag_cats):
    """The shelf the nav, footer, home page and /authors/african all point at."""
    assert tag_cats.get("african-literature") == "African Literature"


def test_tag_backed_shelves_have_descriptions(tag_cats, descs):
    """A tag-backed shelf without a description shows placeholder copy."""
    missing = sorted(s for s in tag_cats if s not in descs)
    assert not missing, f"tag-backed shelves with no description: {missing}"
