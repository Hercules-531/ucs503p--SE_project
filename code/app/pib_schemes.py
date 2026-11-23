"""Conservative scheme snapshot from a dated PIB Ministry of Finance release."""

from collections.abc import Iterable
from typing import Any

from app.ingestion import DataSourceAdapter
from app.models import Scheme

SOURCE_URL = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2247026&lang=2&reg=3"
POLICY_URL = "https://www.pib.gov.in/content/3604_2_CopyrightPolicy.aspx?lang=1&reg=6"
SOURCE_DATE = "2026-03-30"

# Names and responsible ministries are transcribed from the PIB release's scheme table.
# Categories and tags are BharatOS discovery labels, not eligibility determinations.
RECORDS = (
    (
        "pib-acabc",
        "agri-clinics-business-centres",
        "Agri Clinics and Agri Business Centres Scheme",
        "ACABC",
        "Ministry of Agriculture and Farmers' Welfare",
        "Agriculture",
        ["agriculture", "credit"],
    ),
    (
        "pib-aif",
        "agriculture-infrastructure-fund",
        "Agriculture Infrastructure Fund",
        "AIF",
        "Ministry of Agriculture and Farmers Welfare",
        "Agriculture",
        ["agriculture", "credit"],
    ),
    (
        "pib-pmmy",
        "pradhan-mantri-mudra-yojana",
        "Pradhan Mantri Mudra Yojana",
        "PMMY",
        "Ministry of Finance",
        "Finance",
        ["credit", "business"],
    ),
    (
        "pib-pmegp",
        "prime-ministers-employment-generation-programme",
        "Prime Minister's Employment Generation Programme",
        "PMEGP",
        "Ministry of Micro, Small and Medium Enterprises",
        "Employment",
        ["employment", "credit"],
    ),
    (
        "pib-cgse",
        "credit-guarantee-scheme-exporters",
        "Credit Guarantee Scheme for Exporters",
        "CGSE",
        "Ministry of Finance",
        "Finance",
        ["export", "credit"],
    ),
    (
        "pib-day-nrlm",
        "deen-dayal-antyodaya-national-rural-livelihoods",
        "Deen Dayal Antyodaya Yojana - National Rural Livelihood Mission",
        "DAY-NRLM",
        "Ministry of Rural Development",
        "Employment",
        ["rural", "livelihood", "credit"],
    ),
    (
        "pib-ekun",
        "e-kisan-upaj-nidhi",
        "e-Kisan Upaj Nidhi",
        "eKUN",
        "Department of Food and Public Distribution, Warehousing Development and "
        "Regulatory Authority, Department of Financial Services and NABARD",
        "Agriculture",
        ["agriculture", "credit"],
    ),
    (
        "pib-urban-home-loan",
        "urban-home-loan-ews-lig-mig",
        "Home loan scheme for EWS, LIG and MIG: Urban Areas",
        "Urban home loan",
        "Ministry of Housing and Urban Affairs",
        "Housing",
        ["housing", "urban", "credit"],
    ),
    (
        "pib-kisan-credit-card",
        "kisan-credit-card",
        "Kisan Credit Card",
        "Kisan Credit Card",
        "Ministry of Agriculture and Farmers Welfare",
        "Agriculture",
        ["agriculture", "credit"],
    ),
    (
        "pib-kisan-credit-card-fisheries",
        "kisan-credit-card-fisheries",
        "Kisan Credit Card - Fisheries",
        "KCC - Fisheries",
        "Department of Fisheries, Ministry of Fisheries, Animal Husbandry and Dairying",
        "Agriculture",
        ["fisheries", "credit"],
    ),
    (
        "pib-loan-for-startups",
        "loan-for-startups",
        "Loan for Startups",
        "Startup loan",
        "Ministry of Finance and Department for Promotion of Industry and Internal Trade, "
        "Ministry of Commerce and Industry",
        "Finance",
        ["startup", "credit"],
    ),
    (
        "pib-namaste",
        "national-action-mechanized-sanitation-ecosystem",
        "National Action for Mechanized Sanitation Ecosystem",
        "NAMASTE",
        "National Safai Karamcharis Finance and Development Corporation, "
        "Ministry of Social Justice and Empowerment",
        "Employment",
        ["sanitation", "credit"],
    ),
    (
        "pib-solar",
        "roof-top-solar-installation-financing",
        "Roof Top Solar Installation Financing",
        "Solar financing",
        "Ministry of New and Renewable Energy",
        "Energy",
        ["solar", "renewable energy", "credit"],
    ),
    (
        "pib-weaver-mudra",
        "weaver-mudra-scheme",
        "Weaver Mudra Scheme",
        "WMS",
        "Ministry of Textiles",
        "Employment",
        ["weaver", "textiles", "credit"],
    ),
)


class PibSchemeSnapshotAdapter(DataSourceAdapter):
    name = "pib-jansamarth-2026-03"
    kind = "scheme"
    model = Scheme
    id_field = "id"
    complete_snapshot = True

    def collect(self) -> Iterable[dict[str, Any]]:
        for identifier, slug, name, short_name, ministry, category, tags in RECORDS:
            yield {
                "id": identifier,
                "slug": slug,
                "name": name,
                "short_name": short_name,
                "ministry": ministry,
                "category": category,
                "summary": (
                    "Listed among credit-linked schemes in a PIB release dated 30 March 2026."
                ),
                "benefit_summary": (
                    "Credit-linked scheme; verify current benefits with the official source."
                ),
                "eligibility_summary": (
                    "Eligibility is not specified in this source table. "
                    "Check the responsible ministry or official portal."
                ),
                "states": [],
                "audiences": [],
                "tags": tags,
                "source": {
                    "name": "Press Information Bureau — Ministry of Finance",
                    "url": SOURCE_URL,
                    "last_verified": SOURCE_DATE,
                    "freshness_status": "review_due",
                    "license_name": "PIB copyright policy",
                    "license_url": POLICY_URL,
                },
            }
