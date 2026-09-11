from datetime import date

from app.models import LocationRecord, Scheme, SourceMetadata

VERIFIED_ON = date(2026, 9, 9)


def source(name: str, url: str) -> SourceMetadata:
    return SourceMetadata(name=name, url=url, last_verified=VERIFIED_ON)


SCHEMES = [
    Scheme(
        id="scheme-pm-kisan",
        slug="pm-kisan",
        name="Pradhan Mantri Kisan Samman Nidhi",
        short_name="PM-KISAN",
        ministry="Ministry of Agriculture & Farmers Welfare",
        category="Agriculture",
        summary="Income-support programme for eligible landholding farmer families.",
        benefit_summary="Periodic financial support, subject to the official scheme rules.",
        eligibility_summary=(
            "Potential relevance: landholding farmer families. Exclusions, land records and "
            "verification requirements must be checked on the official portal."
        ),
        audiences=["Farmers"],
        tags=["income support", "agriculture", "farmer", "rural"],
        source=source("myScheme — Digital India", "https://www.myscheme.gov.in/schemes/pm-kisan"),
    ),
    Scheme(
        id="scheme-pm-jay",
        slug="ayushman-bharat-pm-jay",
        name="Ayushman Bharat Pradhan Mantri Jan Arogya Yojana",
        short_name="AB PM-JAY",
        ministry="Ministry of Health & Family Welfare",
        category="Health",
        summary="Public health-assurance scheme for eligible beneficiary families.",
        benefit_summary="Cashless access to covered secondary and tertiary care services.",
        eligibility_summary=(
            "Potential relevance depends on the official beneficiary database and current "
            "scheme rules; this prototype does not determine enrolment."
        ),
        audiences=["Families", "Senior citizens"],
        tags=["health", "hospital", "assurance", "cashless"],
        source=source("myScheme — Digital India", "https://www.myscheme.gov.in/schemes/ab-pmjay"),
    ),
    Scheme(
        id="scheme-pmay-u",
        slug="pmay-urban-2",
        name="Pradhan Mantri Awas Yojana - Urban 2.0",
        short_name="PMAY-U 2.0",
        ministry="Ministry of Housing and Urban Affairs",
        category="Housing",
        summary="Housing assistance programme for eligible urban families.",
        benefit_summary="Support through the programme vertical applicable to the household.",
        eligibility_summary=(
            "Potential relevance: urban households subject to income, property and "
            "programme-specific conditions on the official portal."
        ),
        audiences=["Urban households", "Women"],
        tags=["housing", "urban", "home", "assistance"],
        source=source("myScheme — Digital India", "https://www.myscheme.gov.in/schemes/pmay-u"),
    ),
    Scheme(
        id="scheme-pmuy",
        slug="pradhan-mantri-ujjwala-yojana",
        name="Pradhan Mantri Ujjwala Yojana",
        short_name="PMUY",
        ministry="Ministry of Petroleum and Natural Gas",
        category="Energy",
        summary="Clean-cooking fuel support intended for eligible adult women in households.",
        benefit_summary="Support for an LPG connection under the current official programme rules.",
        eligibility_summary=(
            "Potential relevance: eligible adult women without an existing household LPG "
            "connection. The official portal must confirm documents and exclusions."
        ),
        audiences=["Women", "Families"],
        tags=["lpg", "cooking", "energy", "women"],
        source=source("myScheme — Digital India", "https://www.myscheme.gov.in/schemes/pmuy"),
    ),
    Scheme(
        id="scheme-pm-svanidhi",
        slug="pm-svanidhi",
        name="PM Street Vendor's AtmaNirbhar Nidhi",
        short_name="PM SVANidhi",
        ministry="Ministry of Housing and Urban Affairs",
        category="Employment",
        summary="Working-capital support programme for eligible urban street vendors.",
        benefit_summary=(
            "Collateral-free working-capital loans with incentives under current rules."
        ),
        eligibility_summary=(
            "Potential relevance: street vendors covered by the scheme's survey, certificate "
            "or recommendation processes. Confirm status with the local urban body."
        ),
        audiences=["Street vendors", "Self-employed"],
        tags=["vendor", "loan", "livelihood", "urban"],
        source=source(
            "myScheme — Digital India", "https://www.myscheme.gov.in/schemes/pm-svanidhi"
        ),
    ),
    Scheme(
        id="scheme-apy",
        slug="atal-pension-yojana",
        name="Atal Pension Yojana",
        short_name="APY",
        ministry="Ministry of Finance",
        category="Social security",
        summary="Contribution-based pension scheme focused on long-term income security.",
        benefit_summary=(
            "A chosen guaranteed minimum pension after age 60, subject to contributions."
        ),
        eligibility_summary=(
            "Potential relevance: Indian citizens aged 18–40 with an eligible savings account; "
            "current taxpayer restrictions and other rules apply."
        ),
        audiences=["Workers", "Self-employed"],
        tags=["pension", "retirement", "worker", "social security"],
        source=source(
            "Pension Fund Regulatory and Development Authority",
            "https://pfrda.org.in/web/pfrda/schemes/atal-pension-yojana-apy",
        ),
    ),
    Scheme(
        id="scheme-dhtess",
        slug="delhi-higher-education-support",
        name="Delhi Higher & Technical Education Support Scheme",
        short_name="DHTESS",
        ministry="Higher Education Department, Government of NCT of Delhi",
        category="Education",
        summary="Tuition-fee assistance for eligible undergraduate students in Delhi.",
        benefit_summary="Tuition-fee support through participating government institutions.",
        eligibility_summary=(
            "Potential relevance: Delhi residents in eligible regular undergraduate courses, "
            "subject to academic, income and institution conditions."
        ),
        states=["Delhi"],
        audiences=["Students"],
        tags=["education", "student", "scholarship", "tuition"],
        source=source("myScheme — Digital India", "https://www.myscheme.gov.in/schemes/dhtess"),
    ),
    Scheme(
        id="scheme-jsy",
        slug="janani-suraksha-yojana",
        name="Janani Suraksha Yojana",
        short_name="JSY",
        ministry="Ministry of Health & Family Welfare",
        category="Health",
        summary="Safe-motherhood intervention supporting eligible pregnant women.",
        benefit_summary="Conditional assistance connected with institutional delivery and care.",
        eligibility_summary=(
            "Potential relevance varies by state category and beneficiary circumstances. "
            "Confirm current criteria with the official scheme or local health authority."
        ),
        audiences=["Women", "Families"],
        tags=["maternal health", "pregnancy", "hospital", "women"],
        source=source("myScheme — Digital India", "https://www.myscheme.gov.in/schemes/jsy1"),
    ),
]


PINCODE_SOURCE = source(
    "Open Government Data Platform India — Department of Posts",
    "https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month",
)

LOCATIONS = {
    "147004": LocationRecord(
        pincode="147004",
        office_name="Thapar College Patiala S.O",
        district="Patiala",
        state="Punjab",
        source=PINCODE_SOURCE,
    ),
    "110001": LocationRecord(
        pincode="110001",
        office_name="New Delhi G.P.O.",
        district="New Delhi",
        state="Delhi",
        source=PINCODE_SOURCE,
    ),
    "560001": LocationRecord(
        pincode="560001",
        office_name="Bengaluru G.P.O.",
        district="Bengaluru",
        state="Karnataka",
        source=PINCODE_SOURCE,
    ),
}


def filter_schemes(
    *, q: str = "", category: str = "", state: str = "", audience: str = ""
) -> list[Scheme]:
    query = q.strip().casefold()
    category_key = category.strip().casefold()
    state_key = state.strip().casefold()
    audience_key = audience.strip().casefold()

    def matches(scheme: Scheme) -> bool:
        searchable = " ".join(
            [scheme.name, scheme.short_name, scheme.ministry, scheme.summary, *scheme.tags]
        ).casefold()
        states = {item.casefold() for item in scheme.states}
        audiences = {item.casefold() for item in scheme.audiences}
        category_match = not category_key or scheme.category.casefold() == category_key
        state_match = not state_key or "all india" in states or state_key in states
        audience_match = not audience_key or audience_key in audiences
        return (
            (not query or query in searchable) and category_match and state_match and audience_match
        )

    return [scheme for scheme in SCHEMES if matches(scheme)]


def find_scheme(identifier: str) -> Scheme | None:
    return next(
        (item for item in SCHEMES if item.id == identifier or item.slug == identifier),
        None,
    )
