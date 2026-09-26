"""Unit tests for the metadata cleaners.

These run the pure text functions directly, without a database: the live
catalogue rewrite is irreversible enough that the string handling has to be
pinned down here first.
"""
import importlib.util
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "clean_metadata", os.path.join(BACKEND, "app", "scripts", "clean_metadata.py")
)
clean_metadata = importlib.util.module_from_spec(_spec)
sys.modules["clean_metadata"] = clean_metadata
_spec.loader.exec_module(clean_metadata)

clean_title = clean_metadata.clean_title
clean_author = clean_metadata.clean_author


@pytest.mark.parametrize("raw,expected", [
    # MARC $b marks the remainder of the 245 field; the code must go but the
    # words around it must stay.
    ("A military dictionary : $b or, Explanation of the several systems",
     "A military dictionary: or, Explanation of the several systems"),
    ("LIFE AND TIMES OF FREDERICK DOUGLASS : $B HIS EARLY LIFE AS A SLAVE",
     "LIFE AND TIMES OF FREDERICK DOUGLASS: HIS EARLY LIFE AS A SLAVE"),
    ("Demonologia : $b or, natural knowledge revealed",
     "Demonologia: or, natural knowledge revealed"),
    # adjacent codes
    ("Some work $a $b rest of it", "Some work rest of it"),
])
def test_strips_marc_subfield_codes(raw, expected):
    assert clean_title(raw) == expected


@pytest.mark.parametrize("raw", [
    "The Communist Movement",
    "Kenilworth, vol. 1/4",
    "The Assassination Bureau, Ltd.",
    "",
])
def test_leaves_good_titles_alone(raw):
    assert clean_title(raw) == raw


def test_missing_title_is_left_missing():
    assert clean_title(None) is None


def test_truncates_runaway_titles_on_a_word_boundary():
    raw = "The Complete Distiller: " + "descriptions of the several instruments " * 12
    out = clean_title(raw)
    assert len(out) <= clean_metadata.MAX_TITLE + 1
    assert out.endswith("…")
    # no mid-word cut
    assert not out[:-1].endswith(("instru", "descri", "the s"))


def test_cleans_punctuation_scaffolding():
    assert "  " not in clean_title("A work :  $b with  spaces")
    assert ": :" not in clean_title("A work : $b : more")


@pytest.mark.parametrize("raw,expected", [
    # a reversal pass turned an already-natural name inside out
    ("London, Jack", "Jack London"),
    ("Bourget, Paul", "Paul Bourget"),
    ("Shakespeare, William", "William Shakespeare"),
])
def test_unreverses_mangled_authors(raw, expected):
    assert clean_author(raw) == expected


@pytest.mark.parametrize("raw", [
    # "Surname, Given" is a legitimate catalogue convention, not a defect.
    # These stay put rather than being mass-rewritten.
    "Twain, Mark",
    # surnames that read as given names must not be flipped
    "Psalms, David",
    # second token is not a given name
    "Ebers, Georg",
    "Anonymous",
    "Various",
    "",
    None,
])
def test_leaves_author_forms_alone(raw):
    assert clean_author(raw) is None
