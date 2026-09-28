"""Give bundles an owner, so a reader's collection is theirs and not stock.

POST /bundles/custom is how a reader groups books they want. It wrote the
result into the shared `bundles` table, which is the same table the storefront
lists, searches, prices and sells from. So every reader's personal grouping
became a globally visible, standard-priced, purchasable product in the
catalogue, with no record of who made it: unbounded growth of near-identical
listings, each one on sale, and none of them editable or deletable by the
person who made them (PATCH and DELETE both require admin).

`owner_id` separates the two populations. NULL means a product -- curated,
admin-made, or the anonymous one-off that checkout needs. Non-NULL means a
personal collection belonging to that reader: excluded from the public list,
invisible to everyone but the owner, not purchasable, and editable and
deletable only by them.

The price is left as-is rather than zeroed. Nothing reads price_cents for a
personal bundle once checkout rejects it, and a future "what if a reader
wants to price their own collection" should be an explicit decision rather
than a NULL column implying a free product. Setting it to 0 would also make
the row indistinguishable from a genuine free promotion in any report that
sums bundle revenue by price.

Nullable, with no backfill: the existing rows are all products, which is
exactly what NULL means, so no data has to be rewritten and the migration is
instant. The index is on owner_id alone because the access pattern is "list my
collections" (WHERE owner_id = ?), and the public listing needs
"WHERE owner_id IS NULL" which the same index serves.

Downgrade drops the column. Any personal bundles created since are lost, which
is the honest cost of reversing a feature: they are user data, so this
migration is the thing to think twice about before running, not something to
paper over.
"""

from alembic import op
import sqlalchemy as sa

revision = "b7c8d9e0f1a2"
down_revision = "ab12cd34ef56"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("bundles", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.create_index("ix_bundles_owner_id", "bundles", ["owner_id"], unique=False)
    op.create_foreign_key(
        "fk_bundles_owner_id_users",
        "bundles",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint("fk_bundles_owner_id_users", "bundles", type_="foreignkey")
    op.drop_index("ix_bundles_owner_id", table_name="bundles")
    op.drop_column("bundles", "owner_id")
