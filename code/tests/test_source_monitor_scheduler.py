import httpx
import pytest
from sqlalchemy.orm import Session

from app.source_checks import OFFICIAL_SOURCES, latest_source_checks
from app.storage import Base, create_database
from scripts import schedule_source_checks


def test_one_source_monitor_run_persists_results(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'monitor.db').as_posix()}"
    engine = create_database(url)
    Base.metadata.create_all(engine)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 200)

    real_client = httpx.Client
    monkeypatch.setattr(
        schedule_source_checks.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr("sys.argv", ["monitor", "--once", "--database-url", url])
    schedule_source_checks.main()
    with Session(engine) as session:
        checks = latest_source_checks(session)
        assert len(checks) == len(OFFICIAL_SOURCES)
        assert checks[0]["status"] == "server_error"
        assert all(check["checked_at"] for check in checks)
    assert all(request.method == "HEAD" for request in calls)
    engine.dispose()


def test_monitor_refuses_short_interval(monkeypatch):
    monkeypatch.setattr("sys.argv", ["monitor", "--once", "--interval-seconds", "299"])
    with pytest.raises(SystemExit) as error:
        schedule_source_checks.main()
    assert error.value.code == 2
