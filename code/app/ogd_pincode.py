"""Import a user-supplied Department of Posts OGD PIN directory CSV."""

import csv
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TextIO

from app.ingestion import DataSourceAdapter
from app.models import LocationRecord

SOURCE_URL = "https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month"
LICENSE_URL = "https://data.gov.in/Godl"


class OgdPincodeCsvAdapter(DataSourceAdapter):
    name = "ogd-department-of-posts-pincode-csv"
    kind = "location"
    model = LocationRecord
    id_field = "pincode"
    complete_snapshot = True

    def __init__(self, path: Path, verified_on: date):
        if verified_on > datetime.now(UTC).date():
            raise ValueError("Verification date cannot be in the future")
        self.path = path
        self.verified_on = verified_on

    def collect(self) -> Iterable[dict[str, Any]]:
        with self.path.open("r", encoding="utf-8-sig", newline="") as file:
            yield from self.collect_file(file)

    def collect_file(self, file: TextIO) -> Iterable[dict[str, Any]]:
        grouped: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
        reader = csv.DictReader(file, strict=True)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header")
        headers = {}
        for header in reader.fieldnames:
            normalized = re.sub(r"[^a-z0-9]", "", header.casefold())
            if not normalized or normalized in headers:
                raise ValueError("CSV contains blank or duplicate normalized column names")
            headers[normalized] = header
        required = ("officename", "pincode", "district", "statename")
        if not all(field in headers for field in required):
            raise ValueError("CSV must contain officename, pincode, district and statename")
        for line, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"Extra fields in CSV record at line {line}")
            values = [(row.get(headers[field]) or "").strip() for field in required]
            office, pincode, district, state = values
            if not re.fullmatch(r"[0-9]{6}", pincode) or not all((office, district, state)):
                raise ValueError(f"Invalid office record at CSV line {line}")
            grouped[pincode].add((office, district, state))
        for pincode, entries in sorted(grouped.items()):
            offices = [
                {"office_name": office, "district": district, "state": state}
                for office, district, state in sorted(entries)
            ]
            yield {
                "pincode": pincode,
                **offices[0],
                "offices": offices,
                "source": {
                    "name": "Department of Posts, Government of India — OGD Platform",
                    "url": SOURCE_URL,
                    "last_verified": self.verified_on.isoformat(),
                    "license_name": "Government Open Data License - India",
                    "license_url": LICENSE_URL,
                },
            }
