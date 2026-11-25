-- Run as the migration owner after applying migrations in a dedicated BharatOS database.
-- Create the login and set its password separately.
\set ON_ERROR_STOP on
BEGIN;

DO $check$
DECLARE
    web_oid oid;
    protected_table text;
BEGIN
    SELECT oid INTO web_oid
    FROM pg_roles
    WHERE rolname = 'bharatos_web'
      AND rolcanlogin
      AND NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);

    IF web_oid IS NULL THEN
        RAISE EXCEPTION 'Provision a non-privileged bharatos_web login first';
    END IF;

    IF EXISTS (SELECT FROM pg_auth_members WHERE member = web_oid)
        OR has_database_privilege(web_oid, current_database(), 'CREATE')
        OR has_schema_privilege(web_oid, 'public', 'CREATE')
        OR EXISTS (
            SELECT FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relowner = web_oid
        )
    THEN
        RAISE EXCEPTION 'bharatos_web already has elevated access in this database';
    END IF;

    FOREACH protected_table IN ARRAY ARRAY[
        'public.alembic_version', 'public.normalized_records', 'public.datasets',
        'public.dataset_revisions',
        'public.scheme_search_index', 'public.scheme_search_values', 'public.ingestion_runs',
        'public.import_checkpoints'
    ] LOOP
        IF has_any_column_privilege(web_oid, protected_table, 'INSERT, UPDATE')
            OR has_table_privilege(web_oid, protected_table, 'DELETE, TRUNCATE, TRIGGER')
        THEN
            RAISE EXCEPTION 'bharatos_web already has write access to %', protected_table;
        END IF;
    END LOOP;
END
$check$;

GRANT USAGE ON SCHEMA public TO bharatos_web;
GRANT SELECT ON public.alembic_version, public.normalized_records, public.datasets,
    public.dataset_revisions,
    public.scheme_search_index,
    public.scheme_search_values, public.ingestion_runs TO bharatos_web;

-- Registration, session creation/logout, key creation/rotation and usage recording.
GRANT SELECT, INSERT ON public.developer_accounts, public.api_keys,
    public.api_request_logs TO bharatos_web;
GRANT SELECT, INSERT, DELETE ON public.developer_sessions TO bharatos_web;
GRANT UPDATE (revoked_at) ON public.api_keys TO bharatos_web;
GRANT USAGE ON SEQUENCE public.developer_accounts_id_seq,
    public.api_request_logs_id_seq TO bharatos_web;

-- Administrators may trigger a fixed set of source checks from the web interface.
GRANT SELECT, INSERT ON public.source_probes TO bharatos_web;
GRANT UPDATE (checked_at, status, http_status, duration_ms)
    ON public.source_probes TO bharatos_web;

COMMIT;
