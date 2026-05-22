"""Tenant lifecycle endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from .. import provisioner, registry
from ..crypto import unwrap_dek
from ..validators import assert_valid_slug

router = APIRouter(prefix="/v1/tenants", tags=["tenants"])


class TenantIn(BaseModel):
    slug: str = Field(min_length=2, max_length=63, pattern=r"^[a-z][a-z0-9_]{1,62}$")
    display_name: str = Field(min_length=1, max_length=128)
    plan_tier: str = "standard"
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    csm_user_id: int | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    backup_schedule_cron: str | None = None
    install_modules: list[str] | None = None


class TenantOut(BaseModel):
    slug: str
    display_name: str
    db_name: str
    state: str
    plan_tier: str | None = None
    contact_email: str | None = None
    last_backup_at: Any | None = None
    activated_at: Any | None = None
    suspended_at: Any | None = None
    archived_at: Any | None = None
    features: dict[str, Any] = Field(default_factory=dict)


class ProvisionResult(BaseModel):
    slug: str
    db_name: str
    admin_login: str
    admin_password: str  # returned ONCE — ops must capture
    fernet_key_dek: str  # returned ONCE — Odoo caches in-memory


class SuspendIn(BaseModel):
    reason: str | None = None


class ArchiveIn(BaseModel):
    retention_days: int = Field(default=30, ge=1, le=365)


def _row_to_out(row: dict) -> TenantOut:
    return TenantOut(
        slug=row["slug"],
        display_name=row["display_name"],
        db_name=row["db_name"],
        state=row["state"],
        plan_tier=row.get("plan_tier"),
        contact_email=row.get("contact_email"),
        last_backup_at=row.get("last_backup_at"),
        activated_at=row.get("activated_at"),
        suspended_at=row.get("suspended_at"),
        archived_at=row.get("archived_at"),
        features=row.get("features") or {},
    )


@router.get("", response_model=list[TenantOut])
def list_tenants_endpoint(state: str | None = None) -> list[TenantOut]:
    return [_row_to_out(r) for r in registry.list_tenants(state=state)]


@router.get("/{slug}", response_model=TenantOut)
def get_tenant_endpoint(slug: str) -> TenantOut:
    assert_valid_slug(slug)
    row = registry.get_tenant(slug)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tenant '{slug}' not found")
    return _row_to_out(row)


@router.post("", response_model=ProvisionResult, status_code=status.HTTP_201_CREATED)
def create_tenant_endpoint(body: TenantIn, request: Request) -> ProvisionResult:
    actor = getattr(request.state, "actor", "system")
    try:
        result = provisioner.provision(
            slug=body.slug,
            display_name=body.display_name,
            plan_tier=body.plan_tier,
            contact_email=body.contact_email,
            contact_phone=body.contact_phone,
            csm_user_id=body.csm_user_id,
            features=body.features,
            backup_schedule_cron=body.backup_schedule_cron,
            actor=actor,
            install_modules=body.install_modules,
        )
        return ProvisionResult(**result)
    except FileExistsError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.post("/{slug}/suspend", response_model=TenantOut)
def suspend_endpoint(slug: str, body: SuspendIn, request: Request) -> TenantOut:
    assert_valid_slug(slug)
    actor = getattr(request.state, "actor", "system")
    try:
        provisioner.suspend(slug, actor=actor, reason=body.reason)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tenant '{slug}' not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return _row_to_out(registry.get_tenant(slug))  # type: ignore[arg-type]


@router.post("/{slug}/resume", response_model=TenantOut)
def resume_endpoint(slug: str, request: Request) -> TenantOut:
    assert_valid_slug(slug)
    actor = getattr(request.state, "actor", "system")
    try:
        provisioner.resume(slug, actor=actor)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tenant '{slug}' not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return _row_to_out(registry.get_tenant(slug))  # type: ignore[arg-type]


@router.delete("/{slug}", response_model=TenantOut)
def archive_endpoint(slug: str, body: ArchiveIn, request: Request) -> TenantOut:
    assert_valid_slug(slug)
    actor = getattr(request.state, "actor", "system")
    try:
        provisioner.archive(slug, actor=actor, retention_days=body.retention_days)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tenant '{slug}' not found")
    return _row_to_out(registry.get_tenant(slug))  # type: ignore[arg-type]


class DekOut(BaseModel):
    slug: str
    fernet_key_dek: str


@router.get("/{slug}/dek", response_model=DekOut)
def get_tenant_dek(slug: str) -> DekOut:
    """Return the unwrapped per-tenant Fernet DEK for Odoo to cache in-memory.

    This endpoint is HMAC-protected and should only be called over the trusted
    internal Docker network. Odoo MUST NOT persist the returned key to disk.
    """
    assert_valid_slug(slug)
    row = registry.get_tenant(slug)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tenant '{slug}' not found")
    if not row.get("fernet_key_wrapped"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Tenant has no DEK provisioned")
    try:
        dek = unwrap_dek(bytes(row["fernet_key_wrapped"]))
    except ValueError as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)) from e
    return DekOut(slug=slug, fernet_key_dek=dek.decode())
