"""Rename ``books.license_verified`` to ``books.asset_verified``.

The old name was a claim about copyright status: it said the catalogue had
established that a work was free to sell. It had not. The review queue held
Death of a Salesman (1949), A Streetcar Named Desire (1947), The Skin Of Our
Teeth (1942) and The Time Of Your Life (1939), every one of them labelled
``public_domain``, because the audit treated an HTTP 200 from the source as
proof of public domain. Four of them were approved through the per-book
endpoint and went on sale before being recalled.

The rename is not a cosmetic tidy. It replaces a legal assertion we could not
support with a factual one we can: the publisher's own page has been checked
and the file is present, opens, and matches the edition described. That is
what Standard Ebooks states on each book page -- either that the work has
already entered the US public domain, or, in two phrasings, the year it will.
Classification against that statement is what sets this flag, so a title
cannot reach the catalogue merely because someone clicked Approve.

The protection did not live in the column name and does not move with it: the
approve endpoint still refuses a known in-copyright source_id and any work
published 1940 or later, so a deliberate manual override of a modern title
stays blocked.

PostgreSQL RENAME COLUMN is metadata-only -- no table rewrite, no data
movement -- so this is instant on the live 84k-row table. SQLite has no
equivalent, so the tests use batch_alter_table, which copies the table. The
tests hold a few hundred rows, so that is affordable there and irrelevant in
production.
"""
from alembic import op
import sqlalchemy as sa

revision = "c9e0f1a2b3c4"
down_revision = "b8d9e0f1a2b3"

branch_labels = None
depends_on = None

INDEXES = (
    "ix_books_status_license_created",
    "ix_books_category_status",
    "ix_books_source_status",
)


def upgrade():
    with op.batch_alter_table("books", schema=None) as batch:
        batch.alter_column("license_verified", new_column_name="asset_verified")

    # The three composite indexes name the column explicitly, so renaming it
    # does not update them; Postgres keeps them but the ORM would then be
    # describing indexes that no longer exist. Rebuild rather than leave a
    # silent mismatch between the model and the live schema.
    op.drop_index("ix_books_status_license_created", table_name="books")
    op.drop_index("ix_books_category_status", table_name="books")
    op.drop_index("ix_books_source_status", table_name="books")
    op.create_index(
        "ix_books_status_asset_created", "books", ["status", "asset_verified", "created_at"]
    )
    op.create_index(
        "ix_books_category_status", "books", ["category", "status", "asset_verified"]
    )
    op.create_index(
        "ix_books_source_status", "books", ["source", "status", "asset_verified"]
    )


def downgrade():
    op.drop_index("ix_books_status_asset_created", table_name="books")
    op.drop_index("ix_books_category_status", table_name="books")
    op.drop_index("ix_books_source_status", table_name="books")
    op.create_index(
        "ix_books_status_license_created", "books", ["status", "license_verified", "created_at"]
    )
    op.create_index(
        "ix_books_category_status", "books", ["category", "status", "license_verified"]
    )
    op.create_index(
        "ix_books_source_status", "books", ["source", "status", "license_verified"]
    )
    with op.batch_alter_table("books", schema=None) as batch:
        batch.alter_column("asset_verified", new_column_name="license_verified")
