"""Summarize source-attributed records without treating import status as live availability."""

from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import LocationRecord, Scheme, SourceMetadata
from app.storage import IngestionRun, StoredRecord

REQUIRED_FIELDS = {
    "scheme": (
        "id",
        "slug",
        "name",
        "short_name",
        "ministry",
        "category",
        "summary",
        "benefit_summary",
        "eligibility_summary",
        "states",
        "audiences",
        "tags",
    ),
    "location": ("pincode", "office_name", "district", "state", "country"),
}
MODELS = {"scheme": Scheme, "location": LocationRecord}


def present(value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(present(item) for item in value)
    return value is not None


def quality_checks(kind: str, identifier: str, payload: object) -> tuple[bool, bool]:
    """Return completeness and schema/identifier consistency for known record types."""
    if kind not in MODELS or not isinstance(payload, dict):
        return False, False
    source = payload.get("source")
    complete = (
        all(present(payload.get(field)) for field in REQUIRED_FIELDS[kind])
        and isinstance(source, dict)
        and all(present(source.get(field)) for field in ("name", "url", "last_verified"))
    )
    try:
        record = MODELS[kind].model_validate(payload)
        actual_id = record.id if kind == "scheme" else record.pincode
        consistent = actual_id == identifier
    except ValidationError:
        consistent = False
    return complete, consistent


def source_summaries(session: Session) -> list[dict]:
    latest_ids = select(func.max(IngestionRun.id)).group_by(IngestionRun.source)
    latest_runs = {
        run.source: run
        for run in session.scalars(select(IngestionRun).where(IngestionRun.id.in_(latest_ids)))
    }
    summaries: dict[str | None, dict] = {}

    def initialize(adapter: str | None) -> dict:
        latest = latest_runs.get(adapter)
        return {
            "source": adapter or "Unassigned legacy records",
            "records": 0,
            "current": 0,
            "review_due": 0,
            "unknown": 0,
            "complete_records": 0,
            "consistent_records": 0,
            "oldest_verified": None,
            "last_import_status": latest.status if latest else "unknown",
            "last_import_started_at": latest.started_at.isoformat() if latest else None,
        }

    for adapter in latest_runs:
        summaries[adapter] = initialize(adapter)
    records = session.execute(
        select(
            StoredRecord.source_adapter,
            StoredRecord.kind,
            StoredRecord.identifier,
            StoredRecord.payload,
        ).execution_options(yield_per=250)
    )
    for adapter, kind, identifier, payload in records:
        if adapter not in summaries:
            summaries[adapter] = initialize(adapter)
        summary = summaries[adapter]
        summary["records"] += 1
        complete, consistent = quality_checks(kind, identifier, payload)
        summary["complete_records"] += int(complete)
        summary["consistent_records"] += int(consistent)
        try:
            metadata = SourceMetadata.model_validate(payload.get("source"))
        except (ValidationError, AttributeError, TypeError):
            summary["unknown"] += 1
            continue
        summary[metadata.freshness_status] += 1
        if metadata.last_verified is not None:
            verified = metadata.last_verified.isoformat()
            if summary["oldest_verified"] is None or verified < summary["oldest_verified"]:
                summary["oldest_verified"] = verified
    for summary in summaries.values():
        count = summary["records"]
        summary["freshness_percent"] = round(summary["current"] * 100 / count, 1) if count else None
        summary["completeness_percent"] = (
            round(summary["complete_records"] * 100 / count, 1) if count else None
        )
        summary["consistency_percent"] = (
            round(summary["consistent_records"] * 100 / count, 1) if count else None
        )
    return sorted(summaries.values(), key=lambda item: item["source"])


def monitoring_alerts(
    sources: list[dict], cache: dict, probes: list[dict], *, now: datetime | None = None
) -> list[dict]:
    """Compute current dashboard alerts; no notification delivery or history is implied."""
    alerts = []
    if not sources:
        alerts.append(
            {
                "severity": "warning",
                "code": "NO_SOURCES",
                "message": "No source records or import runs are available.",
            }
        )
    for source in sources:
        name = source["source"]
        if source["last_import_status"] == "failed":
            alerts.append(
                {
                    "severity": "error",
                    "code": "IMPORT_FAILED",
                    "message": f"The latest import failed for {name}.",
                }
            )
        if source["records"] == 0:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "NO_RECORDS",
                    "message": f"No stored records are associated with {name}.",
                }
            )
        if source["review_due"]:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "REVIEW_DUE",
                    "message": f"{source['review_due']} records require review for {name}.",
                }
            )
        if source["unknown"]:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "FRESHNESS_UNKNOWN",
                    "message": f"Freshness is unknown for {source['unknown']} records in {name}.",
                }
            )
    if cache["status"] == "unavailable":
        alerts.append(
            {
                "severity": "error",
                "code": "CACHE_UNAVAILABLE",
                "message": "Redis cache metrics are unavailable.",
            }
        )
    for probe in probes:
        checked_at = probe.get("checked_at")
        if not checked_at:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "SOURCE_NOT_CHECKED",
                    "message": f"No source-page check has been recorded for {probe['source']}.",
                }
            )
        else:
            try:
                checked = datetime.fromisoformat(checked_at)
                if checked.tzinfo is None:
                    checked = checked.replace(tzinfo=UTC)
                age = (now or datetime.now(UTC)) - checked.astimezone(UTC)
                if age < timedelta(0):
                    raise ValueError("Check time is in the future")
                if age > timedelta(hours=24):
                    alerts.append(
                        {
                            "severity": "warning",
                            "code": "SOURCE_CHECK_STALE",
                            "message": (
                                f"The last source-page check for {probe['source']} "
                                "is over 24 hours old."
                            ),
                        }
                    )
            except (TypeError, ValueError):
                alerts.append(
                    {
                        "severity": "warning",
                        "code": "SOURCE_CHECK_TIME_INVALID",
                        "message": f"The source-page check time for {probe['source']} is invalid.",
                    }
                )
        if probe["status"] in {"unavailable", "server_error"}:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "SOURCE_CHECK_FAILED",
                    "message": (
                        f"The last HEAD check for {probe['source']} reported {probe['status']} "
                        f"at {probe['checked_at']}."
                    ),
                }
            )
    return alerts
