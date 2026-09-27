"""The illegal-books results page: pagination must actually paginate.

Two bugs lived here, both user-visible on any page with more than 30 records,
and neither was caught because the file had no coverage:

* "Show more" did nothing. The button is rendered into #more-wrap, a SIBLING of
  #results, but the delegated click listener was bound to #results -- so the
  click never reached showMore(). The page advertised a control that was inert.
* The counter read "Showing 0 of N" on first paint, because unitsShown stayed
  0 after the initial render. The first working "Show more" would then have
  re-inserted units[0:30], duplicating page one.

These assert the two facts that make the bug unrepresentable: that the
container the listener is bound to actually contains the button, and that
unitsShown is derived from the rendered page rather than left at zero.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HTML_PATH = ROOT / "frontend" / "illegal-books.html"
JS_PATH = ROOT / "frontend" / "js" / "illegal-books.js"


@pytest.fixture(scope="module")
def html():
    return HTML_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js():
    return JS_PATH.read_text(encoding="utf-8")


def _element_span(markup, element_id):
    """Return (start, end) offsets of the element with this id."""
    m = re.search(rf'<(\w+)[^>]*\bid="{element_id}"', markup)
    assert m, f"#{element_id} not found in {HTML_PATH.name}"
    start = m.start()
    tag = m.group(1)
    # Walk forward counting nested opens of the same tag to find its close.
    depth, pos = 0, start
    for t in re.finditer(rf'<(/?){tag}\b', markup[start:]):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return start, start + t.end()
        pos = start + t.end()
    raise AssertionError(f"unterminated <{tag}> for #{element_id}")


def test_more_wrap_is_not_inside_results(html):
    """The precondition for the bug. If this ever changes, the test below
    becomes conservative rather than wrong."""
    rs, re_ = _element_span(html, "results")
    ms, me = _element_span(html, "more-wrap")
    assert not (rs < ms and me < re_), \
        "#more-wrap is now inside #results; revisit the listener assertion below"


def _binds_click(js, element_id):
    """True if a click listener is attached to this element id.

    Substring rather than regex: the only thing that matters is that
    `$('more-wrap').addEventListener('click'` appears, and a regex over
    quote-nested JS selectors is far easier to get subtly wrong than a needle.
    Both quote styles are accepted so re-quoting the file does not fail a test.
    """
    for q in ("'", '"'):
        if f"$({q}{element_id}{q}).addEventListener({q}click{q}" in js:
            return True
    return False


def test_show_more_is_bound_to_a_container_that_holds_the_button(js):
    """The click listener must be attached to #more-wrap or an ancestor of it.

    Bound to #results it can never fire, because the button is not a descendant
    of #results.
    """
    assert _binds_click(js, "more-wrap"), \
        "no click listener bound to #more-wrap, so [data-action=more] is inert"

    # The results container must no longer be the only place 'more' is handled.
    # This file caches $('#results') in a local `results`, so match that form.
    results_listener = re.search(
        r"results\.addEventListener\('click'(.*?)\n    \}", js, re.S)
    assert results_listener, "no click listener on #results (flag buttons would break)"
    assert 'data-action="more"' not in results_listener.group(0), \
        "the 'more' action is still only handled on #results, where the button is not"


def test_units_shown_reflects_the_first_rendered_page(js):
    """Otherwise the counter says 0 and the next page duplicates page one."""
    load = re.search(r"function load\(\).*?\n  \}", js, re.S).group(0)
    assert not re.search(r"unitsShown\s*=\s*0\s*;", load), \
        "unitsShown is still reset to 0 after the initial render, so the counter " \
        "reads 0 and the next page duplicates page one"
    assert re.search(r"unitsShown\s*=\s*Math\.min\(PAGE_UNITS,\s*units\.length\)", load), \
        "unitsShown must be set to the number of units actually rendered"


def test_meta_line_counts_from_units_shown(js):
    """The old expression was min(PAGE_UNITS, countItems(0, unitsShown)), which
    is 0 whenever unitsShown is 0."""
    assert "Math.min(PAGE_UNITS, countItems(0, unitsShown))" not in js, \
        "meta still double-counts through a min() that zeroes the first render"
    assert re.search(r"'Showing ' \+ countItems\(0, unitsShown\) \+ ' of '", js), \
        "the first-render meta line should count the units actually shown"


def test_show_more_clamps_to_the_end_of_the_list(js):
    """Without a clamp the final click claims a page past the end."""
    body = re.search(r"function showMore\(\).*?\n  \}", js, re.S).group(0)
    assert re.search(r"next\s*=\s*Math\.min\(unitsShown \+ PAGE_UNITS,\s*units\.length\)", body), \
        "showMore does not clamp `next` to units.length"
    assert "sliceMarkup(unitsShown, next)" in body, "showMore must append from unitsShown onward"


def test_page_size_and_paging_stay_aligned(js):
    """PAGE_UNITS drives both the first page and every later one; a mismatch
    silently drops or repeats records."""
    size = int(re.search(r"var PAGE_UNITS\s*=\s*(\d+)", js).group(1))
    assert size > 0
    first = re.search(r"unitsShown\s*=\s*Math\.min\(PAGE_UNITS,\s*units\.length\)", js)
    assert first, "first page no longer sized by PAGE_UNITS"
    body = re.search(r"function showMore\(\).*?\n  \}", js, re.S).group(0)
    assert "PAGE_UNITS" in body
