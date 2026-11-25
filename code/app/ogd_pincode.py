"""Import a user-supplied Department of Posts OGD PIN directory CSV."""

import csv
import hashlib
import io
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TextIO

from app.ingestion import DataSourceAdapter, ImportRejected
from app.models import LocationRecord

SOURCE_URL = "https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month"
LICENSE_URL = "https://data.gov.in/Godl"
ARCHIVE_2019_URL = (
    "https://www.data.gov.in/sites/default/files/dataurl31052019/Pincode_30052019.csv"
)
ARCHIVE_2019_SHA256 = "e2fc773ebc697bb5aa96b76b6a38a2289d450e896769550259df89a2afe54c90"
ARCHIVE_2019_DATE = date(2019, 5, 30)
MAX_SNAPSHOT_BYTES = 100 * 1024 * 1024


def read_snapshot(path: Path) -> bytes:
    with path.open("rb") as file:
        data = file.read(MAX_SNAPSHOT_BYTES + 1)
    if len(data) > MAX_SNAPSHOT_BYTES:
        raise ImportRejected("SNAPSHOT_TOO_LARGE", "Snapshot exceeds the size limit")
    return data


class OgdPincodeCsvAdapter(DataSourceAdapter):
    name = "ogd-department-of-posts-pincode-csv"
    kind = "location"
    model = LocationRecord
    id_field = "pincode"
    complete_snapshot = True
    encoding = "utf-8-sig"

    def __init__(self, path: Path, verified_on: date, *, expected_sha256: str | None = None):
        if verified_on > datetime.now(UTC).date():
            raise ValueError("Verification date cannot be in the future")
        self.path = path
        self.verified_on = verified_on
        if expected_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ValueError("Expected checksum must be a lowercase SHA-256 digest")
        self.expected_sha256 = expected_sha256

    def collect(self) -> Iterable[dict[str, Any]]:
        yield from self.collect_bytes(read_snapshot(self.path))

    def collect_bytes(self, data: bytes) -> Iterable[dict[str, Any]]:
        digest = hashlib.sha256(data).hexdigest()
        if self.expected_sha256 is not None and digest != self.expected_sha256:
            raise ImportRejected(
                "SNAPSHOT_CHECKSUM_MISMATCH", "Snapshot checksum does not match the approved digest"
            )
        with io.StringIO(data.decode(self.encoding), newline="") as file:
            for record in self.collect_file(file):
                record["source"]["snapshot_sha256"] = digest
                yield record

    def source_metadata(self) -> dict[str, Any]:
        return {
            "name": "Department of Posts, Government of India — OGD Platform",
            "url": SOURCE_URL,
            "last_verified": self.verified_on.isoformat(),
            "license_name": "Government Open Data License - India",
            "license_url": LICENSE_URL,
        }

    def collect_file(self, file: TextIO) -> Iterable[dict[str, Any]]:
        grouped: dict[str, dict[tuple[str, str, str], dict[str, set[str]]]] = defaultdict(dict)
        reader = csv.DictReader(file, strict=True)
        if reader.fieldnames is None:
            raise ImportRejected("INVALID_CSV_HEADER", "CSV has no header")
        headers = {}
        for header in reader.fieldnames:
            normalized = re.sub(r"[^a-z0-9]", "", header.casefold())
            if not normalized or normalized in headers:
                raise ImportRejected(
                    "INVALID_CSV_HEADER", "CSV contains blank or duplicate normalized column names"
                )
            headers[normalized] = header
        required = ("officename", "pincode", "district", "statename")
        if not all(field in headers for field in required):
            raise ImportRejected(
                "INVALID_CSV_HEADER", "CSV must contain officename, pincode, district and statename"
            )
        for row in reader:
            line = reader.line_num
            if None in row:
                raise ImportRejected(
                    "INVALID_CSV_ROW",
                    f"Extra fields in CSV record at line {line}",
                    position=line,
                    position_kind="csv_line",
                )
            original = [row.get(headers[field]) or "" for field in required]
            values = [value.strip() for value in original]
            office, pincode, district, state = values
            if not re.fullmatch(r"[0-9]{6}", pincode) or not all((office, district, state)):
                raise ImportRejected(
                    "INVALID_CSV_ROW",
                    f"Invalid office record at CSV line {line}",
                    position=line,
                    position_kind="csv_line",
                )
            changed = grouped[pincode].setdefault((office, district, state), {})
            for field, raw, normalized in zip(required, original, values, strict=True):
                if raw != normalized:
                    changed.setdefault(field, set()).add(raw)
        for pincode, entries in sorted(grouped.items()):
            offices = [
                {
                    "office_name": office,
                    "district": district,
                    "state": state,
                    "original_values": {field: sorted(values) for field, values in changed.items()},
                }
                for (office, district, state), changed in sorted(entries.items())
            ]
            yield {
                "pincode": pincode,
                **offices[0],
                "offices": offices,
                "source": self.source_metadata(),
            }


class OgdPincode2019ArchiveAdapter(OgdPincodeCsvAdapter):
    """Match the known government archive bytes and serve them with historical provenance."""

    name = "ogd-department-of-posts-pincode-archive-2019"
    preserve_other_sources = True
    encoding = "cp1252"  # The pinned CSV uses byte 0xa0 for nonbreaking spaces.

    def __init__(self, path: Path):
        super().__init__(path, ARCHIVE_2019_DATE, expected_sha256=ARCHIVE_2019_SHA256)

    def source_metadata(self) -> dict[str, Any]:
        return {
            **super().source_metadata(),
            "name": (
                "Department of Posts, All India Pincode Directory, Open Government Data "
                "Platform India (2019)"
            ),
            "url": ARCHIVE_2019_URL,
            "snapshot_date": ARCHIVE_2019_DATE.isoformat(),
            "last_verified": None,
            "review_reason": "historical_snapshot",
            "verification_note": "May 2019 archive. Confirm current details with India Post.",
        }
