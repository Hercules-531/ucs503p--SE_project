"""Initialize a local BharatOS database once and run the application on localhost."""

import argparse
import os
import socket
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import URL
from sqlalchemy.orm import Session

from app.ingestion import LocationSnapshotAdapter, SchemeSnapshotAdapter, ingest
from app.pib_environment import PibEnvironmentSnapshotAdapter
from app.pib_programmes import PROGRAMME_SNAPSHOTS
from app.pib_schemes import PibSchemeSnapshotAdapter
from app.pib_transport import PibTransportSnapshotAdapter
from app.pincode_mirror import PincodeMirrorAdapter
from app.storage import Base, create_database

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "bharatos-local.db"
DEFAULT_MIRROR = ROOT / "data" / "raw" / "pincode-github-2024.csv"


def find_available_port(start: int = 8000, end: int = 8100) -> int:
    """Find a currently available localhost port without disturbing its current owner."""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise ValueError(f"No available localhost port between {start} and {end}")


def sqlite_url(path: Path) -> str:
    return URL.create("sqlite", database=path.resolve().as_posix()).render_as_string()


def require_current_schema(path: Path, config: Config) -> None:
    """Inspect an existing database without migrating, seeding or creating tables."""
    try:
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as connection:
            rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
            names = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
    except sqlite3.Error as exc:
        raise ValueError(
            "Existing file is not a migrated BharatOS database; it was not changed."
        ) from exc
    head = ScriptDirectory.from_config(config).get_current_head()
    if rows != [(head,)]:
        raise ValueError(
            "Existing database is not at the current migration; "
            "back it up and migrate it explicitly."
        )
    if not set(Base.metadata.tables).issubset(names):
        raise ValueError("Existing database is missing required tables; it was not changed.")


def initialize_database(path: Path, mirror_path: Path | None = None) -> tuple[bool, list[str]]:
    """Build a new database in a temporary file and publish it only after all imports succeed."""
    path = path.resolve()
    config = Config(str(ROOT / "alembic.ini"))
    if path.exists():
        require_current_schema(path, config)
        return False, []
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".bharatos-init-", suffix=".db", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    previous_url = os.environ.get("DATABASE_URL")
    report = []
    try:
        os.environ["DATABASE_URL"] = sqlite_url(temporary)
        command.upgrade(config, "head")
        engine = create_database(sqlite_url(temporary))
        try:
            with Session(engine) as session:
                adapters = [
                    SchemeSnapshotAdapter(),
                    LocationSnapshotAdapter(),
                    PibSchemeSnapshotAdapter(),
                    PibTransportSnapshotAdapter(),
                    PibEnvironmentSnapshotAdapter(),
                    *PROGRAMME_SNAPSHOTS,
                ]
                if mirror_path is not None:
                    adapters.append(PincodeMirrorAdapter(mirror_path))
                for adapter in adapters:
                    run = ingest(session, adapter)
                    report.append(f"{run.source}: {run.accepted} records")
        finally:
            engine.dispose()
        # Both paths are in the same directory. Hard-link creation fails if the target appeared
        # concurrently, avoiding any overwrite of an existing database.
        os.link(temporary, path)
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        temporary.unlink(missing_ok=True)
    return True, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--skip-mirror", action="store_true")
    args = parser.parse_args()
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    try:
        port = args.port if args.port is not None else find_available_port()
    except ValueError as exc:
        parser.exit(1, f"Local startup failed: {exc}\n")
    mirror = DEFAULT_MIRROR if not args.skip_mirror and DEFAULT_MIRROR.is_file() else None
    try:
        created, report = initialize_database(args.db, mirror)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Local startup failed: {exc}\n")
    for item in report:
        print(item, flush=True)
    if not created:
        print("Using the existing database without reimporting records.", flush=True)
    elif mirror is None:
        print(
            "Historical PIN mirror not imported; the three sample PINs remain available.",
            flush=True,
        )
    print(f"Open http://127.0.0.1:{port}", flush=True)
    os.environ["DATABASE_URL"] = sqlite_url(args.db)
    # This launcher is the self-contained local mode; the Compose stack configures Redis separately.
    os.environ.pop("REDIS_URL", None)
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
