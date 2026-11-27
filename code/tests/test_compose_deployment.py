"""Verify the localhost HTTPS profile with Docker and a disposable database."""

import hashlib
import os
import ssl
import subprocess
from pathlib import Path
from secrets import token_hex
from time import monotonic, sleep
from uuid import uuid4

import httpx
import pytest

from scripts.database_backup import backup, restore_to_new_database

ROOT = Path(__file__).resolve().parents[1]
CA_PATH = "/data/caddy/pki/authorities/local/root.crt"


@pytest.fixture
def compose_project(tmp_path, monkeypatch):
    project = f"bharatos-test-{uuid4().hex[:12]}"
    web_password = token_hex(24)
    admin_token = token_hex(24)
    postgres_password = token_hex(24)
    web_url = f"postgresql+psycopg://bharatos_web:{web_password}@db:5432"
    for name in list(os.environ):
        if name.startswith("COMPOSE_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("COMPOSE_DISABLE_ENV_FILE", "1")
    monkeypatch.setenv("POSTGRES_PASSWORD", postgres_password)
    monkeypatch.setenv("ADMIN_TOKEN", admin_token)
    monkeypatch.delenv("BHARATOS_DATABASE", raising=False)
    monkeypatch.setenv("WEB_DATABASE_URL", f"{web_url}/bharatos")
    monkeypatch.setenv("WEB_HTTP_PORT", "0")
    monkeypatch.setenv("TLS_PORT", "0")

    def compose(*args, input_text=None, check=True):
        process = subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                project,
                "--profile",
                "tls",
                *args,
            ],
            cwd=ROOT,
            input=input_text,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=240,
        )
        if check and process.returncode:
            output = process.stderr + process.stdout
            for secret in (web_password, admin_token, postgres_password):
                output = output.replace(secret, "[redacted]")
            pytest.fail(f"Docker Compose {' '.join(args)} failed:\n{output}", pytrace=False)
        return process

    def sql(statement, *, database="bharatos"):
        return compose(
            "exec",
            "-T",
            "db",
            "psql",
            "-XAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "bharatos",
            "-d",
            database,
            input_text=statement,
        ).stdout.strip()

    grants = (ROOT / "deploy/web_database_grants.sql").read_text(encoding="utf-8")

    def use_recovered_database(database):
        sql(grants, database=database)
        monkeypatch.setenv("BHARATOS_DATABASE", database)
        stale_connection = compose(
            "run", "--rm", "--no-deps", "web", "python", "-c", "import app.main", check=False
        )
        assert stale_connection.returncode != 0
        assert "The web connection must match BHARATOS_DATABASE" in stale_connection.stderr
        monkeypatch.setenv("WEB_DATABASE_URL", f"{web_url}/{database}")
        compose("up", "--wait", "--wait-timeout", "80", "web")

    try:
        compose("up", "--build", "--detach", "setup")
        compose("wait", "setup")
        sql(f"CREATE ROLE bharatos_web LOGIN PASSWORD '{web_password}';")
        sql(grants)
        compose("run", "--rm", "--no-deps", "setup", "python", "-m", "scripts.ingest_snapshots")
        compose("up", "--build", "--wait", "--wait-timeout", "80", "proxy")

        address = compose("port", "proxy", "443").stdout.strip()
        host, port = address.rsplit(":", 1)
        assert host == "127.0.0.1"
        ca_path = tmp_path / "caddy-root.crt"
        deadline = monotonic() + 20
        while compose("exec", "-T", "proxy", "test", "-s", CA_PATH, check=False).returncode:
            if monotonic() >= deadline:
                pytest.fail("Caddy did not create the local CA certificate.")
            sleep(0.5)
        compose("cp", f"proxy:{CA_PATH}", str(ca_path))
        tls = ssl.create_default_context(cafile=ca_path)
        with httpx.Client(
            base_url=f"https://localhost:{port}", verify=tls, trust_env=False
        ) as client:
            yield client, admin_token, sql, project, use_recovered_database, compose
    finally:
        # The random project name scopes deletion to this test's containers and volumes.
        compose(
            "--profile",
            "ingestion",
            "--profile",
            "monitoring",
            "down",
            "--volumes",
            "--rmi",
            "local",
            "--remove-orphans",
        )


@pytest.mark.skipif(os.getenv("RUN_COMPOSE_TESTS") != "1", reason="Requires local Docker Compose")
def test_compose_https_with_restricted_database_role(compose_project, tmp_path, monkeypatch):
    client, admin_token, sql, project, use_recovered_database, compose = compose_project
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "checks": {"database": "ok", "redis": "ok"}}
    assert client.get("/schemes/pm-kisan").status_code == 200

    portal = client.get("/developers")
    assert portal.status_code == 200
    assert 'href="/static/styles.css"' in portal.text
    assert 'src="/static/app.js"' in portal.text
    assert client.get("/static/styles.css").headers["content-type"].startswith("text/css")
    assert client.get("/static/app.js").status_code == 200

    account = {"email": "compose-test@example.org", "password": token_hex(24)}
    assert client.post("/api/v1/developers/register", json=account).status_code == 201
    login = client.post("/api/v1/developers/login", json=account)
    assert login.status_code == 200
    session = {"Authorization": f"Bearer {login.json()['session_token']}"}
    issued = client.post("/api/v1/developers/keys", headers=session)
    assert issued.status_code == 201
    key = {"X-API-Key": issued.json()["key"]}

    for _ in range(2):
        catalogue = client.get("/api/v1/schemes", headers=key)
        assert catalogue.status_code == 200
        assert catalogue.json()["data"][0]["source"]["url"].startswith("https://")
    usage = client.get("/api/v1/developers/usage", headers=session)
    assert usage.json()["total_requests"] == 2
    assert client.get("/api/v1/admin/overview").status_code == 401
    overview = client.get("/api/v1/admin/overview", headers={"X-Admin-Token": admin_token})
    assert overview.status_code == 200
    assert overview.json()["cache"]["hits"] >= 1
    assert overview.json()["recent_ingestion_runs"]

    privileges = sql("""
        SELECT EXISTS (SELECT FROM pg_stat_activity WHERE usename = 'bharatos_web'),
               has_table_privilege('bharatos_web', 'normalized_records', 'SELECT'),
               has_table_privilege('bharatos_web', 'normalized_records', 'DELETE'),
               has_any_column_privilege('bharatos_web', 'normalized_records', 'INSERT, UPDATE'),
               has_any_column_privilege('bharatos_web', 'alembic_version', 'INSERT, UPDATE'),
               has_schema_privilege('bharatos_web', 'public', 'CREATE');
    """)
    assert privileges == "t|t|f|f|f|f"
    key_id = issued.json()["id"]
    assert client.delete(f"/api/v1/developers/keys/{key_id}", headers=session).status_code == 200
    assert client.get("/api/v1/schemes", headers=key).status_code == 401

    active_key = client.post("/api/v1/developers/keys", headers=session)
    assert active_key.status_code == 201
    archive = tmp_path / "recovery.dump"
    backup(archive, project)

    truncated = tmp_path / "truncated.dump"
    contents = archive.read_bytes()
    truncated.write_bytes(contents[: len(contents) // 2])
    with pytest.raises(subprocess.CalledProcessError):
        restore_to_new_database(truncated, "bharatos_restore_invalid", project)
    assert (
        sql("SELECT count(*) FROM pg_database WHERE datname = 'bharatos_restore_invalid';") == "0"
    )

    restored = "bharatos_restore_check"
    restore_to_new_database(archive, restored, project)
    use_recovered_database(restored)
    assert client.get("/health/ready").json() == ready.json()
    assert (
        sql(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = 'bharatos_restore_check' "
            "AND usename = 'bharatos_web';"
        )
        != "0"
    )
    recovered_usage = client.get("/api/v1/developers/usage", headers=session)
    assert recovered_usage.status_code == 200
    assert recovered_usage.json()["total_requests"] == 2
    assert client.get("/api/v1/schemes", headers=key).status_code == 401
    recovered_catalogue = client.get(
        "/api/v1/schemes", headers={"X-API-Key": active_key.json()["key"]}
    )
    assert recovered_catalogue.status_code == 200
    assert recovered_catalogue.json()["data"] == catalogue.json()["data"]
    assert sql("SELECT count(*) FROM api_request_logs;") == "2"
    assert sql("SELECT count(*) FROM api_request_logs;", database=restored) == "3"

    snapshot = tmp_path / "recovery-pins.csv"
    snapshot.write_bytes(
        b"officename,pincode,district,statename\n"
        b"Recovery Test Post Office,123456,Example District,Delhi\n"
    )
    monkeypatch.setenv("PIN_SNAPSHOT_PATH", str(snapshot))
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    compose(
        "--profile",
        "ingestion",
        "run",
        "--build",
        "--rm",
        "--no-deps",
        "scheduler",
        "python",
        "-m",
        "scripts.schedule_pincode",
        "/snapshots/pincode.csv",
        "--verified-on",
        "2026-01-01",
        "--sha256",
        digest,
        "--once",
    )
    pin = client.get("/locations", params={"pincode": "123456"})
    assert pin.status_code == 200 and "Recovery Test Post Office" in pin.text
    pin_record = "SELECT count(*) FROM normalized_records WHERE identifier = '123456';"
    assert sql(pin_record) == "0"

    # Use the actual monitoring service connection while keeping source probes off the network.
    compose(
        "--profile",
        "monitoring",
        "run",
        "--build",
        "--rm",
        "--no-deps",
        "source-monitor",
        "python",
        "-c",
        """
import os
import httpx
from sqlalchemy.orm import Session
from app.source_checks import run_source_checks
from app.storage import create_database

with Session(create_database(os.environ['DATABASE_URL'])) as session:
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        run_source_checks(session, client)
""",
    )
    monitored = client.get("/api/v1/admin/overview", headers={"X-Admin-Token": admin_token})
    checks = monitored.json()["source_checks"]
    assert checks and all(check["status"] == "accessible" for check in checks)
    assert sql("SELECT count(*) FROM source_probes;") == "0"

    next_archive = tmp_path / "post-recovery.dump"
    backup(next_archive, project, database=restored)
    restore_to_new_database(next_archive, "bharatos_restore_recheck", project)
    assert sql("SELECT count(*) FROM api_request_logs;", database="bharatos_restore_recheck") == "3"
    assert sql(pin_record, database="bharatos_restore_recheck") == "1"
