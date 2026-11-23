# Local backup and recovery drill — 8 November 2026

An isolated Compose project using PostgreSQL 17.11 was migrated and populated with eight curated
scheme snapshots and three sample PIN records. A custom-format `pg_dump` archive was created
using `scripts.database_backup` and restored into a newly created database.

The original and recovered databases each contained 11 normalized records and reported Alembic
revision `20261105_06`. A second restore attempt using the same target database was refused by
`createdb` before `pg_restore` ran. The original database was not modified by the restore.

The first drill exposed a buffered-input stream positioning problem. The restore command was
corrected to pass an unbuffered, rewound file descriptor to `pg_restore`, and the successful
restore above was repeated into a different new database. Automated tests cover the stream
position, invalid input, overwrite protection and the create-before-restore sequence.

The isolated Compose containers and test database volume were removed after the drill. This
confirms a local recovery exercise for sample data; it does not replace an operational backup
schedule, encrypted off-host storage or a documented production cutover and recovery-time test.
