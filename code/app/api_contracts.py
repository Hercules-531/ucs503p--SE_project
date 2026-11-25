"""JSON response contracts for developer access and administration."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

IsoTimestamp = Annotated[str, Field(description="ISO 8601 timestamp. An omitted offset means UTC.")]
IsoDate = Annotated[str, Field(json_schema_extra={"format": "date"})]


class MessageResponse(BaseModel):
    message: str


class DeveloperLoginResponse(BaseModel):
    session_token: str = Field(description="Bearer token for developer account endpoints.")
    expires_at: IsoTimestamp


class IssuedKeyResponse(MessageResponse):
    id: str
    key: str = Field(description="Full API key, returned only upon creation or rotation.")


class DeveloperKeySummary(BaseModel):
    id: str
    prefix: str
    revoked: bool


class DeveloperKeysResponse(BaseModel):
    keys: list[DeveloperKeySummary]


class EndpointUsage(BaseModel):
    path: str
    count: int


class DeveloperUsageResponse(BaseModel):
    total_requests: int
    average_duration_ms: float | None
    requests_today: int
    success_rate: float | None = Field(
        description="Fraction of recorded requests with a 2xx status."
    )
    endpoints: list[EndpointUsage]


class RouteErrorCount(BaseModel):
    route: str
    status: int
    count: int


class RecentApiErrors(BaseModel):
    since: IsoTimestamp
    until: IsoTimestamp
    by_route: list[RouteErrorCount]


class IngestionRunSummary(BaseModel):
    source: str
    status: str
    accepted: int
    started_at: IsoTimestamp
    finished_at: IsoTimestamp | None
    failure_code: str | None
    failure_position: int | None
    failure_position_kind: str | None


class SourceSummary(BaseModel):
    source: str
    record_kind: str | None
    complete_snapshot: bool | None
    preserve_other_sources: bool | None
    records: int
    current: int
    review_due: int
    unknown: int
    complete_records: int
    consistent_records: int
    oldest_verified: IsoDate | None
    last_import_status: str
    last_import_started_at: IsoTimestamp | None
    freshness_percent: float | None
    completeness_percent: float | None
    consistency_percent: float | None


class SourceCheck(BaseModel):
    source: str
    url: str
    status: str
    http_status: int | None
    checked_at: IsoTimestamp | None
    duration_ms: float | None


class SourceChecksResponse(BaseModel):
    source_checks: list[SourceCheck]


class CacheMetrics(BaseModel):
    status: Literal["available", "not_configured", "unavailable"]
    hits: int | None
    misses: int | None
    errors: int | None
    hit_ratio: float | None


class MonitoringAlert(BaseModel):
    severity: Literal["warning", "error"]
    code: str
    message: str


class AdminOverviewResponse(SourceChecksResponse):
    record_counts: dict[str, int]
    request_count: int
    error_count: int
    error_rate: float | None
    recent_api_errors: RecentApiErrors
    recent_ingestion_runs: list[IngestionRunSummary]
    sources: list[SourceSummary]
    cache: CacheMetrics
    alerts: list[MonitoringAlert]
