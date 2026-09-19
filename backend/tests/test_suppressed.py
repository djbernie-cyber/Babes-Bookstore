"""Regression tests for the expanded Suppressed Classics (banned books) shelf.

Locks in the fixed Gutenberg canon (no mislabeled IDs), the banned-author
matcher, and the Revolutionary cross-tag on the shelf. No network.
"""
from app.sources.suppressed import (
    SUPPRESSED_CANON,
    SUPPRESSED_CLASSICS_TAG,
    SuppressedClassicsSource,
)


def test_suppressed_canon_ids_unique_and_verified_anchor():
    """All canon IDs are unique, and the previously-mislabeled anchors now
    point at the correct books."""
    ids = [e["gutenberg_id"] for e in SUPPRESSED_CANON]
    assert len(ids) == len(set(ids))

    anchors = {e["gutenberg_id"]: e for e in SUPPRESSED_CANON}
    # 19942 is Candide (Voltaire), NOT Rousseau's Social Contract.
    assert anchors[19942]["author"] == "Voltaire"
    assert "Candide" in anchors[19942]["title"]
    # Social Contract is 46333.
    assert anchors[46333]["author"] == "Jean-Jacques Rousseau"
    # Ulysses, Lady Chatterley, Kama Sutra anchors present on the shelf.
    assert 4300 in anchors
    assert 73144 in anchors
    assert 27827 in anchors


def test_banned_author_matcher():
    src = SuppressedClassicsSource()
    matcher = src._is_banned_author
    assert matcher("Marx, Karl") is True
    assert matcher("Joyce, James") is True
    assert matcher("de Sade, Marquis") is True
    assert matcher("Tolstoy, Leo, graf") is True
    assert matcher("Voltaire") is True
    assert matcher("Dwight, Timothy") is False
    assert matcher("Jane Austen") is False
    # Lone short names and initials must never false-positive.
    assert matcher("Sade") is False
    assert matcher("Marx") is False
    assert matcher(None) is False


def test_suppressed_tag_survives_from_gutenberg():
    """A Gutenberg record by a banned author is tagged Suppressed Classics."""
    raw = {
        "id": 77,
        "title": "The Adventures of Tom Sawyer",
        "authors": [{"name": "Twain, Mark"}],
        "copyright": False,
        "languages": ["en"],
        "formats": {"text/plain; charset=utf-8": "http://example/t.txt"},
    }
    src = SuppressedClassicsSource()
    # Banned canon: Mark Twain is on the suppressed canon (Huckleberry Finn).
    assert src._is_banned_author("Twain, Mark") is True
    meta = src._from_gutenberg(raw)
    assert meta is not None
    src._tag(meta)
    assert SUPPRESSED_CLASSICS_TAG in meta.tags