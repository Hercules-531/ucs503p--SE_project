from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.main as web
from app.credentials import token_hash
from app.ingestion import ingest
from app.pib_environment import SOURCE_DATE, SOURCE_URL, PibEnvironmentSnapshotAdapter
from app.storage import ApiKey, Base, DeveloperAccount, StoredRecord, create_database, utc_now


def test_environment_snapshot_ingests_and_is_available_through_ui_and_api(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'environment.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert ingest(session, PibEnvironmentSnapshotAdapter()).accepted == 1
        assert ingest(session, PibEnvironmentSnapshotAdapter()).accepted == 1
        record = session.get(StoredRecord, ("scheme", "pib-ncap"))
        assert record.payload["source"]["url"] == SOURCE_URL
        assert record.payload["source"]["snapshot_date"] == SOURCE_DATE
        assert record.payload["source"]["freshness_status"] == "review_due"
        account = DeveloperAccount(email="environment@example.org", password_hash="unused")
        session.add(account)
        session.flush()
        session.add(
            ApiKey(
                id="env",
                account_id=account.id,
                key_hash=token_hash("env-key"),
                prefix="env",
                created_at=utc_now(),
            )
        )
        session.commit()
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "cache_client", None)
    monkeypatch.setattr(web, "rate_limiter", None)
    with TestClient(web.app) as client:
        page = client.get("/", params={"category": "Environment"})
        assert "National Clean Air Programme" in page.text
        detail = client.get("/schemes/national-clean-air-programme")
        assert "not an individual payment" in detail.text
        assert "Review needed" in detail.text
        response = client.get(
            "/api/v1/schemes", params={"category": "Environment"}, headers={"X-API-Key": "env-key"}
        )
        assert response.status_code == 200
        assert [item["id"] for item in response.json()["data"]] == ["pib-ncap"]
    engine.dispose()
