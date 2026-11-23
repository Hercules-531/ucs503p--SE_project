import sqlite3

import pytest
from alembic import command
from alembic.config import Config

from scripts.start_local import ROOT, initialize_database, sqlite_url
from scripts.upgrade_local_copy import upgrade_copy


def test_upgrade_creates_new_migrated_copy_and_preserves_source(tmp_path, monkeypatch):
    source = tmp_path / "old.db"
    destination = tmp_path / "upgraded.db"
    initialize_database(source)
    monkeypatch.setenv("DATABASE_URL", sqlite_url(source))
    command.downgrade(Config(str(ROOT / "alembic.ini")), "20261113_08")
    before = source.read_bytes()
    upgrade_copy(source, destination)
    assert source.read_bytes() == before
    with sqlite3.connect(source) as old, sqlite3.connect(destination) as new:
        assert old.execute("SELECT version_num FROM alembic_version").fetchone() == ("20261113_08",)
        assert new.execute("SELECT version_num FROM alembic_version").fetchone() == ("20261115_09",)
        old_count = old.execute("SELECT COUNT(*) FROM normalized_records").fetchone()
        assert old_count[0] > 0
        assert new.execute("SELECT COUNT(*) FROM normalized_records").fetchone() == old_count
        assert new.execute(
            "SELECT COUNT(*) FROM scheme_search_index WHERE slug IS NULL"
        ).fetchone() == (0,)
    assert not list(tmp_path.glob(".bharatos-upgrade-*.db"))


def test_upgrade_rejects_existing_destination_and_unrelated_database(tmp_path):
    source = tmp_path / "unrelated.db"
    destination = tmp_path / "existing.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE important_data (value TEXT)")
        connection.execute("INSERT INTO important_data VALUES ('keep')")
    destination.write_bytes(b"keep destination")
    before = source.read_bytes()
    with pytest.raises(ValueError, match="Destination already exists"):
        upgrade_copy(source, destination)
    assert destination.read_bytes() == b"keep destination"
    destination.unlink()
    with pytest.raises(sqlite3.Error):
        upgrade_copy(source, destination)
    assert source.read_bytes() == before
    assert not destination.exists()
    assert not list(tmp_path.glob(".bharatos-upgrade-*.db"))


def test_failed_migration_does_not_publish_a_copy(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    destination = tmp_path / "copy.db"
    initialize_database(source)
    before = source.read_bytes()

    def fail_upgrade(*args, **kwargs):
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr("scripts.upgrade_local_copy.command.upgrade", fail_upgrade)
    with pytest.raises(RuntimeError, match="simulated migration failure"):
        upgrade_copy(source, destination)
    assert source.read_bytes() == before
    assert not destination.exists()
    assert not list(tmp_path.glob(".bharatos-upgrade-*.db"))
