"""Create normalized records and ingestion runs.

Revision ID: 20261105_01
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "20261105_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "normalized_records",
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("identifier", sa.String(128), primary_key=True),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("accepted", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(1000)),
    )


def downgrade() -> None:
    op.drop_table("ingestion_runs")
    op.drop_table("normalized_records")
