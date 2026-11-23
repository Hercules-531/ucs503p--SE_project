import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion import ingest
from app.ogd_pincode import OgdPincodeCsvAdapter
from app.scheduled_import import run_checked_import
from app.storage import Base, IngestionRun, create_database, read_records


def test_scheduled_snapshot_skips_unchanged_and_recovers_from_tampering(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'scheduled.db').as_posix()}")
    Base.metadata.create_all(engine)
    path = tmp_path / "snapshot.csv"
    original = b"officename,pincode,district,statename\nOffice,123456,District,State\n"
    digest = hashlib.sha256(original).hexdigest()
    path.write_bytes(original)
    verified_on = datetime.now(UTC).date() - timedelta(days=45)
    with Session(engine) as session:
        assert run_checked_import(session, path, verified_on, digest) == "imported"
        assert run_checked_import(session, path, verified_on, digest) == "unchanged"
        assert session.scalar(select(func.count()).select_from(IngestionRun)) == 1
        record = read_records(session, "location")[0]
        assert record["source"]["last_verified"] == verified_on.isoformat()
        assert record["source"]["snapshot_sha256"] == digest
        assert record["source"]["freshness_status"] == "review_due"

        path.write_bytes(original + b"Modified,999999,District,State\n")
        with pytest.raises(ValueError, match="checksum"):
            run_checked_import(session, path, verified_on, digest)
        assert len(read_records(session, "location")) == 1
        assert (
            session.scalar(select(IngestionRun).order_by(IngestionRun.id.desc())).status == "failed"
        )

        path.write_bytes(original)
        assert run_checked_import(session, path, verified_on, digest) == "imported"
        assert run_checked_import(session, path, verified_on, digest) == "unchanged"
        assert session.scalar(select(func.count()).select_from(IngestionRun)) == 3
        assert (
            read_records(session, "location")[0]["source"]["last_verified"]
            == verified_on.isoformat()
        )
        ingest(session, OgdPincodeCsvAdapter(path, verified_on))
        assert run_checked_import(session, path, verified_on, digest) == "imported"
    engine.dispose()


def test_invalid_checksum_is_rejected_without_import(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'invalid.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        with pytest.raises(ValueError, match="checksum"):
            run_checked_import(session, tmp_path / "missing.csv", datetime.now(UTC).date(), "bad")
        assert session.scalar(select(func.count()).select_from(IngestionRun)) == 0
    engine.dispose()


def test_missing_file_marks_recent_snapshot_for_review(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'missing.db').as_posix()}")
    Base.metadata.create_all(engine)
    path = tmp_path / "snapshot.csv"
    original = b"officename,pincode,district,statename\nOffice,123456,District,State\n"
    path.write_bytes(original)
    digest = hashlib.sha256(original).hexdigest()
    today = datetime.now(UTC).date()
    with Session(engine) as session:
        run_checked_import(session, path, today, digest)
        assert read_records(session, "location")[0]["source"]["freshness_status"] == "current"
        missing = tmp_path / "missing.csv"
        with pytest.raises(ValueError, match="could not be read"):
            run_checked_import(session, missing, today, digest)
        assert read_records(session, "location")[0]["source"]["freshness_status"] == "review_due"
    engine.dispose()
