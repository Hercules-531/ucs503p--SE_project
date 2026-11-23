"""Measure local HTTP concurrency without recording credentials or query values."""

import argparse
import asyncio
import json
import math
import os
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

LEVELS = (10, 50, 100, 500)


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percentile_value) - 1)]


def valid_provenance(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    meta, records = payload.get("meta"), payload.get("data")
    if not isinstance(meta, dict) or not all(meta.get(k) for k in ("source", "last_verified")):
        return False
    return isinstance(records, list) and bool(records) and all(
        isinstance(record, dict)
        and isinstance(record.get("source"), dict)
        and record["source"].get("url")
        and record["source"].get("last_verified")
        for record in records
    )


async def measure_level(
    client: httpx.AsyncClient, concurrency: int, total: int, *, endpoint: str = "/api/v1/schemes"
) -> dict:
    semaphore = asyncio.Semaphore(concurrency)

    async def request_one() -> tuple[int | None, float, bool]:
        async with semaphore:
            started = time.perf_counter()
            try:
                response = await client.get(endpoint)
                duration = (time.perf_counter() - started) * 1000
                try:
                    provenance = response.status_code == 200 and valid_provenance(response.json())
                except ValueError:
                    provenance = False
                return response.status_code, duration, provenance
            except httpx.RequestError:
                return None, (time.perf_counter() - started) * 1000, False

    started = time.perf_counter()
    results = await asyncio.gather(*(request_one() for _ in range(total)))
    elapsed = time.perf_counter() - started
    latencies = [duration for _, duration, _ in results]
    success = sum(status == 200 for status, _, _ in results)
    attributed = sum(provenance for _, _, provenance in results)
    status_counts: dict[str, int] = {}
    for status, _, _ in results:
        label = str(status) if status is not None else "network_error"
        status_counts[label] = status_counts.get(label, 0) + 1
    return {
        "concurrency": concurrency,
        "requests": total,
        "successful": success,
        "error_rate": round((total - success) / total, 4),
        "p50_ms": round(statistics.median(latencies), 2),
        "p95_ms": round(percentile(latencies, 0.95), 2),
        "elapsed_seconds": round(elapsed, 3),
        "requests_per_second": round(total / elapsed, 2),
        "provenance_coverage": round(attributed / success, 4) if success else None,
        "status_counts": status_counts,
    }


async def run(
    base_url: str, api_key: str, requests_per_level: int, *, endpoint: str = "/api/v1/schemes"
) -> list[dict]:
    limits = httpx.Limits(max_connections=550, max_keepalive_connections=100)
    async with httpx.AsyncClient(
        base_url=base_url, headers={"X-API-Key": api_key}, timeout=30.0, limits=limits,
        trust_env=False,
    ) as client:
        warmup = await client.get(endpoint)
        warmup.raise_for_status()
        return [
            await measure_level(client, level, requests_per_level, endpoint=endpoint)
            for level in LEVELS
        ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8767")
    parser.add_argument("--requests", type=int, default=500, help="Requests at each level (>=500)")
    parser.add_argument("--limit", type=int, help="Optional scheme page size (1–100)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--configuration", required=True, help="Describe the server setup")
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        parser.error("Only localhost URLs are permitted")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("URL must not contain credentials, query or fragment")
    if args.requests < max(LEVELS):
        parser.error("Requests per level must be at least 500")
    if args.limit is not None and not 1 <= args.limit <= 100:
        parser.error("Page size must be between 1 and 100")
    key = os.environ.get("BHARATOS_BENCHMARK_KEY")
    if not key:
        parser.error("Set BHARATOS_BENCHMARK_KEY in the environment")
    endpoint = "/api/v1/schemes"
    if args.limit is not None:
        endpoint += f"?limit={args.limit}"
    results = asyncio.run(run(args.url.rstrip("/"), key, args.requests, endpoint=endpoint))
    report = {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "configuration": args.configuration,
        "client_platform": platform.platform(),
        "python": platform.python_version(),
        "endpoint": endpoint,
        "methodology": (
            "One warm-up, then fixed request count at each concurrency; p95 includes failures."
        ),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
