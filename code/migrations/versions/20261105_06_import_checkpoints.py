"""Track verified snapshot imports for scheduled runs."""

import sqlalchemy as sa
from alembic import op

revision = "20261105_06"
down_revision = "20261105_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_checkpoints",
        sa.Column("source", sa.String(128), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("verified_on", sa.Date, nullable=False),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("ingestion_runs.id"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("import_checkpoints")
