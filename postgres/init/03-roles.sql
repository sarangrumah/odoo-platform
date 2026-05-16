-- ============================================================
-- Least-privilege roles
-- The default Odoo connection uses the superuser POSTGRES_USER (odoo) since
-- Odoo needs CREATE on its own DBs. We add:
--  - odoo_readonly : reporting / pgAdmin select-only access
--  - odoo_pdp_writer : grant to Odoo runtime so it can INSERT into pdp.audit_log
--  - odoo_pdp_reader : SELECT on pdp.audit_log_v only
-- ============================================================

DO $$
BEGIN
  -- Read-only role for analytics tools / pgadmin browsing
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'odoo_readonly') THEN
    CREATE ROLE odoo_readonly NOLOGIN;
  END IF;

  -- Writer for audit log only
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'odoo_pdp_writer') THEN
    CREATE ROLE odoo_pdp_writer NOLOGIN;
  END IF;

  -- Reader for audit log view only
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'odoo_pdp_reader') THEN
    CREATE ROLE odoo_pdp_reader NOLOGIN;
  END IF;
END$$;

-- Default privileges on pdp schema
GRANT USAGE ON SCHEMA pdp TO odoo_pdp_writer, odoo_pdp_reader, odoo_readonly;
GRANT INSERT ON pdp.audit_log TO odoo_pdp_writer;
GRANT SELECT ON pdp.audit_log_v TO odoo_pdp_reader, odoo_readonly;
GRANT EXECUTE ON FUNCTION pdp.verify_audit_chain(INTEGER) TO odoo_pdp_reader, odoo_readonly;

-- Ensure the main odoo role inherits writer (so Odoo runtime can audit)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user) THEN
    EXECUTE format('GRANT odoo_pdp_writer TO %I', current_user);
    EXECUTE format('GRANT odoo_pdp_reader TO %I', current_user);
  END IF;
END$$;
