"""Regression tests for the African-author matcher and shelf fixes.

Locks in the tightened ``_name_matches`` (initials and lone short names must
never false-positive onto full names) and the author-page normalisation helpers.
"""
from app.sources.african_ebooks import AfricanEbooksSource as S
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