import subprocess

import pytest

from scripts.database_backup import backup, compose_command, restore_to_new_database


def test_backup_refuses_overwrite_and_validates_dump(tmp_path, monkeypatch):
    destination = tmp_path / "backup.dump"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        kwargs["stdout"].write(b"PGDMPfixture")

    monkeypatch.setattr(subprocess, "run", fake_run)
    backup(destination, "testproject")
    assert destination.read_bytes() == b"PGDMPfixture"
    assert "pg_dump" in calls[0]
    with pytest.raises(FileExistsError):
        backup(destination, "testproject")
    assert len(calls) == 1


def test_backup_can_use_a_recovered_database(tmp_path, monkeypatch):
    destination = tmp_path / "backup.dump"

    def fake_run(command, **kwargs):
        assert command[command.index("-d") + 1] == "bharatos_restore_active"
        kwargs["stdout"].write(b"PGDMPfixture")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="Backup database"):
        backup(destination, database="postgres")
    backup(destination, database="bharatos_restore_active")
    assert destination.read_bytes() == b"PGDMPfixture"


@pytest.mark.parametrize("failure", ["pg_dump", "invalid_dump", "destination_race"])
def test_backup_publishes_only_a_successful_dump(tmp_path, monkeypatch, failure):
    destination = tmp_path / "backup.dump"

    def fake_run(command, **kwargs):
        assert not destination.exists()
        kwargs["stdout"].write(b"PGDMPfixture" if failure != "invalid_dump" else b"partial")
        if failure == "pg_dump":
            raise subprocess.CalledProcessError(1, command)
        if failure == "destination_race":
            destination.write_bytes(b"another backup")

    monkeypatch.setattr(subprocess, "run", fake_run)
    errors = {
        "pg_dump": subprocess.CalledProcessError,
        "invalid_dump": ValueError,
        "destination_race": FileExistsError,
    }
    with pytest.raises(errors[failure]):
        backup(destination, "testproject")
    if failure == "destination_race":
        assert destination.read_bytes() == b"another backup"
        assert list(tmp_path.iterdir()) == [destination]
    else:
        assert not list(tmp_path.iterdir())


def test_restore_validates_target_and_never_restores_if_create_fails(tmp_path, monkeypatch):
    source = tmp_path / "backup.dump"
    source.write_bytes(b"PGDMPfixture")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "createdb" in command:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ValueError):
        restore_to_new_database(source, "bharatos")
    with pytest.raises(subprocess.CalledProcessError):
        restore_to_new_database(source, "bharatos_restore_test")
    assert len(calls) == 2
    assert "--file=/dev/null" in calls[0]
    assert "createdb" in calls[1]
    with pytest.raises(ValueError):
        compose_command("--invalid", "createdb")


@pytest.mark.parametrize("archive", [b"not a dump", b"PGDMPcorrupt"])
def test_restore_requires_valid_archive_before_creating_database(tmp_path, monkeypatch, archive):
    source = tmp_path / "invalid.dump"
    source.write_bytes(archive)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert "--file=/dev/null" in command
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", fake_run)
    if archive.startswith(b"PGDMP"):
        with pytest.raises(subprocess.CalledProcessError):
            restore_to_new_database(source, "bharatos_restore_test")
        assert len(calls) == 1
    else:
        with pytest.raises(ValueError, match="custom-format"):
            restore_to_new_database(source, "bharatos_restore_test")
        assert not calls


def test_restore_stream_is_rewound_for_child_process(tmp_path, monkeypatch):
    source = tmp_path / "backup.dump"
    source.write_bytes(b"PGDMP" + b"x" * 10000)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "pg_restore" in command:
            # Child processes receive the underlying descriptor, not Python's read buffer.
            assert kwargs["stdin"].read(5) == b"PGDMP"
            kwargs["stdin"].read()

    monkeypatch.setattr(subprocess, "run", fake_run)
    restore_to_new_database(source, "bharatos_restore_test")
    assert len(calls) == 3
