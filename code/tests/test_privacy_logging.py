import logging

import pytest

from app.privacy import PrivacyAccessFilter, safe_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/?q=private-search&state=private-state", "/"),
        ("/locations?pincode=147004", "/locations"),
        ("/schemes/private-slug?secret=value", "/schemes/{slug}"),
        ("/api/v1/schemes/private-id", "/api/v1/schemes/{scheme_id}"),
        ("/api/v1/locations/pincode/147004", "/api/v1/locations/pincode/{pincode}"),
        ("/api/v1/developers/keys/private-id/rotate", "/api/v1/developers/keys/{key_id}"),
        ("/unknown-private-path", "/[redacted]"),
    ],
)
def test_access_paths_do_not_expose_user_input(path, expected):
    assert safe_path(path) == expected


def test_access_filter_removes_client_and_query_and_rejects_unexpected_format():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("192.0.2.1:1234", "GET", "/?q=private-search", "1.1", 200),
        None,
    )
    assert PrivacyAccessFilter().filter(record)
    rendered = record.getMessage()
    assert "private-search" not in rendered
    assert "192.0.2.1" not in rendered
    assert '"GET / HTTP/1.1"' in rendered
    unexpected = logging.LogRecord("uvicorn.access", logging.INFO, "", 1, "secret", (), None)
    assert not PrivacyAccessFilter().filter(unexpected)
