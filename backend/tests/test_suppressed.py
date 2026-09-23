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


def test_is_suppressed_book_purges_stale_canon_junk():
    """`is_suppressed_book` keeps legit shelf members but purges the old
    wrong-ID canon books that resolved to unrelated Gutenberg titles."""
    keep = SuppressedClassicsSource.is_suppressed_book
    # Canon book (source=suppressed) keeps its tag.
    assert keep("James Joyce", "suppressed", "4300") is True
    # Banned author's work surfaced by the plain gutenberg source keeps it.
    assert keep("Marx, Karl", "gutenberg", "61") is True
    # Old junk: 3315 resolved to 'Down the Mother Lode' (Hemphill) — purge.
    assert keep("Hemphill, Vivia", "gutenberg", "3315") is False
    assert keep("Patton", "gutenberg", "10989") is False
    # Unknown author, non-suppressed source — never tagged.
    assert keep("Jane Austen", "african_ebooks", "12") is False

def test_gutenberg_cache_cover_derivation():
    """Gutendex omits image/jpeg for many books even though Gutenberg serves a
    cover at the standard cache path — the helper must build that URL, and
    never for non-Gutenberg sources or non-numeric ids (OpenStax numeric ids
    would resolve to unrelated Gutenberg books)."""
    from app.sources.gutenberg import (
        GUTENBERG_ID_SOURCES,
        gutenberg_cache_cover,
    )

    assert gutenberg_cache_cover("military", "132") == (
        "https://www.gutenberg.org/cache/epub/132/pg132.cover.medium.jpg"
    )
    assert gutenberg_cache_cover("suppressed", "46333")
    assert gutenberg_cache_cover("african_ebooks", "12")
    assert gutenberg_cache_cover("gutenberg", "1")

    # Non-Gutenberg sources → None, even with a numeric id.
    assert gutenberg_cache_cover("openstax", "14") is None
    assert gutenberg_cache_cover("wikibooks", "123") is None
    assert gutenberg_cache_cover("internet_archive", "42") is None

    # Non-numeric ids → None.
    assert gutenberg_cache_cover("military", "Nothing-Else-But-A-Number") is None
    assert gutenberg_cache_cover("military", "") is None
    assert gutenberg_cache_cover("military", None) is None

    # Discipline list matches what ingest/backfill rely on.
    assert GUTENBERG_ID_SOURCES == {"gutenberg", "military", "african_ebooks", "suppressed"}
