"""Programme summaries from dated releases by four government ministries."""

from collections.abc import Iterable
from datetime import date

from app.ingestion import DataSourceAdapter
from app.models import Scheme, SourceMetadata
from app.pib_schemes import POLICY_URL


class PibProgrammeSnapshot(DataSourceAdapter):
    kind = "scheme"
    model = Scheme
    id_field = "id"
    preserve_other_sources = True
    complete_snapshot = True

    def __init__(
        self,
        name: str,
        ministry: str,
        category: str,
        release_url: str,
        release_date: date,
        programmes: list[dict],
    ) -> None:
        self.name = name
        self.ministry = ministry
        self.category = category
        self.source = SourceMetadata(
            name=f"Press Information Bureau — {ministry}",
            url=release_url,
            snapshot_date=release_date,
            last_verified=date(2026, 11, 23),
            verification_note="The linked release was checked. Confirm current programme details.",
            freshness_status="review_due",
            license_name="PIB copyright policy",
            license_url=POLICY_URL,
        )
        self.programmes = programmes

    def collect(self) -> Iterable[dict]:
        for programme in self.programmes:
            yield {
                **programme,
                "id": f"pib-{programme['slug']}",
                "category": self.category,
                "ministry": self.ministry,
                "states": [],
                "source": self.source.model_dump(mode="json"),
            }


PROGRAMME_SNAPSHOTS = (
    PibProgrammeSnapshot(
        "pib-health-2297506",
        "Ministry of Health and Family Welfare",
        "Health",
        "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2297506&lang=2&reg=48",
        date(2026, 8, 11),
        [
            {
                "slug": "national-dialysis-programme",
                "name": "Pradhan Mantri National Dialysis Programme",
                "short_name": "PMNDP",
                "summary": "A National Health Mission programme supporting access to dialysis.",
                "benefit_summary": (
                    "The release describes dialysis services for eligible patients at "
                    "participating district hospitals and other health facilities."
                ),
                "eligibility_summary": (
                    "Ask a participating health facility about its current programme criteria "
                    "and service availability."
                ),
                "audiences": ["Patients"],
                "tags": ["dialysis", "district hospitals", "National Health Mission"],
            }
        ],
    ),
    PibProgrammeSnapshot(
        "pib-education-2297131",
        "Ministry of Education",
        "Education",
        "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2297131&lang=1&reg=48",
        date(2026, 8, 10),
        [
            {
                "slug": "samagra-shiksha",
                "name": "Samagra Shiksha",
                "short_name": "Samagra Shiksha",
                "summary": "A school education programme that supports access and inclusion.",
                "benefit_summary": (
                    "The release describes support for quality education and inclusive classrooms."
                ),
                "eligibility_summary": (
                    "The release describes school-level measures. Ask the school or education "
                    "department about locally available support."
                ),
                "audiences": ["Students", "Schools"],
                "tags": ["schools", "school education", "inclusion"],
            },
            {
                "slug": "nipun-bharat",
                "name": "NIPUN Bharat Mission",
                "short_name": "NIPUN Bharat",
                "summary": "An initiative for foundational reading and numeracy in primary school.",
                "benefit_summary": (
                    "The initiative targets foundational literacy and numeracy by Grade 3."
                ),
                "eligibility_summary": (
                    "This record describes an education initiative. Ask the school how it "
                    "supports children in the early grades."
                ),
                "audiences": ["Students", "Schools"],
                "tags": ["primary school", "reading", "numeracy", "foundational literacy"],
            },
        ],
    ),
    PibProgrammeSnapshot(
        "pib-employment-2275419",
        "Ministry of Labour and Employment",
        "Employment",
        "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2275419&lang=1&reg=1",
        date(2026, 6, 19),
        [
            {
                "slug": "viksit-bharat-rozgar-yojana",
                "name": "Pradhan Mantri Viksit Bharat Rozgar Yojana",
                "short_name": "PM-VBRY",
                "summary": "An employment programme that encourages formal job creation.",
                "benefit_summary": (
                    "The release describes separate incentives for qualifying first-time "
                    "employees and employers that add jobs."
                ),
                "eligibility_summary": (
                    "Check the current EPFO registration, employment and establishment criteria "
                    "for the relevant part of the scheme."
                ),
                "audiences": ["Workers", "Employers"],
                "tags": ["first jobs", "formal employment", "EPFO", "job creation"],
            }
        ],
    ),
    PibProgrammeSnapshot(
        "pib-agriculture-2244625",
        "Ministry of Agriculture and Farmers Welfare",
        "Agriculture",
        "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2244625&lang=2&reg=3",
        date(2026, 3, 24),
        [
            {
                "slug": "national-mission-on-natural-farming",
                "name": "National Mission on Natural Farming",
                "short_name": "NMNF",
                "summary": "A mission that supports farmers in adopting natural farming practices.",
                "benefit_summary": (
                    "The release describes farmer training, village-level guidance and "
                    "support through local clusters."
                ),
                "eligibility_summary": (
                    "Ask the agriculture department about participating clusters and current "
                    "enrolment criteria."
                ),
                "audiences": ["Farmers"],
                "tags": ["natural farming", "farmer training", "clusters"],
            }
        ],
    ),
)
