"""Associate stored records with the adapter that last imported them."""

import sqlalchemy as sa
from alembic import op

revision = "20261105_05"
down_revision = "20261105_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("normalized_records", sa.Column("source_adapter", sa.String(128), nullable=True))
    op.create_index(
        "ix_normalized_records_source_adapter", "normalized_records", ["source_adapter"]
    )


def downgrade() -> None:
    op.drop_index("ix_normalized_records_source_adapter", table_name="normalized_records")
    op.drop_column("normalized_records", "source_adapter")
