"""Backfill and uniquely index scheme URL slugs."""

import sqlalchemy as sa
from alembic import op

revision = "20261115_09"
down_revision = "20261113_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    records = sa.table(
        "normalized_records",
        sa.column("kind", sa.String),
        sa.column("identifier", sa.String),
        sa.column("payload", sa.JSON),
    )
    index = sa.table(
        "scheme_search_index",
        sa.column("identifier", sa.String),
        sa.column("slug", sa.Text),
    )
    rows = list(
        connection.execute(
            sa.select(records.c.identifier, records.c.payload).where(records.c.kind == "scheme")
        )
    )
    seen = set()
    for identifier, payload in rows:
        slug = payload.get("slug") if isinstance(payload, dict) else None
        if not isinstance(slug, str) or not slug or slug in seen:
            raise ValueError(
                f"Missing or duplicate scheme slug for {identifier}; repair before upgrade"
            )
        seen.add(slug)
    indexed = set(connection.execute(sa.select(index.c.identifier)).scalars())
    if indexed != {identifier for identifier, _ in rows}:
        raise ValueError("Scheme search index does not match stored records; repair before upgrade")

    op.add_column("scheme_search_index", sa.Column("slug", sa.Text(), nullable=True))
    for identifier, payload in rows:
        connection.execute(
            index.update().where(index.c.identifier == identifier).values(slug=payload["slug"])
        )
    op.create_index("ix_scheme_search_index_slug", "scheme_search_index", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_scheme_search_index_slug", table_name="scheme_search_index")
    op.drop_column("scheme_search_index", "slug")
