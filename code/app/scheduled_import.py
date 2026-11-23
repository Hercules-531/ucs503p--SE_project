"""Run a checked local snapshot import without relabelling old data as newly verified."""

import hashlib
import re
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion import ingest
from app.ogd_pincode import OgdPincodeCsvAdapter, read_snapshot
from app.storage import ImportCheckpoint, IngestionRun, utc_now


class CheckedSnapshotAdapter(OgdPincodeCsvAdapter):
    def __init__(self, path: Path, verified_on: date, data: bytes | None, error: str | None):
        super().__init__(path, verified_on)
        self.data = data
        self.error = error

    def collect(self):
        if self.error is not None:
            raise ValueError(self.error)
        if self.data is None:
            raise ValueError("Snapshot file could not be read")
        yield from self.collect_bytes(self.data)


def run_checked_import(
    session: Session, path: Path, verified_on: date, expected_sha256: str
) -> str:
    """Import once per verified snapshot; a failed retry leaves old data marked for review."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Expected checksum must be a lowercase SHA-256 digest")
    data = None
    error = None
    try:
        data = read_snapshot(path)
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ValueError("Snapshot checksum does not match the approved digest")
    except OSError:
        error = "Snapshot file could not be read"
    except ValueError as exc:
        error = str(exc)

    adapter = CheckedSnapshotAdapter(path, verified_on, data, error)
    checkpoint = session.get(ImportCheckpoint, adapter.name)
    latest = session.scalar(
        select(IngestionRun)
        .where(IngestionRun.source == adapter.name)
        .order_by(IngestionRun.id.desc())
        .limit(1)
    )
    if (
        error is None
        and checkpoint is not None
        and latest is not None
        and latest.status == "success"
        and latest.id == checkpoint.run_id
        and checkpoint.sha256 == expected_sha256
        and checkpoint.verified_on == verified_on
    ):
        return "unchanged"

    run = ingest(session, adapter)
    run_id = run.id
    checkpoint = session.get(ImportCheckpoint, adapter.name)
    if checkpoint is None:
        checkpoint = ImportCheckpoint(source=adapter.name)
        session.add(checkpoint)
    checkpoint.sha256 = expected_sha256
    checkpoint.verified_on = verified_on
    checkpoint.run_id = run_id
    checkpoint.completed_at = utc_now()
    session.commit()
    return "imported"
