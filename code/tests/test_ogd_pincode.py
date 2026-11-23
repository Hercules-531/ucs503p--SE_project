import hashlib
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.ingestion import LocationSnapshotAdapter, ingest
from app.ogd_pincode import OgdPincodeCsvAdapter
from app.storage import Base, create_database, read_records


def test_csv_groups_offices_and_preserves_attribution(tmp_path):
    csv_path = tmp_path / "offices.csv"
    csv_path.write_text(
        "officename,pincode,district,statename\n"
        "Alpha,123456,First,State A\n"
        "Beta,123456,Second,State A\n"
        "Alpha,123456,First,State A\n"
        "Gamma,654321,Third,State B\n",
        encoding="utf-8",
    )
    engine = create_database(f"sqlite:///{(tmp_path / 'data.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        adapter = OgdPincodeCsvAdapter(csv_path, datetime.now(UTC).date(), expected_sha256=digest)
        assert ingest(session, adapter).accepted == 2
        records = read_records(session, "location")
        first = next(record for record in records if record["pincode"] == "123456")
        assert [office["office_name"] for office in first["offices"]] == ["Alpha", "Beta"]
        assert first["offices"][1]["district"] == "Second"
        assert first["source"]["license_name"] == "Government Open Data License - India"
        assert first["source"]["url"].startswith("https://www.data.gov.in/")
        assert first["source"]["snapshot_sha256"] == digest
    engine.dispose()


def test_changed_bytes_fail_before_parsing(tmp_path):
    csv_path = tmp_path / "changed.csv"
    csv_path.write_bytes(b"changed bytes")
    adapter = OgdPincodeCsvAdapter(csv_path, datetime.now(UTC).date(), expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="does not match the approved digest"):
        list(adapter.collect())


def test_malformed_row_fails_atomically(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text(
        "officename,pincode,district,statename\n"
        "Alpha,123456,First,State A\n"
        "Broken,12,Second,State A\n",
        encoding="utf-8",
    )
    engine = create_database(f"sqlite:///{(tmp_path / 'data.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        with pytest.raises(ValueError, match="line 3"):
            ingest(session, OgdPincodeCsvAdapter(csv_path, datetime.now(UTC).date()))
        assert read_records(session, "location") == []
    engine.dispose()


@pytest.mark.parametrize(
    "content, expected",
    [
        ("officename,pin-code,pincode,district,statename\nAlpha,123456,654321,D,S\n", "duplicate"),
        ("officename,pincode,district,statename\nAlpha,123456,D,S,unexpected\n", "Extra fields"),
        ('officename,pincode,district,statename\n"Alpha,123456,D,S\n', "unexpected end"),
    ],
)
def test_ambiguous_or_malformed_csv_never_imports_records(tmp_path, content, expected):
    import csv

    path = tmp_path / "invalid.csv"
    path.write_text(content, encoding="utf-8")
    engine = create_database(f"sqlite:///{(tmp_path / 'invalid.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        with pytest.raises((ValueError, csv.Error), match=expected):
            ingest(session, OgdPincodeCsvAdapter(path, datetime.now(UTC).date()))
        assert read_records(session, "location") == []
    engine.dispose()


def test_omitted_records_are_retained_marked_and_can_recover(tmp_path):
    csv_path = tmp_path / "snapshot.csv"
    first = (
        "officename,pincode,district,statename\n"
        "Alpha,123456,First,State A\n"
        "Beta,654321,Second,State B\n"
    )
    csv_path.write_text(first, encoding="utf-8")
    engine = create_database(f"sqlite:///{(tmp_path / 'omitted.db').as_posix()}")
    Base.metadata.create_all(engine)
    today = datetime.now(UTC).date()
    with Session(engine) as session:
        ingest(session, LocationSnapshotAdapter())
        ingest(session, OgdPincodeCsvAdapter(csv_path, today))
        original = {r["pincode"]: r for r in read_records(session, "location")}
        csv_path.write_text(
            "officename,pincode,district,statename\nAlpha,123456,First,State A\n",
            encoding="utf-8",
        )
        ingest(session, OgdPincodeCsvAdapter(csv_path, today))
        current = {r["pincode"]: r for r in read_records(session, "location")}
        missing = current["654321"]
        assert missing["office_name"] == original["654321"]["office_name"]
        assert missing["source"]["last_verified"] == today.isoformat()
        assert missing["source"]["freshness_status"] == "review_due"
        assert missing["source"]["review_reason"] == "absent_from_snapshot"
        assert current["123456"]["source"]["freshness_status"] == "current"
        assert current["147004"] == original["147004"]
        csv_path.write_text(first, encoding="utf-8")
        ingest(session, OgdPincodeCsvAdapter(csv_path, today))
        recovered = {r["pincode"]: r for r in read_records(session, "location")}
        assert recovered["654321"]["source"]["freshness_status"] == "current"
        assert recovered["654321"]["source"]["review_reason"] is None
    engine.dispose()
