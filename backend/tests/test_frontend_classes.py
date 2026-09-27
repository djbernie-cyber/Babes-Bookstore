"""Every class the storefront uses must actually be defined somewhere.

static/tailwind.css is a *purged* JIT build: it holds only the utilities that
existed when it was generated, and this image has no node, no package.json and
no tailwind.config.js, so it cannot be regenerated. A class outside that set is
not an error -- it silently does nothing. That is how the homepage carousel
shipped with cards that had no width, and how the catalogue filters shipped
with no height: the elements rendered, the layout just quietly collapsed.

This test closes that hole. It resolves each referenced class against
tailwind.css, site.css, theme.css and any inline <style> block, and fails on
anything defined nowhere.

False positives are filtered hard on purpose: only tokens shaped like a CSS
utility (a known Tailwind prefix, optionally behind a variant) are judged, so
JavaScript fragments captured by the quoted-class regexes and semantic hooks
that exist purely as JS handles cannot fail the build.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

STYLESHEETS = [
    FRONTEND / "static" / "tailwind.css",
    FRONTEND / "static" / "site.css",
    FRONTEND / "static" / "theme.css",
]

# A class counts as a real utility only if it starts with one of these, behind
# at most one variant prefix. Everything else is a hook or a JS fragment.

# Tailwind arbitrary values hide arbitrary characters inside brackets, so they
# are stripped before the token is validated: `w-[1.5rem]` -> `w-`.
_BRACKETED = re.compile(r"\[[^\]]*\]")

# A real class token starts with a letter and uses only class-safe characters.
# The positive form matters: a previous version filtered tokens with a negative
# "this looks like JavaScript" regex that included the hyphen, which silently
# discarded *every* hyphenated name -- both component classes (`genre-pill`,
# `bundle-orb`, `google-btn`) and genuine utilities (`text-stone-200`). The
# test passed while seven classes shipped undefined because it had never once
# looked at them.
_CLASS_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_:%/#-]*")

#: Classes that exist only as JavaScript hooks and deliberately have no visual
#: rule. `store.js` hides the Google button with `style.display`, and
#: `my-library.js` paints the selected shelf by toggling Tailwind utilities on
#: it. The `ff-*` / `flag-form` names are DOM handles for the Illegal Books
#: flag form, which is styled entirely with utility classes in its own markup
#: (and repaints its message by swapping `text-amber-700` / `text-emerald-700`
#: rather than a state attribute). In every case the appearance is owned by
#: utility classes on the element, so a rule here would be a second, competing
#: source of truth. Listed explicitly so that adding a *new* unstyled class
#: still fails the test.
_BEHAVIOUR_HOOKS = frozenset({
    "google-btn", "shelf-tab",
    "flag-form", "ff-country", "ff-reason", "ff-status", "ff-msg",
})


def _is_class_token(token: str) -> bool:
    stripped = _BRACKETED.sub("", token)
    # A dot outside brackets is JavaScript member access (`badge.chip`), not a
    # class. Dots inside brackets are part of an arbitrary value.
    if "." in stripped:
        return False
    if not _CLASS_TOKEN.fullmatch(stripped):
        return False
    # Page/element selectors and JS state flags that are not styling hooks.
    return token not in _NOT_CLASSES and token not in _BEHAVIOUR_HOOKS


_NOT_CLASSES = frozenset({
    "curPage", "tp", "totalPages", "badge", "page", "loading", "err",
    "spacer", "pager", "toolbar", "btt", "active", "hidden", "open",
})


def _css_escape(name: str) -> str:
    """Escape a class name the way the JIT compiler writes selectors."""
    return "".join(c if (c.isalnum() or c in "-_") else "\\" + c for c in name)


def _class_tokens(text: str) -> set[str]:
    blobs = (
        re.findall(r'class="([^"]*)"', text)
        + re.findall(r"class=\\?'([^']*)'", text)
        + re.findall(r"classList\.(?:add|toggle|remove|contains)\('([^']*)'", text)
    )
    tokens: set[str] = set()
    for blob in blobs:
        tokens.update(blob.split())
    return tokens


def _sources() -> list[Path]:
    pages = sorted(FRONTEND.rglob("*.html"))
    scripts = sorted((FRONTEND / "js").rglob("*.js"))
    return pages + scripts


def _css_text() -> str:
    parts = [p.read_text() for p in STYLESHEETS if p.exists()]
    # Pages carry their own scoped styles (reader.html styles its whole UI
    # inline), so those definitions count as shipped too. Every page is
    # scanned, not just the one that happened to need it when this was
    # written -- assuming a fixed list is how classes go missing unnoticed.
    for page in FRONTEND.rglob("*.html"):
        parts += re.findall(r"<style[^>]*>(.*?)</style>", page.read_text(), re.S)
    return "\n".join(parts)


CSS = _css_text()




def _is_defined(token: str) -> bool:
    # A definition is the class selector followed by a declaration block or a
    # combinator/selector separator. Allow whitespace first: site.css is
    # hand-formatted as `.foo { ... }` while tailwind.css is minified. A
    # following "." counts too: most component classes are only ever defined as
    # a descendant (`.shelf.is-end-start .shelf-track{...}`), and rejecting that
    # would report them as undefined when they are not.
    return bool(re.search(re.escape("." + _css_escape(token)) + r"\s*(?=[{,:>~.\[])", CSS))


@pytest.mark.parametrize("source", _sources(), ids=lambda p: p.name)
def test_referenced_classes_are_defined(source: Path) -> None:
    """Every class a page or script puts on an element must be styled.

    This deliberately checks *all* class-shaped tokens, not just the ones that
    look like Tailwind utilities. An earlier version filtered to a Tailwind
    prefix allowlist, which meant component classes (`genre-pill`, `eyebrow`,
    `bundle-orb`, `shelf-tab`, `google-btn`) were never checked at all -- seven
    of them shipped undefined and rendered as no-ops while the test passed.
    A class that no stylesheet defines is a silent layout bug, so treat any
    class-shaped token as a real requirement.
    """
    missing = sorted(
        token
        for token in _class_tokens(source.read_text())
        if _is_class_token(token)
        and not _is_defined(token)
    )
    assert not missing, (
        f"{source.name} references {len(missing)} class(es) that no stylesheet "
        f"defines, so they render as no-ops: {missing}\n"
        "static/tailwind.css is a purged JIT build and cannot be regenerated "
        "here; define the class in static/site.css (or a page's own <style>)."
    )


def _rule_body(css: str, selector: str) -> str:
    """Return the declarations of the first `selector { ... }` block, or ""."""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


def test_shelf_card_geometry_is_owned_by_css_not_by_purged_utilities() -> None:
    """The carousel must not depend on Tailwind classes the JIT build dropped.

    static/tailwind.css is a purged build, and it can only contain classes it
    found in markup it scanned. The home feed assembles its cards in JS, so
    w-[158px], sm:w-[184px], flex-shrink-0 and h-44 were all purged away and
    the cards arrived with no width in a display:flex row -- each one stretched
    to fill the track, which is what turned a shelf into a full-width column.
    Assert the geometry is declared in the component layer, and that the JS has
    not gone back to relying on the utilities.
    """
    site = (FRONTEND / "static" / "site.css").read_text()

    # Scope to the rule itself. A whole-file substring search is vacuous here:
    # .coming-soon-badge and .coming-soon-link also declare flex:0, so the
    # geometry can be deleted and the check still passes.
    card = _rule_body(site, ".shelf-card").replace(" ", "").replace("\n", "")
    assert card, ".shelf-card geometry missing from site.css"
    assert "flex:0" in card, ".shelf-card must not grow or shrink in the track"
    assert "width:" in card, ".shelf-card needs an explicit width"

    cover = _rule_body(site, ".shelf-cover").replace(" ", "").replace("\n", "")
    assert "height:" in cover, ".shelf-cover needs an explicit height"

    # The card widens on larger screens, and that override must stay real CSS.
    wide = re.search(r"@media\s*\(min-width:640px\)\s*\{(.*?)\n\}", site, re.S)
    assert wide, "missing the 640px shelf-card breakpoint"
    assert "flex-basis:184px" in wide.group(1).replace(" ", "")

    feed = (FRONTEND / "js" / "home-feed.js").read_text()
    for purged in ("w-[158px]", "sm:w-[184px]", "flex-shrink-0", "h-44"):
        assert purged not in feed, (
            f"home-feed.js uses {purged}, which static/tailwind.css purged. "
            "Size the card with .shelf-card / .shelf-cover instead."
        )
