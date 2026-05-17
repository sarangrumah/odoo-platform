"""Backup / restore endpoints."""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from .. import backup as backup_svc
from .. import registry
from ..validators import assert_valid_slug

router = APIRouter(prefix="/v1/tenants/{slug}/backups", tags=["backups"])


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
    target_db: Optional[str] = Field(
        default=None,
        description="If absent, restored to '<slug>_staging' (non-destructive).",
    )


@router.post("/restore", status_code=status.HTTP_202_ACCEPTED)
def restore_backup_endpoint(slug: str, body: RestoreIn, request: Request) -> dict:
    assert_valid_slug(slug)
    actor = getattr(request.state, "actor", "system")
    try:
        target = backup_svc.restore_backup(
            slug, s3_key=body.s3_key, target_db=body.target_db, actor=actor
        )
        return {"slug": slug, "restored_to_db": target}
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tenant '{slug}' not found")
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
