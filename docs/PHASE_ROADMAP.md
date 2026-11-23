# BharatOS phased roadmap

## Status as of 23 November 2026

This roadmap describes the full target, not a claim that every item is complete. Phase 1 is
implemented. Database models, migrations, curated snapshot imports, optional PostgreSQL/Redis,
developer access, local monitoring, one checked-file scheduler, local HTTPS and backup tooling
have been added in later phases. Structured database search indexes are in place; free-text
substring search still uses SQL `LIKE`. The full official PIN dataset has not been imported, and the PIB
scheme adapter is a dated subset rather than a live feed. Wider source coverage, an external
developer pilot, production security review and deployment remain incomplete. Local test and
measurement evidence is in [evaluation](evaluation/README.md).

Compose can use a [restricted PostgreSQL web login](../code/deploy/README.md). Schema migrations,
ingestion and database backups still run under their existing operator connections.

The current local stack was evaluated with 24 scheme records, 19,300 PIN records and both
forms of the scheme-list API. The [evaluation](evaluation/README.md#23-november-compose-evaluation)
includes measured latency, errors, dated provenance coverage and the developer key flow.

A separate July 2026 PIB transport snapshot adds one review-due PM E-DRIVE record; it does not
constitute complete transport coverage or establish current benefit availability.
An additional dated PIB environment snapshot describes the National Clean Air Programme as
city-level action; it does not imply an individual benefit or complete environment coverage.
Four further PIB releases add five health, education, employment and agriculture records
through the existing scheme schema and ingestion pipeline. The [source register](DATA_SOURCES.md)
lists the publications and dates. These additions expand sector coverage with dated snapshots.
The packaged PostgreSQL importer was run twice and retained five records across the four sources.
The full PostgreSQL and Redis test run passed 149 tests with the expanded seed.

A third-party 2024 PIN-directory mirror was later tested with 19,300 PINs in isolated databases.
Its origin and current accuracy have not been independently verified against the official file;
it does not satisfy the verified official-directory exit criterion.

## Phase 1 — Interactive prototype and software design

**Purpose:** make the system understandable, demonstrable and testable before infrastructure work begins.

Delivered in this repository:

- FastAPI/Jinja multi-page portal.
- Anonymous scheme discovery and details.
- Developer console with a working API playground.
- Read-only administrator preview.
- Three normalized prototype endpoints.
- Pydantic contracts and standardized errors.
- Use case, class, sequence, activity and component diagrams.
- Automated tests and Software Engineering Lab guide.

**Exit criterion:** a reviewer can start the project locally, complete the demonstration flow and explain how phase-one code maps to the target architecture.

## Phase 2 — Data and normalization foundation

- Introduce PostgreSQL, SQLAlchemy and Alembic migrations.
- Implement repository and service boundaries around canonical records.
- Define and implement the `DataSourceAdapter` contract.
- Ingest one permitted official scheme dataset and one location/PIN-code dataset.
- Validate, normalize, deduplicate and attach source/freshness metadata.
- Replace static API data with database-backed queries.

**Exit criterion:** a reproducible ingestion run produces validated records that the versioned API serves end to end.

## Phase 3 — Developer access and API gateway

- Add developer registration, login and secure sessions.
- Generate, hash, rotate and revoke API keys.
- Add Redis-backed response caching and per-key rate limiting.
- Persist request logs and expose real usage metrics.
- Generate an OpenAPI reference from the implemented contract.

**Exit criterion:** a new developer can register, create a key, call the API, see usage and prove that an invalid or revoked key is rejected.

## Phase 4 — Dataset expansion and discovery quality

- Add adapters for health, education, employment, agriculture, transport and environment data.
- Add scheduled ingestion, source-specific validation and search indexing.
- Introduce dataset quality scoring for freshness, completeness and consistency.
- Expand anonymous potential-fit filters without saving citizen profiles.
- Surface source outages and stale records clearly.

**Exit criterion:** multiple source adapters publish through the same canonical contract without changing consumer integrations.

## Phase 5 — Operations, testing and evaluation

- Connect the administrator dashboard to real ingestion, freshness and source-health data.
- Add monitoring, alerts, cache metrics and error analysis.
- Complete unit, integration, security and performance suites.
- Measure concurrency at 10, 50, 100 and 500 requests.
- Conduct and document a developer time-to-first-call pilot.

**Exit criterion:** the functional suite passes and p95 latency, error rate, provenance coverage and pilot results are recorded from repeatable runs.

## Phase 6 — Deployment and optional extensions

- Add Docker Compose, CI checks, environment-based secrets and deployment documentation.
- Configure TLS, backups, recovery and operational ownership.
- Review data permissions and licences before publication.
- Consider a Python SDK, GraphQL, multilingual metadata and geospatial queries only after the REST core meets its evaluation targets.

**Exit criterion:** the system can be deployed reproducibly and operated without hiding failures, stale data or source limitations.
