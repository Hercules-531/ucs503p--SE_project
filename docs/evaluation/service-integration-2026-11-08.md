# Local service integration verification — 8 November 2026

An isolated Docker Compose project was used to verify the current application build. It used
PostgreSQL 17.11, Redis 7.4.12, Docker Engine 29.9.2, Python 3.13.18 and pytest 8.4.2.
The PostgreSQL database contained only the eight curated scheme snapshots and three sample
PIN records. No official bulk dataset or real personal information was imported.

## Observed results

- The application image built, both service health checks passed, and Alembic upgraded an empty
  PostgreSQL database to the latest revision.
- Snapshot ingestion produced eight scheme records and three PIN-code records.
- The full pytest suite ran in a separate disposable container against the PostgreSQL and Redis
  services: **56 passed**, including the three service-integration tests.
- The web container reported both configured dependencies as ready.
- A test developer registered, signed in, created a key, retrieved the scheme list and PIN
  `147004`, exceeded an intentionally reduced two-request quota and received `429`.
- The developer usage endpoint counted three authenticated calls, including the rejected call.
  Revoking the key caused the next request to return `401`.
- The administrator endpoint reported Redis cache metrics as available, with one hit and one
  miss in this small smoke test.

These checks verify the observed local configuration only. They do not establish production
security, availability, throughput or source-data accuracy. The separate performance baseline
in `local-prototype.json` was measured in in-memory mode, not against this service stack.

After the test, the isolated test containers, network and test database volume were removed.
The pre-existing application on port 8000 was not changed.
