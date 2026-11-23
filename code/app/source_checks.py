"""HEAD checks against a fixed set of official source pages."""

from datetime import UTC, datetime
from time import perf_counter

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.storage import SourceProbe

OFFICIAL_SOURCES = {
    "myScheme": "https://www.myscheme.gov.in/",
    "OGD PIN directory": "https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month",
    "PIB JanSamarth release": "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2247026&lang=2&reg=3",
    "PFRDA Atal Pension Yojana": "https://pfrda.org.in/web/pfrda/schemes/atal-pension-yojana-apy",
}


def classify(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "accessible"
    if 300 <= status_code < 400:
        return "redirect"
    if status_code in (401, 403):
        return "restricted"
    if status_code == 405:
        return "head_not_supported"
    if status_code >= 500:
        return "server_error"
    return "client_error"


def run_source_checks(session: Session, client: httpx.Client) -> None:
    """Check fixed URLs only; do not follow redirects, fetch bodies, or store error text."""
    results = []
    for name, url in OFFICIAL_SOURCES.items():
        started = perf_counter()
        try:
            response = client.head(url, follow_redirects=False, timeout=5.0)
            status_code = response.status_code
            status = classify(status_code)
        except httpx.HTTPError:
            status_code = None
            status = "unavailable"
        results.append(
            (
                name,
                status,
                status_code,
                datetime.now(UTC),
                round((perf_counter() - started) * 1000, 2),
            )
        )
    # Network calls finish before database work so slow upstreams do not hold a transaction open.
    store_source_checks(session, results)


def store_source_checks(session: Session, results: list[tuple]) -> None:
    """Atomically retain the newest observation when checks overlap."""
    dialect = session.get_bind().dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise ValueError("Source checks support PostgreSQL and SQLite databases")
    insert = postgres_insert if dialect == "postgresql" else sqlite_insert
    for name, status, status_code, checked_at, duration in results:
        statement = insert(SourceProbe).values(
            source=name,
            status=status,
            http_status=status_code,
            checked_at=checked_at,
            duration_ms=duration,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[SourceProbe.source],
            set_={
                "status": statement.excluded.status,
                "http_status": statement.excluded.http_status,
                "checked_at": statement.excluded.checked_at,
                "duration_ms": statement.excluded.duration_ms,
            },
            where=SourceProbe.checked_at < statement.excluded.checked_at,
        )
        session.execute(statement)
    session.commit()


def latest_source_checks(session: Session) -> list[dict]:
    records = {item.source: item for item in session.scalars(select(SourceProbe))}
    return [
        {
            "source": name,
            "url": url,
            "status": records[name].status if name in records else "not_checked",
            "http_status": records[name].http_status if name in records else None,
            "checked_at": records[name].checked_at.isoformat() if name in records else None,
            "duration_ms": records[name].duration_ms if name in records else None,
        }
        for name, url in OFFICIAL_SOURCES.items()
    ]


def source_check_for_url(session: Session, url: str) -> dict | None:
    """Return the last recorded check only when it checked this exact source URL."""
    name = next((name for name, source_url in OFFICIAL_SOURCES.items() if source_url == url), None)
    if name is None:
        return None
    record = session.get(SourceProbe, name)
    if record is None:
        return {"status": "not_checked", "checked_at": None}
    checked_at = record.checked_at
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=UTC)
    return {"status": record.status, "checked_at": checked_at.astimezone(UTC)}
