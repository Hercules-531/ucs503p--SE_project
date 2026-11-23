"""Remove user-supplied request details from Uvicorn access logs."""

import logging
from urllib.parse import urlsplit

SAFE_PATHS = frozenset(
    {
        "/",
        "/developers",
        "/locations",
        "/docs",
        "/reference",
        "/openapi.json",
        "/admin",
        "/health/live",
        "/health/ready",
        "/api/v1/schemes",
        "/api/v1/developers/register",
        "/api/v1/developers/login",
        "/api/v1/developers/logout",
        "/api/v1/developers/keys",
        "/api/v1/developers/usage",
        "/api/v1/admin/overview",
        "/api/v1/admin/source-checks",
    }
)


def safe_path(raw_path: str) -> str:
    path = urlsplit(raw_path).path
    if path in SAFE_PATHS:
        return path
    if path.startswith("/schemes/"):
        return "/schemes/{slug}"
    if path.startswith("/api/v1/schemes/"):
        return "/api/v1/schemes/{scheme_id}"
    if path.startswith("/api/v1/locations/pincode/"):
        return "/api/v1/locations/pincode/{pincode}"
    if path.startswith("/api/v1/developers/keys/"):
        return "/api/v1/developers/keys/{key_id}"
    if path.startswith("/static/"):
        return "/static/{asset}"
    if path.startswith("/diagrams/"):
        return "/diagrams/{asset}"
    return "/[redacted]"


class PrivacyAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn's access logger supplies (client, method, path, protocol, status).
        # Drop unexpected formats rather than risk emitting an unredacted request.
        if not isinstance(record.args, tuple) or len(record.args) != 5:
            return False
        _, method, path, protocol, status = record.args
        if not isinstance(path, str) or not isinstance(status, int):
            return False
        try:
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                method = "OTHER"
            if protocol not in {"1.0", "1.1", "2", "3"}:
                protocol = "?"
            record.msg = '%s - "%s %s HTTP/%s" %d'
            record.args = ("-", method, safe_path(path), protocol, status)
        except ValueError:
            return False
        return True


def install_access_log_filter() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, PrivacyAccessFilter) for item in logger.filters):
        logger.addFilter(PrivacyAccessFilter())
