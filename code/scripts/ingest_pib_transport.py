"""Import the dated PIB transport snapshot into a migrated database."""

import argparse
import os

from sqlalchemy.orm import Session

from app.ingestion import ingest
from app.pib_transport import PibTransportSnapshotAdapter
from app.storage import create_database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite:///bharatos.db"))
    args = parser.parse_args()
    engine = create_database(args.database_url)
    try:
        with Session(engine) as session:
            run = ingest(session, PibTransportSnapshotAdapter())
            print(f"{run.source}: {run.status}, {run.accepted} records")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
