"""High-level orchestration: provision / suspend / archive a tenant.

Each operation:
  1. Validates input.
  2. Logs the *intent* to the action log.
  3. Performs the underlying ops (DB lifecycle, Odoo RPC, crypto).
  4. Logs success or failure.
On failure mid-flight the tenant state transitions to ``failed`` rather than
being silently dropped — ops can either ``DELETE`` it (which archives) or
``POST /v1/tenants/{slug}/repair`` (future).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import structlog

from . import dbops, registry
from .crypto import generate_tenant_dek, wrap_dek
from .odoo_admin import OdooAdminClient, gen_initial_admin_password
from .validators import assert_valid_slug

log = structlog.get_logger()

# Modules installed automatically on every fresh tenant DB
DEFAULT_TENANT_MODULES = [
    "custom_core",
    "custom_ai_bridge",
    "custom_pdp_core",
    "custom_pdp_audit",
    "custom_pdp_consent",
    "custom_pdp_dsar",
    "custom_pdp_masking",
    "custom_pdp_retention",
    "custom_coretax",
]


def provision(
    slug: str,
    display_name: str,
    *,
    plan_tier: str = "standard",
    contact_email: str | None = None,
    contact_phone: str | None = None,
    csm_user_id: int | None = None,
    features: dict[str, Any] | None = None,
    backup_schedule_cron: str | None = None,
    actor: str = "system",
    install_modules: list[str] | None = None,
) -> dict[str, Any]:
    """Provision a brand-new tenant.

    Returns dict with ``slug``, ``db_name``, ``admin_login``, ``admin_password``
    (the password is returned in clear text ONCE and must be passed back to ops;
    only its bcrypt hash is persisted).
    """
    assert_valid_slug(slug)
    db_name = slug

    # Pre-flight: must not exist
    if registry.get_tenant(slug):
        registry.log_action(
            slug,
            "provision",
            actor,
            {"reason": "slug exists"},
            "failure",
            error="Tenant with this slug already exists",
        )
        raise FileExistsError(f"Tenant '{slug}' already exists")

    # 1. Generate per-tenant DEK + wrap it
    dek = generate_tenant_dek()
    wrapped = wrap_dek(dek)

    # 2. Initial admin password
    admin_pwd_plain = gen_initial_admin_password()
    admin_pwd_hash = bcrypt.hashpw(admin_pwd_plain.encode(), bcrypt.gensalt()).decode()

    # 3. Insert registry row in 'provisioning' state
    row = registry.insert_tenant(
        slug=slug,
        display_name=display_name,
        db_name=db_name,
        plan_tier=plan_tier,
        contact_email=contact_email,
        contact_phone=contact_phone,
        csm_user_id=csm_user_id,
        fernet_key_wrapped=wrapped,
        master_admin_pwd_hash=admin_pwd_hash,
        features=features,
        backup_schedule_cron=backup_schedule_cron,
    )
    registry.log_action(
        slug,
        "provision_started",
        actor,
        {"db_name": db_name, "plan_tier": plan_tier},
        "success",
    )

    # 4. Provision the actual DB via Odoo's create endpoint
    odoo = OdooAdminClient()
    try:
        odoo.create_database(db_name=db_name, admin_password=admin_pwd_plain, demo=False)

        # 5. Install our custom module set
        modules = install_modules or DEFAULT_TENANT_MODULES
        odoo.install_modules(db=db_name, login="admin", password=admin_pwd_plain, module_names=modules)

        # 6. Mark active
        registry.set_state(slug, "active", activated_at=datetime.now(UTC))
        registry.log_action(
            slug,
            "provision_completed",
            actor,
            {"modules": modules},
            "success",
        )
        log.info("tenant.provisioned", slug=slug, db=db_name)
    except Exception as e:
        log.exception("tenant.provision_failed", slug=slug)
        registry.set_state(slug, "failed")
        registry.log_action(
            slug,
            "provision_failed",
            actor,
            {"error": str(e)},
            "failure",
            error=str(e),
        )
        raise
    finally:
        odoo.close()

    return {
        "slug": slug,
        "db_name": db_name,
        "admin_login": "admin",
        "admin_password": admin_pwd_plain,
        "fernet_key_dek": dek.decode(),  # returned ONCE to caller (Odoo) for in-memory cache
    }


def suspend(slug: str, actor: str, reason: str | None = None) -> None:
    t = registry.get_tenant(slug)
    if not t:
        raise LookupError(slug)
    if t["state"] != "active":
        raise ValueError(f"Cannot suspend tenant in state '{t['state']}'")

    # Kill open Odoo sessions so reverse proxy returns 503 on next hit.
    # The proxy itself reads tenant state (or we set a flag in Redis on this transition).
    dbops.terminate_connections(t["db_name"])

    registry.set_state(slug, "suspended", suspended_at=datetime.now(UTC))
    registry.log_action(
        slug,
        "suspend",
        actor,
        {"reason": reason},
        "success",
    )
    log.info("tenant.suspended", slug=slug)


def resume(slug: str, actor: str) -> None:
    t = registry.get_tenant(slug)
    if not t:
        raise LookupError(slug)
    if t["state"] != "suspended":
        raise ValueError(f"Cannot resume tenant in state '{t['state']}'")

    registry.set_state(slug, "active")
    registry.log_action(slug, "resume", actor, None, "success")
    log.info("tenant.resumed", slug=slug)


def archive(slug: str, actor: str, retention_days: int = 30) -> None:
    """Soft delete: rename the DB and schedule purge."""
    t = registry.get_tenant(slug)
    if not t:
        raise LookupError(slug)

    now = datetime.now(UTC)
    archived_db_name = f"_archived_{int(now.timestamp())}_{slug}"
    dbops.rename_database(t["db_name"], archived_db_name)

    registry.set_state(
        slug,
        "archived",
        archived_at=now,
        purge_after=now + timedelta(days=retention_days),
    )
    # Update db_name in registry so purge job can find it later
    # (registry.set_state doesn't currently update db_name; we use a direct UPDATE below)
    from .db import master_connection

    with master_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE tenant_registry.tenants SET db_name = %s WHERE slug = %s",
            (archived_db_name, slug),
        )

    registry.log_action(
        slug,
        "archive",
        actor,
        {"retention_days": retention_days, "renamed_to": archived_db_name},
        "success",
    )
    log.info("tenant.archived", slug=slug, renamed_to=archived_db_name)


def purge_due(actor: str = "scheduler") -> int:
    """Delete archived tenants whose purge_after has passed. Returns count purged."""
    from .db import master_connection

    now = datetime.now(UTC)
    n = 0
    with master_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT slug, db_name FROM tenant_registry.tenants
                WHERE state = 'archived' AND purge_after IS NOT NULL AND purge_after < %s""",
            (now,),
        )
        rows = cur.fetchall()

    for slug, db_name in rows:
        try:
            dbops.drop_database(db_name)
            with master_connection() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM tenant_registry.tenants WHERE slug = %s", (slug,))
            registry.log_action(slug, "purge", actor, {"db_name": db_name}, "success")
            log.info("tenant.purged", slug=slug, db=db_name)
            n += 1
        except Exception as e:
            log.exception("tenant.purge_failed", slug=slug)
            registry.log_action(slug, "purge", actor, None, "failure", error=str(e))
    return n


def fingerprint_payload(payload: dict[str, Any]) -> str:
    """Stable sha256 over a JSON-canonical payload for idempotency keys (future)."""
    import json

    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
