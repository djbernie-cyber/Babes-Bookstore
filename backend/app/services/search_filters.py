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

    for tok in tokens:
        safe = _escape_like(tok)
        in_title = cls.title.ilike(f"%{safe}%")
        in_author = cls.author.ilike(f"%{safe}%")
        in_desc = cls.description.ilike(f"%{safe}%")
        in_tags = tag_text.ilike(f"%{safe}%")
        token_filters.append(or_(in_title, in_author, in_tags))
        score += case((in_title, 400), else_=0)
        score += case((in_author, 200), else_=0)
        score += case((in_desc, 40), else_=0)
        score += case((in_tags, 20), else_=0)

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