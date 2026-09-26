"""Match rules for the Standard Ebooks rescue sweep (brand-critical: a wrong
match would serve a different book than the one the catalogue advertises)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.scripts.rescue_standardebooks import (
    _author_ok,
    _norm,
    _pg_file,
    _surname,
    _title_match,
)


class _Book:
    def __init__(self, source_id=None, source_url="", epub_path=None, title=""):
        self.source_id = source_id
        self.source_url = source_url
        self.epub_path = epub_path
        self.title = title


def test_norm_drops_articles_and_punctuation():
    assert _norm("The Time Machine, by H. G. Wells!") == "time machine by h g wells"
    assert _norm(None) == ""


def test_title_match_is_strict_and_prefix_tolerant():
    assert _title_match("time machine", "time machine")
    assert _title_match("time machine", "time machine the world free")  # subtitle
    assert not _title_match("time machine", "time machines")
    assert not _title_match("war", "warden of the north")  # too short to prefix-match
    assert not _title_match("", "anything")


def test_author_ok_requires_family_name_agreement():
    assert _author_ok("H. G. Wells", "H G Wells")
    assert _author_ok("H. G. Wells", "Wells, H. G.")
    assert _author_ok("H. G. Wells", None)          # unknown is permissive
    assert not _author_ok("H. G. Wells", "Oscar Wilde")  # must not graft


def test_surname_ignores_middle_initials():
    assert _surname("George Bernard Shaw") == "shaw"
    assert _surname("H. G. Wells") == "wells"


def test_pg_file_prefers_gutenberg_id_from_url():
    got = _pg_file(_Book(source_id="x", source_url="https://www.gutenberg.org/ebooks/35"))
    assert got == ("35", "https://www.gutenberg.org/ebooks/35.epub3.images")


def test_pg_file_falls_back_to_numeric_source_id():
    assert _pg_file(_Book(source_id="35"))[1].endswith("35.epub3.images")


def test_pg_file_falls_back_to_stored_epub_path():
    assert _pg_file(_Book(epub_path="https://example.org/a.epub")) == ("", "https://example.org/a.epub")


def test_pg_file_none_when_nothing_downloadable():
    assert _pg_file(_Book(source_id="OL1W", source_url="https://openlibrary.org/OL1W")) is None
