"""Import a locally downloaded official OGD PIN-code CSV into a migrated database."""

import argparse
import os
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.ingestion import ingest
from app.ogd_pincode import OgdPincodeCsvAdapter
from app.storage import create_database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="CSV downloaded from the OGD resource page")
    parser.add_argument("--verified-on", type=date.fromisoformat, required=True,
                        help="Date you verified the snapshot, YYYY-MM-DD")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite:///bharatos.db"))
    parser.add_argument("--sha256", help="Approved lowercase SHA-256 digest of the CSV")
    args = parser.parse_args()
    adapter = OgdPincodeCsvAdapter(args.csv_file, args.verified_on, expected_sha256=args.sha256)
    engine = create_database(args.database_url)
    try:
        with Session(engine) as session:
            run = ingest(session, adapter)
            print(f"{run.source}: {run.status}, {run.accepted} PIN codes")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
