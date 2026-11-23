from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.main as web
from app.ingestion import ingest
from app.pib_transport import SOURCE_DATE, SOURCE_URL, PibTransportSnapshotAdapter
from app.storage import Base, StoredRecord, create_database


def test_transport_snapshot_is_repeatable_and_visible(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'transport.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert ingest(session, PibTransportSnapshotAdapter()).accepted == 1
        assert ingest(session, PibTransportSnapshotAdapter()).accepted == 1
        record = session.get(StoredRecord, ("scheme", "pib-pm-e-drive"))
        assert record.payload["source"]["url"] == SOURCE_URL
        assert record.payload["source"]["snapshot_date"] == SOURCE_DATE
        assert record.payload["source"]["freshness_status"] == "review_due"
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "cache_client", None)
    with TestClient(web.app) as client:
        response = client.get("/", params={"category": "Transport"})
        assert response.status_code == 200
        assert "PM E-DRIVE" in response.text
        detail = client.get("/schemes/pm-e-drive")
        assert detail.status_code == 200
        assert "Review needed" in detail.text
        assert "different conditions and end dates" in detail.text
    engine.dispose()


def test_transport_import_preserves_record_owned_by_another_adapter(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'collision.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest(session, PibTransportSnapshotAdapter())
        record = session.get(StoredRecord, ("scheme", "pib-pm-e-drive"))
        record.source_adapter = "another-source"
        session.commit()
        assert ingest(session, PibTransportSnapshotAdapter()).accepted == 0
        assert session.get(StoredRecord, ("scheme", "pib-pm-e-drive")).source_adapter == (
            "another-source"
        )
    engine.dispose()
