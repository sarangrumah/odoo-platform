"""Backup / restore endpoints."""

from __future__ import annotations

from typing import Any, Literal

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from .. import backup as backup_svc
from .. import registry
from ..validators import (
    EnforceRetentionRequest,
    ReplicateRequest,
    assert_valid_slug,
)

log = structlog.get_logger()

router = APIRouter(prefix="/v1/tenants/{slug}/backups", tags=["backups"])

# Second router for backup-id-centric operations (Track D). Registered
# alongside ``router`` in app.main (merge step).
admin_router = APIRouter(prefix="/v1/backups", tags=["backups"])


class BackupRunIn(BaseModel):
    kind: Literal["manual", "daily", "monthly", "yearly"] = "manual"


class BackupOut(BaseModel):
    id: int
    tenant_slug: str
    kind: str
    started_at: Any
    finished_at: Any | None = None
    size_bytes: int | None = None
    s3_key: str | None = None
    checksum_sha256: str | None = None
    outcome: str
    error: str | None = None
    expires_at: Any | None = None


@router.get("", response_model=list[BackupOut])
def list_backups_endpoint(slug: str, limit: int = 100) -> list[BackupOut]:
    assert_valid_slug(slug)
    rows = registry.list_backups(slug, limit=limit)
    return [BackupOut(**r) for r in rows]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def run_backup_endpoint(slug: str, body: BackupRunIn, request: Request) -> dict:
    assert_valid_slug(slug)
    actor = getattr(request.state, "actor", "system")
    try:
        return backup_svc.run_backup(slug, kind=body.kind, actor=actor)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tenant '{slug}' not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e


class RestoreIn(BaseModel):
    s3_key: str
    target_db: str | None = Field(
        default=None,
        description="If absent, restored to '<slug>_staging' (non-destructive).",
    )


@router.post("/restore", status_code=status.HTTP_202_ACCEPTED)
def restore_backup_endpoint(slug: str, body: RestoreIn, request: Request) -> dict:
    assert_valid_slug(slug)
    actor = getattr(request.state, "actor", "system")
    try:
        target = backup_svc.restore_backup(slug, s3_key=body.s3_key, target_db=body.target_db, actor=actor)
        return {"slug": slug, "restored_to_db": target}
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tenant '{slug}' not found")
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


# ---------------------------------------------------------------------------
# Admin router: backup-id-centric ops (Track D)
# ---------------------------------------------------------------------------


def _get_backup_row(backup_id: int) -> dict:
    """Lookup a single backup row across all tenants."""
    fetch = getattr(registry, "get_backup", None)
    if callable(fetch):
        row = fetch(backup_id)
        if row:
            return row
    # Fallback: scan list_backups for each tenant. Not ideal but works for MVP.
    for tenant in registry.list_tenants():
        for r in registry.list_backups(tenant["slug"], limit=10_000):
            if r["id"] == backup_id:
                return r
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"Backup {backup_id} not found")


@admin_router.get("/{backup_id}", response_model=BackupOut)
def get_backup_endpoint(backup_id: int) -> BackupOut:
    return BackupOut(**_get_backup_row(backup_id))


@admin_router.post("/{backup_id}/replicate", status_code=status.HTTP_202_ACCEPTED)
def replicate_backup_endpoint(
    backup_id: int,
    body: ReplicateRequest,
    request: Request,
) -> dict:
    """Restore a specific backup into the target tenant's <env> DB."""
    actor = getattr(request.state, "actor", "system")
    row = _get_backup_row(backup_id)
    if row.get("outcome") != "success" or not row.get("s3_key"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Backup {backup_id} is not in 'success' state",
        )
    assert_valid_slug(body.target_tenant_slug)
    target_db = body.target_db or f"{body.target_tenant_slug}_{body.target_env}"

    log.info(
        "backup.replicate.start",
        backup_id=backup_id,
        source_slug=row["tenant_slug"],
        target_slug=body.target_tenant_slug,
        target_env=body.target_env,
        target_db=target_db,
        actor=actor,
    )
    try:
        restored = backup_svc.restore_backup(
            row["tenant_slug"],
            s3_key=row["s3_key"],
            target_db=target_db,
            actor=actor,
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except Exception as e:  # noqa: BLE001 — surface as 500
        log.exception("backup.replicate.failed", backup_id=backup_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)) from e

    return {
        "backup_id": backup_id,
        "source_slug": row["tenant_slug"],
        "target_slug": body.target_tenant_slug,
        "target_env": body.target_env,
        "restored_to_db": restored,
    }


@admin_router.post("/enforce-retention", status_code=status.HTTP_200_OK)
def enforce_retention_endpoint(
    body: EnforceRetentionRequest,
    request: Request,
) -> dict:
    """Delete backups older than ``retention_days`` for the given tenant.

    Implementation: marks rows past the cutoff as expired and delegates to
    ``backup.prune_expired`` for the actual S3 + DB cleanup. Falls back to
    calling ``prune_expired`` directly if a dedicated registry helper isn't
    available (MVP).
    """
    assert_valid_slug(body.tenant_slug)
    actor = getattr(request.state, "actor", "system")

    expire_helper = getattr(registry, "expire_backups_older_than", None)
    expired_count = 0
    if callable(expire_helper):
        try:
            expired_count = expire_helper(body.tenant_slug, body.retention_days)
        except Exception as e:  # noqa: BLE001
            log.exception("backup.retention.mark_failed", slug=body.tenant_slug)
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)) from e

    try:
        pruned = backup_svc.prune_expired(actor=actor)
    except Exception as e:  # noqa: BLE001
        log.exception("backup.retention.prune_failed", slug=body.tenant_slug)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)) from e

    log.info(
        "backup.retention.enforced",
        slug=body.tenant_slug,
        retention_days=body.retention_days,
        marked_expired=expired_count,
        pruned=pruned,
        actor=actor,
    )
    return {
        "tenant_slug": body.tenant_slug,
        "retention_days": body.retention_days,
        "marked_expired": expired_count,
        "pruned": pruned,
    }
