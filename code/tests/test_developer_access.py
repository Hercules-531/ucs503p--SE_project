from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.main as web
from app.storage import ApiKey, ApiRequestLog, Base, DeveloperAccount, create_database


@pytest.mark.parametrize(
    "minutes, offset, valid",
    [(15, -12, True), (-15, 14, False), (15, 0, True), (-15, 0, False)],
)
def test_session_expiry_preserves_timezone_offset(monkeypatch, minutes, offset, valid):
    expiry = (datetime.now(UTC) + timedelta(minutes=minutes)).astimezone(
        timezone(timedelta(hours=offset))
    )

    class FakeSession:
        def __init__(self, engine):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, model, key):
            return SimpleNamespace(expires_at=expiry, account_id=7)

    monkeypatch.setattr(web, "engine", object())
    monkeypatch.setattr(web, "Session", FakeSession)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="session")
    if valid:
        assert web.account_session(credentials) == 7
    else:
        with pytest.raises(web.ApiProblem) as error:
            web.account_session(credentials)
        assert error.value.status_code == 401


def test_developer_key_lifecycle(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'access.db').as_posix()}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(web, "engine", engine)
    credentials = {"email": "Person@example.org", "password": "a-strong-test-password"}
    with TestClient(web.app) as client:
        assert client.post("/api/v1/developers/register", json=credentials).status_code == 201
        assert client.post("/api/v1/developers/register", json=credentials).status_code == 409
        assert (
            client.post(
                "/api/v1/developers/login", json={**credentials, "password": "wrong-password"}
            ).status_code
            == 401
        )
        login = client.post("/api/v1/developers/login", json=credentials)
        assert login.status_code == 200
        auth = {"Authorization": "Bearer " + login.json()["session_token"]}
        created = client.post("/api/v1/developers/keys", headers=auth)
        assert created.status_code == 201
        key = created.json()["key"]
        key_id = created.json()["id"]
        assert client.get("/api/v1/schemes", headers={"X-API-Key": key}).status_code == 200
        assert (
            client.get(
                "/api/v1/schemes/not-found?private_query=secret", headers={"X-API-Key": key}
            ).status_code
            == 404
        )
        with Session(engine) as session:
            session.add(
                ApiRequestLog(
                    key_id=key_id,
                    endpoint="/api/v1/schemes",
                    status_code=200,
                    duration_ms=1.0,
                    requested_at=datetime.now(UTC) - timedelta(days=1),
                )
            )
            session.commit()
        usage = client.get("/api/v1/developers/usage", headers=auth).json()
        assert usage["total_requests"] == 3
        assert usage["requests_today"] == 2
        assert usage["success_rate"] == 0.6667
        assert usage["average_duration_ms"] >= 0
        assert {item["path"] for item in usage["endpoints"]} == {
            "/api/v1/schemes",
            "/api/v1/schemes/{scheme_id}",
        }
        assert "secret" not in str(usage)
        other = {"email": "other@example.org", "password": "another-secure-password"}
        assert client.post("/api/v1/developers/register", json=other).status_code == 201
        other_token = client.post("/api/v1/developers/login", json=other).json()["session_token"]
        other_usage = client.get(
            "/api/v1/developers/usage", headers={"Authorization": "Bearer " + other_token}
        )
        assert other_usage.json()["total_requests"] == 0
        assert other_usage.json()["requests_today"] == 0
        assert other_usage.json()["success_rate"] is None
        assert (
            client.get("/api/v1/schemes", headers={"X-API-Key": web.DEMO_API_KEY}).status_code
            == 401
        )
        listing = client.get("/api/v1/developers/keys", headers=auth).json()
        assert key not in str(listing)
        assert client.delete(f"/api/v1/developers/keys/{key_id}", headers=auth).status_code == 200
        assert client.get("/api/v1/schemes", headers={"X-API-Key": key}).status_code == 401
        assert client.post("/api/v1/developers/logout", headers=auth).status_code == 200
        assert client.get("/api/v1/developers/keys", headers=auth).status_code == 401
    with Session(engine) as session:
        account = session.scalar(select(DeveloperAccount))
        stored_key = session.scalar(select(ApiKey))
        assert credentials["password"] not in account.password_hash
        assert key != stored_key.key_hash
        logs = session.scalars(select(ApiRequestLog)).all()
        assert len(logs) == 3
        assert all("secret" not in log.endpoint and key not in log.endpoint for log in logs)
    engine.dispose()


def test_key_rotation_ownership_and_atomic_rollback(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'rotation.db').as_posix()}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(web, "engine", engine)
    first = {"email": "owner@example.org", "password": "long-owner-password"}
    second = {"email": "other@example.org", "password": "long-other-password"}
    with TestClient(web.app, raise_server_exceptions=False) as client:
        for credentials in (first, second):
            assert client.post("/api/v1/developers/register", json=credentials).status_code == 201
        owner = client.post("/api/v1/developers/login", json=first).json()["session_token"]
        other = client.post("/api/v1/developers/login", json=second).json()["session_token"]
        auth = {"Authorization": "Bearer " + owner}
        other_auth = {"Authorization": "Bearer " + other}
        original = client.post("/api/v1/developers/keys", headers=auth).json()
        path = f"/api/v1/developers/keys/{original['id']}/rotate"
        assert client.post(path, headers=other_auth).status_code == 404
        with monkeypatch.context() as patch:
            patch.setattr(web, "new_token", lambda prefix: original["key"])
            assert client.post(path, headers=auth).status_code == 500
        assert (
            client.get("/api/v1/schemes", headers={"X-API-Key": original["key"]}).status_code == 200
        )
        response = client.post(path, headers=auth)
        assert response.status_code == 201
        replacement = response.json()["key"]
        assert replacement != original["key"]
        assert (
            client.get("/api/v1/schemes", headers={"X-API-Key": original["key"]}).status_code == 401
        )
        assert client.get("/api/v1/schemes", headers={"X-API-Key": replacement}).status_code == 200
        assert client.post(path, headers=auth).status_code == 409
        assert replacement not in client.get("/api/v1/developers/keys", headers=auth).text
    engine.dispose()
