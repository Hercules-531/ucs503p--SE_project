"""Import the pinned historical third-party PIN mirror into a migrated database."""

import argparse
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.ingestion import ingest
from app.pincode_mirror import PincodeMirrorAdapter
from app.storage import create_database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="Downloaded pinned mirror CSV")
    parser.add_argument(
        "--database-url", default=os.getenv("DATABASE_URL", "sqlite:///bharatos.db")
    )
    args = parser.parse_args()
    engine = create_database(args.database_url)
    try:
        with Session(engine) as session:
            run = ingest(session, PincodeMirrorAdapter(args.csv_file))
            print(f"{run.source}: {run.status}, {run.accepted} PIN codes")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
