"""Import a locally downloaded official OGD PIN-code CSV into a migrated database."""

import argparse
import os
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.ingestion import ingest
from app.ogd_pincode import OgdPincode2019ArchiveAdapter, OgdPincodeCsvAdapter
from app.storage import create_database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="CSV downloaded from the OGD resource page")
    parser.add_argument(
        "--verified-on", type=date.fromisoformat, help="Date you verified the snapshot, YYYY-MM-DD"
    )
    parser.add_argument(
        "--database-url", default=os.getenv("DATABASE_URL", "sqlite:///bharatos.db")
    )
    parser.add_argument("--sha256", help="Approved lowercase SHA-256 digest of the CSV")
    parser.add_argument("--archive-2019", action="store_true", help="Import the pinned OGD archive")
    args = parser.parse_args()
    if args.archive_2019:
        if args.verified_on is not None or args.sha256 is not None:
            parser.error("The archive uses its own date and checksum")
        adapter = OgdPincode2019ArchiveAdapter(args.csv_file)
    else:
        if args.verified_on is None:
            parser.error("--verified-on is required for a monthly directory snapshot")
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
