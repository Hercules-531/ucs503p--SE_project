"""Ingest curated snapshots into a database prepared with Alembic."""

import argparse
import os

from sqlalchemy.orm import Session

from app.ingestion import LocationSnapshotAdapter, SchemeSnapshotAdapter, ingest
from app.storage import create_database


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite:///bharatos.db"))
    args = parser.parse_args()
    engine = create_database(args.database_url)
    with Session(engine) as session:
        for adapter in (SchemeSnapshotAdapter(), LocationSnapshotAdapter()):
            run = ingest(session, adapter)
            print(f"{run.source}: {run.status}, {run.accepted} records")


if __name__ == "__main__":
    main()
