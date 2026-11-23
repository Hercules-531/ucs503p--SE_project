"""Periodically record HEAD checks of the fixed official source-page list."""

import argparse
import logging
import os
import time

import httpx
from sqlalchemy.orm import Session

from app.source_checks import run_source_checks
from app.storage import create_database

MIN_INTERVAL_SECONDS = 300


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url", default=os.getenv("DATABASE_URL", "sqlite:///bharatos.db")
    )
    parser.add_argument("--interval-seconds", type=int, default=3600)
    parser.add_argument("--once", action="store_true", help="Check once and exit")
    args = parser.parse_args()
    if args.interval_seconds < MIN_INTERVAL_SECONDS:
        parser.error(f"The interval must be at least {MIN_INTERVAL_SECONDS} seconds")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = create_database(args.database_url)
    try:
        with httpx.Client(timeout=5.0, follow_redirects=False) as client:
            while True:
                try:
                    with Session(engine) as session:
                        run_source_checks(session, client)
                    logging.info("Source-page check completed")
                except Exception:
                    # Database exceptions can contain connection details; do not log them.
                    logging.error("Source-page check could not be stored")
                    if args.once:
                        raise SystemExit(1) from None
                if args.once:
                    break
                time.sleep(args.interval_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
