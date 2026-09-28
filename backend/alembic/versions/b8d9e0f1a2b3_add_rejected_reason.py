"""Give a rejected book a recorded reason, and stop an unreachable URL being
treated as proof of infringement.

2,209 books were auto-rejected by the licence audit and the reason was written
only to a log line. Nothing in the database said why, so the queue could not be
reviewed: an admin looking at the page saw 2,099 withdrawn titles and no way to
tell a fabricated modern novel from a Standard Ebooks URL that 404'd for a
week.

Two changes:

1. ``books.rejected_reason`` records why a book was withdrawn, so the review
   page can show it and so a later un-rejection carries its own note.

2. An unresolved source URL is no longer sufficient to reject. A 404, a
   timeout and a DNS failure are indistinguishable from a source that moved,
   rate-limited, or is temporarily down -- none of which is evidence that a
   book is in copyright. Those go to PENDING for a human to look at, because
   the cost of wrongly withdrawing a public-domain book (it vanishes from the
   catalogue) is far higher than the cost of leaving it pending. Only a
   positively identified non-public-domain work -- the known-bad list -- is
   hard-rejected.

The audit keeps its teeth for the case it exists to catch: a fabricated source
id for a modern novel still goes to REJECTED, because the list is curated
evidence rather than a failed HTTP request.
"""
from alembic import op
import sqlalchemy as sa

revision = "b8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"

branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "books",
        sa.Column("rejected_reason", sa.Text(), nullable=True),
    )
    # A rejection with no reason is the state that made this queue unreviewable,
    # so index it: the review page filters on it and so does the dashboard.
    op.create_index(
        "ix_books_rejected_reason",
        "books",
        ["rejected_reason"],
        postgresql_where=sa.text("status = 'REJECTED'"),
    )


def downgrade():
    op.drop_index("ix_books_rejected_reason", table_name="books")
    op.drop_column("books", "rejected_reason")
