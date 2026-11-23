"""Migrate a consistent SQLite backup to a new file, preserving the original database."""

import argparse
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.script.revision import ResolutionError

from scripts.start_local import ROOT, require_current_schema, sqlite_url


def upgrade_copy(source: Path, destination: Path) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("Source and destination must be different files")
    if not source.is_file():
        raise ValueError("Source database does not exist")
    if destination.exists():
        raise ValueError("Destination already exists; no file was changed")
    if not destination.parent.is_dir():
        raise ValueError("Destination directory does not exist")

    config = Config(str(ROOT / "alembic.ini"))
    descriptor, name = tempfile.mkstemp(
        prefix=".bharatos-upgrade-", suffix=".db", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(name)
    previous_url = os.environ.get("DATABASE_URL")
    try:
        with closing(sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(temporary)) as copy:
                original.backup(copy)
                versions = copy.execute("SELECT version_num FROM alembic_version").fetchall()
                try:
                    revision = (
                        ScriptDirectory.from_config(config).get_revision(versions[0][0])
                        if len(versions) == 1
                        else None
                    )
                except ResolutionError:
                    revision = None
                if revision is None:
                    raise ValueError("Source does not have a recognized migration revision")
                copy.execute("PRAGMA journal_mode=DELETE")
        os.environ["DATABASE_URL"] = sqlite_url(temporary)
        command.upgrade(config, "head")
        require_current_schema(temporary, config)
        with closing(sqlite3.connect(temporary)) as copy:
            if copy.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("Upgraded database failed SQLite integrity_check")
            copy.execute("PRAGMA journal_mode=DELETE")
        # Publishing by hard link is atomic and never replaces a concurrently created destination.
        os.link(temporary, destination)
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        upgrade_copy(args.source, args.destination)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"Upgrade failed; original database retained: {exc}\n")
    print(f"Upgraded copy created: {args.destination}")
    print("The original was not replaced. Start the copy with scripts.start_local --db PATH.")


if __name__ == "__main__":
    main()
