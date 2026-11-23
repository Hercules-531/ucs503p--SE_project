"""Opt-in checks against explicitly provisioned, disposable service instances."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.main as web
from app.cache import cache_metrics, cached_records
from app.data import LOCATIONS, SCHEMES, filter_schemes, uncertain_filter_exclusions
from app.ingestion import DataSourceAdapter, SchemeSnapshotAdapter, ingest
from app.models import LocationRecord, Scheme
from app.rate_limit import RedisRateLimiter
from app.search import indexed_scheme_page, indexed_schemes, indexed_uncertain_exclusions
from app.source_checks import store_source_checks
from app.storage import SourceProbe, StoredRecord, create_database, read_records


@pytest.mark.skipif(
    not os.getenv("TEST_SERVICE_DATABASE_URL"), reason="No integration PostgreSQL configured"
)
def test_postgres_migrated_snapshot_is_readable():
    engine = create_database(os.environ["TEST_SERVICE_DATABASE_URL"])
    with Session(engine) as session:
        count = session.scalar(select(func.count()).select_from(StoredRecord))
        assert count >= 11
    engine.dispose()


@pytest.mark.skipif(
    not os.getenv("TEST_SERVICE_DATABASE_URL"), reason="No integration PostgreSQL configured"
)
def test_postgres_scheme_lookup_uses_id_and_slug(monkeypatch):
    engine = create_database(os.environ["TEST_SERVICE_DATABASE_URL"])
    monkeypatch.setattr(web, "engine", engine)
    assert web.current_scheme("scheme-pm-kisan").slug == "pm-kisan"
    assert web.current_scheme("pm-kisan").id == "scheme-pm-kisan"
    assert web.current_scheme_by_slug("pm-kisan").id == "scheme-pm-kisan"
    assert web.current_scheme_by_slug("not-a-scheme") is None
    engine.dispose()


@pytest.mark.skipif(
    not os.getenv("TEST_SERVICE_DATABASE_URL"), reason="No integration PostgreSQL configured"
)
def test_postgres_source_checks_keep_newest_observation():
    engine = create_database(os.environ["TEST_SERVICE_DATABASE_URL"])
    name = "integration-" + uuid4().hex
    now = datetime.now(UTC)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                store_source_checks(session, [(name, "accessible", 200, now, 1.0)])
                store_source_checks(
                    session, [(name, "unavailable", None, now - timedelta(seconds=1), 1.0)]
                )
                assert session.get(SourceProbe, name).status == "accessible"
                store_source_checks(
                    session, [(name, "server_error", 503, now + timedelta(seconds=1), 1.0)]
                )
                assert session.get(SourceProbe, name).status == "server_error"
        finally:
            transaction.rollback()
    engine.dispose()


@pytest.mark.skipif(
    not os.getenv("TEST_SERVICE_DATABASE_URL"), reason="No integration PostgreSQL configured"
)
def test_postgres_indexed_search_matches_snapshot_filters():
    engine = create_database(os.environ["TEST_SERVICE_DATABASE_URL"])
    with Session(engine) as session:
        records = [Scheme.model_validate(item) for item in read_records(session, "scheme")]
        for filters in (
            {"q": "HEALTH"},
            {"state": "Punjab"},
            {"category": "Health", "audience": "Women"},
            {"q": "%"},
        ):
            expected = sorted(item.id for item in filter_schemes(records=records, **filters))
            actual = [item.id for item in indexed_schemes(session, **filters)]
            assert actual == expected
    engine.dispose()


@pytest.mark.skipif(
    not os.getenv("TEST_SERVICE_DATABASE_URL"), reason="No integration PostgreSQL configured"
)
def test_postgres_scheme_pagination_matches_filtered_results():
    engine = create_database(os.environ["TEST_SERVICE_DATABASE_URL"])
    with Session(engine) as session:
        expected = indexed_schemes(session, q="health")
        first, count = indexed_scheme_page(session, q="health", limit=1, offset=0)
        rest, second_count = indexed_scheme_page(session, q="health", limit=100, offset=1)
        assert first + rest == expected
        assert count == second_count == len(expected)
    engine.dispose()


@pytest.mark.skipif(
    not os.getenv("TEST_SERVICE_DATABASE_URL"), reason="No integration PostgreSQL configured"
)
def test_postgres_uncertain_filter_count_matches_python():
    engine = create_database(os.environ["TEST_SERVICE_DATABASE_URL"])
    identifier = "test-uncertain-" + uuid4().hex

    class Snapshot(SchemeSnapshotAdapter):
        name = identifier
        complete_snapshot = False

        def collect(self):
            record = SCHEMES[0].model_dump(mode="json")
            record.update(id=identifier, slug=identifier, states=[], audiences=[])
            yield record

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                ingest(session, Snapshot())
                records = indexed_schemes(session)
                filters = {"state": "Punjab", "audience": "Women"}
                assert indexed_uncertain_exclusions(session, **filters) == (
                    uncertain_filter_exclusions(records, **filters)
                )
                assert indexed_uncertain_exclusions(session, **filters) >= 1
                expected = sorted(
                    record.id for record in filter_schemes(
                        records=records, include_unknown=True, **filters
                    )
                )
                actual = [record.id for record in indexed_schemes(
                    session, include_unknown=True, **filters
                )]
                assert actual == expected
                assert identifier in actual
        finally:
            transaction.rollback()
    engine.dispose()


@pytest.mark.skipif(
    not os.getenv("TEST_SERVICE_DATABASE_URL"), reason="No integration PostgreSQL configured"
)
def test_postgres_full_snapshot_marks_omissions_without_deleting():
    engine = create_database(os.environ["TEST_SERVICE_DATABASE_URL"])
    identifier = "integration-" + uuid4().hex
    fixture = LOCATIONS["147004"].model_dump(mode="json")
    fixture["source"]["last_verified"] = datetime.now(UTC).date().isoformat()
    fixture["source"]["freshness_status"] = "current"

    class Snapshot(DataSourceAdapter):
        name = identifier
        kind = "location"
        model = LocationRecord
        id_field = "pincode"
        complete_snapshot = True

        def __init__(self, pins):
            self.pins = pins

        def collect(self):
            for pin in self.pins:
                yield {**fixture, "pincode": pin}

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                assert session.get(StoredRecord, ("location", "920001")) is None
                assert session.get(StoredRecord, ("location", "920002")) is None
                ingest(session, Snapshot(["920001", "920002"]))
                ingest(session, Snapshot(["920001"]))
                omitted = session.get(StoredRecord, ("location", "920002"))
                assert omitted.payload["source"]["freshness_status"] == "review_due"
                assert omitted.payload["source"]["review_reason"] == "absent_from_snapshot"
        finally:
            transaction.rollback()
    engine.dispose()


@pytest.mark.skipif(
    not os.getenv("TEST_SERVICE_REDIS_URL"), reason="No integration Redis configured"
)
def test_redis_atomic_quota_and_expiry():
    client = Redis.from_url(os.environ["TEST_SERVICE_REDIS_URL"], socket_connect_timeout=2)
    identifier = "integration-" + uuid4().hex
    limiter = RedisRateLimiter(client, limit=1, window_seconds=10)
    try:
        assert limiter.check(identifier).allowed
        assert not limiter.check(identifier).allowed
        assert 0 < client.ttl(f"bharatos:rate:{identifier}") <= 10
    finally:
        client.delete(f"bharatos:rate:{identifier}")
        client.close()


@pytest.mark.skipif(
    not os.getenv("TEST_SERVICE_DATABASE_URL") or not os.getenv("TEST_SERVICE_REDIS_URL"),
    reason="PostgreSQL and Redis integration services required",
)
def test_postgres_catalogue_is_cached_in_real_redis():
    engine = create_database(os.environ["TEST_SERVICE_DATABASE_URL"])
    client = Redis.from_url(os.environ["TEST_SERVICE_REDIS_URL"], socket_connect_timeout=2)
    namespace = "integration-" + uuid4().hex
    try:
        with Session(engine) as session:
            expected = read_records(session, "scheme")
            assert expected, "Seed the integration database before running the cache test"
            first = cached_records(session, "scheme", client, namespace)
            assert first == expected
            keys = list(client.scan_iter(f"bharatos:records:v1:{namespace}:*"))
            assert len(keys) == 1
            assert 0 < client.ttl(keys[0]) <= 120
            assert cached_records(session, "scheme", client, namespace) == first
            metrics = cache_metrics(client, namespace)
            assert metrics["hits"] == 1
            assert metrics["misses"] == 1
            assert metrics["hit_ratio"] == 0.5
    finally:
        for key in client.scan_iter(f"bharatos:records:v1:{namespace}:*"):
            client.delete(key)
        client.delete(f"bharatos:cache-metrics:v1:{namespace}")
        client.close()
        engine.dispose()
