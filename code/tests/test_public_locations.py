import hashlib

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.main as web
import app.pincode_mirror as mirror
from app.ingestion import ingest
from app.storage import Base, create_database


def test_public_lookup_validates_input_without_creating_a_session(monkeypatch):
    monkeypatch.setattr(web, "engine", None)
    with TestClient(web.app) as client:
        blank = client.get("/locations")
        assert blank.status_code == 200
        assert "Six-digit PIN code" in blank.text
        result = client.get("/locations", params={"pincode": "147004"})
        assert result.status_code == 200
        assert "Thapar College Patiala S.O" in result.text
        assert "Only one sample office" in result.text
        assert result.headers["cache-control"] == "no-store"
        assert "set-cookie" not in result.headers
        invalid = client.get("/locations", params={"pincode": "１２３４５６"})
        assert "six-digit PIN code using digits 0–9" in invalid.text
        unknown = client.get("/locations", params={"pincode": "999999"})
        assert "No record for this PIN code" in unknown.text
        api = client.get(
            "/api/v1/locations/pincode/１２３４５６", headers={"X-API-Key": web.DEMO_API_KEY}
        )
        assert api.status_code == 422


def test_public_lookup_displays_all_offices_and_historical_mirror_provenance(tmp_path, monkeypatch):
    csv_file = tmp_path / "mirror.csv"
    data = (
        b"officename,pincode,district,statename\n"
        b"Alpha Office,123456,One,State\nBeta Office,123456,Two,State\n"
    )
    csv_file.write_bytes(data)
    monkeypatch.setattr(mirror, "MIRROR_SHA256", hashlib.sha256(data).hexdigest())
    engine = create_database(f"sqlite:///{(tmp_path / 'locations.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest(session, mirror.PincodeMirrorAdapter(csv_file))
    monkeypatch.setattr(web, "engine", engine)
    with TestClient(web.app) as client:
        response = client.get("/locations", params={"pincode": "123456"})
        assert response.status_code == 200
        assert "Alpha Office" in response.text and "Beta Office" in response.text
        assert "Not independently verified" in response.text
        assert "05 May 2024" in response.text
        assert "historical third-party copy" in response.text
        assert "Original source listed by mirror" in response.text
        assert "set-cookie" not in response.headers
    engine.dispose()
