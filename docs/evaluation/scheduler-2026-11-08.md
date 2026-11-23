# Local scheduler verification — 8 November 2026

An isolated Compose project ran the optional `ingestion` profile with PostgreSQL 17 and a
read-only, synthetic one-row CSV fixture. The configured checksum matched the file; the scheduler
reported a successful import, and PostgreSQL stored one PIN record with the supplied
`2026-09-01` verification date and `review_due` freshness status.

This drill verifies the Compose service, file mount, database connection and first scheduled run.
The fixture is synthetic: it is not an official PIN-directory import. Unit tests separately cover
unchanged snapshots, checksum mismatch, missing files and recovery after failure. The isolated
containers and test database volume were removed after the drill; the fixture remains in the
ignored local `tmp` directory.
