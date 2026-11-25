from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class SourceMetadata(BaseModel):
    name: str
    url: HttpUrl
    last_verified: date | None
    snapshot_date: date | None = None
    snapshot_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    license_name: str | None = None
    license_url: HttpUrl | None = None
    provenance_kind: Literal["third_party_mirror"] | None = None
    original_source_url: HttpUrl | None = None
    verification_note: str | None = None
    freshness_status: Literal["current", "review_due", "unknown"] = "current"
    review_reason: Literal["import_failed", "absent_from_snapshot", "unverified_mirror"] | None = (
        None
    )

    @model_validator(mode="after")
    def mark_outdated(self):
        """Old or future verification dates must not be presented as current."""
        if self.last_verified is None:
            self.freshness_status = "review_due" if self.review_reason else "unknown"
            return self
        age = (datetime.now(UTC).date() - self.last_verified).days
        if age < 0:
            self.freshness_status = "unknown"
        elif (age > 30 or self.review_reason is not None) and self.freshness_status == "current":
            self.freshness_status = "review_due"
        return self


class Scheme(BaseModel):
    id: str
    slug: str
    name: str
    short_name: str
    ministry: str
    category: str
    summary: str
    benefit_summary: str
    eligibility_summary: str
    states: list[str] = Field(default_factory=lambda: ["All India"])
    audiences: list[str]
    tags: list[str]
    source: SourceMetadata


class PostOffice(BaseModel):
    office_name: str = Field(min_length=1)
    district: str = Field(min_length=1)
    state: str = Field(min_length=1)
    original_values: dict[str, list[str]] = Field(default_factory=dict)


class LocationRecord(BaseModel):
    pincode: str = Field(pattern=r"^[0-9]{6}$")
    office_name: str
    district: str
    state: str
    country: str = "India"
    offices: list[PostOffice] = Field(default_factory=list)
    source: SourceMetadata


class ResponseMeta(BaseModel):
    api_version: Literal["v1"] = "v1"
    environment: Literal["prototype"] = "prototype"
    source: str
    last_verified: date | None
    generated_at: datetime
    result_count: int | None = None
    total_count: int | None = None
    limit: int | None = None
    offset: int | None = None
    uncertain_excluded_count: int | None = None
    uncertain_included_count: int | None = None


class SuccessEnvelope[DataT](BaseModel):
    data: DataT
    meta: ResponseMeta


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
