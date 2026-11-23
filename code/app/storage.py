"""Persistence for normalized, attributed civic records and ingestion history."""

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class StoredRecord(Base):
    __tablename__ = "normalized_records"

    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    identifier: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_adapter: Mapped[str | None] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DatasetRevision(Base):
    __tablename__ = "dataset_revisions"
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Dataset(Base):
    """Canonical dataset identity and the adapter's declared import policy."""

    __tablename__ = "datasets"

    source_adapter: Mapped[str] = mapped_column(String(128), primary_key=True)
    record_kind: Mapped[str | None] = mapped_column(String(32))
    complete_snapshot: Mapped[bool | None] = mapped_column(Boolean)
    preserve_other_sources: Mapped[bool | None] = mapped_column(Boolean)


class SchemeIndex(Base):
    __tablename__ = "scheme_search_index"
    identifier: Mapped[str] = mapped_column(String(128), primary_key=True)
    slug: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True, index=True)
    category_key: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    searchable: Mapped[str] = mapped_column(Text, nullable=False)


class SchemeFilterValue(Base):
    __tablename__ = "scheme_search_values"
    identifier: Mapped[str] = mapped_column(
        ForeignKey("scheme_search_index.identifier", ondelete="CASCADE"), primary_key=True
    )
    attribute: Mapped[str] = mapped_column(String(16), primary_key=True)
    value: Mapped[str] = mapped_column(Text, primary_key=True, index=True)


class ImportCheckpoint(Base):
    __tablename__ = "import_checkpoints"
    source: Mapped[str] = mapped_column(String(128), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_on: Mapped[date] = mapped_column(Date, nullable=False)
    run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(1000))


class SourceProbe(Base):
    __tablename__ = "source_probes"
    source: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)


class DeveloperAccount(Base):
    __tablename__ = "developer_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)


class DeveloperSession(Base):
    __tablename__ = "developer_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("developer_accounts.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("developer_accounts.id"), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiRequestLog(Base):
    __tablename__ = "api_request_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_id: Mapped[str] = mapped_column(ForeignKey("api_keys.id"), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def create_database(url: str):
    return create_engine(url, pool_pre_ping=True)


def read_records(session: Session, kind: str) -> list[dict]:
    rows = session.scalars(
        select(StoredRecord).where(StoredRecord.kind == kind).order_by(StoredRecord.identifier)
    )
    return [row.payload for row in rows]


def utc_now() -> datetime:
    return datetime.now(UTC)
