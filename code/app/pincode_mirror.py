"""Pinned, explicitly unverified 2024 third-party mirror of a PIN directory."""

import hashlib
import io
from datetime import date
from pathlib import Path

from app.ingestion import ImportRejected
from app.ogd_pincode import SOURCE_URL, OgdPincodeCsvAdapter, read_snapshot

MIRROR_COMMIT = "d26206918dd2fb9f155bfba18de0421bd5fa0ca8"
MIRROR_URL = f"https://github.com/dropdevrahul/pincodes-india/blob/{MIRROR_COMMIT}/pincode.csv"
MIRROR_LICENSE = f"https://github.com/dropdevrahul/pincodes-india/blob/{MIRROR_COMMIT}/LICENSE"
MIRROR_SHA256 = "84af12fa29adddedfa9addcf46546000d89d2e2899b2993dc88050fafc8861e2"
MIRROR_DATE = date(2024, 5, 5)


class PincodeMirrorAdapter(OgdPincodeCsvAdapter):
    name = "third-party-pincode-mirror-2024"
    preserve_other_sources = True

    def __init__(self, path: Path):
        super().__init__(path, MIRROR_DATE)

    def collect(self):
        data = read_snapshot(self.path)
        if hashlib.sha256(data).hexdigest() != MIRROR_SHA256:
            raise ImportRejected(
                "SNAPSHOT_CHECKSUM_MISMATCH", "Mirror snapshot does not match the pinned checksum"
            )
        with io.StringIO(data.decode("utf-8-sig"), newline="") as source_file:
            for record in self.collect_file(source_file):
                record["source"] = {
                    "name": "Third-party GitHub mirror (origin not independently verified)",
                    "url": MIRROR_URL,
                    "original_source_url": SOURCE_URL,
                    "provenance_kind": "third_party_mirror",
                    "last_verified": None,
                    "snapshot_date": MIRROR_DATE.isoformat(),
                    "snapshot_sha256": MIRROR_SHA256,
                    "verification_note": (
                        "Snapshot date is the mirror commit date, "
                        "not an official verification date."
                    ),
                    "license_name": (
                        "Mirror repository MIT licence; upstream data terms need verification"
                    ),
                    "license_url": MIRROR_LICENSE,
                    "freshness_status": "review_due",
                    "review_reason": "unverified_mirror",
                }
                yield record
