# Local PostgreSQL and Redis verification — 15 November 2026

The current application was tested against isolated disposable containers running PostgreSQL
17.11 and Redis 7.4.12, with host ports bound to localhost. The database began empty; Alembic
upgraded it through revision `20261115_09`, and the curated seed imported eight schemes and
three PIN samples. The full host-side pytest suite ran with both service URLs configured:
**108 passed**, including five opt-in service tests. Subsequently, the transport and environment
snapshot import commands each successfully inserted one record into that PostgreSQL database.

The Docker image also built successfully. Running each of the transport and environment import
commands with `--help` inside that image confirmed that both scripts were packaged and importable.
This check does not demonstrate a populated PostgreSQL upgrade from an older revision; that
backfill path was exercised with SQLite at that point. A subsequent isolated PostgreSQL test
exercised the populated upgrade from `20261113_08`: a duplicate slug stopped the migration,
removing the duplicate allowed backfill, a conflicting insert failed against the unique index,
and downgrade removed the index column. The original fixture record remained unchanged. The test
used a uniquely named temporary schema, which it removed afterward. It also does not establish
production security or government data accuracy. The database contained test and curated sample
data only.

To repeat the populated PostgreSQL migration test, point `TEST_POSTGRES_MIGRATION_URL` at a
disposable PostgreSQL database whose user can create and drop schemas, then run
`python -m pytest tests/test_postgres_migration.py`. The test creates and deletes only its own
randomly named schema; do not point it at a production database.
