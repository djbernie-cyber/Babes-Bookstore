"""Regression tests for the African-author matcher and shelf fixes.

Locks in the tightened ``_name_matches`` (initials and lone short names must
never false-positive onto full names) and the author-page normalisation helpers.
"""
from app.sources.african_ebooks import (
    AfricanEbooksSource as S,
    SOCIALIST_CANON,
    SOCIALIST_AUTHORS,
    SOCIALIST_THEORY_TAG,
)
from app.api.v1.authors import _display_name, _identifiable_author


def _m(record, candidate):
    return S._name_matches(record, candidate)


def test_real_author_idioms_still_match():
    assert _m("Equiano, Olaudah", "Olaudah Equiano")
    assert _m("Olaudah Equiano", "Equiano, Olaudah")
    assert _m("Haggard, H. Rider (Henry Rider)", "H. Rider Haggard")
    assert _m("Henty, G. A. (George Alfred)", "G. A. Henty")
    assert _m("Wheatley, Phillis", "Phillis Wheatley")
    assert _m("Du Bois, W.E.B.", "W.E.B. Du Bois")


def test_initials_and_short_names_cannot_false_positive():
    assert not _m("E. M.", "George Meredith")
    assert not _m("G. E. M.", "George Meredith")
    assert not _m("B. E.", "Barack Obama")
    assert not _m("Vera", "Yvonne Vera")
    assert not _m("Yvonne", "Yvonne Vera")
    assert _m("Avi", "Avi")  # exact self-identity is fine
    assert not _m("L.", "Langston Hughes")
    assert not _m("W. B.", "Wole Soyinka")


def test_identifiable_author_filter():
    assert not _identifiable_author("E. M.")
    assert not _identifiable_author("L.")
    assert not _identifiable_author("Vera")
    assert not _identifiable_author("")
    assert _identifiable_author("Olaudah Equiano")
    assert _identifiable_author("Sol T. Plaatje")
    assert _identifiable_author("Tsitsi Dangarembga")


def test_display_name_normalisation():
    assert _display_name("Equiano, Olaudah") == "Olaudah Equiano"
    assert _display_name("Plaatje, Sol. T. (Solomon Tshekisho)") == "Sol. T. Plaatje"
    assert _display_name("Olaudah Equiano") == "Olaudah Equiano"


def test_given_name_surname_collisions_do_not_match():
    # "Walter, A." is a surname-only record; "Walter A. Rodney" has Walter as
    # a given name — the nesting tokens must not fuse the two.
    assert not _m("Walter, A.", "Walter A. Rodney")
    assert not _m("Walter A. Rodney", "Walter, A.")


def test_socialist_author_membership():
    assert S._is_socialist_author("Marx, Karl")
    assert S._is_socialist_author("Karl Marx, Friedrich Engels")
    assert S._is_socialist_author("Trotsky, Leon")
    assert S._is_socialist_author("Goldman, Emma")
    assert S._is_socialist_author("Kropotkin, Petr Alekseevich, kniaz")
    assert S._is_socialist_author("Eugene V. Debs")
    assert not S._is_socialist_author("E. M.")
    assert not S._is_socialist_author("Jane Austen")


def test_socialist_tagging_on_metadata():
    from app.sources.base import BookMetadata

    meta = BookMetadata(
        title="Capital",
        author="Karl Marx",
        source="african_ebooks",
        source_id="1",
        license_type="public_domain",
    )
    S()._apply_socialist_tags(meta)
    assert "Socialist Theory" in (meta.tags or [])
    assert "Revolutionary" in (meta.tags or [])


def test_socialist_canon_structure_and_harvest():
    ids = [e["gutenberg_id"] for e in SOCIALIST_CANON]
    assert len(ids) == len(set(ids))
    assert all(e.get("title") and e.get("author") for e in SOCIALIST_CANON)
    # Founding texts are present.
    assert 61 in ids  # Communist Manifesto
    assert 3300 in ids  # Capital Vol. I
    assert "Karl Marx" in SOCIALIST_AUTHORS
    assert "Leon Trotsky" in SOCIALIST_AUTHORS
    assert len(SOCIALIST_AUTHORS) == len(set(SOCIALIST_AUTHORS))
    assert hasattr(S(), "harvest_socialist")
    assert SOCIALIST_THEORY_TAG == "Socialist Theory"