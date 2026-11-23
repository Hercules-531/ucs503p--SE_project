import json
from datetime import UTC, datetime

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy.orm import Session

from app.cache import cache_metrics, cached_records
from app.ingestion import SchemeSnapshotAdapter, ingest
from app.storage import Base, create_database


class CacheStub:
    def __init__(self):
        self.values = {}
        self.hits = 0
        self.metrics = {}

    def get(self, key):
        if key in self.values:
            self.hits += 1
        return self.values.get(key)

    def set(self, key, value, ex):
        assert ex == 120
        self.values[key] = value

    def hincrby(self, key, field, amount):
        bucket = self.metrics.setdefault(key, {})
        bucket[field] = bucket.get(field, 0) + amount

    def hgetall(self, key):
        return self.metrics.get(key, {})


def test_cache_hit_and_ingestion_invalidation(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'cache.db').as_posix()}")
    Base.metadata.create_all(engine)
    cache = CacheStub()
    with Session(engine) as session:
        ingest(session, SchemeSnapshotAdapter())
        original = cached_records(session, "scheme", cache, "test")
        assert cached_records(session, "scheme", cache, "test") == original
        assert cache.hits == 1
        assert cache_metrics(cache, "test") == {
            "status": "available",
            "hits": 1,
            "misses": 1,
            "errors": 0,
            "hit_ratio": 0.5,
        }

        class UpdatedAdapter(SchemeSnapshotAdapter):
            def collect(self):
                for raw in super().collect():
                    if raw["id"] == "scheme-pm-kisan":
                        raw["summary"] = "Updated summary"
                    yield raw

        ingest(session, UpdatedAdapter())
        updated = cached_records(session, "scheme", cache, "test")
        assert next(item for item in updated if item["id"] == "scheme-pm-kisan")["summary"] == (
            "Updated summary"
        )
        assert len(cache.values) == 2
        assert all("test-key" not in key for key in cache.values)
    engine.dispose()


def test_corrupt_or_unavailable_cache_falls_back_to_database(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'fallback.db').as_posix()}")
    Base.metadata.create_all(engine)
    cache = CacheStub()
    with Session(engine) as session:
        ingest(session, SchemeSnapshotAdapter())
        cached_records(session, "scheme", cache, "test")
        cache.values[next(iter(cache.values))] = "not json"
        assert len(cached_records(session, "scheme", cache, "test")) == 8
        assert isinstance(json.loads(cache.values[next(iter(cache.values))]), list)

        class BrokenCache:
            def get(self, key):
                raise ConnectionError("offline")

            def set(self, *args, **kwargs):
                raise ConnectionError("offline")

            def hincrby(self, *args, **kwargs):
                raise ConnectionError("offline")

            def hgetall(self, *args, **kwargs):
                raise ConnectionError("offline")

        assert len(cached_records(session, "scheme", BrokenCache(), "test")) == 8
        assert cache_metrics(BrokenCache(), "test")["status"] == "unavailable"
    engine.dispose()


def test_failed_refresh_invalidates_cached_freshness(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'failed-refresh.db').as_posix()}")
    Base.metadata.create_all(engine)
    cache = CacheStub()

    class FreshSource(SchemeSnapshotAdapter):
        name = "fresh-source"

        def collect(self):
            record = next(iter(super().collect()))
            record["source"]["last_verified"] = datetime.now(UTC).date().isoformat()
            record["source"]["freshness_status"] = "current"
            yield record

    class FailedSource(FreshSource):
        def collect(self):
            raise ValueError("source unavailable")

    with Session(engine) as session:
        ingest(session, FreshSource())
        assert (
            cached_records(session, "scheme", cache, "test")[0]["source"]["freshness_status"]
            == "current"
        )
        with pytest.raises(ValueError):
            ingest(session, FailedSource())
        assert (
            cached_records(session, "scheme", cache, "test")[0]["source"]["freshness_status"]
            == "review_due"
        )
        assert len(cache.values) == 2
    engine.dispose()
