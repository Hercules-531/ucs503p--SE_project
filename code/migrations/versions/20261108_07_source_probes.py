"""Store the latest administrator-triggered source probes."""

import sqlalchemy as sa
from alembic import op

revision = "20261108_07"
down_revision = "20261105_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_probes",
        sa.Column("source", sa.String(128), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("http_status", sa.Integer),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Float, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("source_probes")
