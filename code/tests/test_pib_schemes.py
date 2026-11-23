from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.main as web
from app.credentials import token_hash
from app.data import SCHEMES
from app.ingestion import SchemeSnapshotAdapter, ingest
from app.pib_schemes import POLICY_URL, SOURCE_DATE, SOURCE_URL, PibSchemeSnapshotAdapter
from app.storage import ApiKey, Base, DeveloperAccount, create_database, utc_now


def test_pib_snapshot_ingests_and_serves_historical_source(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'pib.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert ingest(session, PibSchemeSnapshotAdapter()).accepted == 14
        assert ingest(session, PibSchemeSnapshotAdapter()).accepted == 14
        owner = DeveloperAccount(email="fixture@example.org", password_hash="unused")
        session.add(owner)
        session.flush()
        session.add(
            ApiKey(
                id="fixture",
                account_id=owner.id,
                key_hash=token_hash("fixture-key"),
                prefix="fixture",
                created_at=utc_now(),
            )
        )
        session.commit()
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "cache_client", None)
    monkeypatch.setattr(web, "rate_limiter", None)
    with TestClient(web.app) as client:
        response = client.get("/api/v1/schemes", headers={"X-API-Key": "fixture-key"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 14
        for params in ({"state": "Punjab"}, {"state": "Punjab", "limit": 1}):
            filtered = client.get(
                "/api/v1/schemes", params=params, headers={"X-API-Key": "fixture-key"}
            )
            assert filtered.status_code == 200
            assert filtered.json()["data"] == []
            assert filtered.json()["meta"]["uncertain_excluded_count"] == 14
        included = client.get(
            "/api/v1/schemes",
            params={"state": "Punjab", "limit": 1, "include_unknown": "true"},
            headers={"X-API-Key": "fixture-key"},
        )
        assert included.json()["meta"]["total_count"] == 14
        assert included.json()["meta"]["uncertain_included_count"] == 14
        assert included.json()["meta"]["uncertain_excluded_count"] == 0
        assert len(included.json()["data"]) == 1
        assert {"ACABC", "AIF", "PMMY", "PMEGP", "NAMASTE"}.issubset(
            {item["short_name"] for item in data}
        )
        assert not {item["id"] for item in data}.intersection(item.id for item in SCHEMES)
        assert not {item["slug"] for item in data}.intersection(item.slug for item in SCHEMES)
        for item in data:
            assert item["source"]["url"] == SOURCE_URL
            assert item["source"]["license_url"] == POLICY_URL
            assert item["source"]["last_verified"] == SOURCE_DATE
            assert item["source"]["freshness_status"] == "review_due"
            assert item["states"] == []
            assert item["audiences"] == []
        detail = client.get("/schemes/pradhan-mantri-mudra-yojana")
        assert detail.status_code == 200
        assert "Review needed" in detail.text
        assert "Geographic scope not specified" in detail.text
        assert "Audience is not specified in this snapshot" in detail.text
        assert "Current snapshot" not in detail.text
        assert (
            client.get(
                "/api/v1/schemes",
                params={"category": "Energy"},
                headers={"X-API-Key": "fixture-key"},
            ).json()["meta"]["result_count"]
            == 1
        )
    engine.dispose()


def test_pib_snapshot_and_default_catalogue_do_not_duplicate_svanidhi(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'combined.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert ingest(session, SchemeSnapshotAdapter()).accepted == 8
        assert ingest(session, PibSchemeSnapshotAdapter()).accepted == 14
        from app.storage import read_records

        records = read_records(session, "scheme")
        assert len(records) == 22
        assert sum("svanidhi" in record["slug"] for record in records) == 1
    engine.dispose()
