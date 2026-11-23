from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.main as web
from app.ingestion import LocationSnapshotAdapter, SchemeSnapshotAdapter, ingest
from app.monitoring import monitoring_alerts
from app.source_checks import (
    OFFICIAL_SOURCES,
    latest_source_checks,
    run_source_checks,
    store_source_checks,
)
from app.storage import Base, SourceProbe, create_database, utc_now


def test_source_checks_classify_without_following_redirects(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'checks.db').as_posix()}")
    Base.metadata.create_all(engine)
    urls = list(OFFICIAL_SOURCES.values())
    calls = []

    def handler(request):
        calls.append(str(request.url))
        assert request.method == "HEAD"
        index = urls.index(str(request.url))
        if index == 0:
            return httpx.Response(200)
        if index == 1:
            return httpx.Response(403)
        if index == 2:
            return httpx.Response(302, headers={"Location": "https://example.com/"})
        raise httpx.ConnectError("private error details", request=request)

    with Session(engine) as session, httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert all(item["status"] == "not_checked" for item in latest_source_checks(session))
        run_source_checks(session, client)
        results = latest_source_checks(session)
        assert [item["status"] for item in results] == [
            "accessible",
            "restricted",
            "redirect",
            "unavailable",
        ]
        assert len(calls) == len(OFFICIAL_SOURCES)
        assert all(item["checked_at"] for item in results)
        assert "private error details" not in str(results)
        alerts = monitoring_alerts([], {"status": "not_configured"}, results)
        failed = [alert for alert in alerts if alert["code"] == "SOURCE_CHECK_FAILED"]
        assert len(failed) == 1
        assert "last HEAD check" in failed[0]["message"]
        run_source_checks(session, client)
        assert len(latest_source_checks(session)) == len(OFFICIAL_SOURCES)
    engine.dispose()


def test_source_check_storage_does_not_overwrite_newer_result(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'race.db').as_posix()}")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        store_source_checks(session, [("myScheme", "accessible", 200, now, 2.0)])
        store_source_checks(
            session, [("myScheme", "unavailable", None, now - timedelta(seconds=1), 4.0)]
        )
        current = session.get(SourceProbe, "myScheme")
        assert current.status == "accessible"
        assert current.http_status == 200
        store_source_checks(
            session, [("myScheme", "server_error", 503, now + timedelta(seconds=1), 5.0)]
        )
        assert session.get(SourceProbe, "myScheme").status == "server_error"
    engine.dispose()


def test_admin_source_checks_require_admin_and_return_persisted_data(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'admin-checks.db').as_posix()}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "ADMIN_TOKEN", "a" * 32)
    called = []

    def fake_checks(session, client):
        called.append(True)
        session.add(
            SourceProbe(
                source="myScheme",
                status="accessible",
                http_status=200,
                checked_at=utc_now(),
                duration_ms=1.0,
            )
        )
        session.commit()

    monkeypatch.setattr(web, "run_source_checks", fake_checks)
    with TestClient(web.app) as client:
        assert client.post("/api/v1/admin/source-checks").status_code == 401
        assert called == []
        headers = {"X-Admin-Token": "a" * 32}
        result = client.post("/api/v1/admin/source-checks", headers=headers)
        assert result.status_code == 200
        assert result.headers["cache-control"] == "no-store"
        assert result.json()["source_checks"][0]["status"] == "accessible"
        overview = client.get("/api/v1/admin/overview", headers=headers)
        assert overview.json()["source_checks"][0]["http_status"] == 200
    engine.dispose()


def test_public_detail_shows_only_matching_recorded_page_checks(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'public-checks.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest(session, SchemeSnapshotAdapter())
        ingest(session, LocationSnapshotAdapter())
        session.add_all(
            [
                SourceProbe(
                    source="PFRDA Atal Pension Yojana",
                    status="unavailable",
                    http_status=None,
                    checked_at=utc_now(),
                    duration_ms=1,
                ),
                SourceProbe(
                    source="myScheme",
                    status="unavailable",
                    http_status=None,
                    checked_at=utc_now(),
                    duration_ms=1,
                ),
                SourceProbe(
                    source="OGD PIN directory",
                    status="restricted",
                    http_status=403,
                    checked_at=utc_now(),
                    duration_ms=1,
                ),
            ]
        )
        session.commit()
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "cache_client", None)
    with TestClient(web.app) as client:
        pension = client.get("/schemes/atal-pension-yojana")
        assert "the page could not be reached" in pension.text
        assert "past check of this exact page" in pension.text
        # A failed check of the myScheme homepage is not a check of each scheme's page.
        scheme = client.get("/schemes/pm-kisan")
        assert "Last source page check" not in scheme.text
        pin = client.get("/locations", params={"pincode": "147004"})
        assert "the HEAD request was denied" in pin.text
        assert "may fail even when the page opens in a browser" in pin.text
    engine.dispose()


def test_public_detail_distinguishes_no_prior_check(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'no-check.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest(session, SchemeSnapshotAdapter())
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "cache_client", None)
    with TestClient(web.app) as client:
        page = client.get("/schemes/atal-pension-yojana")
        assert "This source page has not been checked yet" in page.text
        assert "the page could not be reached" not in page.text
    engine.dispose()
