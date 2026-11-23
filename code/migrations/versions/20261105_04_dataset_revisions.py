"""Add database-owned cache revisions."""

import sqlalchemy as sa
from alembic import op

revision = "20261105_04"
down_revision = "20261105_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_revisions",
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("revision", sa.Integer, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("dataset_revisions")
