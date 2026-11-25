"""Ingest curated snapshots into a database prepared with Alembic."""

import argparse
import os

from sqlalchemy.orm import Session

from app.ingestion import LocationSnapshotAdapter, SchemeSnapshotAdapter, ingest
from app.storage import create_database


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite:///bharatos.db"))
    parser.add_argument("--schemes-only", action="store_true", help="Skip the sample PIN records")
    args = parser.parse_args()
    engine = create_database(args.database_url)
    adapters = [SchemeSnapshotAdapter()]
    if not args.schemes_only:
        adapters.append(LocationSnapshotAdapter())
    try:
        with Session(engine) as session:
            for adapter in adapters:
                run = ingest(session, adapter)
                print(f"{run.source}: {run.status}, {run.accepted} records")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
