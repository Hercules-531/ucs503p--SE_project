from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError
from sqlalchemy.orm import Session

import app.main as web
from app.credentials import token_hash
from app.ingestion import SchemeSnapshotAdapter, ingest
from app.storage import ApiKey, ApiRequestLog, Base, DeveloperAccount, create_database, utc_now


def test_admin_overview_requires_separate_token_and_reports_real_data(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'admin.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest(session, SchemeSnapshotAdapter())
        account = DeveloperAccount(email="person@example.org", password_hash="hash")
        session.add(account)
        session.flush()
        session.add(
            ApiKey(
                id="key",
                account_id=account.id,
                key_hash=token_hash("test-key"),
                prefix="key",
                created_at=utc_now(),
            )
        )
        session.flush()
        now = utc_now()
        session.add_all(
            ApiRequestLog(
                key_id="key",
                endpoint="/api/v1/schemes",
                status_code=status,
                duration_ms=1.0,
                requested_at=recorded_at,
            )
            for status, recorded_at in (
                (429, now),
                (429, now),
                (503, now - timedelta(days=2)),
                (200, now),
                (500, now + timedelta(days=2)),
            )
        )
        session.commit()
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "cache_client", None)
    token = "a" * 32
    monkeypatch.setattr(web, "ADMIN_TOKEN", token)

    def catalogue_failure(_):
        raise RuntimeError("private test failure")

    monkeypatch.setattr(web, "current_scheme", catalogue_failure)
    monkeypatch.setattr(web, "rate_limiter", None)
    with TestClient(web.app, raise_server_exceptions=False) as client:
        assert client.get("/api/v1/admin/overview").status_code == 401
        assert (
            client.get("/api/v1/admin/overview", headers={"X-Admin-Token": "bad"}).status_code
            == 401
        )
        failed = client.get(
            "/api/v1/schemes/private-route-value?q=private-query-value",
            headers={"X-API-Key": "test-key"},
        )
        assert failed.status_code == 500
        response = client.get("/api/v1/admin/overview", headers={"X-Admin-Token": token})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        payload = response.json()
        assert payload["record_counts"]["scheme"] == 8
        assert payload["request_count"] == 6
        assert payload["error_count"] == 5
        assert payload["recent_api_errors"]["by_route"] == [
            {"route": "/api/v1/schemes", "status": 429, "count": 2},
            {"route": "/api/v1/schemes/{scheme_id}", "status": 500, "count": 1},
        ]
        assert "private-route-value" not in response.text
        assert "private-query-value" not in response.text
        assert "private test failure" not in response.text
        assert payload["cache"]["status"] == "not_configured"
        assert payload["recent_ingestion_runs"][0]["status"] == "success"
        source = payload["sources"][0]
        assert source["source"] == "curated-schemes"
        assert source["records"] == 8
        assert source["current"] + source["review_due"] + source["unknown"] == 8
        assert source["last_import_status"] == "success"
        assert "person@example.org" not in response.text
        assert token not in response.text
        assert "error" not in payload["recent_ingestion_runs"][0]
    engine.dispose()


def test_admin_unavailable_without_strong_configured_token(monkeypatch):
    monkeypatch.setattr(web, "ADMIN_TOKEN", "short")
    with TestClient(web.app) as client:
        assert client.get("/api/v1/admin/overview").status_code == 503
        assert "Monitoring is not configured" in client.get("/admin").text


def test_monitoring_reports_failed_import_without_exposing_error(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'failed.db').as_posix()}")
    Base.metadata.create_all(engine)

    class FailedAdapter(SchemeSnapshotAdapter):
        def collect(self):
            raise ValueError("private local file path")

    with Session(engine) as session:
        ingest(session, SchemeSnapshotAdapter())
        with pytest.raises(ValueError):
            ingest(session, FailedAdapter())
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "ADMIN_TOKEN", "a" * 32)
    with TestClient(web.app) as client:
        response = client.get("/api/v1/admin/overview", headers={"X-Admin-Token": "a" * 32})
        source = response.json()["sources"][0]
        assert source["last_import_status"] == "failed"
        assert source["review_due"] == 8
        assert "IMPORT_FAILED" in {alert["code"] for alert in response.json()["alerts"]}
        assert "REVIEW_DUE" in {alert["code"] for alert in response.json()["alerts"]}
        assert "private local file path" not in response.text
    engine.dispose()


def test_first_import_failure_and_cache_outage_generate_alerts(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'first-failure.db').as_posix()}")
    Base.metadata.create_all(engine)

    class FailedAdapter(SchemeSnapshotAdapter):
        def collect(self):
            raise ValueError("private source information")

    class BrokenRedis:
        def hgetall(self, key):
            raise ConnectionError("offline")

    with Session(engine) as session:
        with pytest.raises(ValueError):
            ingest(session, FailedAdapter())
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "ADMIN_TOKEN", "a" * 32)
    monkeypatch.setattr(web, "cache_client", BrokenRedis())
    with TestClient(web.app) as client:
        response = client.get("/api/v1/admin/overview", headers={"X-Admin-Token": "a" * 32})
        assert response.status_code == 200
        data = response.json()
        assert data["sources"][0]["records"] == 0
        assert data["sources"][0]["record_kind"] == "scheme"
        assert data["sources"][0]["complete_snapshot"] is True
        assert data["sources"][0]["freshness_percent"] is None
        assert {"IMPORT_FAILED", "NO_RECORDS", "CACHE_UNAVAILABLE"}.issubset(
            {alert["code"] for alert in data["alerts"]}
        )
        assert "private source information" not in response.text
    engine.dispose()
