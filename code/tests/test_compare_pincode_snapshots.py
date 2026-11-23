import hashlib

import pytest

import app.pincode_mirror as mirror_adapter
import scripts.compare_pincode_snapshots as comparison


def test_compare_reports_sets_and_checksums_without_importing(tmp_path, monkeypatch):
    mirror = tmp_path / "mirror.csv"
    mirror.write_text(
        "officename,pincode,district,statename\n"
        "Same,123456,District,State\n"
        "Old,654321,District,State\n"
        "Only mirror,111111,District,State\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(mirror.read_bytes()).hexdigest()
    monkeypatch.setattr(mirror_adapter, "MIRROR_SHA256", digest)
    monkeypatch.setattr(comparison, "MIRROR_SHA256", digest)
    candidate = tmp_path / "candidate.csv"
    candidate.write_text(
        "officename,pincode,district,statename\n"
        "Same,123456,District,State\n"
        "New,654321,District,State\n"
        "Only candidate,222222,District,State\n",
        encoding="utf-8",
    )
    before = candidate.read_bytes(), mirror.read_bytes()
    result = comparison.compare(candidate, mirror)
    assert result["candidate_pins"] == result["mirror_pins"] == 3
    assert result["shared_pins"] == 2
    assert result["identical_office_sets"] == result["different_office_sets"] == 1
    assert result["candidate_only_pins"] == result["mirror_only_pins"] == 1
    assert result["candidate_sha256"] == hashlib.sha256(before[0]).hexdigest()
    assert result["mirror_sha256"] == digest
    assert (candidate.read_bytes(), mirror.read_bytes()) == before


def test_compare_rejects_modified_mirror(tmp_path):
    candidate = tmp_path / "candidate.csv"
    mirror = tmp_path / "mirror.csv"
    for path in (candidate, mirror):
        path.write_text("officename,pincode,district,statename\nA,123456,D,S\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        comparison.compare(candidate, mirror)
