"""Tokenised, portable search.

Orders of magnitude better than a single sub-string ``ILIKE``: "sol pla"
finds *Sol T. Plaatje*, "jane austen" finds *Pride and Prejudice*, and
partial words match anywhere in title, author, description or tags.

Works identically on SQLite (tests) and Postgres (prod): every token is
required to appear in at least one searchable field (AND), and results are
ranked by exact-title, then title/phrase coverage, then author, then
description/tags.
"""
import re
from sqlalchemy import case, cast, func, or_, and_
from sqlalchemy.sql.expression import ColumnElement
from sqlalchemy.types import String as SQLString

#: Searchable plain-text fields on the book row.
_BOOK_FIELDS = ("title", "author", "description")

_TOKEN_SPLIT = re.compile(r"[^\w]+", re.UNICODE)

#: Characters folded to ASCII in ``search_text``. Kept deliberately explicit
#: rather than leaning on ``unicodedata`` at query time: the column is built
#: once on write and matched with ILIKE, so both sides have to agree, and the
#: SQL backfill in the migration can only use ``replace()``.
#: The pairing is (folded, written) and covers Latin-1 Supplement, Latin
#: Extended-A, the common typographic marks, and the Nordic ligatures.
_FOLD_PAIRS = (
    ("àáâãäåāăą", "a"), ("æ", "ae"),
    ("çćĉċč", "c"),
    ("ďđ", "d"),
    ("èéêëēĕėęě", "e"),
    ("ĝğġģ", "g"),
    ("ĥħ", "h"),
    ("ìíîïĩīĭįı", "i"),
    ("ĵ", "j"),
    ("ķ", "k"),
    ("ĺļľŀł", "l"),
    ("ñńņňŉ", "n"),
    ("òóôõöøōŏő", "o"), ("œ", "oe"),
    ("ŕŗř", "r"),
    ("śŝşš", "s"), ("ß", "ss"),
    ("ţťŧ", "t"),
    ("ùúûüũūŭůűų", "u"),
    ("ŵ", "w"),
    ("ýÿŷ", "y"),
    ("źżž", "z"),
    ("·", " "), ("’", "'"), ("‘", "'"),
    ("“", '"'), ("”", '"'), ("–", "-"), ("—", "-"),
)
_FOLD_MAP = {ch: rep for group, rep in _FOLD_PAIRS for ch in group}

#: Extra keys folded by the Python side that SQL ``replace()`` cannot express
#: because they expand to more than one character.
_FOLD_MAP["ß"] = "ss"


def fold(text: str) -> str:
    """Lower-case and strip diacritics, so a typed ASCII spelling matches.

    Without this, ``dvorak`` returns nothing while ``Dvořák`` returns two
    results, and the same holds for Ngũgĩ, Márquez and Jiménez. Readers do not
    know which spelling a catalogue file happens to use, and the ASCII one is
    the one they type.
    """
    if not text:
        return ""
    return "".join(_FOLD_MAP.get(ch, ch) for ch in str(text).lower())


def book_search_text(title: str, author: str, description: str, tags, isbn: str) -> str:
    """The folded haystack for one book, in the same order the SQL builds it."""
    tag_text = ""
    if tags:
        tag_text = " ".join(str(t) for t in tags) if isinstance(tags, (list, tuple)) else str(tags)
    return fold(" ".join(str(x) for x in (title, author, description, tag_text, isbn) if x))



def _normalise(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "")).strip().lower()


def tokenize(raw: str) -> list:
    """Split a query into searchable tokens (2+ chars), lower-cased."""
    text = _normalise(raw)
    if not text:
        return []
    return [t for t in _TOKEN_SPLIT.split(text) if len(t) >= 2]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def book_match_filter(cls, raw: str):
    """Return ``(where_clause, score_expr)`` for a token query on a Book class.

    ``where_clause``: every token must appear in at least one of
    title/author/description/tags (rendered as JSON text for portability).

    ``score_expr``: a portable integer ranking — exact title match dominates,
    then whole-phrase in the title, then per-token coverage weighted by field.
    Higher is better.
    """
    tokens = tokenize(raw)
    phrase = _normalise(raw)

    if not tokens:
        return None, None

    tag_text = cast(cls.tags, SQLString)
    # AND across tokens; inside a token, title/author/tags are the primary
    # fields (description only contributes to ranking — matching against it
    # made broad phrases like "sol pla" drag in thousands of covers whose
    # blurbs merely mention a word).
    token_filters = []
    score = case((func.lower(cls.title) == phrase, 100_000), else_=0)
    score += case((cls.title.ilike(f"%{_escape_like(phrase)}%"), 50_000), else_=0)
    score += case((cls.author.ilike(f"%{_escape_like(phrase)}%"), 10_000), else_=0)
    if hasattr(cls, "search_text"):
        # A folded phrase that opens the haystack is the accented row the
        # reader was actually looking for, so it has to outrank a literal
        # mid-string hit rather than trail it.
        score += case((cls.search_text.ilike(f"{_escape_like(fold(phrase))}%"), 60_000), else_=0)

    for tok in tokens:
        safe = _escape_like(tok)
        in_title = cls.title.ilike(f"%{safe}%")
        in_author = cls.author.ilike(f"%{safe}%")
        in_desc = cls.description.ilike(f"%{safe}%")
        in_tags = tag_text.ilike(f"%{safe}%")
        # The folded token against the folded haystack. This is what makes an
        # ASCII spelling reach an accented row, and it also covers isbn, which
        # the per-field clauses above never looked at.
        folded = _escape_like(fold(tok))
        in_folded = cls.search_text.ilike(f"%{folded}%") if hasattr(cls, "search_text") else None
        token_filters.append(or_(in_title, in_author, in_tags, in_folded))
        score += case((in_title, 400), else_=0)
        score += case((in_author, 500), else_=0)
        score += case((in_desc, 40), else_=0)
        score += case((in_tags, 20), else_=0)
        # Ranked below the real fields: a folded hit is a weaker signal than a
        # literal one, but it must still be findable.
        if in_folded is not None:
            score += case((in_folded, 120), else_=0)

    return and_(*token_filters) if len(token_filters) > 1 else token_filters[0], score


def author_match_filter(cls, raw: str, column=None) -> ColumnElement:
    """AND-every-token name matcher for author credits (e.g. "sol pla").

    ``column``: the column to match against (default: ``cls.author``; for
    author-list endpoints pass ``cls.name`` if that's the field).
    """
    tokens = tokenize(raw)
    if not tokens:
        return None
    col = column or cls.author
    clauses = [col.ilike(f"%{_escape_like(t)}%") for t in tokens]
    return and_(*clauses) if len(clauses) > 1 else clauses[0]