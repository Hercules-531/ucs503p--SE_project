"""Compare a candidate PIN CSV with the pinned historical mirror without importing either."""

import argparse
import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path

from app.ogd_pincode import OgdPincodeCsvAdapter, read_snapshot
from app.pincode_mirror import MIRROR_SHA256, PincodeMirrorAdapter


def collect_offices(records) -> dict[str, set[tuple[str, str, str]]]:
    return {
        record["pincode"]: {
            (office["office_name"], office["district"], office["state"])
            for office in record["offices"]
        }
        for record in records
    }


def compare(candidate: Path, mirror: Path) -> dict:
    data = read_snapshot(candidate)
    adapter = OgdPincodeCsvAdapter(candidate, datetime.now(UTC).date())
    with io.StringIO(data.decode("utf-8-sig"), newline="") as source:
        candidate_records = collect_offices(adapter.collect_file(source))
    mirror_records = collect_offices(PincodeMirrorAdapter(mirror).collect())
    if not candidate_records or not mirror_records:
        raise ValueError("Both snapshots must contain at least one PIN")
    candidate_pins, mirror_pins = set(candidate_records), set(mirror_records)
    common = candidate_pins & mirror_pins
    matching = sum(candidate_records[pin] == mirror_records[pin] for pin in common)
    return {
        "candidate_sha256": hashlib.sha256(data).hexdigest(),
        "mirror_sha256": MIRROR_SHA256,
        "candidate_pins": len(candidate_pins),
        "mirror_pins": len(mirror_pins),
        "shared_pins": len(common),
        "identical_office_sets": matching,
        "different_office_sets": len(common) - matching,
        "candidate_only_pins": len(candidate_pins - mirror_pins),
        "mirror_only_pins": len(mirror_pins - candidate_pins),
        "comparison_fields": ["pincode", "officename", "district", "statename"],
        "note": "Comparison does not verify origin, freshness, licence, or unexamined fields.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, help="CSV whose origin you intend to review")
    parser.add_argument("mirror", type=Path, help="Pinned historical mirror CSV")
    args = parser.parse_args()
    try:
        result = compare(args.candidate, args.mirror)
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(1, f"Comparison failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
