"""A dated, manually curated environmental programme record from PIB."""

from collections.abc import Iterable
from typing import Any

from app.ingestion import DataSourceAdapter
from app.models import Scheme
from app.pib_schemes import POLICY_URL

SOURCE_URL = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2291891&lang=1&reg=6"
SOURCE_DATE = "2026-07-30"


class PibEnvironmentSnapshotAdapter(DataSourceAdapter):
    name = "pib-environment-2026-07"
    kind = "scheme"
    model = Scheme
    id_field = "id"
    complete_snapshot = True
    preserve_other_sources = True

    def collect(self) -> Iterable[dict[str, Any]]:
        yield {
            "id": "pib-ncap",
            "slug": "national-clean-air-programme",
            "name": "National Clean Air Programme",
            "short_name": "NCAP",
            "ministry": "Ministry of Environment, Forest and Climate Change",
            "category": "Environment",
            "summary": "A public programme for city-specific air pollution action plans.",
            "benefit_summary": (
                "The July 2026 release describes clean air action plans for 130 cities. "
                "This is an area-based programme, not an individual payment."
            ),
            "eligibility_summary": (
                "The source describes city-level action, not an application or eligibility "
                "process for individuals. Check current coverage with the ministry."
            ),
            "states": [],
            "audiences": [],
            "tags": ["air quality", "pollution", "clean air", "environment"],
            "source": {
                "name": (
                    "Press Information Bureau — Ministry of Environment, Forest and Climate Change"
                ),
                "url": SOURCE_URL,
                "last_verified": SOURCE_DATE,
                "snapshot_date": SOURCE_DATE,
                "freshness_status": "review_due",
                "license_name": "PIB copyright policy",
                "license_url": POLICY_URL,
            },
        }
