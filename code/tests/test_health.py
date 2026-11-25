import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

import app.main as web
from app.storage import create_database


def test_readiness_reports_configured_dependencies(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'health.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(str(web.PROJECT_DIR / "alembic.ini")), "head")
    engine = create_database(database_url)
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "cache_client", None)
    with TestClient(web.app) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json()["checks"] == {"database": "ok", "redis": "not_configured"}
        assert ready.headers["cache-control"] == "no-store"
        command.downgrade(Config(str(web.PROJECT_DIR / "alembic.ini")), "20261115_09")
        assert client.get("/health/ready").json()["checks"]["database"] == "schema_mismatch"
        assert client.get("/health/ready").status_code == 503
    engine.dispose()


def test_readiness_detects_a_missing_table_even_at_the_current_revision(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'health-incomplete.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(str(web.PROJECT_DIR / "alembic.ini")), "head")
    engine = create_database(database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE datasets"))
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "cache_client", None)
    with TestClient(web.app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["database"] == "schema_unavailable"
        assert "datasets" not in response.text
    engine.dispose()


def test_readiness_fails_when_redis_is_unavailable(monkeypatch):
    class BrokenRedis:
        def ping(self):
            raise ConnectionError("offline")

    monkeypatch.setattr(web, "engine", None)
    monkeypatch.setattr(web, "cache_client", BrokenRedis())
    with TestClient(web.app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["redis"] == "unavailable"


@pytest.mark.parametrize("failure", ["operational", "pool_timeout"])
def test_database_failure_returns_safe_error_for_api_and_website(monkeypatch, caplog, failure):
    def unavailable():
        if failure == "operational":
            raise OperationalError("private SQL", {}, Exception("secret database detail"))
        raise SQLAlchemyTimeoutError("secret pool detail")

    monkeypatch.setattr(web, "engine", None)
    monkeypatch.setattr(web, "current_schemes", unavailable)
    with TestClient(web.app) as client:
        api = client.get("/api/v1/schemes", headers={"X-API-Key": web.DEMO_API_KEY})
        assert api.status_code == 503
        assert api.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert api.json()["error"]["request_id"]
        assert api.headers["cache-control"] == "no-store"
        page = client.get("/")
        assert page.status_code == 503
        assert "data service is temporarily unavailable" in page.text
        assert page.headers["cache-control"] == "no-store"
        assert "secret" not in api.text + page.text + caplog.text
        assert "private SQL" not in api.text + page.text + caplog.text


def test_unopenable_database_is_reported_as_unavailable(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'missing' / 'database.db').as_posix()}")
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "cache_client", None)
    with TestClient(web.app) as client:
        assert client.get("/").status_code == 503
        response = client.get("/api/v1/schemes", headers={"X-API-Key": "example"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert client.get("/health/ready").json()["checks"]["database"] == "unavailable"
    engine.dispose()
