"""Tenant orchestrator settings — loaded from env via pydantic-settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # ---- Postgres master + orchestrator role ----
    pg_host: str = "postgres"
    pg_port: int = 5432
    pg_master_db: str = "postgres"
    pg_super_user: str = "odoo"  # POSTGRES_USER (used for CREATEDB)
    pg_super_password: str = Field(min_length=16)
    pg_orchestrator_user: str = "tenant_orchestrator"
    pg_orchestrator_password: str = Field(min_length=16)
    # Default odoo role on tenant DBs (the role Odoo container uses to log in).
    # We grant ownership of the freshly-created DB to this role so Odoo can DDL.
    pg_tenant_owner_role: str = "odoo"

    # ---- Cryptography ----
    # Master KMS wrapping key (32-byte URL-safe base64 for Fernet). Used to wrap per-tenant keys.
    master_wrapping_key: str = Field(min_length=44, max_length=44)

    # ---- HMAC API auth (shared with Odoo super-admin module) ----
    orchestrator_shared_secret: str = Field(min_length=32)
    hmac_window_seconds: int = 300

    # ---- MinIO / S3 backup ----
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = Field(min_length=8)
    s3_region: str = "us-east-1"
    s3_bucket: str = "platform-backups"
    s3_use_ssl: bool = False

    # ---- Backup defaults ----
    backup_schedule_cron: str = "0 2 * * *"
    backup_retention_daily: int = 30
    backup_retention_monthly: int = 12
    backup_retention_yearly: int = 5
    backup_tmp_dir: str = "/tmp/orchestrator-backups"

    # ---- Odoo connection (used during provisioning to install base modules) ----
    odoo_host: str = "odoo"
    odoo_port: int = 8069
    odoo_admin_passwd: str = Field(min_length=8)
    odoo_filestore_root: str = "/var/lib/odoo/filestore"

    # ---- Operational ----
    log_level: str = "info"
    enable_backup_scheduler: bool = True


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
