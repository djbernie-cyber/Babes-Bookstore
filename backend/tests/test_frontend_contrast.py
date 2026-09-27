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

    These pages render light paper, so any near-white text inside their content
    region sits on a light surface and is invisible -- that is the whole bug.
    Their footers are deliberately dark and are excluded, because near-white
    there is correct.
    """
    offenders: dict[str, list[str]] = {}
    for name in ("banned-works.html",):
        page = FRONTEND / name
        main = re.search(r"<main\b.*?</main>", page.read_text(), re.S)
        assert main, f"{name}: no <main> region found; update this guard"
        for cls in sorted(set(re.findall(r"text-stone-(?:100|200|300)\b", main.group(0)))):
            offenders.setdefault(cls, []).append(name)
    assert not offenders, (
        "near-white text in a light content region: "
        f"{offenders} -- use text-stone-600/700 on paper"
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
