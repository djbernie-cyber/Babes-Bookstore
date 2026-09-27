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
"""
from alembic import op
import sqlalchemy as sa

revision = "9c4d5e6f7a8"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("books", sa.Column("search_text", sa.Text(), nullable=True))
    op.create_index("ix_books_search_text", "books", ["search_text"])

    # Generated from search_filters._FOLD_PAIRS -- keep in step with it.
    expr = "lower(coalesce(title,'') || ' ' || coalesce(author,'') || ' ' || coalesce(description,'') || ' ' || coalesce(cast(tags as varchar),'') || ' ' || coalesce(isbn,''))"
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

    op.execute("UPDATE books SET search_text = " + expr)


def downgrade():
    op.drop_index("ix_books_search_text", table_name="books")
    op.drop_column("books", "search_text")
