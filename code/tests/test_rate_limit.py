from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError
from sqlalchemy.orm import Session

import app.main as web
from app.credentials import token_hash
from app.rate_limit import RedisRateLimiter
from app.storage import ApiKey, Base, DeveloperAccount, create_database, utc_now


class RedisStub:
    def __init__(self):
        self.counters = {}

    def eval(self, script, count, key, seconds):
        assert "INCR" in script and "EXPIRE" in script and count == 1
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key], seconds


def test_quota_is_per_key_and_rejection_has_retry_header(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'quota.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        owner = DeveloperAccount(email="owner@example.org", password_hash="unused")
        session.add(owner)
        session.flush()
        for key in ("first", "second"):
            session.add(
                ApiKey(
                    id=key,
                    account_id=owner.id,
                    key_hash=token_hash(key),
                    prefix=key,
                    created_at=utc_now(),
                )
            )
        session.commit()
    redis = RedisStub()
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "rate_limiter", RedisRateLimiter(redis, limit=1, window_seconds=30))
    with TestClient(web.app) as client:
        assert client.get("/api/v1/schemes", headers={"X-API-Key": "first"}).status_code == 200
        denied = client.get("/api/v1/schemes", headers={"X-API-Key": "first"})
        assert denied.status_code == 429
        assert denied.headers["retry-after"] == "30"
        assert denied.json()["error"]["code"] == "RATE_LIMITED"
        assert client.get("/api/v1/schemes", headers={"X-API-Key": "second"}).status_code == 200
        assert client.get("/api/v1/schemes", headers={"X-API-Key": "invalid"}).status_code == 401
    assert set(redis.counters) == {"bharatos:rate:first", "bharatos:rate:second"}
    engine.dispose()


def test_unavailable_limiter_returns_503(tmp_path, monkeypatch):
    class BrokenRedis:
        def eval(self, *args):
            raise ConnectionError("offline")

    engine = create_database(f"sqlite:///{(tmp_path / 'offline.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        account = DeveloperAccount(email="owner@example.org", password_hash="unused")
        session.add(account)
        session.flush()
        session.add(
            ApiKey(
                id="id",
                account_id=account.id,
                key_hash=token_hash("key"),
                prefix="key",
                created_at=utc_now(),
            )
        )
        session.commit()
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "rate_limiter", RedisRateLimiter(BrokenRedis()))
    with TestClient(web.app) as client:
        response = client.get("/api/v1/schemes", headers={"X-API-Key": "key"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "RATE_LIMIT_UNAVAILABLE"
    engine.dispose()


def test_auth_attempts_are_limited_without_storing_credentials(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'auth.db').as_posix()}")
    Base.metadata.create_all(engine)
    redis = RedisStub()
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "login_limiter", RedisRateLimiter(redis, limit=1, window_seconds=30))
    monkeypatch.setattr(
        web, "registration_limiter", RedisRateLimiter(redis, limit=1, window_seconds=30)
    )
    credentials = {"email": "private@example.org", "password": "a-long-password-123"}
    with TestClient(web.app) as client:
        assert client.post("/api/v1/developers/login", json=credentials).status_code == 401
        denied = client.post("/api/v1/developers/login", json=credentials)
        assert denied.status_code == 429
        assert denied.headers["retry-after"] == "30"
        # Registration has a separate quota.
        assert client.post("/api/v1/developers/register", json=credentials).status_code == 201
        assert client.post("/api/v1/developers/register", json=credentials).status_code == 429
    assert all(
        "private@example.org" not in key and "a-long-password" not in key for key in redis.counters
    )
    engine.dispose()


def test_auth_limiter_outage_fails_closed(tmp_path, monkeypatch):
    class BrokenRedis:
        def eval(self, *args):
            raise ConnectionError("offline")

    engine = create_database(f"sqlite:///{(tmp_path / 'auth-offline.db').as_posix()}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "login_limiter", RedisRateLimiter(BrokenRedis()))
    with TestClient(web.app) as client:
        response = client.post(
            "/api/v1/developers/login",
            json={
                "email": "person@example.org",
                "password": "a-long-password-123",
            },
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "RATE_LIMIT_UNAVAILABLE"
    engine.dispose()
