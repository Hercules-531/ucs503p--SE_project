"""Index request timestamps for windowed monitoring queries."""

from alembic import op

revision = "20261125_11"
down_revision = "20261123_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_api_request_logs_requested_at", "api_request_logs", ["requested_at"])


def downgrade() -> None:
    op.drop_index("ix_api_request_logs_requested_at", table_name="api_request_logs")
