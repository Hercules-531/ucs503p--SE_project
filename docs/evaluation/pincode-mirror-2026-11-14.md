# Historical PIN mirror import — 14 November 2026

The official OGD page's download could not be obtained in this environment. A third-party GitHub
mirror was downloaded separately; its repository claims the CSV originated from the Department of
Posts dataset. The copy has not been compared against an official file, and its current accuracy
is not established. Its repository commit date is 5 May 2024, which is not proof of the date of
the underlying postal data.

The downloaded CSV's SHA-256 is
`84af12fa29adddedfa9addcf46546000d89d2e2899b2993dc88050fafc8861e2`. A structural scan found
157,126 rows and 19,300 distinct six-digit PINs. The raw CSV and local provenance note are in the
ignored `data/raw/` folder, not in Git.

## Import checks

- A migrated, isolated SQLite database imported 19,300 PIN records. Reimporting the same file
  succeeded without increasing the record count.
- Sample PINs `147004`, `110001` and `560001` had six, 23 and ten post-office entries in this
  mirror copy. An authenticated API request for `147004` returned its offices with
  `provenance_kind: third_party_mirror`, `review_reason: unverified_mirror`,
  `last_verified: null` and `snapshot_date: 2024-05-05`.
- In a separate PostgreSQL test stack seeded with three curated PIN records, the mirror import
  applied 19,297 records and preserved the three records owned by the curated adapter. An
  authenticated API request for mirror PIN `515631` returned 15 offices and the same unverified
  provenance and null verification date.
- The full test suite subsequently passed **91 tests** with PostgreSQL and Redis services,
  including snapshot omission handling. The isolated PostgreSQL test volume was then removed.

The isolated SQLite database remains in the ignored `tmp` directory and contains only test
accounts and data. This exercise demonstrates a working historical-mirror import; it is not an
official full-directory verification or a claim that any listed PIN is currently valid.
