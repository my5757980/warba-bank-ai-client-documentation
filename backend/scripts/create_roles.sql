-- Warba Bank — AI-Powered Client Documentation
-- Database roles and the audit immutability grant.
--
-- Constitution Principle VIII / FR-032: no application user may edit or delete an
-- audit record. Enforcing that only in application code means one missing guard, one
-- ORM misuse, or one admin console defeats it. A privilege that was never granted
-- cannot be forgotten.
--
-- Two roles:
--   warba_migrate  — owns the schema, runs Alembic. Not used by the application.
--   warba_app      — the API runs as this. INSERT+SELECT on audit_event, nothing more.
--
-- Run against the target database BEFORE `alembic upgrade head`.

-- ---------------------------------------------------------------------------
-- Roles
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'warba_migrate') THEN
        CREATE ROLE warba_migrate LOGIN PASSWORD 'migrate_local_only';
    END IF;

    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'warba_app') THEN
        CREATE ROLE warba_app LOGIN PASSWORD 'app_local_only';
    END IF;
END
$$;

-- NOTE: the passwords above are local development values and are referenced in
-- .env.example as placeholders. Any real deployment supplies them from a secret
-- manager (Constitution Principle I).

-- Dynamic, because the database is not always called warba_docs. Locally it is; on a
-- managed host the name is whatever the provider chose (Railway uses `railway`), and a
-- hardcoded name fails the whole script there — taking the audit grant with it.
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO warba_app', current_database());
END
$$;

GRANT USAGE ON SCHEMA public TO warba_app;
ALTER SCHEMA public OWNER TO warba_migrate;

-- ---------------------------------------------------------------------------
-- Default grants: full DML on ordinary tables for the application role
-- ---------------------------------------------------------------------------

ALTER DEFAULT PRIVILEGES FOR ROLE warba_migrate IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO warba_app;

ALTER DEFAULT PRIVILEGES FOR ROLE warba_migrate IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO warba_app;

-- ---------------------------------------------------------------------------
-- The audit exception — apply AFTER `alembic upgrade head`
-- ---------------------------------------------------------------------------
-- Wrapped so this file is safe to run before the table exists (e.g. as a Docker
-- init script). Re-run `apply_audit_grants()` after migrations to be certain.

CREATE OR REPLACE FUNCTION apply_audit_grants() RETURNS void AS $$
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'audit_event') THEN
        -- Revoke everything first so re-running cannot silently widen access.
        REVOKE ALL ON TABLE audit_event FROM warba_app;

        -- The application may append and read. It may never rewrite history.
        GRANT INSERT, SELECT ON TABLE audit_event TO warba_app;

        -- Explicit and redundant after the REVOKE above, but stated so the intent
        -- survives future edits to this file.
        REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_event FROM warba_app;

        RAISE NOTICE 'audit_event: granted INSERT, SELECT to warba_app; UPDATE/DELETE withheld';
    ELSE
        RAISE NOTICE 'audit_event does not exist yet — run alembic upgrade head, then: SELECT apply_audit_grants();';
    END IF;
END
$$ LANGUAGE plpgsql;

SELECT apply_audit_grants();

-- Verification (expected to FAIL as warba_app — that failure is the guarantee):
--   psql -U warba_app warba_docs -c "DELETE FROM audit_event WHERE true;"
--   ERROR:  permission denied for table audit_event
