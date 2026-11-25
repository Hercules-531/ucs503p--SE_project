# Local prototype performance measurement

## 25 November official archive import

Two consecutive imports of the [May 2019 Department of Posts archive](../DATA_SOURCES.md#department-of-posts-may-2019-archive)
into an isolated PostgreSQL 17 database each accepted 19,252 PINs. The database retained
19,252 distinct location records after both runs. An authenticated request for `515631` returned
15 offices, the official download URL, the file checksum, the archive date and `review_due`
status. The response's `last_verified` remained empty because current details were unverified.
The SQLite localhost launcher also imported all 19,252 PINs in a separate database.

## 23 November Compose evaluation

The 23 November 2026 run used a Windows client and one Docker-hosted Uvicorn worker built from
`986aa17`, with PostgreSQL 17 and Redis 7. The isolated database contained 24 schemes from the
curated and PIB adapters and 19,300 PINs, including the historical third-party mirror. The
benchmark exercised the scheme list. A separate authenticated PIN lookup returned 15 offices for
`515631` with mirror provenance and a null verification date.

| Concurrency | p95, full list | p95, 12-record page |
| ---: | ---: | ---: |
| 10 | 48.97 ms | 44.40 ms |
| 50 | 302.26 ms | 450.37 ms |
| 100 | 1,325.76 ms | 1,296.56 ms |
| 500 | 2,328.55 ms | 2,044.31 ms |

All 500 requests at every level succeeded in each run. Every successful response contained a
nonempty result set and dated source metadata in the envelope and each returned record. This
metric measures the presence of provenance fields. Some sources are historical and still require
review. The paged API reads through the database, while the full-list API uses the Redis catalogue
cache. The runs were sequential, once per endpoint, and used different response sizes and access
paths. The local test suite was running during the start of the full-list run. At 500 concurrent
requests, both runs exceeded two seconds at p95. These results describe
one local configuration, and the PIN endpoint has no concurrency results from this run.

An automated HTTP check registered a test account, signed in, created a key and made calls to
the list and PIN endpoints. Usage reported all 4,005 authenticated requests, including warm-ups
and smoke calls. The admin endpoint reported the expected record counts and 2,001 cache hits,
one miss and zero cache errors. The revoked key received HTTP 401. The separate developer pilot
still requires observations from volunteers.

The complete test suite passed all 149 tests in a Linux container against the seeded PostgreSQL
and Redis services, including the populated PostgreSQL migration and Redis cache checks. The
test stack and its disposable volume were removed after verification.

Raw data is available for the [full list](local-compose-2026-11-23-full.json) and
[12-record page](local-compose-2026-11-23-page-12.json). To repeat, start an isolated Compose project,
apply migrations and import the curated, JanSamarth, transport, environment and pinned mirror
snapshots. Launch one web worker on an unused localhost port with `API_RATE_LIMIT=10000` and the
default 60-second window. Create a personal key and supply it through `BHARATOS_BENCHMARK_KEY`.
Run `python -m scripts.measure_performance` with `--url`, `--configuration` and a new `--output`
file. Repeat with `--limit 12` and a second output file. Use a separate key or wait for the quota
window if repeating multiple runs. A test quota override belongs in the isolated test process.

## 5 November prototype baseline

The recorded run in `local-prototype.json` measured one Windows localhost process on 5 November
2026. The server used one Uvicorn worker, in-memory scheme snapshots and the demonstration key;
PostgreSQL, Redis and rate limiting were not enabled. Client and server shared the same machine.
This is a baseline for the prototype, not a production capacity estimate.

Each concurrency level ran 500 GET requests to `/api/v1/schemes`, after one warm-up request.
The p95 is the nearest-rank 95th percentile of client-observed request latency, including failed
requests; time waiting for the benchmark's concurrency semaphore is excluded. Error rate counts
anything other than HTTP 200, including connection errors. Provenance coverage is the fraction of
successful responses containing source and verification fields in metadata and in each record.

| Concurrent requests | Successful / total | p95 latency | Error rate | Provenance coverage |
| --- | ---: | ---: | ---: | ---: |
| 10 | 500 / 500 | 54.74 ms | 0% | 100% |
| 50 | 500 / 500 | 858.19 ms | 0% | 100% |
| 100 | 500 / 500 | 2,204.37 ms | 0% | 100% |
| 500 | 500 / 500 | 3,294.57 ms | 0% | 100% |

This is a single short run with 500 samples per level. The large p95 increase under higher
concurrency is a finding to investigate, not proof of a universal performance limit. Repeat runs
are required. A developer time-to-first-call pilot has not been conducted.
The [pilot protocol](DEVELOPER_PILOT.md) provides a repeatable task and outcome summary procedure;
it contains no participant results.

## PostgreSQL and Redis run

The separate `local-postgres-redis.json` run on 8 November 2026 used a Windows HTTP client and
one Docker-hosted Uvicorn worker, PostgreSQL 17.11, Redis 7.4.12, eight curated scheme snapshots,
and an intentionally raised API quota of 5,000 requests per 60 seconds. The cache was warmed
before the measured levels. This is a local single-run result, not a production capacity claim.

| Concurrent requests | Successful / total | p95 latency | Error rate | Provenance coverage |
| --- | ---: | ---: | ---: | ---: |
| 10 | 500 / 500 | 48.98 ms | 0% | 100% |
| 50 | 500 / 500 | 877.24 ms | 0% | 100% |
| 100 | 500 / 500 | 1,799.95 ms | 0% | 100% |
| 500 | 500 / 500 | 3,167.86 ms | 0% | 100% |

Redis reported 4,001 cache hits and one miss after the warm-up and 2,000 measured requests;
the list route read the catalogue twice per request in that run. PostgreSQL recorded 2,001 API
calls, including warm-up. These are cache-operation counters, not one count per API request.
The two runs used different application revisions and execution environments, so their numbers
are not a controlled before-and-after comparison. Repeat tests, larger real datasets, different
worker counts and a multi-client setup are needed for reliable capacity conclusions.

The isolated benchmark containers and their test-only database volume were removed after the run.

### Single catalogue-read follow-up

After removing the second catalogue read from each list request, a further run on 8 November
2026 used the same stated local PostgreSQL/Redis configuration and 500 requests per level. The
raw results are in `local-postgres-redis-single-read.json`.

| Concurrent requests | Successful / total | p95 latency | Error rate | Provenance coverage |
| --- | ---: | ---: | ---: | ---: |
| 10 | 500 / 500 | 56.13 ms | 0% | 100% |
| 50 | 500 / 500 | 754.48 ms | 0% | 100% |
| 100 | 500 / 500 | 1,975.55 ms | 0% | 100% |
| 500 | 500 / 500 | 3,502.71 ms | 0% | 100% |

Redis recorded 2,000 hits and one miss for the 2,001 calls including warm-up, confirming one
catalogue-cache lookup per call. The previous run recorded 4,001 hits and one miss. Latencies
improved at one level and worsened at others; one run of each is insufficient to infer a
performance improvement. The isolated follow-up containers and their test-only database volume
were removed after measurement.

The separate [service integration verification](service-integration-2026-11-08.md) records
functional checks against real PostgreSQL and Redis; it is not a load benchmark.

The separate [backup and recovery drill](backup-restore-2026-11-08.md) records a local
PostgreSQL dump and restore into a new database.

The [scheduler verification](scheduler-2026-11-08.md) records a Compose run using a synthetic
snapshot; it does not establish that an official file was imported.

The [local HTTPS verification](local-tls-2026-11-08.md) covers a development CA and a verified
localhost connection, not public deployment.

The [source-check verification](source-checks-2026-11-13.md) records administrator-triggered
HEAD results and their limitations.

The [scheme-search verification](search-index-2026-11-13.md) records SQLite and PostgreSQL
filter and migration checks; it is not a large-dataset benchmark.

The [historical PIN mirror import](pincode-mirror-2026-11-14.md) records a full-file integration
check, source limitations and the behavior when records already belong to another adapter.

The [local launcher verification](local-launcher-2026-11-14.md) records first-start and restart
behavior using an isolated SQLite database.

To repeat the baseline, start the server with no `DATABASE_URL` or `REDIS_URL` in one terminal:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8767
```

In another terminal:

```powershell
$env:BHARATOS_BENCHMARK_KEY = "bharatos_demo_2026"
.venv\Scripts\python.exe -m scripts.measure_performance --output tmp\performance.json --configuration "Single local worker; in-memory prototype"
```

The harness only permits localhost targets. Database-backed runs require a valid developer API
key and must report the active rate limit, cache state, worker count and dataset size. The output
does not include the API key. Do not compare the results with this baseline without recording
the configuration and client/server environment.
# Recent service verification

[15 November 2026: PostgreSQL, Redis and image checks](service-integration-2026-11-15.md).
