"""Input validators used at the API boundary."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
DB_NAME_RE = SLUG_RE  # we use the slug as the db name 1:1


def is_valid_slug(slug: str) -> bool:
    """Lowercase, must start with a letter, [a-z0-9_], 2-63 chars."""
    return bool(SLUG_RE.match(slug))


def assert_valid_slug(slug: str) -> None:
    if not is_valid_slug(slug):
        raise ValueError(
            f"Invalid slug '{slug}': must match {SLUG_RE.pattern} "
            "(lowercase, start with letter, alphanumeric + underscore, length 2-63)"
        )


# ---------------------------------------------------------------------------
# VPS lifecycle request schemas
# ---------------------------------------------------------------------------


class _VPSBase(BaseModel):
    """Common SSH target fields used by every /v1/vps/* call."""

    vps_id: int = Field(ge=1)
    hostname: str = Field(min_length=1, max_length=255)
    public_ip: str | None = None
    ssh_user: str = Field(default="root", min_length=1, max_length=64)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_credential_ref: str = Field(
        min_length=4,
        description="Pointer to credential vault — e.g. vault://, env://, file://. NEVER raw key.",
    )


class VPSRegisterRequest(_VPSBase):
    """POST /v1/vps/register — just probes SSH reachability."""


class BootstrapRequest(_VPSBase):
    """POST /v1/vps/{id}/bootstrap — runs harden_os + install_docker + install_caddy."""

    tenant_slug: str | None = None


class DeployStackRequest(_VPSBase):
    """POST /v1/vps/{id}/deploy-stack — generate docker-compose + up -d."""

    env_type: Literal["dev", "staging", "prod"] = "dev"
    tenant_slug: str = Field(min_length=2, max_length=63, pattern=SLUG_RE.pattern)
    db_name: str = Field(min_length=2, max_length=63, pattern=SLUG_RE.pattern)
    pg_password: str | None = None
    workers: int | None = Field(default=2, ge=1, le=32)


class SyncAddonsRequest(_VPSBase):
    """POST /v1/vps/{id}/sync-addons — rsync addons + restart + -u all."""

    env_type: Literal["dev", "staging", "prod"] = "dev"
    tenant_slug: str = Field(min_length=2, max_length=63, pattern=SLUG_RE.pattern)
    db_name: str = Field(min_length=2, max_length=63, pattern=SLUG_RE.pattern)


# ---------------------------------------------------------------------------
# Backup admin request schemas
# ---------------------------------------------------------------------------


class ReplicateRequest(BaseModel):
    """Body for POST /v1/backups/{backup_id}/replicate."""

    target_tenant_slug: str = Field(min_length=2, max_length=63, pattern=SLUG_RE.pattern)
    target_env: Literal["prod", "staging", "dev"] = "staging"
    target_db: str | None = Field(
        default=None,
        description="Override target DB name. Defaults to '<slug>_<env>'.",
    )


class EnforceRetentionRequest(BaseModel):
    """Body for POST /v1/backups/enforce-retention."""

    tenant_slug: str = Field(min_length=2, max_length=63, pattern=SLUG_RE.pattern)
    retention_days: int = Field(default=30, ge=1, le=3650)


# ---------------------------------------------------------------------------
# Public intake (Next.js landing-public → orchestrator → odoo-mgmt)
# ---------------------------------------------------------------------------


class IntakeSubmitRequest(BaseModel):
    """Body for POST /v1/intake/submit (from hub-portal IntakeWizard)."""

    company_name: str = Field(min_length=2, max_length=200)
    contact_email: str = Field(min_length=3, max_length=200)
    contact_phone: str = Field(min_length=6, max_length=32)
    # Vertical code controlled by the UI dropdown (tokens.js). Kept as Char on the
    # Odoo side, so accept any short string here rather than coupling to an enum.
    vertical_target: str = Field(min_length=2, max_length=40)
    modules_wishlist: list[str] = Field(default_factory=list, max_length=50)
    business_process_narrative: str = Field(min_length=50, max_length=20000)
    company_logo_base64: str | None = Field(default=None, max_length=2_000_000)
    npwp: str | None = Field(default=None, max_length=32)
    bank_name: str | None = Field(default=None, max_length=100)
    bank_account: str | None = Field(default=None, max_length=64)
    turnstile_token: str = Field(min_length=1, max_length=4096)
    brd_file_base64s: list[str] | None = Field(default=None, max_length=5)
    source_ip: str | None = Field(default=None, max_length=64)


class IntakeSubmitResponse(BaseModel):
    token: str
    status_url: str


class IntakeStatusResponse(BaseModel):
    token: str
    stage: str
    status: str
    target_go_live: str | None = None
    progress_pct: float | None = None
    journey_id: int | None = None
