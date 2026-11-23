from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

import app.main as web
from app.data import SCHEMES, filter_schemes, uncertain_filter_exclusions
from app.ingestion import SchemeSnapshotAdapter, ingest
from app.search import indexed_scheme_page, indexed_schemes, indexed_uncertain_exclusions
from app.storage import Base, StoredRecord, create_database


@pytest.mark.parametrize(
    "filters",
    [
        {"q": "HEALTH"},
        {"category": "Health", "audience": "Women"},
        {"state": "Punjab"},
        {"state": "Delhi", "audience": "Students"},
        {"q": "%"},
        {"q": "_"},
        {"q": "STRASSE"},
        {"q": "nothing-matches"},
    ],
)
def test_indexed_filters_match_python_semantics(tmp_path, filters):
    engine = create_database(f"sqlite:///{(tmp_path / 'search.db').as_posix()}")
    Base.metadata.create_all(engine)

    class Fixture(SchemeSnapshotAdapter):
        def collect(self):
            yield from super().collect()
            item = SCHEMES[0].model_dump(mode="json")
            item.update(id="special", slug="special", name="Straße 100% support_under")
            yield item

    with Session(engine) as session:
        ingest(session, Fixture())
        all_records = indexed_schemes(session)
        expected = sorted(record.id for record in filter_schemes(records=all_records, **filters))
        actual = [record.id for record in indexed_schemes(session, **filters)]
        assert actual == expected
    engine.dispose()


def test_index_updates_with_reimport(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'update.db').as_posix()}")
    Base.metadata.create_all(engine)

    class Changed(SchemeSnapshotAdapter):
        def collect(self):
            for item in super().collect():
                if item["id"] == "scheme-dhtess":
                    item.update(category="Housing", states=["Punjab"], audiences=["Workers"])
                yield item

    with Session(engine) as session:
        ingest(session, SchemeSnapshotAdapter())
        assert [r.id for r in indexed_schemes(session, state="Delhi", audience="Students")] == [
            "scheme-dhtess"
        ]
        ingest(session, Changed())
        assert not indexed_schemes(session, state="Delhi", audience="Students")
        assert [
            r.id
            for r in indexed_schemes(
                session, state="Punjab", audience="Workers", category="Housing"
            )
        ] == ["scheme-dhtess"]
    engine.dispose()


def test_indexed_page_filters_counts_and_orders_before_limiting(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'pages.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest(session, SchemeSnapshotAdapter())
        expected = indexed_schemes(session, q="health")
        first, total = indexed_scheme_page(session, q="health", limit=1, offset=0)
        second, second_total = indexed_scheme_page(session, q="health", limit=1, offset=1)
        beyond, beyond_total = indexed_scheme_page(session, q="health", limit=1, offset=100)
        assert first + second == expected
        assert total == second_total == beyond_total == 2
        assert beyond == []
    engine.dispose()


def test_indexed_uncertain_counts_match_public_filter_semantics(tmp_path):
    engine = create_database(f"sqlite:///{(tmp_path / 'uncertain.db').as_posix()}")
    Base.metadata.create_all(engine)

    class Fixture(SchemeSnapshotAdapter):
        def collect(self):
            for number, (states, audiences) in enumerate(
                [
                    ([], []),
                    ([], ["Farmers"]),
                    (["Delhi"], []),
                    (["Punjab"], ["Women"]),
                    (["All India"], []),
                ]
            ):
                record = SCHEMES[0].model_dump(mode="json")
                record.update(
                    id=f"fixture-{number}",
                    slug=f"fixture-{number}",
                    states=states,
                    audiences=audiences,
                )
                yield record

    with Session(engine) as session:
        ingest(session, Fixture())
        records = indexed_schemes(session)
        for filters in (
            {},
            {"state": "Punjab"},
            {"audience": "Women"},
            {"state": "Punjab", "audience": "Women"},
            {"state": "Punjab", "q": "no match"},
            {"category": "Health", "audience": "Women"},
        ):
            assert indexed_uncertain_exclusions(session, **filters) == uncertain_filter_exclusions(
                records, **filters
            )
            expected = sorted(

                    record.id
                    for record in filter_schemes(records=records, include_unknown=True, **filters)

            )
            actual = [
                record.id for record in indexed_schemes(session, include_unknown=True, **filters)
            ]
            assert actual == expected
            page, total = indexed_scheme_page(
                session, include_unknown=True, limit=2, offset=0, **filters
            )
            assert [record.id for record in page] == expected[:2]
            assert total == len(expected)
    engine.dispose()


def test_migration_backfills_existing_schemes(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'migrate-search.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "20261108_07")
    engine = create_database(url)
    record = SCHEMES[0]
    with Session(engine) as session:
        session.add(
            StoredRecord(
                kind="scheme",
                identifier=record.id,
                source_url=str(record.source.url),
                source_adapter="legacy",
                payload=record.model_dump(mode="json"),
                updated_at=datetime.now(UTC),
            )
        )
        session.commit()
    command.upgrade(config, "head")
    with Session(engine) as session:
        assert [r.id for r in indexed_schemes(session, q="farmer")] == [record.id]
    command.downgrade(config, "20261108_07")
    assert "scheme_search_index" not in inspect(engine).get_table_names()
    with Session(engine) as session:
        assert session.get(StoredRecord, ("scheme", record.id)) is not None
    engine.dispose()


def test_individual_scheme_lookup_is_indexed_and_does_not_load_catalogue(tmp_path, monkeypatch):
    engine = create_database(f"sqlite:///{(tmp_path / 'details.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest(session, SchemeSnapshotAdapter())
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    monkeypatch.setattr(web, "engine", engine)
    assert web.current_scheme("scheme-pm-kisan").slug == "pm-kisan"
    assert len(statements) == 1
    assert "WHERE" in statements[0].upper()
    statements.clear()
    assert web.current_scheme("pm-kisan").id == "scheme-pm-kisan"
    assert len(statements) == 2
    assert all("WHERE" in statement.upper() for statement in statements)
    statements.clear()
    assert web.current_scheme_by_slug("pm-kisan").id == "scheme-pm-kisan"
    assert len(statements) == 1
    assert "scheme_search_index.slug" in statements[0]
    assert web.current_scheme("missing") is None
    assert web.current_scheme_by_slug("missing") is None
    engine.dispose()
