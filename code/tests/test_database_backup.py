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


def test_restore_validates_target_and_never_restores_if_create_fails(tmp_path, monkeypatch):
    source = tmp_path / "backup.dump"
    source.write_bytes(b"PGDMPfixture")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ValueError):
        restore_to_new_database(source, "bharatos")
    with pytest.raises(subprocess.CalledProcessError):
        restore_to_new_database(source, "bharatos_restore_test")
    assert len(calls) == 1
    assert "createdb" in calls[0]
    with pytest.raises(ValueError):
        compose_command("--invalid", "createdb")


def test_restore_requires_valid_archive_before_creating_database(tmp_path, monkeypatch):
    source = tmp_path / "invalid.dump"
    source.write_bytes(b"not a dump")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("must not execute"))
    with pytest.raises(ValueError, match="custom-format"):
        restore_to_new_database(source, "bharatos_restore_test")


def test_restore_stream_is_rewound_for_child_process(tmp_path, monkeypatch):
    source = tmp_path / "backup.dump"
    source.write_bytes(b"PGDMP" + b"x" * 10000)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "pg_restore" in command:
            # Child processes receive the underlying descriptor, not Python's read buffer.
            assert kwargs["stdin"].read(5) == b"PGDMP"

    monkeypatch.setattr(subprocess, "run", fake_run)
    restore_to_new_database(source, "bharatos_restore_test")
    assert len(calls) == 2
