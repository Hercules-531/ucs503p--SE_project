"""Create and backfill canonical scheme search metadata."""

import sqlalchemy as sa
from alembic import op

revision = "20261113_08"
down_revision = "20261108_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheme_search_index",
        sa.Column("identifier", sa.String(128), primary_key=True),
        sa.Column("category_key", sa.Text, nullable=False),
        sa.Column("searchable", sa.Text, nullable=False),
    )
    op.create_index("ix_scheme_search_index_category_key", "scheme_search_index", ["category_key"])
    op.create_table(
        "scheme_search_values",
        sa.Column(
            "identifier",
            sa.String(128),
            sa.ForeignKey("scheme_search_index.identifier", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("attribute", sa.String(16), primary_key=True),
        sa.Column("value", sa.Text, primary_key=True),
    )
    op.create_index("ix_scheme_search_values_value", "scheme_search_values", ["value"])
    records = sa.table(
        "normalized_records",
        sa.column("kind", sa.String),
        sa.column("identifier", sa.String),
        sa.column("payload", sa.JSON),
    )
    index = sa.table(
        "scheme_search_index",
        sa.column("identifier", sa.String),
        sa.column("category_key", sa.Text),
        sa.column("searchable", sa.Text),
    )
    values = sa.table(
        "scheme_search_values",
        sa.column("identifier", sa.String),
        sa.column("attribute", sa.String),
        sa.column("value", sa.Text),
    )
    indexed, attributes = [], []
    for identifier, payload in op.get_bind().execute(
        sa.select(records.c.identifier, records.c.payload).where(records.c.kind == "scheme")
    ):
        text = " ".join(
            [
                payload["name"],
                payload["short_name"],
                payload["ministry"],
                payload["summary"],
                *payload["tags"],
            ]
        ).casefold()
        indexed.append(
            {
                "identifier": identifier,
                "category_key": payload["category"].casefold(),
                "searchable": text,
            }
        )
        pairs = {("state", item.casefold()) for item in payload.get("states", ["All India"])}
        pairs.update(("audience", item.casefold()) for item in payload["audiences"])
        attributes.extend(
            {"identifier": identifier, "attribute": kind, "value": value} for kind, value in pairs
        )
    if indexed:
        op.bulk_insert(index, indexed)
    if attributes:
        op.bulk_insert(values, attributes)


def downgrade() -> None:
    op.drop_index("ix_scheme_search_values_value", table_name="scheme_search_values")
    op.drop_table("scheme_search_values")
    op.drop_index("ix_scheme_search_index_category_key", table_name="scheme_search_index")
    op.drop_table("scheme_search_index")
