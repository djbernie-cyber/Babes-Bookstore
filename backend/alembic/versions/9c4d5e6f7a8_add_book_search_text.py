r"""Add books.search_text so search folds diacritics.

Typing the ASCII spelling of an accented author returned nothing: "dvorak"
matched zero rows while the caroned spelling matched two, and the same held
for Ngugi, Marquez and Jimenez. Readers do not know which spelling a
catalogue file happens to use, and the ASCII one is the one they type.

ILIKE cannot fold the stored side, and the Postgres unaccent extension is not
available on the SQLite the tests run against, so the folded text is
materialised in a column instead. The backfill chains replace() over the same
88 letters that fold() in app/services/search_filters.py maps, generated from that table so
the two cannot drift. Book's before_insert and before_update events keep the
column current for every later write.

10 punctuation normalisations from that table are deliberately absent here: tokenize()
splits on [^\w], so a curly quote or en dash can never occur inside a search
token, and folding one would need a doubled SQL quote literal for no gain.

Deliberately NOT indexed. Every predicate in book_match_filter() is a
leading-wildcard ILIKE ('%tok%'), which no btree index can serve, and this
database's collation is en_US.utf8 rather than C, so the one prefix-form
match could not use a default text index either -- it would need
text_pattern_ops on a C collation. So a plain index here buys nothing.

It would also cost the deploy: 9 of the 84,605 production rows fold to more
than 2,704 bytes (longest 4,867), and btree refuses index entries above that
limit, so CREATE/UPDATE would abort the migration outright and -- because
the app group boots `alembic upgrade head && exec uvicorn` -- take the
health check down with it. A trigram index is the right structure for this
query and pg_trgm 1.6 is available, but that is a separate change with its
own build cost, not something to bundle into the deploy that unblocks the
column.
"""
from alembic import op
import sqlalchemy as sa

# sa.func.replace is SQLAlchemy 2.x's generic-function handle for the SQL
# REPLACE() built-in. It is not importable by name from
# sqlalchemy.sql.functions in 2.0, which is what made the original version of
# this file die with NameError on the first fold.
replace = sa.func.replace

revision = "9c4d5e6f7a8"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("books", sa.Column("search_text", sa.Text(), nullable=True))

    # Generated from search_filters._FOLD_PAIRS -- keep in step with it.
    #
    # Built as a SQLAlchemy expression tree, not as a string. A raw Python
    # string handed to func.replace() becomes a single *literal bind
    # parameter*, so the whole UPDATE would have collapsed to
    # replace(:param, 'z', 'z') -- folding the text "lower(coalesce(title..."
    # and writing that back into every row. Naming the columns keeps the
    # base a real expression the database evaluates per row.
    t = sa.table(
        "books",
        sa.column("title"),
        sa.column("author"),
        sa.column("description"),
        sa.column("tags"),
        sa.column("isbn"),
        sa.column("search_text"),
    )
    parts = [
        sa.func.coalesce(t.c.title, ""),
        sa.func.coalesce(t.c.author, ""),
        sa.func.coalesce(t.c.description, ""),
        sa.func.coalesce(sa.cast(t.c.tags, sa.String), ""),
        sa.func.coalesce(t.c.isbn, ""),
    ]
    expr = sa.func.lower(sa.func.concat(*parts, " "))
    expr = replace(expr, 'ž', 'z')
    expr = replace(expr, 'ż', 'z')
    expr = replace(expr, 'ź', 'z')
    expr = replace(expr, 'ŷ', 'y')
    expr = replace(expr, 'ŵ', 'w')
    expr = replace(expr, 'ų', 'u')
    expr = replace(expr, 'ű', 'u')
    expr = replace(expr, 'ů', 'u')
    expr = replace(expr, 'ŭ', 'u')
    expr = replace(expr, 'ū', 'u')
    expr = replace(expr, 'ũ', 'u')
    expr = replace(expr, 'ŧ', 't')
    expr = replace(expr, 'ť', 't')
    expr = replace(expr, 'ţ', 't')
    expr = replace(expr, 'š', 's')
    expr = replace(expr, 'ş', 's')
    expr = replace(expr, 'ŝ', 's')
    expr = replace(expr, 'ś', 's')
    expr = replace(expr, 'ř', 'r')
    expr = replace(expr, 'ŗ', 'r')
    expr = replace(expr, 'ŕ', 'r')
    expr = replace(expr, 'ő', 'o')
    expr = replace(expr, 'ŏ', 'o')
    expr = replace(expr, 'ō', 'o')
    expr = replace(expr, 'ŉ', 'n')
    expr = replace(expr, 'ň', 'n')
    expr = replace(expr, 'ņ', 'n')
    expr = replace(expr, 'ń', 'n')
    expr = replace(expr, 'ł', 'l')
    expr = replace(expr, 'ŀ', 'l')
    expr = replace(expr, 'ľ', 'l')
    expr = replace(expr, 'ļ', 'l')
    expr = replace(expr, 'ĺ', 'l')
    expr = replace(expr, 'ķ', 'k')
    expr = replace(expr, 'ĵ', 'j')
    expr = replace(expr, 'ı', 'i')
    expr = replace(expr, 'į', 'i')
    expr = replace(expr, 'ĭ', 'i')
    expr = replace(expr, 'ī', 'i')
    expr = replace(expr, 'ĩ', 'i')
    expr = replace(expr, 'ħ', 'h')
    expr = replace(expr, 'ĥ', 'h')
    expr = replace(expr, 'ģ', 'g')
    expr = replace(expr, 'ġ', 'g')
    expr = replace(expr, 'ğ', 'g')
    expr = replace(expr, 'ĝ', 'g')
    expr = replace(expr, 'ě', 'e')
    expr = replace(expr, 'ę', 'e')
    expr = replace(expr, 'ė', 'e')
    expr = replace(expr, 'ĕ', 'e')
    expr = replace(expr, 'ē', 'e')
    expr = replace(expr, 'đ', 'd')
    expr = replace(expr, 'ď', 'd')
    expr = replace(expr, 'č', 'c')
    expr = replace(expr, 'ċ', 'c')
    expr = replace(expr, 'ĉ', 'c')
    expr = replace(expr, 'ć', 'c')
    expr = replace(expr, 'ą', 'a')
    expr = replace(expr, 'ă', 'a')
    expr = replace(expr, 'ā', 'a')
    expr = replace(expr, 'ÿ', 'y')
    expr = replace(expr, 'ý', 'y')
    expr = replace(expr, 'ü', 'u')
    expr = replace(expr, 'û', 'u')
    expr = replace(expr, 'ú', 'u')
    expr = replace(expr, 'ù', 'u')
    expr = replace(expr, 'ø', 'o')
    expr = replace(expr, 'ö', 'o')
    expr = replace(expr, 'õ', 'o')
    expr = replace(expr, 'ô', 'o')
    expr = replace(expr, 'ó', 'o')
    expr = replace(expr, 'ò', 'o')
    expr = replace(expr, 'ñ', 'n')
    expr = replace(expr, 'ï', 'i')
    expr = replace(expr, 'î', 'i')
    expr = replace(expr, 'í', 'i')
    expr = replace(expr, 'ì', 'i')
    expr = replace(expr, 'ë', 'e')
    expr = replace(expr, 'ê', 'e')
    expr = replace(expr, 'é', 'e')
    expr = replace(expr, 'è', 'e')
    expr = replace(expr, 'ç', 'c')
    expr = replace(expr, 'å', 'a')
    expr = replace(expr, 'ä', 'a')
    expr = replace(expr, 'ã', 'a')
    expr = replace(expr, 'â', 'a')
    expr = replace(expr, 'á', 'a')
    expr = replace(expr, 'à', 'a')

    # A real UPDATE construct, not string concatenation. With expr as a
    # ClauseElement, "UPDATE books SET search_text = " + expr silently
    # becomes SQL '||' concatenation -- the literal on the left, the fold
    # chain on the right -- and op.execute then runs that bare expression
    # instead of an UPDATE. Nothing about it looks wrong in a diff.
    op.execute(t.update().values(search_text=expr))


def downgrade():
    op.drop_column("books", "search_text")
