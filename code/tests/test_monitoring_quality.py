from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.data import SCHEMES
from app.monitoring import monitoring_alerts, source_summaries
from app.storage import Base, StoredRecord, create_database, utc_now


def test_quality_percentages_reflect_record_fields_and_identifier(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'quality.db').as_posix()}")
    Base.metadata.create_all(engine)
    valid = SCHEMES[0].model_dump(mode="json")
    valid["source"]["last_verified"] = datetime.now(UTC).date().isoformat()
    valid["source"]["freshness_status"] = "current"
    damaged = {**valid, "id": "different-id", "ministry": ""}
    with Session(engine) as session:
        session.add_all(
            [
                StoredRecord(
                    kind="scheme",
                    identifier=valid["id"],
                    source_url="https://example.org",
                    source_adapter="test-source",
                    payload=valid,
                    updated_at=utc_now(),
                ),
                StoredRecord(
                    kind="scheme",
                    identifier="another-id",
                    source_url="https://example.org",
                    source_adapter="test-source",
                    payload=damaged,
                    updated_at=utc_now(),
                ),
            ]
        )
        session.commit()
        summary = source_summaries(session)[0]
        assert summary["records"] == 2
        assert summary["freshness_percent"] == 100.0
        assert summary["completeness_percent"] == 50.0
        assert summary["consistency_percent"] == 50.0
        assert summary["last_import_status"] == "unknown"
    engine.dispose()


def test_source_checks_report_missing_stale_and_invalid_times_without_claiming_outage():
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    probes = [
        {"source": "missing", "status": "not_checked", "checked_at": None},
        {
            "source": "old",
            "status": "accessible",
            "checked_at": (now - timedelta(hours=25)).isoformat(),
        },
        {
            "source": "recent",
            "status": "accessible",
            "checked_at": (now - timedelta(hours=2)).isoformat(),
        },
        {
            "source": "future",
            "status": "accessible",
            "checked_at": (now + timedelta(minutes=1)).isoformat(),
        },
        {"source": "broken", "status": "unavailable", "checked_at": now.isoformat()},
    ]
    alerts = monitoring_alerts([], {"status": "not_configured"}, probes, now=now)
    codes = [alert["code"] for alert in alerts]
    assert codes.count("SOURCE_NOT_CHECKED") == 1
    assert codes.count("SOURCE_CHECK_STALE") == 1
    assert codes.count("SOURCE_CHECK_TIME_INVALID") == 1
    assert codes.count("SOURCE_CHECK_FAILED") == 1
    assert not any("recent" in alert["message"] for alert in alerts)
    assert "old" in next(
        alert["message"] for alert in alerts if alert["code"] == "SOURCE_CHECK_STALE"
    )
