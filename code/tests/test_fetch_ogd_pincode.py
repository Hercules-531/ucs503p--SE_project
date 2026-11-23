import csv
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from app.ogd_pincode import OgdPincodeCsvAdapter
from scripts.fetch_ogd_pincode import fetch_snapshot


def test_fetch_writes_all_pages_without_persisting_key(tmp_path):
    resource = str(uuid.uuid4())
    secret = "synthetic-secret"
    calls = []

    def handler(request):
        calls.append(request)
        offset = int(request.url.params["offset"])
        assert request.url.host == "api.data.gov.in"
        assert request.url.path == f"/resource/{resource}"
        assert request.url.params["api-key"] == secret
        record = {
            "OfficeName": f"Office {offset}",
            "Pincode": "123456",
            "District": "Example",
            "StateName": "State",
        }
        return httpx.Response(
            200, json={"total": 2, "offset": offset, "count": 1, "records": [record]}
        )

    destination = tmp_path / "snapshot.csv"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch_snapshot(resource, secret, destination, client) == 2
    with destination.open(encoding="utf-8", newline="") as file:
        records = list(csv.DictReader(file))
    assert [record["officename"] for record in records] == ["Office 0", "Office 1"]
    assert secret not in destination.read_text(encoding="utf-8")
    assert len(calls) == 2
    records = list(OgdPincodeCsvAdapter(destination, datetime.now(UTC).date()).collect())
    assert len(records) == 1
    assert len(records[0]["offices"]) == 2


@pytest.mark.parametrize("failure", ["http", "wrong_offset", "changed_total", "invalid_record"])
def test_fetch_failure_does_not_publish_partial_file(tmp_path, failure):
    destination = tmp_path / "snapshot.csv"

    def handler(request):
        offset = int(request.url.params["offset"])
        if failure == "http" and offset:
            return httpx.Response(403)
        record = {"officename": "Office", "pincode": "123456", "district": "D", "statename": "S"}
        if failure == "invalid_record" and offset:
            record.pop("pincode")
        return httpx.Response(
            200,
            json={
                "total": 3 if failure == "changed_total" and offset else 2,
                "offset": 0 if failure == "wrong_offset" and offset else offset,
                "count": 1,
                "records": [record],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError) as error:
            fetch_snapshot(str(uuid.uuid4()), "synthetic-secret", destination, client)
    assert "synthetic-secret" not in str(error.value)
    assert not destination.exists()
    assert not list(tmp_path.glob(".ogd-fetch-*.csv"))


def test_fetch_refuses_existing_file_and_non_uuid(tmp_path):
    target = tmp_path / "existing.csv"
    target.write_text("keep", encoding="utf-8")
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        with pytest.raises(ValueError, match="already exists"):
            fetch_snapshot(str(uuid.uuid4()), "key", target, client)
        with pytest.raises(ValueError, match="UUID"):
            fetch_snapshot("https://example.org/", "key", tmp_path / "new.csv", client)
    assert target.read_text(encoding="utf-8") == "keep"
