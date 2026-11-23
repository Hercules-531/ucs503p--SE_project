"""Periodically check one explicitly approved local OGD PIN-code snapshot."""

import argparse
import logging
import os
import time
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.scheduled_import import run_checked_import
from app.storage import create_database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--verified-on", type=date.fromisoformat, required=True)
    parser.add_argument("--sha256", required=True, help="Approved lowercase SHA-256 digest")
    parser.add_argument(
        "--database-url", default=os.getenv("DATABASE_URL", "sqlite:///bharatos.db")
    )
    parser.add_argument("--interval-seconds", type=int, default=3600)
    parser.add_argument(
        "--once", action="store_true", help="Check once instead of running continuously"
    )
    args = parser.parse_args()
    if args.interval_seconds < 60:
        parser.error("The interval must be at least 60 seconds")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = create_database(args.database_url)
    try:
        while True:
            try:
                with Session(engine) as session:
                    result = run_checked_import(
                        session, args.csv_file, args.verified_on, args.sha256
                    )
                logging.info("PIN snapshot check: %s", result)
            except Exception:
                logging.exception("PIN snapshot check failed")
                if args.once:
                    raise
            if args.once:
                break
            time.sleep(args.interval_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
