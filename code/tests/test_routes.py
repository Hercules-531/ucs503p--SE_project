import re
from datetime import date
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.main as web
from app.data import SCHEMES
from app.ingestion import SchemeSnapshotAdapter, ingest
from app.main import DEMO_API_KEY, app
from app.storage import Base, create_database

client = TestClient(app)
KEY_HEADER = {"X-API-Key": DEMO_API_KEY}


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/schemes/pm-kisan",
        "/developers",
        "/docs",
        "/admin",
        "/diagrams/index.html",
    ],
)
def test_user_facing_routes_load(path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert "Student project" in response.text


def test_unknown_scheme_page_returns_404() -> None:
    response = client.get("/schemes/not-real")
    assert response.status_code == 404
    assert "not in the prototype catalogue" in response.text


def test_anonymous_filtering_does_not_create_a_session() -> None:
    response = client.get("/", params={"q": "health", "audience": "Women"})
    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    assert "Janani Suraksha Yojana" in response.text


def test_state_filter_offers_clear_link() -> None:
    response = client.get("/", params={"state": "Punjab"})
    assert response.status_code == 200
    assert "Clear filters" in response.text
    assert 'value="Punjab" selected' in response.text
    assert 'value="Ladakh"' in response.text


@pytest.mark.parametrize("database_mode", [False, True])
def test_catalogue_pagination_preserves_filters(tmp_path, monkeypatch, database_mode):
    records = []
    for index in range(25):
        record = SCHEMES[0].model_copy(deep=True)
        record.id = f"fixture-{index:02}"
        record.slug = f"fixture-{index:02}"
        record.name = f"Page Fixture {index:02}"
        record.states, record.audiences = [], []
        records.append(record)
    records[-1].states = ["Punjab"]
    records[-1].audiences = ["OBC students"]

    class Fixture(SchemeSnapshotAdapter):
        def collect(self):
            return (record.model_dump(mode="json") for record in records)

    engine = None
    if database_mode:
        engine = create_database(f"sqlite:///{(tmp_path / 'pages.db').as_posix()}")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            ingest(session, Fixture())

        def reject_full_catalogue():
            pytest.fail("A paginated database request must not load the full catalogue")

        monkeypatch.setattr(web, "current_schemes", reject_full_catalogue)
    else:
        monkeypatch.setattr(web, "current_schemes", lambda: records)
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "cache_client", None)
    params = {"q": "Page Fixture", "state": "Punjab", "include_unknown": "true"}
    first = client.get("/", params=params)
    assert first.status_code == 200
    assert "25 potential matches" in first.text
    assert 'value="Punjab" selected' in first.text
    assert 'value="OBC students"' in first.text
    assert "24 included records have incomplete filter information" in first.text
    assert "Page 1 of 3" in first.text
    assert "Page Fixture 00" in first.text and "Page Fixture 12" not in first.text
    next_match = re.search(r'href="([^"]+)">Next</a>', first.text)
    assert next_match is not None
    next_link = unescape(next_match.group(1))
    assert parse_qs(urlsplit(next_link).query) == {
        "q": ["Page Fixture"],
        "state": ["Punjab"],
        "include_unknown": ["true"],
        "page": ["2"],
    }
    second = client.get(next_link)
    assert "Page 2 of 3" in second.text
    assert "Page Fixture 12" in second.text and "Page Fixture 00" not in second.text
    last = client.get("/", params={**params, "page": 99})
    assert "Page 3 of 3" in last.text and "Page Fixture 24" in last.text
    if engine is not None:
        engine.dispose()


def test_filters_explain_records_hidden_by_missing_information(monkeypatch):
    unknown = SCHEMES[0].model_copy(deep=True, update={"states": [], "audiences": []})
    monkeypatch.setattr(web, "engine", None)
    monkeypatch.setattr(web, "current_schemes", lambda: [unknown])
    response = client.get("/", params={"state": "Punjab", "audience": "Women"})
    assert response.status_code == 200
    assert "1 additional record has incomplete filter information" in response.text
    assert "Missing information does not mean ineligibility" in response.text
    assert "0 potential matches" in response.text
    assert "incomplete filter information" not in client.get("/").text
    for params in (
        {"state": "Punjab", "audience": "Women"},
        {"state": "Punjab", "audience": "Women", "limit": 1},
    ):
        api = client.get("/api/v1/schemes", params=params, headers=KEY_HEADER)
        assert api.status_code == 200
        assert api.json()["meta"]["uncertain_excluded_count"] == 1
    included = client.get(
        "/", params={"state": "Punjab", "audience": "Women", "include_unknown": "true"}
    )
    assert "1 included record has incomplete filter information" in included.text
    assert "State or audience details are unspecified" in included.text
    for params in (
        {"state": "Punjab", "audience": "Women", "include_unknown": "true"},
        {"state": "Punjab", "audience": "Women", "include_unknown": "true", "limit": 1},
    ):
        api = client.get("/api/v1/schemes", params=params, headers=KEY_HEADER)
        assert api.status_code == 200
        assert len(api.json()["data"]) == 1
        assert api.json()["meta"]["uncertain_included_count"] == 1
        assert api.json()["meta"]["uncertain_excluded_count"] == 0


def test_api_requires_exact_demo_key(monkeypatch) -> None:
    def reject_data_access():
        pytest.fail("Requests without a valid key must not read the catalogue")

    monkeypatch.setattr(web, "current_schemes", reject_data_access)
    missing = client.get("/api/v1/schemes")
    invalid = client.get("/api/v1/schemes", headers={"X-API-Key": "wrong"})
    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.json()["error"]["code"] == "INVALID_API_KEY"
    assert missing.json()["error"]["request_id"]


def test_openapi_documents_distinct_security_schemes_and_errors() -> None:
    spec = client.get("/openapi.json").json()
    schemes = spec["components"]["securitySchemes"]
    assert schemes["ApiKey"]["name"] == "X-API-Key"
    assert schemes["DeveloperSession"]["scheme"] == "bearer"
    data = spec["paths"]["/api/v1/schemes"]["get"]
    assert {"ApiKey": []} in data["security"]
    assert {"q", "category", "state", "audience"}.issubset(
        {parameter["name"] for parameter in data["parameters"]}
    )
    assert {"200", "401", "429"}.issubset(data["responses"])
    assert (
        data["responses"]["401"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ErrorEnvelope"
    )
    keys = spec["paths"]["/api/v1/developers/keys"]["get"]
    assert {"DeveloperSession": []} in keys["security"]
    reference = client.get("/reference")
    assert reference.status_code == 200
    assert 'data-openapi-url="/openapi.json"' in reference.text
    assert 'src="/static/vendor/swagger-ui/swagger-ui-bundle.js"' in reference.text


def test_browser_security_headers_keep_portal_and_reference_same_origin(monkeypatch) -> None:
    monkeypatch.setattr(web, "engine", None)
    for path in (
        "/",
        "/locations?pincode=147004",
        "/developers",
        "/reference",
        "/diagrams/index.html",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "SAMEORIGIN"
        policy = response.headers["content-security-policy"]
        assert "default-src 'self'" in policy
        assert "frame-ancestors 'self'" in policy
        assert "object-src 'none'" in policy
        assert "'unsafe-eval'" not in policy
        if path == "/diagrams/index.html":
            assert "script-src 'none'" in policy
        else:
            assert "'unsafe-inline'" not in policy

    api = client.get("/api/v1/admin/overview")
    assert api.status_code == 503
    assert api.headers["cache-control"] == "no-store"
    assert api.headers["x-content-type-options"] == "nosniff"


def test_openapi_documents_developer_and_admin_responses() -> None:
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    assert spec["components"]["securitySchemes"]["AdminToken"]["name"] == "X-Admin-Token"

    expected = [
        ("developers/register", "post", "201", {"message"}, None, {"409", "422", "429", "503"}),
        (
            "developers/login",
            "post",
            "200",
            {"session_token", "expires_at"},
            None,
            {"401", "422", "429", "503"},
        ),
        ("developers/logout", "post", "200", {"message"}, "DeveloperSession", {"401", "503"}),
        (
            "developers/keys",
            "post",
            "201",
            {"id", "key", "message"},
            "DeveloperSession",
            {"401", "503"},
        ),
        ("developers/keys", "get", "200", {"keys"}, "DeveloperSession", {"401", "503"}),
        (
            "developers/usage",
            "get",
            "200",
            {"total_requests", "endpoints"},
            "DeveloperSession",
            {"401", "503"},
        ),
        (
            "developers/keys/{key_id}",
            "delete",
            "200",
            {"message"},
            "DeveloperSession",
            {"401", "404", "503"},
        ),
        (
            "developers/keys/{key_id}/rotate",
            "post",
            "201",
            {"id", "key", "message"},
            "DeveloperSession",
            {"401", "404", "409", "503"},
        ),
        (
            "admin/overview",
            "get",
            "200",
            {"recent_ingestion_runs", "sources", "cache", "alerts"},
            "AdminToken",
            {"401", "503"},
        ),
        ("admin/source-checks", "post", "200", {"source_checks"}, "AdminToken", {"401", "503"}),
    ]
    for path, method, success, fields, security, errors in expected:
        operation = spec["paths"][f"/api/v1/{path}"][method]
        assert operation.get("security", []) == ([{security: []}] if security else [])
        responses = operation["responses"]
        output_schema = responses[success]["content"]["application/json"]["schema"]["$ref"]
        assert fields <= schemas[output_schema.rsplit("/", 1)[1]]["properties"].keys()
        for status in errors:
            assert (
                responses[status]["content"]["application/json"]["schema"]["$ref"]
                == "#/components/schemas/ErrorEnvelope"
            )
        if "429" in errors:
            assert "Retry-After" in responses["429"]["headers"]

    key_items = schemas["DeveloperKeysResponse"]["properties"]["keys"]["items"]["$ref"]
    assert set(schemas[key_items.rsplit("/", 1)[1]]["properties"]) == {"id", "prefix", "revoked"}
    assert schemas["DeveloperCredentials"]["properties"]["password"]["writeOnly"] is True


def test_invalid_api_request_uses_error_envelope_without_echoing_secrets() -> None:
    response = client.post(
        "/api/v1/developers/register", json={"email": "not-an-email", "password": "secret"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert "secret" not in response.text


def test_scheme_list_uses_standard_envelope_and_filters() -> None:
    response = client.get("/api/v1/schemes", params={"q": "health"}, headers=KEY_HEADER)
    payload = response.json()
    assert response.status_code == 200
    assert payload["meta"]["api_version"] == "v1"
    assert payload["meta"]["environment"] == "prototype"
    assert payload["meta"]["result_count"] == 2
    assert len(payload["data"]) == 2
    assert all(item["source"]["url"] for item in payload["data"])


def test_scheme_pagination_is_ordered_and_validated() -> None:
    first = client.get("/api/v1/schemes", params={"limit": 1, "q": "health"}, headers=KEY_HEADER)
    second = client.get(
        "/api/v1/schemes", params={"limit": 1, "offset": 1, "q": "health"}, headers=KEY_HEADER
    )
    assert first.status_code == second.status_code == 200
    pages = first.json(), second.json()
    assert [page["meta"]["total_count"] for page in pages] == [2, 2]
    assert all(page["meta"]["result_count"] == 1 for page in pages)
    assert pages[0]["data"][0]["id"] < pages[1]["data"][0]["id"]
    assert client.get("/api/v1/schemes", params={"limit": 0}, headers=KEY_HEADER).status_code == 422
    assert (
        client.get("/api/v1/schemes", params={"limit": 101}, headers=KEY_HEADER).status_code == 422
    )
    assert (
        client.get("/api/v1/schemes", params={"offset": 1}, headers=KEY_HEADER).status_code == 422
    )
    empty = client.get("/api/v1/schemes", params={"limit": 1, "offset": 100}, headers=KEY_HEADER)
    assert empty.json()["data"] == []
    assert empty.json()["meta"]["total_count"] == len(SCHEMES)


def test_scheme_list_reads_one_catalogue_and_uses_returned_provenance(monkeypatch):
    records = [SCHEMES[0].model_copy(deep=True), SCHEMES[1].model_copy(deep=True)]
    records[0].source.last_verified = date(2024, 1, 1)
    records[1].source.last_verified = date(2025, 1, 1)
    calls = []

    def get_catalogue():
        calls.append(1)
        return records

    monkeypatch.setattr(web, "current_schemes", get_catalogue)
    response = client.get("/api/v1/schemes", params={"q": "health"}, headers=KEY_HEADER)
    assert response.status_code == 200
    assert response.json()["meta"]["last_verified"] == "2025-01-01"
    assert len(calls) == 1
    calls.clear()
    empty = client.get("/api/v1/schemes", params={"q": "no match"}, headers=KEY_HEADER)
    assert empty.json()["data"] == []
    assert empty.json()["meta"]["last_verified"] == "2024-01-01"
    assert len(calls) == 1


def test_empty_scheme_catalogue_has_no_fabricated_verification_date(monkeypatch):
    monkeypatch.setattr(web, "current_schemes", lambda: [])
    response = client.get("/api/v1/schemes", headers=KEY_HEADER)
    assert response.status_code == 200
    assert response.json()["meta"]["last_verified"] is None


def test_catalogue_metadata_is_unknown_if_a_result_has_no_verification_date(monkeypatch):
    records = [SCHEMES[0].model_copy(deep=True), SCHEMES[1].model_copy(deep=True)]
    records[0].source.last_verified = None
    monkeypatch.setattr(web, "current_schemes", lambda: records)
    response = client.get("/api/v1/schemes", headers=KEY_HEADER)
    assert response.status_code == 200
    assert response.json()["meta"]["last_verified"] is None


def test_scheme_pages_handle_unverified_source_dates(monkeypatch):
    record = SCHEMES[0].model_copy(deep=True)
    record.source.last_verified = None
    record.source.freshness_status = "unknown"
    monkeypatch.setattr(web, "current_schemes", lambda: [record])
    home = client.get("/")
    detail = client.get(f"/schemes/{record.slug}")
    assert home.status_code == 200
    assert "Review needed" in home.text
    assert detail.status_code == 200
    assert "Not independently verified" in detail.text


def test_scheme_detail_displays_summary_relevance_and_source():
    record = SCHEMES[0]
    response = client.get(f"/schemes/{record.slug}")
    assert response.status_code == 200
    rendered = unescape(response.text)
    assert record.summary in rendered
    assert record.eligibility_summary in rendered
    assert str(record.source.url) in rendered
    assert record.source.last_verified.strftime("%d %b %Y") in rendered


def test_scheme_detail_api_handles_success_and_missing_record() -> None:
    success = client.get("/api/v1/schemes/scheme-pm-kisan", headers=KEY_HEADER)
    missing = client.get("/api/v1/schemes/not-real", headers=KEY_HEADER)
    assert success.status_code == 200
    assert success.json()["data"]["short_name"] == "PM-KISAN"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "SCHEME_NOT_FOUND"


def test_pincode_api_validates_shape_and_prototype_coverage() -> None:
    success = client.get("/api/v1/locations/pincode/147004", headers=KEY_HEADER)
    invalid = client.get("/api/v1/locations/pincode/ABC", headers=KEY_HEADER)
    missing = client.get("/api/v1/locations/pincode/999999", headers=KEY_HEADER)
    assert success.status_code == 200
    assert success.json()["data"]["office_name"] == "Thapar College Patiala S.O"
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_PINCODE"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PINCODE_NOT_FOUND"
