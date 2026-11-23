# Scheme search verification — 13 November 2026

The SQLite suite compares database-backed filtering with the original Python filtering for text,
category, state and audience combinations, case folding, and literal `%` and `_` characters. It
also checks that reimport updates the index and that upgrading an existing database backfills the
index without deleting canonical records.

An isolated Docker Compose project with PostgreSQL 17 and Redis 7 ran the full suite with live
service tests: **84 passed**. A separate new PostgreSQL database was migrated to the previous
revision, populated with one scheme fixture, and upgraded to the current revision. Searching the
backfilled index returned the expected record. The isolated test containers and database volume
were removed afterwards.

These tests establish functional behavior for the exercised records, not a performance claim for
large datasets. Category and state/audience values are indexed; free-text substring matching still
uses SQL `LIKE` and may require a dedicated full-text index as the catalogue grows.
