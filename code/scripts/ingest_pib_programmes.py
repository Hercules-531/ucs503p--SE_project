"""Add the health, education, employment and agriculture releases to a migrated database."""

import argparse
import os

from sqlalchemy.orm import Session

from app.ingestion import ingest
from app.pib_programmes import PROGRAMME_SNAPSHOTS
from app.storage import create_database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite:///bharatos.db"))
    args = parser.parse_args()
    engine = create_database(args.database_url)
    try:
        with Session(engine) as session:
            for adapter in PROGRAMME_SNAPSHOTS:
                run = ingest(session, adapter)
                print(f"{run.source}: {run.status}, {run.accepted} records")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
