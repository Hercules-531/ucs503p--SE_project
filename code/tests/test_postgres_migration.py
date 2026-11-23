"""Opt-in PostgreSQL migration verification using a temporary, isolated schema."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.data import SCHEMES
from app.storage import Dataset, SchemeIndex, StoredRecord, create_database, utc_now


@pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_MIGRATION_URL"), reason="No disposable PostgreSQL configured"
)
def test_populated_postgres_slug_upgrade_and_conflict_recovery(monkeypatch):
    url = os.environ["TEST_POSTGRES_MIGRATION_URL"]
    schema = "bharatos_test_" + uuid4().hex
    admin = create_database(url)
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    scoped_url = make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
    scoped_url = scoped_url.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", scoped_url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    engine = create_database(scoped_url)
    try:
        command.upgrade(config, "20261113_08")
        metadata = MetaData()
        records = Table("normalized_records", metadata, autoload_with=engine)
        index = Table("scheme_search_index", metadata, autoload_with=engine)
        record = SCHEMES[0].model_dump(mode="json")
        with engine.begin() as connection:
            for identifier in (record["id"], "duplicate-id"):
                payload = {**record, "id": identifier}
                connection.execute(
                    records.insert().values(
                        kind="scheme",
                        identifier=identifier,
                        source_url=record["source"]["url"],
                        source_adapter="fixture",
                        payload=payload,
                        updated_at=utc_now(),
                    )
                )
                connection.execute(
                    index.insert().values(
                        identifier=identifier,
                        category_key="fixture",
                        searchable="fixture",
                    )
                )
        with pytest.raises(ValueError, match="duplicate scheme slug"):
            command.upgrade(config, "head")
        assert "slug" not in {
            col["name"] for col in inspect(engine).get_columns("scheme_search_index")
        }
        with engine.begin() as connection:
            connection.execute(index.delete().where(index.c.identifier == "duplicate-id"))
            connection.execute(records.delete().where(records.c.identifier == "duplicate-id"))
        command.upgrade(config, "head")
        with Session(engine) as session:
            assert session.scalar(select(SchemeIndex.slug)) == record["slug"]
            dataset = session.get(Dataset, "fixture")
            assert dataset.record_kind == "scheme"
            assert dataset.complete_snapshot is None
            assert session.get(StoredRecord, ("scheme", record["id"])).payload == record
            session.add(
                SchemeIndex(
                    identifier="conflict",
                    slug=record["slug"],
                    category_key="fixture",
                    searchable="fixture",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
        command.downgrade(config, "20261113_08")
        assert "slug" not in {
            col["name"] for col in inspect(engine).get_columns("scheme_search_index")
        }
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()
