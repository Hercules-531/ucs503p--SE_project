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
`postgresql+psycopg://bharatos_web:YOUR_WEB_PASSWORD@db:5432/bharatos`, replacing the password.
Recreate the web service so it reads the new connection string.

```powershell
docker compose up -d --build --force-recreate web
```

Open the configured local web port. Check `/health/ready`, browse schemes, then register a test
developer, create a key, make a request and verify that it appears in usage. The grant script
can be re-run for the same login. Review its table and sequence list after schema changes and
reapply it after a restore if the restore omitted grants.

On a database that grants `PUBLIC` permission to create in the `public` schema, the script stops.
Review that grant with the database owner before running it again. Use a dedicated login without
role memberships or additional object grants.

For ongoing operation, assign an owner for imports, credential rotation, restores and workload
monitoring. The local README describes the HTTPS profile and verified backup and restore procedure.
Public deployment still requires an approved host, TLS configuration, data permission review and
production security review.

On 23 November 2026, the restricted login passed a Compose test on PostgreSQL 17 and Redis 7.
The test covered discovery, registration, sign-in, protected requests, usage, key rotation,
revocation, sign-out and admin overview. Source check inserts and updates succeeded.
PostgreSQL rejected catalogue and migration writes, public schema creation and request-log
deletion with insufficient-privilege errors.
