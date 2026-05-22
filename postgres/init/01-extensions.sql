-- ============================================================
-- Postgres extensions for Odoo 19 Platform
-- Runs on first init only (Postgres image runs /docker-entrypoint-initdb.d/*)
-- ============================================================

-- Required by Odoo
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Crypto for sertel encryption + audit log hashing
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- GIN on btree types (faster jsonb + composite search)
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- Vector embeddings (used by ai-gateway /v1/embed)
-- pgvector is bundled in postgres:16-alpine via separate install on most setups;
-- if missing, the CREATE will raise NOTICE and we fall back to bytea storage.
-- Catch-all WHEN OTHERS: Postgres reports missing control file as
-- feature_not_supported (0A000) on some builds, undefined_file (58P01) on
-- others — either way we want the init script to continue.
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'pgvector not available (%): embedding features will use bytea fallback', SQLERRM;
END$$;
