import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.main as web
import app.pincode_mirror as mirror
from app.credentials import token_hash
from app.ingestion import LocationSnapshotAdapter, ingest
from app.monitoring import source_summaries
from app.storage import ApiKey, Base, DeveloperAccount, create_database, read_records, utc_now


def test_mirror_import_preserves_unverified_provenance(tmp_path, monkeypatch):
    csv_path = tmp_path / "mirror.csv"
    contents = b"officename,pincode,district,statename\nOffice,123456,District,State\n"
    csv_path.write_bytes(contents)
    monkeypatch.setattr(mirror, "MIRROR_SHA256", hashlib.sha256(contents).hexdigest())
    engine = create_database(f"sqlite:///{(tmp_path / 'mirror.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert ingest(session, mirror.PincodeMirrorAdapter(csv_path)).accepted == 1
        assert source_summaries(session)[0]["oldest_verified"] is None
        account = DeveloperAccount(email="fixture@example.org", password_hash="unused")
        session.add(account)
        session.flush()
        session.add(
            ApiKey(
                id="fixture",
                account_id=account.id,
                key_hash=token_hash("test-key"),
                prefix="test",
                created_at=utc_now(),
            )
        )
        session.commit()
    monkeypatch.setattr(web, "engine", engine)
    monkeypatch.setattr(web, "rate_limiter", None)
    with TestClient(web.app) as client:
        response = client.get("/api/v1/locations/pincode/123456", headers={"X-API-Key": "test-key"})
        assert response.status_code == 200
        source = response.json()["data"]["source"]
        assert source["provenance_kind"] == "third_party_mirror"
        assert source["url"] == mirror.MIRROR_URL
        assert source["original_source_url"] == mirror.SOURCE_URL
        assert source["freshness_status"] == "review_due"
        assert source["review_reason"] == "unverified_mirror"
        assert source["last_verified"] is None
        assert source["snapshot_date"] == "2024-05-05"
        assert source["snapshot_sha256"] == hashlib.sha256(contents).hexdigest()
        assert response.json()["meta"]["last_verified"] is None
        assert "not an official verification" in source["verification_note"]
    engine.dispose()


def test_mirror_rejects_changed_bytes(tmp_path):
    path = tmp_path / "modified.csv"
    path.write_text("officename,pincode,district,statename\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        list(mirror.PincodeMirrorAdapter(path).collect())


def test_mirror_preserves_records_owned_by_other_sources(tmp_path, monkeypatch):
    path = tmp_path / "mirror.csv"
    data = (
        b"officename,pincode,district,statename\n"
        b"Mirror Office,147004,Patiala,Punjab\n"
        b"Another Office,123456,District,State\n"
    )
    path.write_bytes(data)
    monkeypatch.setattr(mirror, "MIRROR_SHA256", hashlib.sha256(data).hexdigest())
    engine = create_database(f"sqlite:///{(tmp_path / 'ownership.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest(session, LocationSnapshotAdapter())
        before = {r["pincode"]: r for r in read_records(session, "location")}
        assert ingest(session, mirror.PincodeMirrorAdapter(path)).accepted == 1
        after = {r["pincode"]: r for r in read_records(session, "location")}
        assert after["147004"] == before["147004"]
        assert after["123456"]["source"]["provenance_kind"] == "third_party_mirror"
        assert ingest(session, mirror.PincodeMirrorAdapter(path)).accepted == 1
    engine.dispose()
