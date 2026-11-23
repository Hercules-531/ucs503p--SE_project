"""Register datasets from existing normalized records and ingestion history."""

import sqlalchemy as sa
from alembic import op

revision = "20261123_10"
down_revision = "20261115_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    datasets = op.create_table(
        "datasets",
        sa.Column("source_adapter", sa.String(128), primary_key=True),
        sa.Column("record_kind", sa.String(32)),
        sa.Column("complete_snapshot", sa.Boolean),
        sa.Column("preserve_other_sources", sa.Boolean),
    )
    records = sa.table(
        "normalized_records", sa.column("source_adapter", sa.String), sa.column("kind", sa.String)
    )
    runs = sa.table("ingestion_runs", sa.column("source", sa.String))
    observed = sa.union_all(
        sa.select(records.c.source_adapter.label("adapter"), records.c.kind)
        .where(records.c.source_adapter.is_not(None)),
        sa.select(runs.c.source, sa.cast(sa.null(), sa.String(32))),
    ).subquery()
    # Leave the kind unknown for failed-only runs or conflicting historical evidence.
    kind = sa.case(
        (sa.func.count(sa.distinct(observed.c.kind)) == 1, sa.func.min(observed.c.kind))
    )
    op.get_bind().execute(
        datasets.insert().from_select(
            ["source_adapter", "record_kind"],
            sa.select(observed.c.adapter, kind).group_by(observed.c.adapter),
        )
    )


def downgrade() -> None:
    op.drop_table("datasets")
