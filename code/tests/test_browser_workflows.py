"""Exercise the real developer portal and protected requests in Chromium."""

import json
import os
import socket
from datetime import UTC, datetime
from threading import Thread
from time import monotonic, sleep

import pytest
from playwright.sync_api import expect, sync_playwright
from sqlalchemy.orm import Session
from uvicorn import Config, Server

import app.main as web
from app.ingestion import ingest
from app.ogd_pincode import OgdPincodeCsvAdapter
from app.storage import create_database
from scripts.start_local import initialize_database, sqlite_url

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BROWSER_TESTS") != "1",
    reason="Install Chromium and set RUN_BROWSER_TESTS=1 to run browser checks",
)


@pytest.fixture
def developer_portal(tmp_path, monkeypatch):
    database = tmp_path / "browser.db"
    initialize_database(database)
    engine = create_database(sqlite_url(database))
    monkeypatch.setattr(web, "engine", engine)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = Server(Config(web.app, loop="asyncio", log_level="warning"))
        worker = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        worker.start()
        try:
            deadline = monotonic() + 10
            while not server.started and worker.is_alive() and monotonic() < deadline:
                sleep(0.02)
            assert server.started, "The test portal did not start"
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            worker.join(timeout=5)
            engine.dispose()


def test_developer_registers_runs_playground_and_revokes_key(developer_portal):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(f"{developer_portal}/developers", wait_until="domcontentloaded")
            page.get_by_label("Email").fill("developer@example.org")
            page.get_by_label("Password").fill("temporary-browser-test-password")
            page.get_by_role("button", name="Register", exact=True).click()
            expect(page.locator("#developer-message")).to_contain_text("Account created")
            page.get_by_role("button", name="Sign in", exact=True).click()
            page.get_by_role("button", name="Create key", exact=True).click()
            expect(page.locator("#new-key")).to_contain_text("bsk_")

            page.get_by_role("combobox", name="Endpoint").select_option("pincode")
            page.locator("#endpoint-parameter").fill("147004")
            page.get_by_role("button", name="Run request", exact=True).click()
            expect(page.locator("#request-status")).to_contain_text("200")
            payload = json.loads(page.locator("#api-response").inner_text())
            assert payload["data"]["pincode"] == "147004"
            assert payload["meta"]["api_version"] == "v1"
            expect(page.locator("#usage-today")).to_contain_text("Requests today (UTC): 1")
            expect(page.locator("#usage-today")).to_contain_text("100.0%")
            expect(page.locator("#usage-endpoints")).to_contain_text("/api/v1/locations/pincode/")

            page.get_by_role("button", name="Revoke key").click()
            expect(page.locator("#developer-key-list")).to_contain_text("revoked")
            page.get_by_role("button", name="Run request", exact=True).click()
            expect(page.locator("#request-status")).to_contain_text("401")
            assert json.loads(page.locator("#api-response").inner_text())["error"]["code"] == (
                "INVALID_API_KEY"
            )
        finally:
            browser.close()


def test_reference_authorizes_and_calls_api_without_external_assets(developer_portal):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.set_default_timeout(8000)
            outside_requests = []

            def stay_local(route):
                if route.request.url.startswith(f"{developer_portal}/"):
                    route.continue_()
                else:
                    outside_requests.append(route.request.url)
                    route.abort()

            page.route("**/*", stay_local)
            page.add_init_script("""
                window.blockedResources = [];
                document.addEventListener('securitypolicyviolation', event => {
                    window.blockedResources.push([event.violatedDirective, event.blockedURI]);
                });
            """)
            credentials = {"email": "reference@example.org", "password": "example-only-14-chars"}
            developers = f"{developer_portal}/api/v1/developers"
            assert page.request.post(f"{developers}/register", data=credentials).status == 201
            login = page.request.post(f"{developers}/login", data=credentials)
            assert login.status == 200
            issued = page.request.post(
                f"{developers}/keys",
                headers={"Authorization": f"Bearer {login.json()['session_token']}"},
            )
            assert issued.status == 201

            page.goto(f"{developer_portal}/reference", wait_until="domcontentloaded")
            expect(page.get_by_role("heading", name="BharatOS API", level=1)).to_be_visible()
            page.get_by_role("button", name="Authorize", exact=True).first.click()
            key_dialog = page.locator(".auth-container").filter(has_text="X-API-Key")
            key_dialog.locator("input").fill(issued.json()["key"])
            key_dialog.get_by_role("button", name="Apply credentials").click()
            key_dialog.get_by_role("button", name="Close", exact=True).click()

            operation = page.locator(".opblock").filter(
                has=page.locator('.opblock-summary-path[data-path="/api/v1/schemes"]')
            )
            operation.locator(".opblock-summary-control").click()
            operation.get_by_role("button", name="Try it out").click()
            with page.expect_response(
                lambda response: (
                    response.url.partition("?")[0] == f"{developer_portal}/api/v1/schemes"
                )
            ) as api_response:
                operation.get_by_role("button", name="Execute").click()
            response = api_response.value
            assert response.status == 200
            assert response.json()["meta"]["api_version"] == "v1"
            expect(operation.locator(".live-responses-table")).to_contain_text("200")
            assert not outside_requests
            assert page.evaluate("window.blockedResources") == []
        finally:
            browser.close()


def test_admin_shows_the_rejected_csv_line_without_source_values(
    developer_portal, tmp_path, monkeypatch
):
    token = "disposable-browser-admin-token-for-tests"
    monkeypatch.setattr(web, "ADMIN_TOKEN", token)
    snapshot = tmp_path / "invalid.csv"
    snapshot.write_text(
        "officename,pincode,district,statename\nPrivate fixture,123,D,S\n", encoding="utf-8"
    )
    with Session(web.engine) as session:
        with pytest.raises(ValueError, match="CSV line 2"):
            ingest(session, OgdPincodeCsvAdapter(snapshot, datetime.now(UTC).date()))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(f"{developer_portal}/admin", wait_until="domcontentloaded")
            page.get_by_label("Administrator token").fill(token)
            page.get_by_role("button", name="Load monitoring").click()
            runs = page.locator("#admin-runs")
            expect(runs).to_contain_text("INVALID_CSV_ROW (CSV line 2)")
            expect(runs).not_to_contain_text("Private fixture")
        finally:
            browser.close()
