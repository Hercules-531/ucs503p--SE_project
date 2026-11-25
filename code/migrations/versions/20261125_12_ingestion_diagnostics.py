"""Record safe failure diagnostics without rewriting historic run records."""

import sqlalchemy as sa
from alembic import op

revision = "20261125_12"
down_revision = "20261125_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_runs", sa.Column("failure_code", sa.String(40), nullable=True))
    op.add_column("ingestion_runs", sa.Column("failure_position", sa.Integer(), nullable=True))
    op.add_column(
        "ingestion_runs", sa.Column("failure_position_kind", sa.String(16), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("ingestion_runs", "failure_position_kind")
    op.drop_column("ingestion_runs", "failure_position")
    op.drop_column("ingestion_runs", "failure_code")
