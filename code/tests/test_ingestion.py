from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

import app.main as web
from app.credentials import token_hash
from app.data import SCHEMES
from app.ingestion import LocationSnapshotAdapter, SchemeSnapshotAdapter, ingest
from app.storage import (
    ApiKey,
    Base,
    Dataset,
    DeveloperAccount,
    IngestionRun,
    StoredRecord,
    create_database,
    read_records,
    utc_now,
)


def test_snapshot_ingestion_is_repeatable_and_attributed(tmp_path):
    engine = create_database(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)

    class WrongKind(LocationSnapshotAdapter):
        name = SchemeSnapshotAdapter.name

    with Session(engine) as session:
        assert ingest(session, SchemeSnapshotAdapter()).accepted == 8
        assert ingest(session, SchemeSnapshotAdapter()).accepted == 8
        with pytest.raises(ValueError, match="already uses a different record kind"):
            ingest(session, WrongKind())
        records = read_records(session, "scheme")
        assert len(records) == 8
        assert all(record["source"]["url"].startswith("https://") for record in records)
        assert len(session.scalars(select(IngestionRun)).all()) == 2
        dataset = session.get(Dataset, SchemeSnapshotAdapter.name)
        assert dataset.record_kind == "scheme"
        assert dataset.complete_snapshot
        assert not read_records(session, "location")


def test_invalid_batch_does_not_overwrite_existing_records(tmp_path):
    engine = create_database(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)

    class BadAdapter(SchemeSnapshotAdapter):
        def collect(self):
            yield from super().collect()
            yield {"id": "invalid"}

    with Session(engine) as session:
        ingest(session, SchemeSnapshotAdapter())
        before = read_records(session, "scheme")
        with pytest.raises(ValueError):
            ingest(session, BadAdapter())
        after = read_records(session, "scheme")
        assert len(after) == len(before)
        for original, current in zip(before, after, strict=True):
            assert current["id"] == original["id"]
            assert current["summary"] == original["summary"]
            assert current["source"]["last_verified"] == original["source"]["last_verified"]
            assert current["source"]["review_reason"] == "import_failed"
        last_run = session.scalars(select(IngestionRun).order_by(IngestionRun.id.desc())).first()
        assert last_run.status == "failed"
        assert last_run.failure_code == "INVALID_RECORD"
        assert last_run.failure_position == 9
        assert last_run.failure_position_kind == "record"
        assert last_run.error is None
        assert len(session.scalars(select(StoredRecord)).all()) == 8


def test_api_serves_ingested_database_records(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest(session, SchemeSnapshotAdapter())
        ingest(session, LocationSnapshotAdapter())
        account = DeveloperAccount(email="test@example.org", password_hash="unused")
        session.add(account)
        session.flush()
        session.add(
            ApiKey(
                id="test",
                account_id=account.id,
                key_hash=token_hash("test-key"),
                prefix="test-key",
                created_at=utc_now(),
            )
        )
        session.commit()
    monkeypatch.setattr(web, "engine", engine)
    with TestClient(web.app) as client:
        headers = {"X-API-Key": "test-key"}
        response = client.get("/api/v1/schemes", params={"q": "health"}, headers=headers)
        assert response.status_code == 200
        assert len(response.json()["data"]) == 2
        paged = client.get(
            "/api/v1/schemes", params={"q": "health", "limit": 1, "offset": 1}, headers=headers
        )
        assert paged.status_code == 200
        assert paged.json()["meta"]["total_count"] == 2
        assert paged.json()["meta"]["result_count"] == 1
        assert paged.json()["data"][0]["id"] == sorted(
            item["id"] for item in response.json()["data"]
        )[1]
        page = client.get("/", params={"q": "health", "audience": "Women"})
        assert page.status_code == 200
        assert "Janani Suraksha Yojana" in page.text
        assert "Ayushman Bharat Pradhan Mantri Jan Arogya Yojana" not in page.text
        assert client.get("/api/v1/locations/pincode/147004", headers=headers).status_code == 200


def test_pincode_lookup_queries_only_the_requested_record(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'lookup.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest(session, LocationSnapshotAdapter())
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture_query(connection, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))

    monkeypatch.setattr(web, "engine", engine)
    location = web.current_location("147004")
    assert location.pincode == "147004"
    assert len(statements) == 1
    statement, parameters = statements[0]
    assert "WHERE" in statement.upper()
    assert "147004" in parameters
    assert "location" in parameters
    assert web.current_location("999999") is None
    engine.dispose()


def test_failed_source_marks_only_its_records_for_review_and_recovers(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'freshness.db').as_posix()}")
    Base.metadata.create_all(engine)

    class FirstSource(SchemeSnapshotAdapter):
        name = "source-one"

        def collect(self):
            record = next(iter(super().collect()))
            record["source"]["last_verified"] = datetime.now(UTC).date().isoformat()
            record["source"]["freshness_status"] = "current"
            yield record

    class SecondSource(SchemeSnapshotAdapter):
        name = "source-two"

        def collect(self):
            records = list(super().collect())
            record = records[1]
            record["source"]["last_verified"] = datetime.now(UTC).date().isoformat()
            record["source"]["freshness_status"] = "current"
            yield record

    class BrokenSource(FirstSource):
        def collect(self):
            raise ValueError("source unavailable")

    with Session(engine) as session:
        ingest(session, FirstSource())
        ingest(session, SecondSource())
        before = {record["id"]: record for record in read_records(session, "scheme")}
        with pytest.raises(ValueError, match="source unavailable"):
            ingest(session, BrokenSource())
        after = {record["id"]: record for record in read_records(session, "scheme")}
        assert after["scheme-pm-kisan"]["source"]["freshness_status"] == "review_due"
        assert after["scheme-pm-kisan"]["summary"] == before["scheme-pm-kisan"]["summary"]
        assert after["scheme-pm-jay"] == before["scheme-pm-jay"]
        ingest(session, FirstSource())
        restored = {record["id"]: record for record in read_records(session, "scheme")}
        assert restored["scheme-pm-kisan"]["source"]["freshness_status"] == "current"
    engine.dispose()


class LargeFixtureAdapter(SchemeSnapshotAdapter):
    name = "synthetic-load-fixture"

    def collect(self):
        for index in range(1201):
            record = SCHEMES[0].model_dump(mode="json")
            record["id"] = f"synthetic-{index:04d}"
            record["slug"] = f"synthetic-{index:04d}"
            yield record


def test_large_import_uses_batched_lookups_and_upserts(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'large.db').as_posix()}")
    Base.metadata.create_all(engine)
    lookups = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture_query(connection, cursor, statement, parameters, context, executemany):
        if (
            statement.lstrip().upper().startswith("SELECT")
            and "normalized_records" in statement
            and " IN " in statement.upper()
        ):
            lookups.append(statement)

    with Session(engine) as session:
        assert ingest(session, LargeFixtureAdapter()).accepted == 1201
        assert len(lookups) == 3
        lookups.clear()
        assert ingest(session, LargeFixtureAdapter()).accepted == 1201
        assert len(lookups) == 3
        assert len(read_records(session, "scheme")) == 1201
    engine.dispose()


def test_database_error_after_first_batch_rolls_back_new_records(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'rollback.db').as_posix()}")
    Base.metadata.create_all(engine)
    lookup_count = 0

    @event.listens_for(engine, "before_cursor_execute")
    def fail_second_lookup(connection, cursor, statement, parameters, context, executemany):
        nonlocal lookup_count
        if (
            statement.lstrip().upper().startswith("SELECT")
            and "normalized_records" in statement
            and " IN " in statement.upper()
        ):
            lookup_count += 1
            if lookup_count == 2:
                raise RuntimeError("simulated database failure")

    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="simulated database failure"):
            ingest(session, LargeFixtureAdapter())
        assert read_records(session, "scheme") == []
        run = session.scalar(select(IngestionRun))
        assert run.status == "failed"


def test_import_rejects_duplicate_slugs_within_batch_or_against_existing_records(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'slugs.db').as_posix()}")
    Base.metadata.create_all(engine)

    class DuplicateBatch(SchemeSnapshotAdapter):
        name = "duplicate-batch"

        def collect(self):
            first, second = list(super().collect())[:2]
            second["slug"] = first["slug"]
            yield first
            yield second

    class DuplicateExisting(SchemeSnapshotAdapter):
        name = "duplicate-existing"

        def collect(self):
            record = next(iter(super().collect()))
            record["id"] = "another-id"
            yield record

    with Session(engine) as session:
        with pytest.raises(ValueError, match="Duplicate scheme slug"):
            ingest(session, DuplicateBatch())
        assert read_records(session, "scheme") == []
        ingest(session, SchemeSnapshotAdapter())
        before = read_records(session, "scheme")
        with pytest.raises(ValueError, match="Duplicate scheme slug"):
            ingest(session, DuplicateExisting())
        assert read_records(session, "scheme") == before
    engine.dispose()


def test_scheme_detail_resolves_slug_and_api_prioritizes_id(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'routing.db').as_posix()}")
    Base.metadata.create_all(engine)

    class OverlappingIdentifiers(SchemeSnapshotAdapter):
        name = "overlap-fixture"

        def collect(self):
            first, second = list(super().collect())[:2]
            first["id"], first["slug"] = "a", "shared"
            second["id"], second["slug"] = "shared", "other"
            yield first
            yield second

    with Session(engine) as session:
        ingest(session, OverlappingIdentifiers())
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "cache_client", None)
    assert web.current_scheme("shared").id == "shared"
    with TestClient(web.app) as client:
        response = client.get("/schemes/shared")
        assert response.status_code == 200
        assert SCHEMES[0].name in response.text
        assert SCHEMES[1].name not in response.text
    engine.dispose()
    engine.dispose()
