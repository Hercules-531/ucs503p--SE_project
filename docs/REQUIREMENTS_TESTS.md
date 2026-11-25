# Functional requirement test coverage

This matrix maps the prototype report's eight requirements and each mandatory behavior in
Section 3.2 of the course SRS to automated tests. Sub-IDs identify individual bullets within
the four SRS groups. The names below are pytest node IDs relative to the application directory.

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
| FR-1.1 | Register and sign in through the developer portal | `tests/test_browser_workflows.py::test_developer_registers_runs_playground_and_revokes_key` |
| FR-1.2 | Associate key management and usage with the correct account | `tests/test_developer_access.py::test_developer_key_lifecycle`, `tests/test_developer_access.py::test_key_rotation_ownership_and_atomic_rollback` |
| FR-1.3 | Exercise authentication with an empty civic catalogue | `tests/test_developer_access.py::test_developer_key_lifecycle` |
| FR-2.1 | Generate and revoke API keys as an authenticated developer | `tests/test_browser_workflows.py::test_developer_registers_runs_playground_and_revokes_key` |
| FR-2.2 | Validate a key before retrieving protected data | `tests/test_routes.py::test_api_requires_exact_demo_key` |
| FR-2.3 | Expose schemes and locations through versioned REST endpoints | `tests/test_routes.py::test_scheme_detail_api_handles_success_and_missing_record`, `tests/test_routes.py::test_pincode_api_validates_shape_and_prototype_coverage` |
| FR-2.4 | Return standard JSON success and error envelopes | `tests/test_routes.py::test_scheme_list_uses_standard_envelope_and_filters`, `tests/test_routes.py::test_invalid_api_request_uses_error_envelope_without_echoing_secrets` |
| FR-2.5 | Apply rate limits independently per key | `tests/test_rate_limit.py::test_quota_is_per_key_and_rejection_has_retry_header` |
| FR-2.6 | Use the cache on a hit and read the database on a miss | `tests/test_cache.py::test_cache_hit_and_ingestion_invalidation`, `tests/test_service_integration.py::test_postgres_catalogue_is_cached_in_real_redis` |
| FR-2.7 | Log API request activity for usage reporting | `tests/test_developer_access.py::test_developer_key_lifecycle` |
| FR-3.1 | Read datasets through source-specific adapters | `tests/test_pib_schemes.py::test_pib_snapshot_ingests_and_serves_historical_source`, `tests/test_ogd_pincode.py::test_csv_groups_offices_and_preserves_attribution` |
| FR-3.2 | Parse and validate records before storage | `tests/test_ogd_pincode.py::test_malformed_row_fails_atomically`, `tests/test_ingestion.py::test_invalid_batch_does_not_overwrite_existing_records` |
| FR-3.3 | Clean records and normalize them to the shared schema | `tests/test_ogd_pincode.py::test_csv_groups_offices_and_preserves_attribution` |
| FR-3.4 | Preserve source values changed by normalization | `tests/test_ogd_pincode.py::test_csv_groups_offices_and_preserves_attribution` |
| FR-3.5 | Identify and handle duplicate records | `tests/test_ogd_pincode.py::test_csv_groups_offices_and_preserves_attribution`, `tests/test_pib_schemes.py::test_pib_snapshot_and_default_catalogue_do_not_duplicate_svanidhi` |
| FR-3.6 | Associate source and freshness metadata with records | `tests/test_ingestion.py::test_snapshot_ingestion_is_repeatable_and_attributed`, `tests/test_ingestion.py::test_failed_source_marks_only_its_records_for_review_and_recovers` |
| FR-3.7 | Store processed records in PostgreSQL and retrieve them through the API | `tests/test_service_integration.py::test_postgres_serves_a_canonical_pin_through_the_protected_api` |
| FR-3.8 | Provide an initial canonical dataset for PIN lookup | `tests/test_routes.py::test_pincode_api_validates_shape_and_prototype_coverage`, `tests/test_service_integration.py::test_postgres_serves_a_canonical_pin_through_the_protected_api`, `tests/test_start_local.py::test_new_database_serves_official_archive_with_historical_provenance`, `tests/test_start_local.py::test_archive_checksum_failure_leaves_no_local_database` |
| FR-4.1 | Document endpoints, parameters, response formats and errors | `tests/test_routes.py::test_openapi_documents_distinct_security_schemes_and_errors`, `tests/test_routes.py::test_openapi_documents_developer_and_admin_responses` |
| FR-4.2 | Generate OpenAPI and make it available through Swagger UI | `tests/test_routes.py::test_openapi_documents_distinct_security_schemes_and_errors`, `tests/test_browser_workflows.py::test_reference_authorizes_and_calls_api_without_external_assets` |
| FR-4.3 | Report requests today, success rate, latency and per-endpoint traffic | `tests/test_developer_access.py::test_developer_key_lifecycle` |
| FR-4.4 | Show dataset status, API error rate and freshness to administrators | `tests/test_admin.py::test_admin_overview_requires_separate_token_and_reports_real_data`, `tests/test_admin.py::test_monitoring_reports_failed_import_without_exposing_error` |
| FR-4.5 | Identify failed requests and data-source or freshness problems | `tests/test_admin.py::test_admin_overview_requires_separate_token_and_reports_real_data`, `tests/test_monitoring_quality.py::test_source_checks_report_missing_stale_and_invalid_times_without_claiming_outage`, `tests/test_browser_workflows.py::test_admin_shows_the_rejected_csv_line_without_source_values` |

## Run the tests

The application workflow installs headless Chromium and runs the browser and PostgreSQL/Redis
tests alongside the default suite. It also runs
`tests/test_compose_deployment.py::test_compose_https_with_restricted_database_role` against the
localhost HTTPS profile. Locally, to enable the browser test:

```powershell
uv sync --frozen
.venv\Scripts\python.exe -m playwright install --only-shell chromium
$env:RUN_BROWSER_TESTS = "1"
.venv\Scripts\python.exe -m pytest tests/test_browser_workflows.py -q
```

The automated PIN CSV tests use fixtures, and the PostgreSQL API test uses a seeded canonical
PIN. The [source register](DATA_SOURCES.md#department-of-posts-may-2019-archive) records the
separate official archive verification. The current monthly directory import and volunteer
evaluation remain open.
