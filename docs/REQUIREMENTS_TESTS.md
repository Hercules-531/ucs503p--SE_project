# Functional requirement test coverage

This matrix covers the prototype report's eight requirements and the four requirement groups
in Section 3.2 of the course SRS. Their numbering differs. The names below are pytest node IDs,
relative to the application directory.

## Prototype report

| ID | Behavior | Automated evidence |
| --- | --- | --- |
| FR-01 | Search and combine scheme filters | `tests/test_data.py::test_filters_are_composable`, `tests/test_search.py::test_indexed_filters_match_python_semantics` |
| FR-02 | Display summary, potential relevance and provenance | `tests/test_routes.py::test_scheme_detail_displays_summary_relevance_and_source`, `tests/test_routes.py::test_scheme_pages_handle_unverified_source_dates` |
| FR-03 | Serve normalized scheme and PIN data through versioned APIs | `tests/test_routes.py::test_scheme_list_uses_standard_envelope_and_filters`, `tests/test_routes.py::test_pincode_api_validates_shape_and_prototype_coverage` |
| FR-04 | Reject missing or invalid keys before retrieving data | `tests/test_routes.py::test_api_requires_exact_demo_key` |
| FR-05 | Execute a real API request and inspect its JSON in the browser | `tests/test_browser_workflows.py::test_developer_registers_runs_playground_and_revokes_key` |
| FR-06 | Report source freshness, ingestion runs and API activity | `tests/test_admin.py::test_admin_overview_requires_separate_token_and_reports_real_data`, `tests/test_admin.py::test_monitoring_reports_failed_import_without_exposing_error`, `tests/test_browser_workflows.py::test_admin_shows_the_rejected_csv_line_without_source_values`, `tests/test_source_checks.py::test_admin_source_checks_require_admin_and_return_persisted_data` |
| FR-07 | Register, sign in, create, rotate and revoke developer keys | `tests/test_developer_access.py::test_developer_key_lifecycle`, `tests/test_developer_access.py::test_key_rotation_ownership_and_atomic_rollback` |
| FR-08 | Collect, validate, normalize and deduplicate source records | `tests/test_ogd_pincode.py::test_csv_groups_offices_and_preserves_attribution`, `tests/test_ingestion.py::test_invalid_batch_does_not_overwrite_existing_records` |

## Course SRS

| ID | Behavior | Automated evidence |
| --- | --- | --- |
| FR-1 | Register and sign in through the portal. Associate keys and usage with the correct account. Exercise authentication without relying on a live civic dataset. | `tests/test_browser_workflows.py::test_developer_registers_runs_playground_and_revokes_key`, `tests/test_developer_access.py::test_developer_key_lifecycle`, `tests/test_developer_access.py::test_key_rotation_ownership_and_atomic_rollback` |
| FR-2 | Protect versioned JSON endpoints, manage keys, record requests, enforce quotas and handle cache hits and misses. | `tests/test_developer_access.py::test_developer_key_lifecycle`, `tests/test_routes.py::test_api_requires_exact_demo_key`, `tests/test_routes.py::test_scheme_list_uses_standard_envelope_and_filters`, `tests/test_rate_limit.py::test_quota_is_per_key_and_rejection_has_retry_header`, `tests/test_cache.py::test_cache_hit_and_ingestion_invalidation`, `tests/test_service_integration.py::test_postgres_catalogue_is_cached_in_real_redis` |
| FR-3 | Ingest through source-specific adapters. Validate before storage, normalize and deduplicate PIN data, preserve changed field values and provenance, and serve stored records from PostgreSQL. | `tests/test_pib_schemes.py::test_pib_snapshot_ingests_and_serves_historical_source`, `tests/test_ogd_pincode.py::test_csv_groups_offices_and_preserves_attribution`, `tests/test_ogd_pincode.py::test_malformed_row_fails_atomically`, `tests/test_service_integration.py::test_postgres_serves_a_canonical_pin_through_the_protected_api` |
| FR-4 | Document available endpoints, parameters and errors through OpenAPI. Show account usage, error rate, ingestion status, and freshness problems. | `tests/test_routes.py::test_openapi_documents_distinct_security_schemes_and_errors`, `tests/test_developer_access.py::test_developer_key_lifecycle`, `tests/test_admin.py::test_admin_overview_requires_separate_token_and_reports_real_data`, `tests/test_admin.py::test_monitoring_reports_failed_import_without_exposing_error`, `tests/test_monitoring_quality.py::test_source_checks_report_missing_stale_and_invalid_times_without_claiming_outage` |

## Run the tests

The application workflow installs headless Chromium and runs the browser and PostgreSQL/Redis
tests alongside the default suite. Locally, to enable the browser test:

```powershell
uv sync --frozen
.venv\Scripts\python.exe -m playwright install --only-shell chromium
$env:RUN_BROWSER_TESTS = "1"
.venv\Scripts\python.exe -m pytest tests/test_browser_workflows.py -q
```

The official PIN CSV adapter tests use fixtures, and the PostgreSQL API test uses a seeded
canonical PIN. A verified full official directory import and the volunteer evaluation remain
separate project milestones.
