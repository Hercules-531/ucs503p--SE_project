"""Atomic ingestion of validated source snapshots through a shared adapter contract."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.data import LOCATIONS, SCHEMES
from app.models import LocationRecord, Scheme
from app.search import update_scheme_index
from app.storage import Dataset, DatasetRevision, IngestionRun, StoredRecord, utc_now

LOOKUP_BATCH_SIZE = 500


class DataSourceAdapter(ABC):
    name: str
    kind: str
    model: type[BaseModel]
    id_field: str
    complete_snapshot: bool = False
    preserve_other_sources: bool = False

    @abstractmethod
    def collect(self) -> Iterable[dict[str, Any]]:
        """Collect records from a source snapshot or a permitted source."""

    def normalize(self, raw: dict[str, Any]) -> BaseModel:
        return self.model.model_validate(raw)


class SchemeSnapshotAdapter(DataSourceAdapter):
    name = "curated-schemes"
    kind = "scheme"
    model = Scheme
    id_field = "id"
    complete_snapshot = True

    def collect(self) -> Iterable[dict[str, Any]]:
        return (record.model_dump(mode="json") for record in SCHEMES)


class LocationSnapshotAdapter(DataSourceAdapter):
    name = "curated-pincodes"
    kind = "location"
    model = LocationRecord
    id_field = "pincode"
    complete_snapshot = True

    def collect(self) -> Iterable[dict[str, Any]]:
        return (record.model_dump(mode="json") for record in LOCATIONS.values())


def register_dataset(session: Session, adapter: DataSourceAdapter) -> None:
    dialect = session.get_bind().dialect.name
    insert = {"sqlite": sqlite_insert, "postgresql": postgres_insert}[dialect]
    policy = {
        "record_kind": adapter.kind,
        "complete_snapshot": adapter.complete_snapshot,
        "preserve_other_sources": adapter.preserve_other_sources,
    }
    statement = insert(Dataset).values(source_adapter=adapter.name, **policy)
    registered = session.scalar(
        statement.on_conflict_do_update(
            index_elements=[Dataset.source_adapter],
            set_=policy,
            where=Dataset.record_kind.is_(None) | (Dataset.record_kind == adapter.kind),
        ).returning(Dataset.source_adapter)
    )
    if registered is None:
        session.rollback()
        raise ValueError(f"Dataset {adapter.name} already uses a different record kind")


def bump_revision(session: Session, kind: str) -> None:
    result = session.execute(
        update(DatasetRevision)
        .where(DatasetRevision.kind == kind)
        .values(revision=DatasetRevision.revision + 1)
    )
    if result.rowcount == 0:
        session.add(DatasetRevision(kind=kind, revision=1))


def mark_review(record: StoredRecord, reason: str) -> None:
    payload = dict(record.payload)
    source = dict(payload["source"])
    source["freshness_status"] = "review_due"
    source["review_reason"] = reason
    payload["source"] = source
    record.payload = payload


def validate_scheme_slugs(session: Session, adapter: DataSourceAdapter, records: dict) -> None:
    """Check the resulting catalogue, including records retained from older snapshots."""
    slugs_by_id = {}
    owners = {}
    for identifier, owner, payload in session.execute(
        select(StoredRecord.identifier, StoredRecord.source_adapter, StoredRecord.payload).where(
            StoredRecord.kind == "scheme"
        )
    ):
        slugs_by_id[identifier] = payload["slug"]
        owners[identifier] = owner
    for identifier, scheme in records.items():
        if (
            identifier in owners
            and adapter.preserve_other_sources
            and owners[identifier] != adapter.name
        ):
            continue
        slugs_by_id[identifier] = scheme.slug
    identifiers_by_slug = {}
    for identifier, slug in slugs_by_id.items():
        if slug in identifiers_by_slug:
            raise ValueError(f"Duplicate scheme slug: {slug}")
        identifiers_by_slug[slug] = identifier


def ingest(session: Session, adapter: DataSourceAdapter) -> IngestionRun:
    """Validate the whole batch before updating records; persist failure without partial writes."""
    register_dataset(session, adapter)
    run = IngestionRun(source=adapter.name, started_at=utc_now(), status="running", accepted=0)
    session.add(run)
    session.commit()
    try:
        records: dict[str, BaseModel] = {}
        for raw in adapter.collect():
            normalized = adapter.normalize(raw)
            identifier = str(getattr(normalized, adapter.id_field))
            if identifier in records:
                if records[identifier] != normalized:
                    raise ValueError(f"Conflicting duplicate identifier: {identifier}")
                continue
            records[identifier] = normalized
        if not records:
            raise ValueError("Source returned an empty batch")
        if adapter.kind == "scheme":
            validate_scheme_slugs(session, adapter, records)
        identifiers = list(records)
        accepted = 0
        for start in range(0, len(identifiers), LOOKUP_BATCH_SIZE):
            batch = identifiers[start : start + LOOKUP_BATCH_SIZE]
            indexed_records = []
            existing_records = {
                record.identifier: record
                for record in session.scalars(
                    select(StoredRecord).where(
                        StoredRecord.kind == adapter.kind,
                        StoredRecord.identifier.in_(batch),
                    )
                )
            }
            for identifier in batch:
                payload = records[identifier].model_dump(mode="json")
                existing = existing_records.get(identifier)
                if (
                    existing is not None
                    and adapter.preserve_other_sources
                    and existing.source_adapter != adapter.name
                ):
                    continue
                if existing is None:
                    existing = StoredRecord(kind=adapter.kind, identifier=identifier)
                    session.add(existing)
                existing.payload = payload
                existing.source_url = payload["source"]["url"]
                existing.source_adapter = adapter.name
                existing.updated_at = utc_now()
                accepted += 1
                if adapter.kind == "scheme":
                    indexed_records.append(records[identifier])
            if adapter.kind == "scheme":
                update_scheme_index(session, indexed_records)
        if adapter.complete_snapshot:
            previous = session.scalars(
                select(StoredRecord)
                .where(
                    StoredRecord.kind == adapter.kind,
                    StoredRecord.source_adapter == adapter.name,
                )
                .execution_options(yield_per=500)
            )
            for existing in previous:
                if existing.identifier not in records:
                    mark_review(existing, "absent_from_snapshot")
        bump_revision(session, adapter.kind)
        run.status = "success"
        run.accepted = accepted
        run.finished_at = utc_now()
        session.commit()
    except Exception as exc:
        session.rollback()
        affected = session.scalars(
            select(StoredRecord).where(
                StoredRecord.kind == adapter.kind, StoredRecord.source_adapter == adapter.name
            )
        ).all()
        for existing in affected:
            mark_review(existing, "import_failed")
        if affected:
            bump_revision(session, adapter.kind)
        run.status = "failed"
        run.error = str(exc)[:1000]
        run.finished_at = utc_now()
        session.commit()
        raise
    return run
