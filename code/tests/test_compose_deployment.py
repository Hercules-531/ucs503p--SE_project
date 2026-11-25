"""Verify the localhost HTTPS profile with Docker and a disposable database."""

import os
import ssl
import subprocess
from pathlib import Path
from secrets import token_hex
from time import monotonic, sleep
from uuid import uuid4

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
CA_PATH = "/data/caddy/pki/authorities/local/root.crt"


@pytest.fixture
def compose_project(tmp_path):
    project = f"bharatos-test-{uuid4().hex[:12]}"
    web_password = token_hex(24)
    admin_token = token_hex(24)
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("COMPOSE_")
    }
    environment.update(
        POSTGRES_PASSWORD=token_hex(24),
        ADMIN_TOKEN=admin_token,
        WEB_DATABASE_URL=f"postgresql+psycopg://bharatos_web:{web_password}@db:5432/bharatos",
        WEB_HTTP_PORT="0",
        TLS_PORT="0",
    )
    env_file = tmp_path / "test.env"
    env_file.touch()

    def compose(*args, input_text=None, check=True):
        process = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(env_file),
                "-p",
                project,
                "--profile",
                "tls",
                *args,
            ],
            cwd=ROOT,
            env=environment,
            input=input_text,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=240,
        )
        if check and process.returncode:
            output = process.stderr + process.stdout
            for secret in (web_password, admin_token, environment["POSTGRES_PASSWORD"]):
                output = output.replace(secret, "[redacted]")
            pytest.fail(f"Docker Compose {' '.join(args)} failed:\n{output}", pytrace=False)
        return process

    def sql(statement):
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
            "bharatos",
            input_text=statement,
        ).stdout.strip()

    try:
        compose("up", "--build", "--detach", "setup")
        compose("wait", "setup")
        sql(f"CREATE ROLE bharatos_web LOGIN PASSWORD '{web_password}';")
        sql((ROOT / "deploy/web_database_grants.sql").read_text(encoding="utf-8"))
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
            yield client, admin_token, sql
    finally:
        # The random project name scopes deletion to this test's containers and volumes.
        compose("down", "--volumes", "--rmi", "local", "--remove-orphans")


@pytest.mark.skipif(os.getenv("RUN_COMPOSE_TESTS") != "1", reason="Requires local Docker Compose")
def test_compose_https_with_restricted_database_role(compose_project):
    client, admin_token, sql = compose_project
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
