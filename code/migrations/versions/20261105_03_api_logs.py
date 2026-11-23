"""Record protected API calls without request parameters or credentials."""

import sqlalchemy as sa
from alembic import op

revision = "20261105_03"
down_revision = "20261105_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_request_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("key_id", sa.String(32), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("endpoint", sa.String(200), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("duration_ms", sa.Float, nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_api_request_logs_key_id", "api_request_logs", ["key_id"])


def downgrade() -> None:
    op.drop_index("ix_api_request_logs_key_id", table_name="api_request_logs")
    op.drop_table("api_request_logs")
