-- =============================================================================
-- Read-only Postgres role for the Levi's Finance Cockpit.
--
-- Separate from the sales dashboard's `cockpit_ro` on purpose. This role reads
-- the ledger, the bank statements and the POS clearing runs; that grant list
-- has no business hanging off a sales dashboard's credential, and splitting
-- them means revoking one never disturbs the other.
--
-- It must never be able to write, so the role gets SELECT on an explicit table
-- list -- not `ALL TABLES` -- and its sessions default to read-only at the
-- server, not in application code.
--
-- res_users is deliberately absent: login goes through Odoo's own
-- /web/session/authenticate, so the dashboard never needs to see password
-- hashes. The cost is that `create_uid` on a journal entry can only be shown as
-- a number; that is the trade we are making, on purpose.
--
-- Run as a superuser against the postgres database, then against the tenant:
--   psql -U odoo -d postgres          -v finance_password=... -f 001_finance_ro_role.sql
--   psql -U odoo -d prd_levis_begbal                          -f 001_finance_ro_role.sql
-- Both halves are idempotent.
-- =============================================================================

\set ON_ERROR_STOP on

-- --- Role (cluster-wide; runs in whichever database you connect to) ---------
-- \gexec rather than a DO block: psql does not interpolate :variables inside
-- dollar-quoted strings, so the password would arrive as the literal text
-- ":'finance_password'".
SELECT format('CREATE ROLE finance_ro LOGIN PASSWORD %L', :'finance_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finance_ro')
\gexec

ALTER ROLE finance_ro SET default_transaction_read_only = on;
-- Netting fetches an account at a time, and the largest (GR/IR textile, 58.840
-- open lines) comes back in about a second. 30s leaves room for a cold cache
-- without letting a runaway query hold a connection all day.
ALTER ROLE finance_ro SET statement_timeout = '30s';
ALTER ROLE finance_ro NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;

-- --- Grants (tenant database only) ------------------------------------------
-- Guarded so the role half above can be run against `postgres` without this
-- half failing on tables that only exist in the tenant.
DO $$
DECLARE
    tbl text;
    tables text[] := ARRAY[
        -- Ledger core
        'account_move', 'account_move_line', 'account_account', 'account_journal',
        'account_partial_reconcile', 'account_full_reconcile',
        'account_tax', 'account_move_line_account_tax_rel',
        'account_payment', 'account_payment_method', 'account_payment_method_line',
        'account_lock_exception',
        'account_analytic_account', 'account_analytic_plan',
        -- Master data
        'res_company', 'res_partner', 'res_currency', 'res_currency_rate',
        -- Bank and POS clearing
        'account_bank_statement', 'account_bank_statement_line',
        'levis_pos_clearing', 'levis_pos_clearing_line', 'levis_pos_clearing_alloc',
        'levis_pos_clearing_leg', 'levis_pos_clearing_receipt', 'levis_pos_clearing_diag',
        'levis_clearing_config',
        'levis_clearing_config_bank_journal_rel', 'levis_clearing_config_posrec_rel',
        'levis_bank_mid_map', 'levis_mdr_bin', 'levis_purchase_account_map',
        -- Views the accounting modules already maintain
        'custom_reconcile_account', 'custom_followup_stat_by_partner',
        'custom_report_journal_item_analysis'
    ];
BEGIN
    IF current_database() <> 'prd_levis_begbal' THEN
        RAISE NOTICE 'Not the tenant database (%), skipping grants.', current_database();
        RETURN;
    END IF;

    EXECUTE 'GRANT CONNECT ON DATABASE ' || quote_ident(current_database()) || ' TO finance_ro';
    EXECUTE 'GRANT USAGE ON SCHEMA public TO finance_ro';

    FOREACH tbl IN ARRAY tables LOOP
        -- information_schema.tables covers views as well as base tables, which
        -- is what we want: three of the entries above are views owned by odoo,
        -- and a grant on the view is enough because Postgres runs it with the
        -- owner's rights.
        IF EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema = 'public' AND table_name = tbl) THEN
            EXECUTE format('GRANT SELECT ON public.%I TO finance_ro', tbl);
        ELSE
            RAISE WARNING 'Table % not found, skipped.', tbl;
        END IF;
    END LOOP;
END
$$;
