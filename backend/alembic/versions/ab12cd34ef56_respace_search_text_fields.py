r"""Rebuild books.search_text with field separators, folding via translate().

9c4d5e6f7a8 concatenated the folded fields with no separator between them:
concat(a, b, c, d, e, ' ') puts the space *after* isbn rather than between the
fields, because the separator was passed as one more positional argument instead
of being interleaved. All 84,605 backfilled rows therefore read
"krakatitcapek, karel" where book_search_text() -- which the model's
before_insert/before_update listeners call on every later write -- produces
"krakatit capek, karel". Migrated books and subsequently-written books
disagreed about the shape of the one column that exists to make them agree.

It never showed up as wrong results, which is why it survived two deploys.
Every predicate in book_match_filter() is a leading-wildcard ILIKE ('%tok%')
and the tokens are ANDed independently, so "capek" still matched inside
"krakatitcapek". The cost was boundary-spanning false positives, not dropped
hits -- the failure mode that hides.

concat_ws with nullif() fixes the separators and reproduces the Python exactly.
book_search_text joins the *truthy* fields with " ", so a missing field must
contribute neither text nor a separator: concat_ws skips NULL arguments, and
nullif(coalesce(x, ''), '') turns NULL and empty into NULL.

Folding with translate() rather than 91 chained replace() calls:

* Nesting. Each replace() wraps the previous one, so 91 letters is 91 levels of
  SQLAlchemy expression tree. That compiles at ~286 frames of recursion, which
  overflowed the default limit of 1000 under pytest's stack and would do so
  again anywhere the boot stack is deeper. translate() maps a whole group in
  one call: 19 groups plus 3 replacements for the ligatures is 4 levels.
* It is also markedly cheaper for the planner, and the SQL is readable enough
  to check by eye, which is the property whose absence let the original bug
  through twice.

translate() is strictly one character to one character, so the three expansions
in _FOLD_MAP -- ae, oe and ss -- stay as replace(). Those are also the only
three letters 9c4d5e6f7a8 missed: its 88 pairs are a correct subset of the 91,
with the expanding ones omitted, which is exactly the kind of gap a count does
not reveal. Without ss, a reader typing "strasse" does not find "Strasse".

The 10 punctuation normalisations in _FOLD_MAP are deliberately still absent:
tokenize() splits on [^\w], so a curly quote or en dash can never occur inside
a search token, and folding one would need a doubled SQL quote literal for no
gain.

Data-only. No schema change, so it takes no DDL lock, and it rewrites the
column 9c4d5e6f7a8 created.
"""

from alembic import op
import sqlalchemy as sa

revision = "ab12cd34ef56"
down_revision = "9c4d5e6f7a8"
branch_labels = None
depends_on = None

# Same field order as book_search_text(), and as 9c4d5e6f7a8 and the model
# listeners.
_FIELDS = ("title", "author", "description", "tags", "isbn")

# (target letter, the characters that fold onto it). Generated from _FOLD_MAP --
# do not hand-edit without re-running test_search_text_respace.py, which fails
# if this drifts from the runtime fold.
_GROUPS = (
    ('a', 'àáâãäå'),
    ('a', 'āăą'),
    ('c', 'çćĉċč'),
    ('d', 'ďđ'),
    ('e', 'èéêë'),
    ('e', 'ēĕėęě'),
    ('g', 'ĝğġģ'),
    ('h', 'ĥħ'),
    ('i', 'ìíîïĩ'),
    ('i', 'īĭįı'),
    ('j', 'ĵ'),
    ('k', 'ķ'),
    ('l', 'ĺļľŀł'),
    ('n', 'ñńņňŉ'),
    ('o', 'òóôõöø'),
    ('o', 'ōŏő'),
    ('r', 'ŕŗř'),
    ('s', 'śŝşš'),
    ('t', 'ţťŧ'),
    ('u', 'ùúûüũ'),
    ('u', 'ūŭůűų'),
    ('w', 'ŵ'),
    ('y', 'ýÿŷ'),
    ('z', 'źżž'),
)

# The characters whose fold is longer than one character. translate() cannot
# express these, so they stay as individual replace() calls -- three levels,
# applied innermost-last.
_LIGATURES = (
    ('æ', 'ae'),
    ('œ', 'oe'),
    ('ß', 'ss'),
)


def _fold(expr):
    for target, chars in _GROUPS:
        expr = sa.func.translate(expr, sa.literal(chars),
                                 sa.literal(target * len(chars)))
    for src, target in _LIGATURES:
        expr = sa.func.replace(expr, src, target)
    return expr


def upgrade():
    t = sa.table("books", *(sa.column(c) for c in _FIELDS), sa.column("search_text"))

    def part(col):
        # NULL or empty -> NULL, so concat_ws drops the field *and* its
        # separator instead of leaving a double space behind.
        return sa.func.nullif(sa.func.coalesce(col, ""), "")

    parts = [
        part(t.c.title),
        part(t.c.author),
        part(t.c.description),
        part(sa.cast(t.c.tags, sa.String)),
        part(t.c.isbn),
    ]
    expr = _fold(sa.func.lower(sa.func.concat_ws(" ", *parts)))
    op.execute(t.update().values(search_text=expr))


def downgrade():
    r"""No-op, deliberately.

    The state this migration replaces is the defect: it is a correction to
    data, and the column it rewrites is the one the previous revision created.
    Rewriting 84,605 rows back into a shape no code path produces any more
    would be a downgrade that breaks the invariant it claims to restore, and it
    would need the 91-call chain reinstated to do it.

    Downgrading the *schema* is a different question and still works: dropping
    search_text is 9c4d5e6f7a8's downgrade, reachable via
    `alembic downgrade 9c4d5e6f7a8`.
    """
    pass
