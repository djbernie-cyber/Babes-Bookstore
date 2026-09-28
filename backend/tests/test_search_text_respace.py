"""The backfill must produce byte-identical text to the runtime write path.

9c4d5e6f7a8 concatenated the folded fields with no separator, so all 84,605
backfilled rows read "krakatitcapek, karel" while book_search_text() -- which
the model's before_insert/before_update listeners call on every later write --
produced "krakatit capek, karel". Migrated and subsequently-written rows
disagreed about the shape of the one column that exists to make them agree.

It did not surface as wrong results, which is why it survived two deploys.
Every predicate is a leading-wildcard ILIKE and the tokens are ANDed
independently, so "capek" still matched inside "krakatitcapek". The damage was
boundary-spanning false positives, not dropped hits.

So the assertions here are behavioural on purpose: they execute the migration's
own emitted SQL against a real database and compare the result to
book_search_text(). Source matching is exactly what let the original bug
through twice -- a reader looking at sa.func.concat(*parts, " ") sees five
arguments and a space, with no way to notice the space is the last one instead
of being between them.

SQLite stands in for Postgres. lower(), replace(), nullif() and
CAST(... AS VARCHAR) it already has; concat_ws and translate are registered as
UDFs reproducing their documented Postgres behaviour. Those two are the whole
basis of the correctness argument, so they are spelled out rather than assumed.
"""
import importlib.util
import pathlib
import re
import sqlite3

import pytest

from app.services.search_filters import _FOLD_MAP, book_search_text, tokenize

ROOT = pathlib.Path(__file__).resolve().parents[2]
RESPACE = (ROOT / "backend" / "alembic" / "versions"
           / "ab12cd34ef56_respace_search_text_fields.py")
ORIGINAL = (ROOT / "backend" / "alembic" / "versions"
            / "9c4d5e6f7a8_add_book_search_text.py")

def _sql_tags(values):
    """How the backfill renders tags: the raw json column cast to text.

    book_search_text() instead receives a Python list and joins it with " ".
    The two differ, and deliberately so -- see
    test_tag_rendering_is_never_rewritten and the module docstring. ROWS below
    passes tags in this form so the byte-identity assertions cover the four text
    fields rather than silently papering over the fifth.
    """
    if not values:
        return None
    return "[" + ", ".join(f'"{v}"' for v in values) + "]"


# (title, author, description, tags, isbn) -- tags as the json column renders
# them, which is what the backfill casts. See _sql_tags.
ROWS = [
    # The row that exposed the defect: two populated fields, no separator.
    ("Krakatit", "Čapek, Karel", None, None, None),
    # ss/ae/oe fold to two characters; absent from 9c4d5e6f7a8's 88 pairs.
    ("Straße", "Ærø", "Sœur's tale", _sql_tags(["fiction"]), "978-1"),
    # NULL and empty fields must contribute neither text nor a separator.
    ("Only a title", None, "", None, ""),
    # Every field empty: a separator would leave a stray space.
    ("", "", "", "", ""),
    # A lone field, so no separator should appear at all.
    ("Solo", None, None, None, None),
    # Multi-word and comma-bearing tags, to keep the tag rendering honest.
    ("Tagged", "Someone", None, _sql_tags(["suppressed classics", "history, politics"]), ""),
]


def _pg_concat_ws(sep, *args):
    """Postgres concat_ws: NULL arguments are skipped, not rendered."""
    return sep.join(a for a in args if a is not None)


def _pg_translate(s, chars, targets):
    """Postgres translate: positional, 1:1; unmapped characters pass through."""
    return "".join(targets[chars.index(c)] if c in chars else c for c in s)


@pytest.fixture(scope="module")
def emitted_sql():
    from sqlalchemy.dialects import postgresql

    from alembic import op as real_op

    stmts = []
    original = real_op.execute
    real_op.execute = stmts.append
    try:
        spec = importlib.util.spec_from_file_location("mig_respace", RESPACE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.upgrade()
    finally:
        real_op.execute = original
    assert len(stmts) == 1, f"expected one statement, got {len(stmts)}"
    return str(stmts[0].compile(dialect=postgresql.dialect(),
                                compile_kwargs={"literal_binds": True}))


def backfilled(sql):
    """Run the migration's SQL and return the resulting search_text per row."""
    con = sqlite3.connect(":memory:")
    con.create_function("concat_ws", -1, _pg_concat_ws)
    con.create_function("translate", 3, _pg_translate)
    # SQLite's built-in lower() is ASCII-only and leaves C-cedilla alone, so a
    # "Čapek" row would come back unfolded and the test would blame the
    # migration for a dialect difference. Production runs en_US.utf8, where
    # lower() does fold it, so override with Python's Unicode-aware version to
    # model the database we actually ship against.
    con.create_function("lower", 1, lambda s: s.lower())
    con.execute(
        "create table books (id integer primary key, title text, author text,"
        " description text, tags text, isbn text, search_text text)"
    )
    con.executemany(
        "insert into books (id, title, author, description, tags, isbn)"
        " values (?, ?, ?, ?, ?, ?)",
        [(i, *r) for i, r in enumerate(ROWS)],
    )
    con.execute(sql)
    return [r[0] for r in con.execute("select search_text from books order by id")]


def test_emitted_sql_matches_the_runtime_write_path(emitted_sql):
    """The whole point: the two producers of search_text must agree."""
    got = backfilled(emitted_sql)
    expected = [book_search_text(*r) for r in ROWS]
    assert got == expected, (
        "the backfill and book_search_text() disagree:\n"
        f"  migration: {got[0]!r}\n"
        f"  runtime  : {expected[0]!r}"
    )


def test_tag_rendering_differs_from_python_but_tokenises_identically(emitted_sql):
    """The one place the two still differ, and why that is fine.

    The backfill casts the json column, so tags reach the column as
    ``["suppressed classics", "history, politics"]`` where the Python path
    joins a list with " " and produces "suppressed classics history, politics".

    They are not byte-identical and are not meant to be. tokenize() splits on
    [^\\w], so both forms yield exactly the same tokens, which is the only thing
    book_match_filter() searches over. The SQL is the accurate rendering of
    what is stored; the Python one is an interpretation of it.
    """
    tags = ["suppressed classics", "history, politics"]
    stored = _sql_tags(tags)
    joined = " ".join(tags)
    assert stored != joined, "premise: these two really do differ"
    assert tokenize(stored) == tokenize(joined), \
        "if the two forms tokenise differently the difference stops being cosmetic"
    # And the backfill really does emit the stored rendering, comma and all.
    got = backfilled(emitted_sql)[5]
    assert got == f"tagged someone {stored}"
    assert tokenize(got) == tokenize(
        book_search_text("Tagged", "Someone", None, tags, ""))


def test_tag_rendering_is_never_rewritten():
    """Guards the tempting 'fix' that would corrupt real data.

    Making the SQL emit Python's tag rendering means stripping JSON syntax with
    regexp_replace(text, '[",]', ' ', 'g'). Measured on production: 30,252 tag
    values contain a comma and 11 contain a quote, so that rewrite would split
    "history, politics" into two tags and strip the quote from the rest --
    destroying data to make a cosmetic difference go away. The separator fix is
    the one that was needed; this is not.
    """
    src = RESPACE.read_text(encoding="utf-8")
    assert "regexp_replace" not in src, \
        "regexp surgery over the tags column would rewrite 30,252 comma-bearing tags"
    assert "cast(t.c.tags" in src, \
        "tags should be cast and left alone, not transformed"


def test_no_field_is_joined_without_a_separator(emitted_sql):
    assert backfilled(emitted_sql)[0] == "krakatit capek, karel", \
        "the separator must sit *between* fields, not after the last one"


def test_empty_and_null_fields_contribute_neither_text_nor_separator(emitted_sql):
    got = backfilled(emitted_sql)
    assert got[2] == "only a title", \
        "a NULL or empty field left a double space behind"
    assert got[3] == "", "an all-empty row must not be a single space"
    assert got[4] == "solo", "a lone field must not be padded"


def test_ligatures_fold_to_two_characters(emitted_sql):
    assert backfilled(emitted_sql)[1].startswith("strasse"), \
        "ß must fold to ss, as _FOLD_MAP does, so 'strasse' finds 'Strasse'"


def test_separator_is_a_concat_ws_argument_not_a_trailing_concat_arg():
    """Pins the exact shape of the original defect.

    concat(a, b, c, d, e, ' ') has six arguments and one space -- the space is
    a sixth field rather than a delimiter, which is what produced
    "krakatitcapek, karel". concat_ws takes the separator as its first
    argument, so the broken form reappearing in the source is a hard failure
    rather than something for a reviewer to spot.
    """
    src = RESPACE.read_text(encoding="utf-8")
    assert re.search(r'concat\(\*parts,\s*" "\)', src) is None, \
        "the broken concat(*parts, ' ') form is back"
    assert 'concat_ws(" ", *parts)' in src, \
        "the separator must be concat_ws's first argument"


def test_fold_does_not_nest_deeply_enough_to_overflow_the_stack(emitted_sql):
    """91 chained replace() calls are ~286 frames of SQLAlchemy recursion.

    That overflowed the default limit of 1000 under pytest and would do so
    again wherever the stack is deeper, which is a property of the machine
    running the deploy rather than of the code. translate() collapses each
    group into one call, so the tree depth is bounded by the group count.
    """
    assert emitted_sql.count("translate(") == _group_count(RESPACE)
    assert emitted_sql.count("replace(") == _ligature_count(RESPACE), \
        "only the multi-character folds may remain as replace()"
    assert emitted_sql.count("replace(") + emitted_sql.count("translate(") < 30


def test_folds_exactly_the_letters_in_the_fold_map():
    """Set equality, not a count, so a fold cannot be added or dropped quietly.

    9c4d5e6f7a8 folded 88 of the 91 letter characters; the three it missed are
    the ones that expand to two characters, which is precisely what a count
    check cannot see.
    """
    letters = {c: r for c, r in _FOLD_MAP.items() if c.isalpha()}
    assert _folds_in(RESPACE) == letters, (
        f"missing { {c: letters[c] for c in letters if c not in _folds_in(RESPACE)} }, "
        f"extra { {c: _folds_in(RESPACE)[c] for c in _folds_in(RESPACE) if c not in letters} }"
    )


def _block(path, name):
    """Source of one named tuple literal, so _GROUPS and _LIGATURES stay apart.

    Both are written as ('x', 'y'), lines, so a single regex over the file reads
    the ligature rows ('ss',) as translate groups and silently rewrites a, e, o
    and s to point at the ligature characters.
    """
    src = path.read_text(encoding="utf-8")
    start = src.index(f"{name} = (")
    end = src.index("\n)", start)
    return src[start:end]


def _folds_in(path):
    """Recover the char -> replacement map a migration file folds."""
    folds = {}
    for target, chars in re.findall(r"\('(.)', '(.+?)'\),", _block(path, "_GROUPS")):
        for c in chars:
            folds[c] = target
    for chars, target in re.findall(
            r"\('(.+?)', '(.+?)'\),", _block(path, "_LIGATURES")):
        folds[chars] = target
    return folds


def _group_count(path):
    return len(re.findall(r"\('(.)', '(.+?)'\),", _block(path, "_GROUPS")))


def _ligature_count(path):
    return len(re.findall(r"\('(.+?)', '(.+?)'\),", _block(path, "_LIGATURES")))


def test_original_migration_folds_a_strict_subset_of_the_map():
    """9c4d5e6f7a8 is applied in production and must not be rewritten.

    It may not fold anything the runtime does not, or the two would disagree in
    the other direction. Its three missing ligatures are corrected forward by
    ab12cd34ef56 rather than by editing applied history.
    """
    letters = {c: r for c, r in _FOLD_MAP.items() if c.isalpha()}
    folds = dict(re.findall(r"expr = replace\(expr, '(.+?)', '(.+?)'\)",
                            ORIGINAL.read_text(encoding="utf-8")))
    assert folds, "could not parse the fold chain out of 9c4d5e6f7a8"
    for c, r in folds.items():
        assert c in letters, f"9c4d5e6f7a8 folds {c!r}, which _FOLD_MAP does not"
        assert letters[c] == r, \
            f"9c4d5e6f7a8 folds {c!r}->{r!r}, _FOLD_MAP says {letters[c]!r}"


def test_downgrade_is_a_documented_noop():
    """A data correction that cannot be reversed has to say so, not bare-pass."""
    down = RESPACE.read_text(encoding="utf-8").split("def downgrade", 1)[1]
    assert "pass" in down, "downgrade should do nothing"
    doc = down.split('r"""', 1)[1].split('"""', 1)[0]
    assert "No-op" in doc and "ab12cd34ef56" not in doc, \
        "the no-op downgrade needs a real explanation, not a bare pass"
    assert "alembic downgrade 9c4d5e6f7a8" in doc, \
        "the way to actually drop the column should be documented here"


def test_revisions_chain_in_order():
    """If down_revision is wrong the migration silently never runs."""
    src = RESPACE.read_text(encoding="utf-8")
    assert re.search(r'^revision = "ab12cd34ef56"', src, re.M)
    assert re.search(r'^down_revision = "9c4d5e6f7a8"', src, re.M)
