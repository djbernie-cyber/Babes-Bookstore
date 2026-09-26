"""Match rules for the Standard Ebooks rescue sweep (brand-critical: a wrong
match would serve a different book than the one the catalogue advertises)."""
import sys
from pathlib import Path

from sqlalchemy import select

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


@pytest.mark.asyncio
async def test_run_actually_persists_the_flips(db, session_factory, monkeypatch, capsys):
    """Regression: the probe phase runs outside the session, so the Book
    instances it started from are detached. Mutating those commits nothing
    and the run still prints a success line — the earlier sweep reported
    '1,134 restored' while the catalogue never changed. Assert the rows are
    genuinely APPROVED afterwards."""
    from app.models.book import Book, BookStatus
    from app.scripts import rescue_standardebooks as r

    monkeypatch.setattr(r, "AsyncSessionLocal", session_factory)

    # One title we keep on Standard Ebooks, one we re-source, one we reject.
    se_live = Book(title="The Time Machine", author="H. G. Wells", source="standard_ebooks",
                   source_id="h-g-wells/the-time-machine", status=BookStatus.REJECTED,
                   license_type="public_domain", license_verified=True,
                   source_url="https://standardebooks.org/ebooks/h-g-wells/the-time-machine")
    dead = Book(title="Curtain", author="Agatha Christie", source="standard_ebooks",
                source_id="a-g-christie/curtain", status=BookStatus.REJECTED,
                license_type="public_domain", license_verified=True,
                source_url="https://standardebooks.org/ebooks/a-g-christie/curtain")
    # A Gutenberg edition of the "dead" title already in the catalogue.
    pool = Book(title="Curtain", author="Agatha Christie", source="gutenberg",
                source_id="1234", status=BookStatus.APPROVED, license_type="public_domain",
                license_verified=True,
                source_url="https://www.gutenberg.org/ebooks/1234")
    db.add_all([se_live, dead, pool])
    await db.commit()
    ids = {"se": se_live.id, "dead": dead.id}

    async def fake_alive(url, ext="epub"):
        return "the-time-machine" in url

    monkeypatch.setattr(r, "_url_alive", fake_alive)

    await r.run()

    # populate_existing: the fixture session still holds the pre-commit
    # objects in its identity map, so a plain re-read would return the old
    # status and hide whether the sweep really wrote.
    rows = {bk.id: bk for bk in (await db.execute(
        select(Book).where(Book.id.in_(list(ids.values())))
        .execution_options(populate_existing=True)
    )).scalars().all()}

    # Standard Ebooks title restored against the live direct-download url.
    assert rows[ids["se"]].status == BookStatus.APPROVED
    assert rows[ids["se"]].epub_path.endswith("h-g-wells_the-time-machine.epub?source=download")
    assert rows[ids["se"]].source == "standard_ebooks"          # not re-pointed
    # Unmatched title stays rejected — Christie is not public domain.
    assert rows[ids["dead"]].status == BookStatus.REJECTED
    assert rows[ids["dead"]].epub_path is None

    out = capsys.readouterr().out
    assert "WRITE CHECK FAILED" not in out
    assert "1 rows targeted, 1 now APPROVED" in out


@pytest.mark.asyncio
async def test_run_re_sources_and_keeps_provenance(db, session_factory, monkeypatch):
    """A re-sourced record points at the Gutenberg edition but remembers where
    it came from, and the author must agree or no match is made."""
    from app.models.book import Book, BookStatus
    from app.scripts import rescue_standardebooks as r

    monkeypatch.setattr(r, "AsyncSessionLocal", session_factory)

    target = Book(title="The Moon Pool", author="Agatha Christie", source="standard_ebooks",
                  source_id="a-g-christie/the-moon-pool", status=BookStatus.REJECTED,
                  license_type="public_domain", license_verified=True,
                  source_url="https://standardebooks.org/ebooks/a-g-christie/the-moon-pool")
    wrong = Book(title="The Moon Pool", author="Agatha Christie", source="gutenberg",
                 source_id="99", status=BookStatus.APPROVED, license_type="public_domain",
                 license_verified=True,
                 source_url="https://www.gutenberg.org/ebooks/99")
    db.add_all([target, wrong])
    await db.commit()
    tid = target.id

    async def se_dead(url, ext="epub"):
        # Standard Ebooks has not published it; the Gutenberg edition is fine.
        return "standardebooks.org" not in url

    monkeypatch.setattr(r, "_url_alive", se_dead)
    await r.run()

    row = (await db.execute(
        select(Book).where(Book.id == tid).execution_options(populate_existing=True)
    )).scalars().one()
    assert row.status == BookStatus.APPROVED
    assert row.epub_path == "https://www.gutenberg.org/ebooks/99.epub3.images"
    # Identity stays standard_ebooks: re-pointing source/source_id would hit
    # UNIQUE(source, source_id) when two SE records share a Gutenberg edition.
    assert row.source == "standard_ebooks"
    assert row.source_id == "a-g-christie/the-moon-pool"
    assert row.source_url.endswith("a-g-christie/the-moon-pool")
    assert row.source_metadata["rescued_from"] == "standard_ebooks"
    assert row.source_metadata["served_from"] == "gutenberg"
    assert row.source_metadata["gutenberg_gid"] == "99"
