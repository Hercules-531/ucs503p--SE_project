# Local launcher verification — 14 November 2026

The `scripts.start_local` launcher was run with a new SQLite database in the ignored `tmp`
directory and the pinned 2024 third-party PIN mirror available in `data/raw/`. It created the
database, applied migrations and imported eight curated schemes, 14 historical PIB scheme
records, three curated PINs and 19,297 additional mirror PINs. The three existing curated PIN
records were preserved. The resulting database contained 22 schemes and 19,300 PIN records.

A test developer registered and made an authenticated request for mirror PIN `515631`. The API
returned 15 offices with `third_party_mirror` provenance, `last_verified: null` and
`review_due` freshness. The local server was stopped and restarted against the same database;
the launcher reported that it reused the database without reimporting records.

Automated tests cover initial setup without the mirror, checksum failure without publishing a
partial database, preservation of unrelated or outdated databases, and source ownership when a
mirror overlaps existing PINs. The test database remains in the ignored `tmp` directory and
contains only sample data and a test account. The historical mirror is not independently verified
against the current official directory.
