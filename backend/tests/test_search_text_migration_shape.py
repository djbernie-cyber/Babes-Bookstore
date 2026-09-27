"""search_text must not get a plain btree index.

It had one, and shipping it would have taken production down rather than
just failing quietly.

Two independent reasons, either of which is sufficient:

* It cannot be used. Every predicate in book_match_filter() is a
  leading-wildcard ILIKE ('%tok%'), and btree cannot serve a leading
  wildcard. The single prefix-form match would need text_pattern_ops on a C
  collation, and the database's collation is en_US.utf8. So the index would
  have been pure write overhead.
* It cannot be created. Measured on the live table: 84,605 rows, 96 MB of
  folded text, and 9 rows fold to more than btree's 2,704-byte index row
  limit (longest 4,867). Populating the column under that index aborts with
  "index row size exceeds btree version 4 maximum". Because the app process
  group boots `alembic upgrade head && exec uvicorn`, a failed migration
  means uvicorn never starts, the health check fails, and Fly restarts the
  machine -- the same crash loop that made babes-bookstore-ziaarq look
  broken.

The real structure for this query is a trigram index (pg_trgm 1.6 is
available in production). That is deliberately a separate migration: it has
a real build-time and storage cost and should be measured, not smuggled into
the deploy that unblocks the column.

These assertions are about the migration source because SQLite cannot
reproduce a btree row-size limit, so no unit test on the test database would
ever have caught this.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "backend" / "alembic" / "versions"
             / "9c4d5e6f7a8_add_book_search_text.py")
FILTERS = ROOT / "backend" / "app" / "services" / "search_filters.py"
BTREE_ROW_LIMIT = 2704


@pytest.fixture(scope="module")
def migration():
    return MIGRATION.read_text(encoding="utf-8")


def test_no_btree_index_on_search_text(migration):
    assert not re.search(r"create_index\([^)]*search_text", migration), \
        "a plain btree index on search_text cannot serve ILIKE '%..%' and " \
        "aborts on rows over 2704 bytes"
    assert "ix_books_search_text" not in migration, \
        "index name is back, along with the failure mode"


def test_downgrade_matches_upgrade(migration):
    """An index dropped in downgrade but never created in upgrade is a bug."""
    up = migration.split("def upgrade", 1)[1].split("def downgrade", 1)[0]
    down = migration.split("def downgrade", 1)[1]
    assert "create_index" in up or "create_index" not in down, \
        "downgrade drops an index that upgrade never creates"


def test_column_is_still_added(migration):
    """Guards against 'fixing' the index problem by dropping the feature."""
    up = migration.split("def upgrade", 1)[1].split("def downgrade", 1)[0]
    assert 'add_column("books"' in up and "search_text" in up
    assert 'drop_column("books", "search_text")' in migration


def test_search_text_predicates_are_not_served_by_a_default_btree_index():
    """Correct the reasoning, because it is easy to get backwards.

    The two predicates are NOT both leading-wildcard:

    * ``search_text ILIKE '%folded%'`` -- a leading wildcard, which btree
      cannot serve under any opclass.
    * ``search_text ILIKE 'folded%'``  -- a prefix match, which btree *could*
      serve, but only via ``text_pattern_ops`` on a C collation. Production
      runs ``en_US.utf8``, so the plain ``create_index`` that was here would
      not have been used for this predicate either.

    So the index was at best half-usable, and the 2,704-byte row limit in
    test_no_btree_index_on_search_text is what actually made it fatal.
    Both facts are asserted here so the argument cannot be restated wrongly
    a third time.
    """
    src = FILTERS.read_text(encoding="utf-8")
    preds = re.findall(r"search_text\.ilike\(f\"(.*?)\"\)", src)
    assert len(preds) == 2, f"expected the two known predicates, found {preds}"
    assert any(p.startswith("%") for p in preds), \
        "no leading-wildcard predicate -- the btree argument is now wrong"
    assert any(not p.startswith("%") for p in preds), \
        "no prefix predicate -- check the text_pattern_ops reasoning"
    assert "text_pattern_ops" not in src, \
        "if a prefix predicate is served, it needs an explicit opclass"


def test_fold_count_matches_the_search_filters_table():
    """The backfill and the runtime fold must not drift apart.

    _FOLD_PAIRS groups characters per target ("a", "c", ...), while the
    migration emits one replace() per character, so the comparison is
    character-wise: every character the SQL folds must appear in some group
    whose target is the same letter.
    """
    pairs = re.findall(r"expr = replace\(expr, '(.+?)', '(.+?)'\)",
                       MIGRATION.read_text(encoding="utf-8"))
    assert len(pairs) == 88
    src = FILTERS.read_text(encoding="utf-8")
    groups = re.findall(r'\("([^"]+)",\s*"([^"]+)"\)', src)
    assert groups, "could not parse _FOLD_PAIRS out of search_filters"
    for a, b in pairs:
        assert any(a in chars and target == b for chars, target in groups), \
            f"migration folds {a!r}->{b!r} but search_filters does not"
