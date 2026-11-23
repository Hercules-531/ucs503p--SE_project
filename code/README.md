# BharatOS

BharatOS is a Software Engineering Lab project that explores a unified interface for Indian public schemes and civic-data APIs. It is a Python-first localhost application: citizens can discover potentially relevant schemes, developers can call a normalized API, and administrators can review recorded operational information.

> **Academic prototype:** BharatOS is not an official Government of India service. Scheme matching is indicative and every result must be verified on its linked official source.

## Current capabilities

- Search and filter eight default source-linked scheme snapshots; database mode supports additional imports.
- Browse scheme results in pages while keeping search filters.
- View scheme detail, potential-fit guidance, provenance and freshness.
- Search loaded PIN-code records anonymously at `/locations`, including their provenance and offices.
- Exercise three versioned data endpoints with a prototype key or a personal key in database mode.
- View recorded developer usage and token-protected administrator monitoring in database mode.
- Review five editable and rendered UML diagrams.
- Use the lab guide for explanation, demonstration and viva preparation.

## Run locally

Requirements: Python 3.12 or newer and `uv`. Install dependencies once, then start the local
database-backed application:

```powershell
uv sync
.venv\Scripts\python.exe -m scripts.start_local
```

Open the URL printed by the launcher. It uses port 8000 if available, otherwise it selects the
first free localhost port through 8100. On first run, it creates `data/bharatos-local.db`, applies
migrations and imports the curated scheme and PIN snapshots plus the dated PIB releases.
If
`data/raw/pincode-github-2024.csv` exists, it also imports that checksum-pinned historical mirror;
those records remain marked for review. Add `--skip-mirror` to omit it on first initialization.
The database is initialized in a temporary file and published only after successful setup. An
existing database is not re-seeded or automatically migrated. The local launcher uses SQLite and
does not enable Redis; use Compose to test the Redis-backed stack. It requires a filesystem that
supports creating hard links in the target directory.

To upgrade an older local SQLite database without replacing it, stop the application and create a
new migrated copy (choose a destination that does not exist):

```powershell
.venv\Scripts\python.exe -m scripts.upgrade_local_copy data\bharatos-local.db data\bharatos-upgraded.db
.venv\Scripts\python.exe -m scripts.start_local --db data\bharatos-upgraded.db
```

The SQLite backup includes committed data and the original file is retained. The new copy is
published only after migration and an integrity check succeed; it is not re-seeded. The destination
directory must exist and support hard links. Keep the original as a backup and check the copy before
using it. Stop writers first so later changes to the old database are not missed in the copy.

The earlier in-memory demonstration can still be started with
`.venv\Scripts\python.exe -m uvicorn app.main:app --reload`. Use `--db PATH` or `--port PORT` with
`scripts.start_local` to select a different local database or port. An explicitly chosen port must
be free. The automatic port check happens before the server binds, so another application could
occupy that port in the meantime; restart the launcher if that happens.

### Run the local service stack with Docker Compose

1. Copy `.env.example` to `.env` and replace the example password with a long random
   alphanumeric value. Keep this file private.
2. Run `docker compose up --build -d`. This starts PostgreSQL, Redis and the web service;
   the setup container applies migrations before the web service starts.
3. On a new installation, seed the existing curated snapshots once with
   `docker compose run --rm setup python -m scripts.ingest_snapshots`.
4. Open <http://127.0.0.1:8000>. Health checks are available at `/health/live` and
   `/health/ready`.

The database is kept in the `postgres_data` Docker volume. `docker compose down` stops the
stack without deleting that volume. Do not use `docker compose down -v` unless you intend to
delete its data. The stack binds only to localhost and is not configured for public deployment;
TLS, an operational backup policy, access controls and security review remain required.

To run the web service with its own PostgreSQL login and restricted grants, follow the
[database access setup](deploy/README.md). Compose uses that login when `WEB_DATABASE_URL`
is set.

### Optional local HTTPS

After setting up `.env`, run `docker compose --profile tls up -d --build proxy` and open
`https://localhost:8443`. The optional proxy creates a local development certificate and binds
only to localhost. The HTTP listener remains available on localhost; set `WEB_HTTP_PORT` or
`TLS_PORT` in `.env` if either default port is occupied.

The certificate is signed by the proxy's private local CA, which browsers do not automatically
trust outside the container. You can inspect or export its public root certificate with
`docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt PATH_TO_NEW_FILE`. To test
without changing the trust store, substitute that path in the following PowerShell command:

```powershell
.venv\Scripts\python.exe -c "import ssl,urllib.request; c=ssl.create_default_context(cafile=r'PATH_TO_NEW_FILE'); print(urllib.request.urlopen('https://localhost:8443/health/ready',context=c).read().decode())"
```

Windows curl using Schannel may reject a local CA because its revocation status is unknown.
Importing a root CA into a system or browser trust store is a separate user decision. Keep the
`caddy_data` volume private: it contains the CA's private key. This localhost configuration is
not a public deployment; a public service requires a domain, publicly trusted certificates,
appropriate network controls and a security review.

### Database backup and recovery

With the Compose database running and the same `.env` configuration available, create a
PostgreSQL custom-format backup at a new path:

```powershell
.venv\Scripts\python.exe -m scripts.database_backup backup C:\Backups\bharatos-2026-11-08.dump
```

The destination directory must already exist; the command refuses to overwrite a file. Backups
contain developer account information and password/key hashes, so protect and store them securely.
Test recovery into a **new** database with a name beginning `bharatos_restore_`:

```powershell
.venv\Scripts\python.exe -m scripts.database_backup restore C:\Backups\bharatos-2026-11-08.dump --target bharatos_restore_test
```

The command refuses an existing target and never drops a database. If recovery fails after the
new database was created, it may leave an incomplete database for an operator to inspect. A
successful restore does not switch the running application to the recovered database; verify the
data and arrange a separate cutover. Both commands accept `--project NAME` before the action for
a non-default Compose project. Back up on a defined schedule and perform periodic restore drills.

To enable the read-only `/admin` monitoring page, set a separate random `ADMIN_TOKEN` of at
least 32 characters in `.env` (or in the server environment) and restart. The page shows stored
record counts, source verification freshness, authenticated API request/error counts and the ten
most recent ingestion runs. Import status records the last attempt; it is not a live source check.
The token is sent in the `X-Admin-Token` header and is not stored in browser storage. Monitoring
excludes request parameters, credentials and ingestion error details. The dashboard shows cache
hits, misses, recorded errors and hit ratio for the current Redis instance. Counters reset with
Redis and cannot reliably record errors while Redis is unreachable. Administrators can explicitly
check a fixed set of official pages using HTTP HEAD; results and check times are stored. Redirects
are not followed, response bodies are not fetched, and a successful page check does not establish
that a dataset download or government service is current. HEAD may be rejected even when a page
loads in a browser. The dashboard computes alerts for failed imports, records needing review,
unknown freshness, unavailable cache metrics and failed last source checks when requested; it
does not send notifications or retain alert history.
The dashboard also warns when a source-page check is missing, more than 24 hours old, or has an
invalid future timestamp. A check is a point-in-time observation, not continuous monitoring.

The dataset registry records the adapter's canonical record type and snapshot policy, including
first runs that fail before publishing records. Migration backfills identities from records and
run history. Policies for older entries become known after another import attempt. Apply the new
migration before running updated imports, and reapply the grants if using the restricted web login.

Scheme and PIN detail pages display a saved check when their exact source URL is in the fixed
check list. They show the check time and result without running a new network request. A check of
a home page does not stand in for checks of individual scheme pages; a denied HEAD request is not
proof that a browser cannot open the page. Unmonitored URLs have no source-check indicator.

The per-adapter quality percentages are internal indicators: freshness is the share of records
with current verification status; completeness is the share with all required canonical and
provenance fields populated; consistency is the share passing the canonical schema with an ID
matching the stored key. Empty values and unsupported record types do not count as complete.
These checks do not verify factual accuracy, eligibility or live source availability.

### Configure a database manually

The local launcher initializes its own SQLite database. To migrate and seed a different database
manually, set `DATABASE_URL` and run the migration and import commands:

```powershell
$env:DATABASE_URL = "sqlite:///bharatos.db"
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m scripts.ingest_snapshots
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

For PostgreSQL, set `DATABASE_URL` to a `postgresql+psycopg://` connection URL before running
the import and server. The import is repeatable, validates the complete batch before committing,
uses bounded database lookup batches, and records successful and failed runs. These are curated
snapshots, not a live government feed; the stored verification date remains the original date.
Alembic migrations and initial source adapters are implemented; full official dataset ingestion
and broader source coverage remain under development.

Before importing into a new database, run `.venv\Scripts\python.exe -m alembic upgrade head`.
If you created a database with the earlier `create_all` version, back it up, verify that its
tables match the initial migration, then run `alembic stamp 20261105_01` once before upgrading.
Do not stamp a database with a different schema.

### Developer access in database mode

After migrating and importing records, register and sign in through the JSON endpoints
`POST /api/v1/developers/register` and `POST /api/v1/developers/login`, with `email` and
`password` (at least 12 characters). Pass the returned session token as
`Authorization: Bearer <session_token>` to `POST /api/v1/developers/keys`. The key is shown
only once; send it as `X-API-Key` on protected data requests. Use `GET /api/v1/developers/keys`
to list key prefixes, `DELETE /api/v1/developers/keys/{id}` to revoke one, and
`POST /api/v1/developers/logout` to end the session. Sessions expire after eight hours.
Use `POST /api/v1/developers/keys/{id}/rotate` to atomically revoke an active key and create
a replacement. The old key stops working immediately. Save the new key from the response;
if the response is lost, create another key from your authenticated session.
The fixed demonstration key only works without `DATABASE_URL`.
`GET /api/v1/developers/usage` reports request totals, average request duration and counts per
route for the signed-in developer. Logs omit request bodies, query parameters and raw credentials.

The `/developers` page also supports registration, sign-in, key creation and revocation in
database mode. A newly created key is inserted into the playground; copy it before leaving the
page. The session token is held only in page memory, so refreshing requires signing in again.
After signing in, the page shows recorded request counts by route and average duration. The local
readiness indicator checks configured application dependencies, not government source availability.

### Import a PIN directory CSV

Download the PIN directory CSV from its [official OGD resource page](https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month),
verify its origin and licence, and import it into a migrated database:

```powershell
.venv\Scripts\python.exe -m scripts.ingest_ogd_pincode path\to\pincodes.csv --verified-on YYYY-MM-DD
```

Use `--sha256` with the lowercase SHA-256 recorded when you reviewed the file to make the
import fail if the bytes changed. New official and mirror imports include
`data.source.snapshot_sha256` in PIN responses. The checksum identifies the imported bytes.
Keep the publisher link and your verification date with the reviewed file.

An optional downloader can request paginated JSON from the official `api.data.gov.in` host when
the platform provides a resource UUID and a working API key. Obtain both from the official API
page; do not paste the key into chat or put it in source control. In a private PowerShell session:

```powershell
$env:OGD_API_KEY = "YOUR_PRIVATE_OGD_KEY"
.venv\Scripts\python.exe -m scripts.fetch_ogd_pincode RESOURCE_UUID data\raw\ogd-review.csv
Remove-Item Env:OGD_API_KEY
```

The destination directory must exist and the CSV must be new. The downloader is tested against
simulated API responses; it has not been verified with the live PIN API or a real key. It checks
page counts but offset pagination cannot guarantee a consistent snapshot if the source changes
during download. Independently verify that the UUID identifies the official PIN directory, review
completeness, update date and licence, and only then use the CSV importer and an honest verification
date. The tool does not import data or independently verify its provenance. API keys appear in
OGD request query parameters, so avoid logging or recording network requests.

The CSV must include `officename`, `pincode`, `district` and `statename` headers. The date is
the date you verified the supplied snapshot, not an automatic freshness check. Multiple offices
are grouped in the `offices` array. Imports add or update PINs. Records previously imported by
this adapter that are absent from a later snapshot are retained but marked `review_due` with an
`absent_from_snapshot` reason; this does not prove an office or PIN has been discontinued. Use
complete snapshots, because a partial file will also cause omitted records to be marked for review.
The importer rejects duplicate normalized headers, extra row fields and malformed CSV quoting;
additional uniquely named columns are allowed.

For the separately downloaded 2024 GitHub mirror, use the dedicated adapter instead:

```powershell
.venv\Scripts\python.exe -m scripts.ingest_pincode_mirror data\raw\pincode-github-2024.csv
```

It checks the pinned SHA-256 and retains the mirror URL, claimed government origin and repository
licence. The mirror commit date is stored as `snapshot_date`; `last_verified` is `null` because
the data has not been independently verified against the official file. Records remain `review_due` and must not be represented as
current or independently verified official data. Import into an isolated database first. Existing
PIN records owned by another adapter (or without recorded ownership) are preserved; the import's
accepted count excludes those skipped records.

To compare a separately obtained candidate CSV with the pinned mirror without importing either:

```powershell
.venv\Scripts\python.exe -m scripts.compare_pincode_snapshots path\to\candidate.csv data\raw\pincode-github-2024.csv
```

The aggregate comparison uses exact office name, district and state sets for each PIN and reports
file checksums. Formatting differences may count as changes. Matching records do not prove the
candidate's origin, licence or freshness, and other fields such as delivery status are not compared.

### Import the PIB scheme snapshot

After running migrations, `.venv\Scripts\python.exe -m scripts.ingest_pib_schemes` imports 14
scheme names and ministries from a March 2026 PIB release. PM SVANidhi is omitted from this
snapshot because it is already in the default catalogue. These records are labelled for review:
the historical table does not establish current eligibility, benefits or coverage. See the
[source register](../docs/DATA_SOURCES.md) for attribution and reuse conditions.

The separately curated PM E-DRIVE transport record can be imported into an existing local
launcher database with:

```powershell
.venv\Scripts\python.exe -m scripts.ingest_pib_transport --database-url sqlite:///data/bharatos-local.db
```

For another migrated database, supply its URL with `--database-url` or set `DATABASE_URL`.
The record describes a July 2026 PIB release, not a live feed; vehicle segments have different
end dates and it is marked for review. Existing local databases are not re-seeded automatically.

The dated National Clean Air Programme record can be added to an existing local launcher database
with `.venv\Scripts\python.exe -m scripts.ingest_pib_environment --database-url sqlite:///data/bharatos-local.db`.
It describes city-level action, not a personal payment or individual eligibility process.

The health, education, employment and agriculture releases add five programme summaries. Fresh
launcher databases include them. To add them to an existing migrated local database, run:

```powershell
.venv\Scripts\python.exe -m scripts.ingest_pib_programmes --database-url sqlite:///data/bharatos-local.db
```

In Compose, run `docker compose run --rm setup python -m scripts.ingest_pib_programmes` after
applying migrations. Each release has its own ingestion run, and re-importing updates the same
record IDs. Source dates appear on scheme details. See the [source register](../docs/DATA_SOURCES.md).

For repeated checks of a previously verified local file, run the optional scheduler after applying
migrations. Supply the verification date and SHA-256 digest obtained when you checked the file:

```powershell
$digest = (Get-FileHash -Algorithm SHA256 path\to\pincodes.csv).Hash.ToLower()
.venv\Scripts\python.exe -m scripts.schedule_pincode path\to\pincodes.csv --verified-on YYYY-MM-DD --sha256 $digest --interval-seconds 3600
```

Add `--once` for a single check. The scheduler verifies the digest before parsing the same bytes,
skips an unchanged successful snapshot, and records a failed run if the file is missing or altered.
An old verification date stays old; this does not download or independently verify source data.
Run only one scheduler for this adapter at a time. For a new snapshot, verify its origin and terms,
then restart the scheduler with its new digest and verification date. A crash between the import
and checkpoint may cause a safe repeat import on restart.

For the optional Compose scheduler, set `PIN_SNAPSHOT_PATH`, `PIN_VERIFIED_ON` and
`PIN_SNAPSHOT_SHA256` in `.env`; the file must already exist and be readable by the container.
Set `PIN_IMPORT_INTERVAL_SECONDS` if needed (minimum 60), then run
`docker compose --profile ingestion up -d scheduler`. The file is mounted read-only. To approve
a replacement file, update its date and checksum and recreate the scheduler with
`docker compose --profile ingestion up -d --force-recreate scheduler`; a file bind mount may not
follow a host-side atomic replacement. Stop it with `docker compose stop scheduler`. Run only one
scheduler per adapter, and do not configure a schedule until the source and licence are verified.

For periodic checks of the fixed official source-page list, start the optional monitoring profile:

```powershell
docker compose --profile monitoring up -d --build source-monitor
```

It records the same HEAD checks used by the administrator dashboard, every hour by default;
`SOURCE_CHECK_INTERVAL_SECONDS` may be set in `.env` to at least 300 seconds. Stop it with
`docker compose stop source-monitor`. Run only one source monitor per database to avoid unnecessary
requests. Overlapping manual checks retain the latest timestamped result for each source. The monitor
follows no redirects and stores only the latest check per source.
Page availability does not verify dataset downloads, current data or eligibility. A 403, redirect
or rejected HEAD request does not necessarily mean the page is unavailable in a browser. This
optional process does not send alerts or collect historical checks.

This access flow is a development implementation. Deployments still need HTTPS, account recovery
and security review before public exposure.

### API rate limiting

Set `REDIS_URL` (for example, `redis://localhost:6379/0`) alongside `DATABASE_URL` to enable
per-key fixed-window limits for the protected data endpoints. `API_RATE_LIMIT` defaults to 60
requests and `API_RATE_WINDOW_SECONDS` defaults to 60 seconds. Exceeding the quota returns a
standard `429` error with a `Retry-After` header. If configured Redis is unavailable, protected
calls return `503` rather than silently bypassing the limiter. Without `REDIS_URL`, rate limiting
is disabled; this mode is for local development, not public deployment. With Redis configured,
login and registration have separate per-client address limits, defaulting to 10 and 5 attempts
per 60 seconds respectively; `LOGIN_RATE_LIMIT`, `REGISTRATION_RATE_LIMIT` and
`AUTH_RATE_WINDOW_SECONDS` configure these limits. Redis holds a hashed client address in a
short-lived counter, not the email or password. The Compose server does not trust proxy headers;
if deployed behind a proxy, configure trusted proxy addresses carefully or all users may share
the same limit. Per-address limits alone do not prevent distributed attacks.

When Redis is configured, the service also caches the database-backed scheme catalogue for up to
120 seconds. PIN lookups use an indexed database query and are not cached. No search terms,
PINs or credentials are included in cache keys.
Successful ingestion increments a database revision in the same transaction as record updates,
so subsequent reads use a new cache entry. Records written outside the ingestion service must
also increment the relevant `dataset_revisions` row, or cached data may remain until expiry.
Cache errors fall back to the database. Apply migrations and re-run ingestion to enable caching
for databases populated before the revision table was introduced.

Database-backed scheme filters use a search metadata index maintained in the same transaction
as ingestion. The migration backfills existing scheme records. Category and structured
state/audience values are indexed; free-text substring matching currently uses SQL `LIKE` and is
not a full-text index. Only source metadata is stored in the index, never user searches. Direct
database writes outside the ingestion service must also maintain the search index and cache
revision; use the ingestion service for normal updates.
Individual database-backed scheme lookups query the primary-key and slug indexes instead of
loading the entire catalogue. List requests and filter controls can still load larger result sets.

Scheme imports reject duplicate URL slugs across the resulting catalogue, including older records
retained for review. A unique index also rejects conflicts between concurrent indexed writes; it
does not make simultaneous imports or external database edits generally safe. Continue running
only one scheduler per adapter. In the API, an exact scheme ID takes precedence over a matching
slug; website detail routes use slugs. Existing databases require an explicit migration after a
backup. The slug migration stops if existing slugs conflict or search indexes are inconsistent;
repair the records and index before retrying.

Scheme-list responses report `meta.uncertain_excluded_count`: records that could match the search
but lack selected state or audience metadata. This count is independent of pagination and is not
an eligibility decision. Set `include_unknown=true` to include such records and report their total
in `meta.uncertain_included_count` instead; inspect each record's fields and source for details.

If an ingestion run fails, records last imported by that adapter are retained and marked
`review_due`; a later successful import can restore their status. Records created before the
source-adapter migration have no adapter association until they are reimported, so failure
marking cannot identify them until then.

If Windows Application Control prevents `uv run` from starting a console wrapper, run tools through `.venv\Scripts\python.exe -m ...` as shown above. The environment is still created and locked by `uv`.

## Test and check

Uvicorn access logs redact client addresses, query strings and dynamic path values. Protected API
usage logs store route patterns rather than parameters. Search filters are still present in the
browser URL, and reverse proxies or external logging systems must be configured separately to
avoid recording request details.

If a database operation cannot connect or the connection pool times out, the API returns a
standard `503 DATABASE_UNAVAILABLE` error and portal pages show a temporary-unavailability message.
The response does not include database error details. This does not cover every possible failure
or replace health checks and operator monitoring.

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe scripts\render_diagrams.py
```

The GitHub Actions checks also provision disposable PostgreSQL and Redis services, run the
populated PostgreSQL migration test, and build the Docker image with both PIB import commands.
The workflow runs when pushed to GitHub; local test results do not prove a remote run has passed.

## Make your first API call

Open `/developers` at the address printed by the local launcher. Register and sign in with a lab
account, create a personal key, and select **Run request** in the playground. A successful call
shows HTTP 200 and a JSON response with `data` and `meta`. For the original in-memory mode, use
the public key `bharatos_demo_2026` displayed on the developer page.

Available endpoints:

```text
GET /api/v1/schemes
GET /api/v1/schemes/{scheme_id}
GET /api/v1/locations/pincode/{pincode}
```

The scheme list optionally accepts `limit` (1–100) and `offset` (0 or greater, requiring a
limit). Pages are ordered by scheme ID; `meta.result_count` is the returned page size and
`meta.total_count` is the number of matches before paging. The legacy unpaged response remains
available when `limit` is omitted. As records change between calls, offset-based pages can shift.

The generated OpenAPI JSON is at `/openapi.json`; the interactive reference is at `/reference`
(its browser assets are loaded from a CDN). The project-specific documentation remains at `/docs`.

For a PowerShell 7.2+ request, use the address printed by the launcher and the key from the developer
console. `Read-Host` keeps the key value out of the entered command.

```powershell
$bharatosUrl = (Read-Host 'BharatOS base URL').TrimEnd('/')
$bharatosKey = Read-Host 'BharatOS API key' -MaskInput
Invoke-RestMethod -Uri "$bharatosUrl/api/v1/schemes?q=health" -Headers @{ 'X-API-Key' = $bharatosKey }
Remove-Variable bharatosKey
```

## Documentation

- [Software Engineering Lab guide](../docs/LAB_GUIDE.md)
- [Phased roadmap](../docs/PHASE_ROADMAP.md)
- [Data-source register](../docs/DATA_SOURCES.md)
- [UML sources and render notes](../docs/diagrams/README.md)
- [Course report folders](../project-report-prototype-stage)

## Phase boundary

The original Phase 1 used in-process snapshots and a public demonstration key. Database-backed
accounts, imports, PostgreSQL support, optional Redis limits and monitoring have since been added.
The application remains an academic prototype: an official full PIN-directory import, broader
datasets, an external developer pilot and production security/deployment are not complete. See
the [roadmap](../docs/PHASE_ROADMAP.md) for the remaining work.
