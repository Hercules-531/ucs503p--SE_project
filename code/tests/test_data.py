import pytest
from pydantic import ValidationError

from app.data import LOCATIONS, SCHEMES, filter_schemes, find_scheme, uncertain_filter_exclusions
from app.models import LocationRecord


def test_catalogue_contains_eight_source_linked_records() -> None:
    assert len(SCHEMES) == 8
    assert len({scheme.id for scheme in SCHEMES}) == 8
    assert all(scheme.source.url and scheme.source.last_verified for scheme in SCHEMES)


def test_text_search_is_case_insensitive_and_searches_tags() -> None:
    results = filter_schemes(q="HEALTH")
    assert {scheme.short_name for scheme in results} == {"AB PM-JAY", "JSY"}


def test_filters_are_composable() -> None:
    results = filter_schemes(category="Health", audience="Women")
    assert [scheme.short_name for scheme in results] == ["JSY"]


def test_missing_filter_details_count_only_plausible_candidates():
    unknown = SCHEMES[0].model_copy(update={"states": [], "audiences": []})
    wrong_audience = SCHEMES[0].model_copy(update={"states": [], "audiences": ["Farmers"]})
    wrong_state = SCHEMES[0].model_copy(update={"states": ["Delhi"], "audiences": []})
    matching = SCHEMES[0].model_copy(update={"states": ["Punjab"], "audiences": ["Women"]})
    records = [unknown, wrong_audience, wrong_state, matching]
    assert uncertain_filter_exclusions(records, state="Punjab", audience="Women") == 1
    assert uncertain_filter_exclusions(records, state="Punjab") == 2
    assert uncertain_filter_exclusions(records, state="Punjab", q="not-a-match") == 0
    assert uncertain_filter_exclusions(records) == 0


def test_national_schemes_apply_to_selected_state() -> None:
    results = filter_schemes(state="Punjab")
    assert results
    assert all("All India" in scheme.states for scheme in results)
    assert find_scheme("delhi-higher-education-support") not in results


def test_find_scheme_accepts_id_or_slug() -> None:
    assert find_scheme("scheme-pm-kisan") == find_scheme("pm-kisan")
    assert find_scheme("missing") is None


def test_location_model_rejects_non_six_digit_pin() -> None:
    valid = LOCATIONS["147004"].model_dump()
    valid["pincode"] = "1470"
    with pytest.raises(ValidationError):
        LocationRecord.model_validate(valid)


def test_source_verification_date_controls_freshness():
    from datetime import UTC, datetime, timedelta

    from app.models import SourceMetadata

    today = datetime.now(UTC).date()
    metadata = SourceMetadata(name="Example", url="https://example.org", last_verified=today)
    assert metadata.freshness_status == "current"
    stale = SourceMetadata(
        name="Example", url="https://example.org", last_verified=today - timedelta(days=31)
    )
    assert stale.freshness_status == "review_due"
    future = SourceMetadata(
        name="Example", url="https://example.org", last_verified=today + timedelta(days=1)
    )
    assert future.freshness_status == "unknown"
    flagged = SourceMetadata(
        name="Example",
        url="https://example.org",
        last_verified=today,
        freshness_status="current",
        review_reason="absent_from_snapshot",
    )
    assert flagged.freshness_status == "review_due"
    unverified = SourceMetadata(name="Example", url="https://example.org", last_verified=None)
    assert unverified.freshness_status == "unknown"


def test_in_memory_sources_refresh_their_status(monkeypatch):
    from datetime import UTC, datetime, timedelta

    import app.main as web

    scheme = SCHEMES[0].model_copy(deep=True)
    scheme.source.last_verified = datetime.now(UTC).date() - timedelta(days=31)
    scheme.source.freshness_status = "current"
    monkeypatch.setattr(web, "engine", None)
    monkeypatch.setattr(web, "SCHEMES", [scheme])
    assert web.current_schemes()[0].source.freshness_status == "review_due"
    assert web.current_scheme(scheme.id).source.freshness_status == "review_due"
    assert scheme.source.freshness_status == "current"
