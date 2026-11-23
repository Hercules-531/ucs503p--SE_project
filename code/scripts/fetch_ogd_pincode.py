"""Download an OGD API resource to a new CSV for separate provenance review."""

import argparse
import csv
import logging
import os
import tempfile
from pathlib import Path
from uuid import UUID

import httpx

PAGE_SIZE = 1000
MAX_RECORDS = 250000
MAX_PAGES = 1000
REQUIRED = {"officename", "pincode", "district", "statename"}


def fetch_snapshot(resource: str, key: str, destination: Path, client: httpx.Client) -> int:
    """Fetch an entire bounded result into a new file; do not persist credentials."""
    try:
        resource_id = str(UUID(resource))
    except ValueError:
        raise ValueError("Resource ID must be a UUID") from None
    if not key.strip():
        raise ValueError("Set OGD_API_KEY in the environment")
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Destination already exists")
    if not destination.parent.is_dir():
        raise ValueError("Destination directory does not exist")

    descriptor, name = tempfile.mkstemp(prefix=".ogd-fetch-", suffix=".csv", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = None
            total = None
            offset = 0
            for _ in range(MAX_PAGES):
                try:
                    response = client.get(
                        f"https://api.data.gov.in/resource/{resource_id}",
                        params={
                            "api-key": key,
                            "format": "json",
                            "offset": offset,
                            "limit": PAGE_SIZE,
                        },
                        timeout=20,
                        follow_redirects=False,
                    )
                except httpx.HTTPError:
                    raise ValueError("OGD request failed; check connectivity and access") from None
                if response.status_code != 200:
                    raise ValueError(f"OGD request returned HTTP {response.status_code}")
                try:
                    payload = response.json()
                    page_total = int(payload["total"])
                    records = payload["records"]
                except (ValueError, TypeError, KeyError):
                    raise ValueError("OGD response has an invalid envelope") from None
                if (
                    not isinstance(records, list)
                    or len(records) > PAGE_SIZE
                    or page_total < 1
                    or page_total > MAX_RECORDS
                ):
                    raise ValueError("OGD returned an empty or oversized result")
                try:
                    returned_offset = int(payload["offset"])
                    returned_count = int(payload["count"])
                except (KeyError, TypeError, ValueError):
                    raise ValueError("OGD response lacks valid pagination metadata") from None
                if returned_offset != offset or returned_count != len(records):
                    raise ValueError("OGD returned inconsistent pagination metadata")
                if total is None:
                    total = page_total
                if total != page_total or not records or offset + len(records) > total:
                    raise ValueError("OGD pagination changed or ended unexpectedly")
                for record in records:
                    if not isinstance(record, dict):
                        raise ValueError("OGD response contains a non-object record")
                    normalized = {str(k).casefold(): v for k, v in record.items()}
                    if len(normalized) != len(record) or not REQUIRED.issubset(normalized):
                        raise ValueError("OGD record lacks unambiguous PIN directory fields")
                    values = [normalized[field] for field in sorted(REQUIRED)]
                    if any(
                        not isinstance(value, (str, int)) or isinstance(value, bool)
                        for value in values
                    ):
                        raise ValueError("OGD record has unsupported PIN field values")
                    if writer is None:
                        writer = csv.writer(stream)
                        writer.writerow(sorted(REQUIRED))
                    writer.writerow(values)
                offset += len(records)
                if offset == total:
                    break
            else:
                raise ValueError("OGD pagination exceeded the page limit")
        # Atomic publication refuses to replace an existing file.
        os.link(temporary, destination)
        return offset
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resource_id", help="UUID copied from the official resource API page")
    parser.add_argument("destination", type=Path, help="New CSV path in an existing directory")
    args = parser.parse_args()
    # HTTPX's INFO request logging includes query strings, which contain the API key.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        with httpx.Client(trust_env=False) as client:
            count = fetch_snapshot(
                args.resource_id, os.getenv("OGD_API_KEY", ""), args.destination, client
            )
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Download failed: {exc}\n")
    print(
        f"Downloaded {count} rows to {args.destination}. "
        "Verify origin, date and licence before import."
    )


if __name__ == "__main__":
    main()
