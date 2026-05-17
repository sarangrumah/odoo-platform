-- ============================================================
-- Tenant registry — master DB schema (multi-tenant orchestration)
-- ----------------------------------------------------------------
-- This schema lives in the "postgres" master DB (the one created by
-- POSTGRES_DB env). Per-tenant Odoo DBs live as siblings; this
-- registry tracks their lifecycle and configuration.
--
-- The tenant-orchestrator service is the sole writer.
-- The custom_super_admin Odoo module reads via a least-privilege
-- role to project this state into Odoo UI.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS tenant_registry;
COMMENT ON SCHEMA tenant_registry IS 'Multi-tenant lifecycle registry (orchestration metadata)';

-- ============================================================
-- ENUM: tenant lifecycle state
-- ============================================================
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tenant_state') THEN
    CREATE TYPE tenant_registry.tenant_state AS ENUM (
      'provisioning',   -- DB being created + seeded
      'active',         -- normal operation
      'suspended',      -- access revoked (read-only or 503 at proxy)
      'archived',       -- soft-deleted, DB renamed, awaiting purge
      'failed'          -- provisioning failure, manual intervention required
    );
  END IF;
END$$;

-- ============================================================
-- Tenant record
-- ============================================================
CREATE TABLE IF NOT EXISTS tenant_registry.tenants (
  id                BIGSERIAL PRIMARY KEY,
  slug              VARCHAR(63)  NOT NULL UNIQUE
                    CHECK (slug ~ '^[a-z][a-z0-9_]{1,62}$'),   -- valid PG identifier prefix
  display_name      VARCHAR(128) NOT NULL,
  db_name           VARCHAR(63)  NOT NULL UNIQUE,
  state             tenant_registry.tenant_state NOT NULL DEFAULT 'provisioning',

  -- Onboarding metadata
  plan_tier         VARCHAR(32),                    -- e.g. 'trial', 'standard', 'enterprise'
  csm_user_id       INTEGER,                        -- ops CSM who owns the relationship
  contact_email     VARCHAR(254),
  contact_phone     VARCHAR(32),

  -- Cryptographic material (envelope-encrypted; tenant-orchestrator stores wrapping key)
  fernet_key_wrapped BYTEA,                         -- per-tenant Fernet key, wrapped with master KMS key
  master_admin_pwd_hash VARCHAR(255),               -- bcrypt of initial admin pwd (rotate after first login)

  -- Backup configuration
  backup_schedule_cron VARCHAR(64) NOT NULL DEFAULT '0 2 * * *',
  backup_retention_daily  INTEGER NOT NULL DEFAULT 30,
  backup_retention_monthly INTEGER NOT NULL DEFAULT 12,
  backup_retention_yearly  INTEGER NOT NULL DEFAULT 5,
  last_backup_at    TIMESTAMPTZ,
  last_backup_size_bytes BIGINT,
  last_backup_id    VARCHAR(128),                   -- opaque S3 object key

  -- Resource caps (advisory; enforced at pgbouncer / nginx level when reloaded)
  max_db_connections INTEGER NOT NULL DEFAULT 20,
  max_req_per_minute INTEGER NOT NULL DEFAULT 600,

  -- Feature flags
  features          JSONB NOT NULL DEFAULT '{}'::jsonb,        -- {"pajakku": true, "marketplace": false}

  -- Lifecycle timestamps
  created_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  activated_at      TIMESTAMPTZ,
  suspended_at      TIMESTAMPTZ,
  archived_at       TIMESTAMPTZ,
  purge_after       TIMESTAMPTZ,                    -- archived tenants purge after this date

  last_seen_at      TIMESTAMPTZ,                    -- updated by health probe
  notes             TEXT
);

CREATE INDEX IF NOT EXISTS tenants_state_idx     ON tenant_registry.tenants(state);
CREATE INDEX IF NOT EXISTS tenants_csm_idx       ON tenant_registry.tenants(csm_user_id);
CREATE INDEX IF NOT EXISTS tenants_purge_idx     ON tenant_registry.tenants(purge_after)
  WHERE state = 'archived';

COMMENT ON TABLE tenant_registry.tenants IS 'Tenant lifecycle + config — sole writer is tenant-orchestrator';

-- ============================================================
-- Action log (lifecycle + ops actions, append-only, hash-chained)
-- Reuses the same proven append-only pattern as pdp.audit_log.
-- ============================================================
CREATE TABLE IF NOT EXISTS tenant_registry.action_log (
  id          BIGSERIAL PRIMARY KEY,
  ts          TIMESTAMPTZ  NOT NULL DEFAULT clock_timestamp(),
  tenant_id   BIGINT       REFERENCES tenant_registry.tenants(id) ON DELETE SET NULL,
  tenant_slug VARCHAR(63),
  action      VARCHAR(64)  NOT NULL,                -- provision/suspend/resume/archive/backup/restore/feature_toggle/...
  actor       VARCHAR(128) NOT NULL,                -- ops user (free-form, set by orchestrator from auth context)
  detail      JSONB,
  outcome     VARCHAR(16)  NOT NULL CHECK (outcome IN ('success','failure','partial')),
  error       TEXT,
  prev_hash   BYTEA,
  hash        BYTEA NOT NULL
);

CREATE INDEX IF NOT EXISTS action_log_ts_idx     ON tenant_registry.action_log(ts DESC);
CREATE INDEX IF NOT EXISTS action_log_tenant_idx ON tenant_registry.action_log(tenant_id);
CREATE INDEX IF NOT EXISTS action_log_action_idx ON tenant_registry.action_log(action);

-- Hash chain: sha256(prev_hash || canonical_row)
CREATE OR REPLACE FUNCTION tenant_registry._compute_action_hash(
  p_prev_hash BYTEA,
  p_ts TIMESTAMPTZ,
  p_tenant_slug TEXT,
  p_action TEXT,
  p_actor TEXT,
  p_detail JSONB,
  p_outcome TEXT,
  p_error TEXT
) RETURNS BYTEA
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  payload BYTEA;
BEGIN
  payload := COALESCE(p_prev_hash, '\x'::bytea)
          || convert_to(
              COALESCE(to_char(p_ts AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'), '')
              || '|' || COALESCE(p_tenant_slug, '')
              || '|' || COALESCE(p_action, '')
              || '|' || COALESCE(p_actor, '')
              || '|' || COALESCE(p_detail::text, '')
              || '|' || COALESCE(p_outcome, '')
              || '|' || COALESCE(p_error, ''),
            'UTF8');
  RETURN digest(payload, 'sha256');
END$$;

CREATE OR REPLACE FUNCTION tenant_registry._action_log_before_insert()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_prev BYTEA;
BEGIN
  SELECT hash INTO v_prev FROM tenant_registry.action_log ORDER BY id DESC LIMIT 1;
  NEW.prev_hash := v_prev;
  NEW.hash := tenant_registry._compute_action_hash(
    NEW.prev_hash, NEW.ts, NEW.tenant_slug, NEW.action,
    NEW.actor, NEW.detail, NEW.outcome, NEW.error
  );
  RETURN NEW;
END$$;

DROP TRIGGER IF EXISTS action_log_before_insert ON tenant_registry.action_log;
CREATE TRIGGER action_log_before_insert
  BEFORE INSERT ON tenant_registry.action_log
  FOR EACH ROW EXECUTE FUNCTION tenant_registry._action_log_before_insert();

-- Block update/delete (append-only — same pattern as pdp.audit_log)
CREATE OR REPLACE FUNCTION tenant_registry._action_log_block_modify()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'tenant_registry.action_log is append-only — % rejected', TG_OP
    USING ERRCODE = 'insufficient_privilege';
END$$;

DROP TRIGGER IF EXISTS action_log_block_update ON tenant_registry.action_log;
CREATE TRIGGER action_log_block_update BEFORE UPDATE ON tenant_registry.action_log
  FOR EACH ROW EXECUTE FUNCTION tenant_registry._action_log_block_modify();

DROP TRIGGER IF EXISTS action_log_block_delete ON tenant_registry.action_log;
CREATE TRIGGER action_log_block_delete BEFORE DELETE ON tenant_registry.action_log
  FOR EACH ROW EXECUTE FUNCTION tenant_registry._action_log_block_modify();

DROP TRIGGER IF EXISTS action_log_block_truncate ON tenant_registry.action_log;
CREATE TRIGGER action_log_block_truncate BEFORE TRUNCATE ON tenant_registry.action_log
  FOR EACH STATEMENT EXECUTE FUNCTION tenant_registry._action_log_block_modify();

-- Read-only view for Odoo consumption (hex-encoded hashes)
CREATE OR REPLACE VIEW tenant_registry.action_log_v AS
SELECT
  id, ts, tenant_id, tenant_slug, action, actor, detail, outcome, error,
  encode(prev_hash, 'hex') AS prev_hash_hex,
  encode(hash, 'hex')      AS hash_hex
FROM tenant_registry.action_log;

-- ============================================================
-- Backup ledger (1:N from tenant)
-- ============================================================
CREATE TABLE IF NOT EXISTS tenant_registry.backups (
  id            BIGSERIAL PRIMARY KEY,
  tenant_id     BIGINT NOT NULL REFERENCES tenant_registry.tenants(id) ON DELETE CASCADE,
  tenant_slug   VARCHAR(63) NOT NULL,
  kind          VARCHAR(16) NOT NULL CHECK (kind IN ('daily','monthly','yearly','manual')),
  started_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  finished_at   TIMESTAMPTZ,
  size_bytes    BIGINT,
  s3_key        VARCHAR(256),                       -- e.g. <slug>/2026-05-17/db.dump
  filestore_key VARCHAR(256),
  checksum_sha256 VARCHAR(64),
  outcome       VARCHAR(16) NOT NULL DEFAULT 'pending' CHECK (outcome IN ('pending','success','failure')),
  error         TEXT,
  expires_at    TIMESTAMPTZ                          -- garbage-collected after this date per retention policy
);

CREATE INDEX IF NOT EXISTS backups_tenant_idx ON tenant_registry.backups(tenant_id, started_at DESC);
CREATE INDEX IF NOT EXISTS backups_expire_idx ON tenant_registry.backups(expires_at)
  WHERE outcome = 'success';

-- ============================================================
-- Per-tenant Pajakku usage meter (billing input)
-- ============================================================
CREATE TABLE IF NOT EXISTS tenant_registry.coretax_usage (
  id          BIGSERIAL PRIMARY KEY,
  tenant_id   BIGINT NOT NULL REFERENCES tenant_registry.tenants(id) ON DELETE CASCADE,
  period      DATE NOT NULL,                        -- 1st of month
  api_calls   INTEGER NOT NULL DEFAULT 0,
  faktur_submits INTEGER NOT NULL DEFAULT 0,
  bupot_submits  INTEGER NOT NULL DEFAULT 0,
  errors      INTEGER NOT NULL DEFAULT 0,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE(tenant_id, period)
);

-- ============================================================
-- Roles
-- ============================================================
DO $$
BEGIN
  -- tenant-orchestrator service role (writer + DBA on Odoo tenant DBs)
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tenant_orchestrator') THEN
    CREATE ROLE tenant_orchestrator LOGIN PASSWORD 'CHANGE_ME_VIA_ALTER_ROLE';
    -- Password must be rotated post-init via ALTER ROLE in the orchestrator entrypoint.
  END IF;

  -- Read-only role for the custom_super_admin Odoo module
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tenant_registry_reader') THEN
    CREATE ROLE tenant_registry_reader NOLOGIN;
  END IF;
END$$;

GRANT USAGE ON SCHEMA tenant_registry TO tenant_orchestrator, tenant_registry_reader;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA tenant_registry TO tenant_orchestrator;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA tenant_registry TO tenant_orchestrator;
GRANT SELECT ON ALL TABLES IN SCHEMA tenant_registry TO tenant_registry_reader;
GRANT SELECT ON tenant_registry.action_log_v TO tenant_registry_reader;

-- tenant_orchestrator needs CREATEDB at cluster level (for provisioning new tenant DBs)
ALTER ROLE tenant_orchestrator CREATEDB;

-- Allow current odoo role (POSTGRES_USER) to inherit registry reader for super-admin module
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user) THEN
    EXECUTE format('GRANT tenant_registry_reader TO %I', current_user);
  END IF;
END$$;

-- ============================================================
-- Chain verification (mirrors pdp.verify_audit_chain)
-- ============================================================
CREATE OR REPLACE FUNCTION tenant_registry.verify_action_chain(p_limit INTEGER DEFAULT NULL)
RETURNS TABLE(broken_id BIGINT, expected_hash TEXT, actual_hash TEXT)
LANGUAGE plpgsql STABLE AS $$
DECLARE
  r RECORD;
  v_expected BYTEA;
  v_prev BYTEA := NULL;
BEGIN
  FOR r IN SELECT * FROM tenant_registry.action_log ORDER BY id ASC LIMIT COALESCE(p_limit, 2147483647)
  LOOP
    v_expected := tenant_registry._compute_action_hash(
      v_prev, r.ts, r.tenant_slug, r.action, r.actor, r.detail, r.outcome, r.error
    );
    IF v_expected <> r.hash THEN
      broken_id := r.id;
      expected_hash := encode(v_expected, 'hex');
      actual_hash := encode(r.hash, 'hex');
      RETURN NEXT;
    END IF;
    v_prev := r.hash;
  END LOOP;
  RETURN;
END$$;

GRANT EXECUTE ON FUNCTION tenant_registry.verify_action_chain(INTEGER) TO tenant_orchestrator, tenant_registry_reader;
