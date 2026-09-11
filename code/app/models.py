from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class SourceMetadata(BaseModel):
    name: str
    url: HttpUrl
    last_verified: date
    freshness_status: Literal["current", "review_due", "unknown"] = "current"


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


class LocationRecord(BaseModel):
    pincode: str = Field(pattern=r"^\d{6}$")
    office_name: str
    district: str
    state: str
    country: str = "India"
    source: SourceMetadata


class ResponseMeta(BaseModel):
    api_version: Literal["v1"] = "v1"
    environment: Literal["prototype"] = "prototype"
    source: str
    last_verified: date
    generated_at: datetime
    result_count: int | None = None


class SuccessEnvelope[DataT](BaseModel):
    data: DataT
    meta: ResponseMeta


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
