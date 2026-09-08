-- =============================================================================
-- Read-only Postgres role for the Levi's Sales Cockpit dashboard.
--
-- The cockpit reads production (prd_levis_begbal) directly because aggregating
-- 52k POS lines across six dimensions is far cheaper in SQL than through the
-- ORM. It must never be able to write, so the role gets SELECT on an explicit
-- table list -- not `ALL TABLES` -- and its sessions default to read-only.
--
-- res_users is deliberately absent: login goes through Odoo's own
-- /web/session/authenticate, so the dashboard never needs to see password
-- hashes.
--
-- Run as a superuser against the postgres database, then against the tenant:
--   psql -U odoo -d postgres          -f 001_cockpit_ro_role.sql   (role part)
--   psql -U odoo -d prd_levis_begbal  -f 001_cockpit_ro_role.sql   (grant part)
-- Both halves are idempotent.
-- =============================================================================

\set ON_ERROR_STOP on

-- --- Role (cluster-wide; runs in whichever database you connect to) ---------
-- \gexec rather than a DO block: psql does not interpolate :variables inside
-- dollar-quoted strings, so the password would arrive as the literal text
-- ":'cockpit_password'".
SELECT format('CREATE ROLE cockpit_ro LOGIN PASSWORD %L', :'cockpit_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cockpit_ro')
\gexec

ALTER ROLE cockpit_ro SET default_transaction_read_only = on;
ALTER ROLE cockpit_ro SET statement_timeout = '30s';
ALTER ROLE cockpit_ro NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;

-- --- Grants (tenant database only) ------------------------------------------
-- Guarded so the role half above can be run against `postgres` without this
-- half failing on tables that only exist in the tenant.
DO $$
DECLARE
    tbl text;
    tables text[] := ARRAY[
        'pos_order', 'pos_order_line', 'pos_session', 'pos_config',
        'pos_payment', 'pos_payment_method',
        'product_product', 'product_template', 'product_category',
        'res_partner', 'res_company', 'res_currency', 'uom_uom',
        'operating_unit',
        'account_move', 'account_move_line', 'account_account'
    ];
BEGIN
    IF current_database() <> 'prd_levis_begbal' THEN
        RAISE NOTICE 'Not the tenant database (%), skipping grants.', current_database();
        RETURN;
    END IF;

    EXECUTE 'GRANT CONNECT ON DATABASE ' || quote_ident(current_database()) || ' TO cockpit_ro';
    EXECUTE 'GRANT USAGE ON SCHEMA public TO cockpit_ro';

    FOREACH tbl IN ARRAY tables LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema = 'public' AND table_name = tbl) THEN
            EXECUTE format('GRANT SELECT ON public.%I TO cockpit_ro', tbl);
        ELSE
            RAISE WARNING 'Table % not found, skipped.', tbl;
        END IF;
    END LOOP;
END
$$;
