"""A dated, manually transcribed transport scheme record from a PIB release."""

from collections.abc import Iterable
from typing import Any

from app.ingestion import DataSourceAdapter
from app.models import Scheme
from app.pib_schemes import POLICY_URL

SOURCE_URL = "https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=2290696&lang=2&reg=48"
SOURCE_DATE = "2026-07-28"


class PibTransportSnapshotAdapter(DataSourceAdapter):
    name = "pib-transport-2026-07"
    kind = "scheme"
    model = Scheme
    id_field = "id"
    complete_snapshot = True
    preserve_other_sources = True

    def collect(self) -> Iterable[dict[str, Any]]:
        yield {
            "id": "pib-pm-e-drive",
            "slug": "pm-e-drive",
            "name": "PM Electric Drive Revolution in Innovative Vehicle Enhancement",
            "short_name": "PM E-DRIVE",
            "ministry": "Ministry of Heavy Industries",
            "category": "Transport",
            "summary": "A scheme to promote electric mobility and charging infrastructure.",
            "benefit_summary": (
                "The July 2026 release describes support for certain electric vehicles and "
                "charging infrastructure. Check current segment-specific conditions."
            ),
            "eligibility_summary": (
                "The release describes different conditions and end dates for vehicle "
                "categories. Verify current eligibility and availability with the ministry."
            ),
            "states": [],
            "audiences": [],
            "tags": ["transport", "electric vehicles", "charging", "mobility"],
            "source": {
                "name": "Press Information Bureau — Ministry of Heavy Industries",
                "url": SOURCE_URL,
                "last_verified": SOURCE_DATE,
                "snapshot_date": SOURCE_DATE,
                "freshness_status": "review_due",
                "license_name": "PIB copyright policy",
                "license_url": POLICY_URL,
            },
        }
