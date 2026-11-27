"""Back up Compose PostgreSQL and restore only into a newly created database."""

import argparse
import errno
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[1]
RESTORE_NAME = re.compile(r"bharatos_restore_[a-z0-9_]{1,40}\Z")
PROJECT_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")


def compose_command(project: str | None, *args: str) -> list[str]:
    if project is not None and not PROJECT_NAME.fullmatch(project):
        raise ValueError("Invalid Compose project name")
    command = ["docker", "compose"]
    if project:
        command.extend(["--project-name", project])
    return [*command, "exec", "-T", "db", *args]


def backup(destination: Path, project: str | None = None, *, database: str = "bharatos") -> None:
    """Create a custom-format dump without overwriting an existing path."""
    if database != "bharatos" and not RESTORE_NAME.fullmatch(database):
        raise ValueError("Backup database must be bharatos or a bharatos_restore_ database")
    if os.path.lexists(destination):
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), destination)
    command = compose_command(
        project,
        "pg_dump",
        "-U",
        "bharatos",
        "-d",
        database,
        "--format=custom",
        "--no-owner",
        "--no-privileges",
    )
    output = NamedTemporaryFile(
        mode="w+b", dir=destination.parent, delete=False, prefix=".bharatos-backup-"
    )
    temporary = Path(output.name)
    try:
        with output:
            subprocess.run(command, cwd=ROOT, stdout=output, check=True)
            output.seek(0)
            if output.read(5) != b"PGDMP":
                raise ValueError("Backup is not a PostgreSQL custom-format dump")
            os.fsync(output.fileno())
        # Publish only after pg_dump succeeds, even if another process claimed the destination.
        os.link(temporary, destination)
    finally:
        temporary.unlink()


def restore_to_new_database(source: Path, target: str, project: str | None = None) -> None:
    """Restore into a new database; never drop or overwrite an existing database."""
    if not RESTORE_NAME.fullmatch(target):
        raise ValueError(
            "Target must start with bharatos_restore_ and use lowercase letters, "
            "digits or underscores"
        )
    validate = compose_command(project, "pg_restore", "--exit-on-error", "--file=/dev/null")
    create = compose_command(project, "createdb", "-U", "bharatos", "--template=template0", target)
    restore = compose_command(
        project,
        "pg_restore",
        "-U",
        "bharatos",
        "--dbname",
        target,
        "--single-transaction",
        "--exit-on-error",
        "--no-owner",
        "--no-privileges",
    )
    # Unbuffered I/O ensures the file descriptor passed to Docker is rewound too.
    with source.open("rb", buffering=0) as backup_file:
        if backup_file.read(5) != b"PGDMP":
            raise ValueError("Input is not a PostgreSQL custom-format dump")
        backup_file.seek(0)
        # Parse the entire archive without a destination connection before creating a database.
        subprocess.run(validate, cwd=ROOT, stdin=backup_file, check=True)
        backup_file.seek(0)
        # createdb fails if the target exists; never proceed to restore in that case.
        subprocess.run(create, cwd=ROOT, check=True)
        subprocess.run(restore, cwd=ROOT, stdin=backup_file, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="Optional Docker Compose project name")
    actions = parser.add_subparsers(dest="action", required=True)
    dump = actions.add_parser("backup")
    dump.add_argument("file", type=Path)
    dump.add_argument(
        "--database", default="bharatos", help="Source database, including a restored database"
    )
    load = actions.add_parser("restore")
    load.add_argument("file", type=Path)
    load.add_argument(
        "--target", required=True, help="New database name beginning bharatos_restore_"
    )
    args = parser.parse_args()
    try:
        if args.action == "backup":
            backup(args.file, args.project, database=args.database)
            print(f"Backup created: {args.file}")
        else:
            restore_to_new_database(args.file, args.target, args.project)
            print(f"Restore completed in new database {args.target}")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Operation failed: {exc}", file=sys.stderr)
        if args.action == "restore":
            print(
                "If database creation succeeded, an incomplete restore database may remain.",
                file=sys.stderr,
            )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
