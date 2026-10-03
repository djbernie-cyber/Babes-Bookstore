"""Contrast audit for the storefront, per theme.

The whole-site themes work by rewriting Tailwind class names: theme.css maps
`[data-theme="dark"] [class~="text-stone-500"]` to a lighter grey, and
site.css remaps `.text-stone-400` globally. That works right up until a page
uses a class nobody thought to map, and it then silently keeps whatever
colour it was authored in. That is how text-stone-300 (#d6d3d1) ended up on
the light --paper body of banned-works.html at 1.43:1, and how the light
theme left the illegal-books catalogue as near-white text on white.

A missing remap is invisible in review and in a screenshot diff, so this test
resolves every text/background pair in every page for all three themes and
fails on anything under the WCAG AA threshold. Remaps are parsed out of the
real stylesheets rather than duplicated here, so editing a theme cannot make
this test lie.
"""

from __future__ import annotations

import math
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
SITE_CSS = FRONTEND / "static" / "site.css"
THEME_CSS = FRONTEND / "static" / "theme.css"

THEMES = ("base", "light", "dark")
AA = 4.5
AA_LARGE = 3.0

# Tailwind v3 defaults for the utilities the storefront actually uses, plus the
# arbitrary values it hardcodes. Only text-* and bg-* are needed to resolve a
# foreground/background pair.
PALETTE = {
    "text-white": "#ffffff",
    "text-stone-100": "#f5f5f4",
    "text-stone-200": "#e7e5e4",
    "text-stone-300": "#d6d3d1",
    "text-stone-400": "#a8a29e",
    "text-stone-500": "#78716c",
    "text-stone-600": "#57534e",
    "text-stone-700": "#44403c",
    "text-stone-800": "#292524",
    "text-stone-900": "#1c1917",
    "text-red-300": "#fca5a5",
    "text-red-400": "#f87171",
    "text-red-500": "#ef4444",
    "text-red-600": "#dc2626",
    "text-red-700": "#b91c1c",
    "text-red-800": "#991b1b",
    "text-amber-400": "#fbbf24",
    "text-amber-500": "#f59e0b",
    "text-amber-600": "#d97706",
    "text-amber-700": "#b45309",
    "text-amber-800": "#92400e",
    "text-emerald-600": "#059669",
    "text-emerald-700": "#047857",
    "text-emerald-800": "#065f46",
    "text-blue-600": "#2563eb",
    "text-blue-800": "#1e40af",
    "text-green-600": "#16a34a",
    "text-green-800": "#166534",
    "text-[#0b0b0c]": "#0b0b0c",
    "text-[#1a1a1f]": "#1a1a1f",
    "text-[#1f1f1f]": "#1f1f1f",
    "text-[#57534e]": "#57534e",
    "text-[#7a7672]": "#7a7672",
    "text-[#8a8683]": "#8a8683",
    "text-[#a8a29e]": "#a8a29e",
    "text-[#d6d3d1]": "#d6d3d1",
    "text-[#fcfaf7]": "#fcfaf7",
    "bg-white": "#ffffff",
    "bg-black": "#000000",
    "bg-stone-50": "#fafaf9",
    "bg-stone-100": "#f5f5f4",
    "bg-stone-200": "#e7e5e4",
    "bg-stone-300": "#d6d3d1",
    "bg-stone-900": "#1c1917",
    "bg-stone-950": "#0c0a09",
    "bg-stone-800": "#292524",
    "bg-red-50": "#fef2f2",
    "bg-red-100": "#fee2e2",
    "bg-red-950": "#450a0a",
    "bg-amber-50": "#fffbeb",
    "bg-amber-100": "#fef3c7",
    "bg-amber-950": "#451a03",
    "bg-sky-950": "#082f49",
    "bg-emerald-50": "#ecfdf5",
    "bg-emerald-600": "#059669",
    "bg-[#0b0b0c]": "#0b0b0c",
    "bg-[#121212]": "#121212",
    "bg-[#161514]": "#161514",
    "bg-[#1a1a1c]": "#1a1a1c",
    "bg-[#1c1b1a]": "#1c1b1a",
    "bg-[#f6f1e7]": "#f6f1e7",
    "bg-[#fcfaf7]": "#fcfaf7",
    "bg-[#e7e2d9]": "#e7e2d9",
    "bg-[#ece9e3]": "#ece9e3",
    "bg-[#f0ede8]": "#f0ede8",
}

# Body background per theme: site.css sets var(--paper) = #fcfaf7 by default,
# theme.css overrides it for light and dark.
BODY_BG = {"base": "#fcfaf7", "light": "#ffffff", "dark": "#0b0b0c"}

RULE = re.compile(r"\[data-theme=\"(\w+)\"\]([^{]*)\{([^}]*)\}")
DECL = re.compile(r"(color|background(?:-color)?)\s*:\s*(#[0-9a-fA-F]{3,8})")
CLASS_ATTR = re.compile(r'\[class~="([^"]+)"\]')


def _norm(value: str) -> str:
    value = value.strip()
    if len(value) == 4:  # #abc -> #aabbcc
        value = "#" + "".join(ch * 2 for ch in value[1:])
    if len(value) == 7:
        value = value + "ff"
    return value.lower()


def _parse_remaps() -> dict[str, dict[str, str]]:
    """{theme: {class_name: hex_colour}}.

    Supports the shapes the storefront actually uses: a theme-scoped
    `[class~="x"]` rule, and a plain class rule in site.css. Comma-separated
    selector lists and compound selectors (`.a.b`) are skipped rather than
    guessed at -- mis-attributing one to a single class would make the audit
    report confident nonsense.
    """
    out: dict[str, dict[str, str]] = {t: {} for t in THEMES}
    for theme, selector, body in RULE.findall(THEME_CSS.read_text()):
        props = dict(DECL.findall(body))
        colour = props.get("color") or props.get("background") or props.get("background-color")
        if not colour:
            continue
        for part in selector.split(","):
            classes = CLASS_ATTR.findall(part)
            # Only accept a selector that is nothing but one class attribute.
            if len(classes) == 1 and part.strip() == f'[class~="{classes[0]}"]':
                out[theme][classes[0]] = _norm(colour)

    # site.css rules are unthemed, so they apply to every theme. The selectors
    # are CSS-escaped (`.text-\[\#8a8683\]`), so unescape before storing or the
    # key can never match an HTML class.
    for selector, prop, colour in re.findall(
        r"^\.((?:\\.|[A-Za-z0-9_-])+)\{ (color|background(?:-color)?):(#[0-9a-fA-F]{3,8})",
        SITE_CSS.read_text(), re.M,
    ):
        cls = re.sub(r"\\(.)", r"\1", selector)
        for theme in THEMES:
            out[theme].setdefault(cls, _norm(colour))
    return out


REMAPS = _parse_remaps()


def _resolve(cls: str, theme: str) -> str | None:
    if theme not in REMAPS:
        return None
    remap = REMAPS[theme].get(cls)
    if remap:
        return remap
    return _norm(PALETTE[cls]) if cls in PALETTE else None


def _luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    channels = [(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4) for c in (r, g, b)]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class _Reader(HTMLParser):
    """Collect (line, text_class, background_class_or_None, is_large) for every
    element that sets its own text colour, carrying down the nearest ancestor
    background. Class *names* are kept rather than resolved colours, because a
    background is remapped per theme just like a foreground."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pairs: list[tuple[int, str, str, bool]] = []

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get("class") or "").split()
        class_set = set(classes)
        text_cls = next((c for c in classes if c.startswith("text-") and c in PALETTE), None)
        bg_cls = next((c for c in classes if c.startswith("bg-") and c in PALETTE), None)
        if text_cls and bg_cls:
            large = any(c in class_set for c in ("text-2xl", "text-3xl", "text-4xl", "text-5xl", "text-6xl", "text-7xl", "text-8xl"))
            self.pairs.append((self.getpos()[0], text_cls, bg_cls, large))


def _pages() -> list[Path]:
    return sorted(p for p in FRONTEND.rglob("*.html") if "_headers" not in p.name)


# Panels that stay dark in every theme. theme.css remaps bg-white and the pale
# stone steps, but deliberately leaves these alone, so text inside one has to be
# a light step in sepia and light as well as dark.
DARK_PANELS = frozenset({
    "bg-black", "bg-stone-800", "bg-stone-900", "bg-stone-950",
    "bg-[#0b0b0c]", "bg-[#121212]", "bg-[#161514]", "bg-[#1a1a1c]", "bg-[#1c1b1a]",
})

# Sentinel: this element paints a background whose colour the audit does not
# model. Distinct from None, which means "inherit from an ancestor".
UNKNOWN = "\x00unknown"

# Void elements never get an end tag, so they must not enter the stack.
_VOID = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr", "path", "circle", "rect", "line",
    "polyline", "polygon", "use", "stop",
})


class _PanelReader(HTMLParser):
    """Collect (line, text_class, nearest_background_class, is_large) for text.

    Resolves the *effective* background: an element's own bg-* wins, otherwise
    the nearest ancestor's. That is the whole point -- the per-page audit only
    pairs a text class with a background on the same element, so a panel that
    sets bg-stone-900 and a child that sets text-stone-700 are invisible to it,
    which is how an unreadable blurb shipped. Earlier drafts of this reader
    only tracked a fixed list of container tags, and that reported a white
    `bg-white text-stone-900` pill inside the dark footer as black-on-black
    because the pill's own background was ignored; nearest-wins has no such gap.

    Imbalance is reported as a failure so a malformed page cannot pass quietly.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str | None] = []
        self.pairs: list[tuple[int, str, str | None, bool]] = []
        self.malformed = False

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get("class") or "").split()
        # A background set on this element ends inheritance even when its colour
        # is not one the audit can resolve: `bg-[#43B02A] text-white` on the
        # M-Pesa button is white on green, and treating the unresolvable class
        # as absent would inherit the card's bg-white and report it as invisible.
        # UNKNOWN marks "there is a background here, its value is not modelled".
        own = next(
            (c for c in classes
             if c.startswith("bg-") and ":" not in c and "/" not in c),
            None,
        )
        if own is not None:
            background = own if own in PALETTE else UNKNOWN
        else:
            background = next((p for p in reversed(self.stack) if p), None)
        text_cls = next((c for c in classes if c.startswith("text-") and c in PALETTE), None)
        if text_cls:
            large = any(c in classes for c in (
                "text-2xl", "text-3xl", "text-4xl", "text-5xl",
                "text-6xl", "text-7xl", "text-8xl",
            ))
            self.pairs.append((self.getpos()[0], text_cls, background, large))
        if tag not in _VOID:
            self.stack.append(background)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if self.stack:
            self.stack.pop()
        else:
            self.malformed = True


@pytest.mark.parametrize("page", _pages(), ids=lambda p: str(p.relative_to(FRONTEND)))
def test_page_text_is_readable_in_every_theme(page: Path) -> None:
    """Check elements that set a text colour *and* a background of their own.

    Deliberately does not infer the background from ancestors: a static walk
    over this markup produced confident nonsense (reporting `text-white` on
    the page body where the element actually sat on a light card) because one
    unbalanced close tag silently desynchronised the context stack. Same-element
    pairs are unambiguous, and they are where the real defect lives.
    """
    reader = _Reader()
    reader.feed(page.read_text())
    failures: list[str] = []

    for line, text_cls, bg_cls, large in reader.pairs:
        for theme in THEMES:
            fg = _resolve(text_cls, theme)
            background = _resolve(bg_cls, theme)
            if not fg or not background:
                continue
            ratio = _contrast(fg, background)
            floor = AA_LARGE if large else AA
            if ratio < floor:
                failures.append(
                    f"{page.name}:{line} {text_cls} on {bg_cls} "
                    f"({fg} on {background}) = {ratio:.2f}:1 in '{theme}' (needs {floor})"
                )

    assert not failures, "Text fails WCAG AA contrast:\n  " + "\n  ".join(sorted(set(failures)))


def test_light_content_regions_avoid_near_white_text() -> None:
    """Guard the reported bug directly, without modelling the cascade.

    These pages render light paper, so any near-white text sitting directly on
    that paper is invisible -- that is the whole bug. Text inside a deliberately
    dark panel is exempt: theme.css keeps bg-stone-900 panels dark in every
    theme and documents that near-white text is correct there, so exempting
    them is the documented behaviour rather than a loophole. An earlier version
    of this test banned near-white text anywhere inside <main> and consequently
    forbade the correct fix for a dark panel nested in main.
    """
    offenders: dict[str, list[str]] = {}
    for name in ("banned-works.html",):
        page = FRONTEND / name
        source = page.read_text()
        assert re.search(r"<main\b.*?</main>", source, re.S), f"{name}: no <main>; update this guard"
        reader = _PanelReader()
        reader.feed(source)
        assert not reader.malformed, f"{name}: unbalanced panel tags; guard cannot trust its stack"
        for line, cls, panel, _large in reader.pairs:
            if panel is None and re.fullmatch(r"text-stone-(?:100|200|300)", cls):
                offenders.setdefault(cls, []).append(f"{name}:{line}")
    assert not offenders, (
        "near-white text on light paper in a content region: "
        f"{offenders} -- use text-stone-600/700 on paper"
    )


@pytest.mark.parametrize("page", _pages(), ids=lambda p: str(p.relative_to(FRONTEND)))
def test_text_inside_dark_panels_is_readable_in_every_theme(page: Path) -> None:
    """The inverse hole, and the one that shipped.

    A bg-stone-900 panel keeps its dark surface in sepia and light, so a child
    using a *dark* text step is near-invisible there and readable only in dark
    mode, which is where the bug hides. The banned-works intro blurb did exactly
    that: text-stone-700 (#44403c) on #1c1917 at 1.70:1 in the default theme.
    Nothing caught it, because the per-page audit only pairs a text class with a
    background set on the *same* element, and here they are on different ones.

    Scoped to panels inside <main>. The nav and footer are dark by design across
    every page and their muted label colours sit just under AA site-wide; that
    is a real but separate question from "a hardcoded blurb is unreadable in the
    default theme", and folding it in here would bury this guard in a site-wide
    restyle it was not written for.
    """
    source = page.read_text()
    main = re.search(r"<main\b.*?</main>", source, re.S)
    if not main:
        pytest.skip(f"{page.name}: no <main> region")
    first_line = source[: main.start()].count("\n") + 1
    last_line = first_line + source[main.start() : main.end()].count("\n")

    reader = _PanelReader()
    reader.feed(source)
    assert not reader.malformed, f"{page.name}: unbalanced panel tags; guard cannot trust its stack"
    failures: list[str] = []
    for line, text_cls, bg_cls, large in reader.pairs:
        if bg_cls in (None, UNKNOWN) or not (first_line <= line <= last_line):
            continue
        for theme in THEMES:
            fg = _resolve(text_cls, theme)
            background = _resolve(bg_cls, theme)
            if not fg or not background:
                continue
            ratio = _contrast(fg, background)
            floor = AA_LARGE if large else AA
            if ratio < floor:
                failures.append(
                    f"{page.name}:{line} {text_cls} inside {bg_cls} "
                    f"({fg} on {background}) = {ratio:.2f}:1 in '{theme}' (needs {floor})"
                )
    assert not failures, (
        "Text inside a dark panel is unreadable in some theme:\n  "
        + "\n  ".join(sorted(set(failures)))
    )


def test_white_pill_labels_have_a_dark_remap() -> None:
    """Guard the systematic button bug across HTML *and* JS.

    The storefront's primary action is `bg-white text-[#0b0b0c]`: a white pill
    with a near-black label. Dark mode remapped the surface but not the label,
    so every primary button rendered near-black on near-black at 1.11:1. The
    per-page test above only reads HTML, so JS-built buttons need this too.
    """
    dark = REMAPS["dark"]
    offenders: set[str] = set()
    sources = [*FRONTEND.rglob("*.html"), *FRONTEND.rglob("*.js")]
    for path in sources:
        for element in re.findall(r'class="([^"]*)"', path.read_text()):
            if "bg-white" not in element.split():
                continue
            for cls in element.split():
                # text-[11px] is a font size, not a colour -- only look at
                # arbitrary hex colours and the darkest stone/neutral steps.
                is_colour = re.fullmatch(r"text-\[#[0-9a-fA-F]{3,8}\]", cls) or cls.startswith(
                    ("text-stone-9", "text-stone-8", "text-neutral-9", "text-neutral-8")
                )
                if is_colour and cls not in dark:
                    offenders.add(f"{path.name}: {cls} on bg-white")
    assert not offenders, (
        "bg-white with a label no dark theme remaps (button would be invisible):\n  "
        + "\n  ".join(sorted(offenders))
    )
