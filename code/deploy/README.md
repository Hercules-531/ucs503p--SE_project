# Run the web service with a restricted database login

Use this procedure on the dedicated BharatOS PostgreSQL 17 database created by the local Compose
stack. The web service will read catalogue and ingestion records while retaining the writes
required for developer accounts, keys, usage and administrator source checks. Setup, migrations
and import jobs continue to use the database owner.

After setting `POSTGRES_PASSWORD` in `.env`, start the database and apply the migrations.

```powershell
docker compose up -d --build setup
docker compose ps -a setup
```

Wait for setup to exit successfully. Create the web login once, then set its password interactively.
Use a separate random password containing URL-safe characters, such as a long alphanumeric value.

```powershell
docker compose exec db psql -X -U bharatos -d bharatos -c "CREATE ROLE bharatos_web LOGIN"
docker compose exec db psql -X -U bharatos -d bharatos
```

At the `psql` prompt, enter `\password bharatos_web` and respond to the password prompts.
Exit using `\q`. Then grant access to the migrated tables.

```powershell
Get-Content -Raw deploy/web_database_grants.sql | docker compose exec -T db psql -X -U bharatos -d bharatos
```

In the private `.env` file, set `WEB_DATABASE_URL` to
`postgresql+psycopg://bharatos_web:YOUR_WEB_PASSWORD@db:5432/${BHARATOS_DATABASE:-bharatos}`,
replacing the password. Compose expands the database name when it reads `.env`.
Recreate the web service so it reads the new connection string.

```powershell
docker compose up -d --build --force-recreate web
```

Open the configured local web port. Check `/health/ready`, browse schemes, then register a test
developer, create a key, make a request and verify that it appears in usage. The grant script
can be re-run for the same login. Review its table and sequence list after schema changes and
reapply it after a restore if the restore omitted grants.
Reapply the grant script when upgrading from a release before the dataset registry or the
revision-aware readiness check.

Readiness returns `schema_mismatch` when the database revision differs from the running
application or the revision table is absent. Migrate an older database with the owner account.
For a newer database, start the matching application release. The result `schema_unavailable` means
the connection works but a required table or column cannot be read. Check the schema and apply
the web grants again before sending traffic to the service.

On a database that grants `PUBLIC` permission to create in the `public` schema, the script stops.
Review that grant with the database owner before running it again. Use a dedicated login without
role memberships or additional object grants.

For ongoing operation, assign an owner for imports, credential rotation, restores and workload
monitoring. The local README describes the HTTPS profile and verified backup and restore procedure.
Public deployment still requires an approved host, TLS configuration, data permission review and
production security review.

The application serves the interactive API reference and its pinned Swagger UI assets on the
same origin. Its content security policy restricts portal scripts and network calls to that
origin, and its referrer policy suppresses URL details when users visit source sites. Keep those
response headers when configuring the reverse proxy. Update Swagger UI from its upstream
distribution and rerun the browser test when the bundle changes.

On 23 November 2026, the restricted login passed a Compose test on PostgreSQL 17 and Redis 7.
The test covered discovery, registration, sign-in, protected requests, usage, key rotation,
revocation, sign-out and admin overview. Source check inserts and updates succeeded.
PostgreSQL rejected catalogue and migration writes, public schema creation and request-log
deletion with insufficient-privilege errors.

## Switch to a recovered database

After restoring a trusted backup into an existing Compose PostgreSQL instance, stop the web
service and any running workers before changing the active database.

```powershell
docker compose --profile ingestion --profile monitoring stop web scheduler source-monitor
```

In `.env`, set `BHARATOS_DATABASE` to the restored database name, for example `bharatos_restore_test`.
This selects the database for migrations, the web service, the PIN scheduler and the source
monitor. If `WEB_DATABASE_URL` is set, use the interpolated name shown above or update its final
path to the same database. The web service checks the database name and Compose host at startup.

```powershell
docker compose up -d --build setup
docker compose wait setup
Get-Content -Raw deploy/web_database_grants.sql | docker compose exec -T db psql -X -U bharatos -d bharatos_restore_test
docker compose up -d --wait web
```

Use the actual restored name in the grant command if using the restricted login. Check
`/health/ready`, a scheme and an authenticated request before restarting the optional workers
you use. Start the `proxy` service with the `tls` profile if you use localhost HTTPS. Pass the
restored name to `scripts.database_backup backup --database NAME` for subsequent backups.
Preserve writes made after cutover when planning a rollback to the original database.

## Repeat the deployment check

With Docker running, use the same HTTPS deployment test as the repository workflow.

```powershell
uv sync --frozen
$env:RUN_COMPOSE_TESTS = '1'
uv run pytest -q tests/test_compose_deployment.py
```

The test creates a fresh Compose project, applies migrations and grants, and runs the developer
API flow over localhost HTTPS. It verifies the proxy certificate with the test project's CA,
checks Redis cache hits and tests the database privileges of the web login. The test rejects a
truncated backup before creating a database, restores the valid backup, reapplies the web grants,
and reconnects the web service. It checks that recovered records, active and revoked API keys,
and usage logs still work over HTTPS. It verifies that the scheduler and source monitor write
to the recovered database and that a stale web connection is rejected. The test removes its
containers, volumes and locally built images when it ends.
