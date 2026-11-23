# Administrator source-check verification — 13 November 2026

An isolated SQLite database and local server were used to test the administrator-triggered
HTTP HEAD checks. The API and browser dashboard both loaded the recorded results. In one observed
run, the OGD PIN resource page and PFRDA page returned HTTP 200, myScheme returned 405 for HEAD,
and the PIB release returned 401 for HEAD. These are observations from this environment at the
recorded time, not statements about the current availability of the services.

Checks use a fixed list of official URLs, do not follow redirects or read response bodies, and
record only the result, HTTP status, check time and duration. A page returning 200 does not verify
the downloadable dataset or its contents. A rejected HEAD request does not prove that an ordinary
browser request or dataset download will fail. Automated tests use mocked responses to cover
authorization, redirects, access restrictions, network failures and persistence.

The isolated SQLite test database remains in the ignored `tmp` directory. It contains test
monitoring records only and no user credentials.

The latest migration was also applied to an isolated PostgreSQL 17 database, where four mocked
probe results were written and read successfully. The full suite ran in a disposable container
with PostgreSQL and Redis: 66 tests passed, including the service-integration tests. The isolated
container stack and its test database volume were removed after verification.
