"""Cache canonical records without storing user queries or credentials."""

import json
import logging

from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.storage import DatasetRevision, read_records

logger = logging.getLogger(__name__)


def record_metric(client, namespace: str, name: str) -> None:
    try:
        client.hincrby(f"bharatos:cache-metrics:v1:{namespace}", name, 1)
    except RedisError:
        logger.warning("Could not record cache metric")


def cache_metrics(client, namespace: str) -> dict:
    if client is None:
        return {
            "status": "not_configured",
            "hits": None,
            "misses": None,
            "errors": None,
            "hit_ratio": None,
        }
    try:
        values = client.hgetall(f"bharatos:cache-metrics:v1:{namespace}")
        counters = {
            key.decode() if isinstance(key, bytes) else key: int(value)
            for key, value in values.items()
        }
        hits, misses, errors = (counters.get(name, 0) for name in ("hits", "misses", "errors"))
        ratio = round(hits / (hits + misses), 4) if hits + misses else None
        return {
            "status": "available",
            "hits": hits,
            "misses": misses,
            "errors": errors,
            "hit_ratio": ratio,
        }
    except (RedisError, ValueError, TypeError):
        return {
            "status": "unavailable",
            "hits": None,
            "misses": None,
            "errors": None,
            "hit_ratio": None,
        }


def cached_records(
    session: Session, kind: str, client, namespace: str, ttl: int = 120
) -> list[dict]:
    if client is None:
        return read_records(session, kind)
    revision = session.get(DatasetRevision, kind)
    # Existing databases without an ingestion revision are read directly until reimported.
    if revision is None:
        return read_records(session, kind)
    cache_key = f"bharatos:records:v1:{namespace}:{kind}:{revision.revision}"
    try:
        value = client.get(cache_key)
        if value is not None:
            parsed = json.loads(value)
            if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
                record_metric(client, namespace, "hits")
                return parsed
            raise ValueError("Invalid cached record shape")
        record_metric(client, namespace, "misses")
    except (ValueError, TypeError):
        record_metric(client, namespace, "misses")
        record_metric(client, namespace, "errors")
        logger.warning("Record cache invalid; reading database")
    except RedisError:
        record_metric(client, namespace, "errors")
        logger.warning("Record cache unavailable or invalid; reading database")
    records = read_records(session, kind)
    try:
        client.set(cache_key, json.dumps(records), ex=ttl)
    except RedisError:
        record_metric(client, namespace, "errors")
        logger.warning("Could not update record cache")
    return records
