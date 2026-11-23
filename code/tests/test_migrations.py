from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.data import SCHEMES
from app.storage import SchemeIndex, StoredRecord, create_database, utc_now


def test_upgrade_and_downgrade(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_database(database_url)
    assert {"normalized_records", "ingestion_runs"}.issubset(inspect(engine).get_table_names())
    command.downgrade(config, "base")
    assert "normalized_records" not in inspect(engine).get_table_names()
    engine.dispose()


def test_slug_migration_backfills_existing_data_and_enforces_uniqueness(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'upgrade.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "20261113_08")
    engine = create_database(url)
    from sqlalchemy import JSON, Column, MetaData, String, Table

    # Reflect the old index without using the new ORM model before migration.
    old_index = Table("scheme_search_index", MetaData(), autoload_with=engine)
    old_records = Table(
        "normalized_records",
        MetaData(),
        Column("kind", String, primary_key=True),
        Column("identifier", String, primary_key=True),
        Column("source_url", String),
        Column("source_adapter", String),
        Column("payload", JSON),
        autoload_with=engine,
        extend_existing=True,
    )
    record = SCHEMES[0].model_dump(mode="json")
    with engine.begin() as connection:
        connection.execute(
            old_records.insert().values(
                kind="scheme",
                identifier=record["id"],
                source_url=record["source"]["url"],
                source_adapter="fixture",
                payload=record,
                updated_at=utc_now(),
            )
        )
        connection.execute(
            old_index.insert().values(
                identifier=record["id"],
                category_key="agriculture",
                searchable="fixture",
            )
        )
    command.upgrade(config, "head")
    with Session(engine) as session:
        assert session.scalar(select(SchemeIndex.slug)) == record["slug"]
        session.add(
            SchemeIndex(
                identifier="conflict", slug=record["slug"], category_key="test", searchable="test"
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.get(StoredRecord, ("scheme", record["id"])) is not None
    command.downgrade(config, "20261113_08")
    assert "slug" not in {
        column["name"] for column in inspect(engine).get_columns("scheme_search_index")
    }
    engine.dispose()
