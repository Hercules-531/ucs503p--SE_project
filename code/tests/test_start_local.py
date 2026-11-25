import hashlib
import socket
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.main as web
import app.ogd_pincode as ogd
import app.pincode_mirror as mirror
from app.storage import IngestionRun, StoredRecord, create_database
from scripts.start_local import find_available_port, initialize_database, sqlite_url


def test_port_selection_skips_a_bound_local_listener():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        occupied = listener.getsockname()[1]
        with pytest.raises(ValueError, match="No available localhost port"):
            find_available_port(occupied, occupied)
    assert find_available_port(occupied, occupied) == occupied


def test_fresh_local_database_is_seeded_once_and_existing_data_is_preserved(tmp_path, monkeypatch):
    database = tmp_path / "local.db"
    created, report = initialize_database(database)
    assert created
    assert len(report) == 9
    engine = create_database(sqlite_url(database))
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(StoredRecord)) == 32
        assert session.scalar(select(func.count()).select_from(IngestionRun)) == 9
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "cache_client", None)
    with TestClient(web.app) as client:
        page = client.get("/developers")
        assert page.status_code == 200
        assert "Across 10 categories" in page.text
        detail = client.get("/schemes/nipun-bharat")
        assert detail.status_code == 200
        assert "10 Aug 2026" in detail.text
        assert "Review needed" in detail.text
        assert "Confirm current programme details." in detail.text
    engine.dispose()
    assert initialize_database(database) == (False, [])
    engine = create_database(sqlite_url(database))
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(IngestionRun)) == 9
    engine.dispose()


def test_initialization_failure_never_publishes_partial_database(tmp_path):
    database = tmp_path / "local.db"
    invalid_mirror = tmp_path / "modified.csv"
    invalid_mirror.write_text("not the approved snapshot", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        initialize_database(database, invalid_mirror)
    assert not database.exists()
    assert not list(tmp_path.glob(".bharatos-init-*.db"))


def test_existing_unrelated_database_is_not_modified(tmp_path):
    database = tmp_path / "other.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE important_data (value TEXT)")
        connection.execute("INSERT INTO important_data VALUES ('keep me')")
    before = database.read_bytes()
    with pytest.raises(ValueError, match="not a migrated BharatOS database"):
        initialize_database(database)
    assert database.read_bytes() == before


def test_existing_outdated_database_is_not_migrated_implicitly(tmp_path):
    database = tmp_path / "old.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        connection.execute("INSERT INTO alembic_version VALUES ('older-revision')")
    before = database.read_bytes()
    with pytest.raises(ValueError, match="migrate it explicitly"):
        initialize_database(database)
    assert database.read_bytes() == before


def test_new_local_database_can_include_checked_historical_mirror(tmp_path, monkeypatch):
    database = tmp_path / "local.db"
    source = tmp_path / "mirror.csv"
    payload = (
        b"officename,pincode,district,statename\n"
        b"Mirror Office,147004,Patiala,Punjab\n"
        b"Other Office,123456,District,State\n"
    )
    source.write_bytes(payload)
    monkeypatch.setattr(mirror, "MIRROR_SHA256", hashlib.sha256(payload).hexdigest())
    created, report = initialize_database(database, source)
    assert created
    assert report[-1].endswith("1 records")
    engine = create_database(sqlite_url(database))
    with Session(engine) as session:
        curated = session.get(StoredRecord, ("location", "147004"))
        imported = session.get(StoredRecord, ("location", "123456"))
        assert curated.source_adapter == "curated-pincodes"
        assert imported.payload["source"]["provenance_kind"] == "third_party_mirror"
        assert imported.payload["source"]["last_verified"] is None
    engine.dispose()


def test_new_database_serves_official_archive_with_historical_provenance(tmp_path, monkeypatch):
    database = tmp_path / "archive.db"
    source = tmp_path / "postal-archive.csv"
    data = (
        b"Office Name,Pincode,District,StateName\n"
        b"Historic Office\xa0,147004,Patiala,Punjab\n"
        b"Other Office,147004,Patiala,Punjab\n"
    )
    source.write_bytes(data)
    monkeypatch.setattr(ogd, "ARCHIVE_2019_SHA256", hashlib.sha256(data).hexdigest())
    assert initialize_database(database, official_archive_path=source)[0]
    with pytest.raises(ValueError, match="new database path"):
        initialize_database(database, official_archive_path=source)

    engine = create_database(sqlite_url(database))
    monkeypatch.setattr(web, "engine", engine)
    with Session(engine) as session:
        stored = session.get(StoredRecord, ("location", "147004"))
        assert stored.source_adapter == ogd.OgdPincode2019ArchiveAdapter.name
        assert stored.payload["offices"][0]["original_values"] == {
            "officename": ["Historic Office\u00a0"]
        }
        metadata = stored.payload["source"]
        assert metadata["snapshot_date"] == "2019-05-30"
        assert metadata["last_verified"] is None
        assert metadata["freshness_status"] == "review_due"
        assert metadata["snapshot_sha256"] == hashlib.sha256(data).hexdigest()
    with TestClient(web.app) as client:
        result = client.get("/locations", params={"pincode": "147004"})
        assert result.status_code == 200
        assert "Historic Office" in result.text and "Other Office" in result.text
        assert "Review needed" in result.text
        assert "30 May 2019" in result.text
        assert ogd.ARCHIVE_2019_URL in result.text
        assert "Government Open Data License - India" in result.text
    engine.dispose()


def test_archive_checksum_failure_leaves_no_local_database(tmp_path):
    database = tmp_path / "archive.db"
    source = tmp_path / "wrong.csv"
    source.write_text("This is a different snapshot", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        initialize_database(database, official_archive_path=source)
    assert not database.exists()
