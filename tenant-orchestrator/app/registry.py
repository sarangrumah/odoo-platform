"""Tenant registry CRUD against the master DB."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from psycopg.rows import dict_row

from .db import master_connection

# ---------------------------------------------------------------------------
# Tenants table
# ---------------------------------------------------------------------------


def list_tenants(state: str | None = None) -> list[dict[str, Any]]:
    with master_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        if state:
            cur.execute(
                "SELECT * FROM tenant_registry.tenants WHERE state = %s ORDER BY id",
                (state,),
            )
        else:
            cur.execute("SELECT * FROM tenant_registry.tenants ORDER BY id")
        return cur.fetchall()


def get_tenant(slug: str) -> dict[str, Any] | None:
    with master_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM tenant_registry.tenants WHERE slug = %s",
            (slug,),
        )
        return cur.fetchone()


def insert_tenant(
    *,
    slug: str,
    display_name: str,
    db_name: str,
    plan_tier: str | None,
    contact_email: str | None,
    contact_phone: str | None,
    csm_user_id: int | None,
    fernet_key_wrapped: bytes,
    master_admin_pwd_hash: str,
    features: dict[str, Any] | None = None,
    backup_schedule_cron: str | None = None,
) -> dict[str, Any]:
    sql = """
        INSERT INTO tenant_registry.tenants (
            slug, display_name, db_name, state,
            plan_tier, contact_email, contact_phone, csm_user_id,
            fernet_key_wrapped, master_admin_pwd_hash,
            features, backup_schedule_cron
        ) VALUES (
            %s, %s, %s, 'provisioning',
            %s, %s, %s, %s,
            %s, %s,
            %s::jsonb, COALESCE(%s, '0 2 * * *')
        )
        RETURNING *
    """
    with master_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            sql,
            (
                slug,
                display_name,
                db_name,
                plan_tier,
                contact_email,
                contact_phone,
                csm_user_id,
                fernet_key_wrapped,
                master_admin_pwd_hash,
                json.dumps(features or {}),
                backup_schedule_cron,
            ),
        )
        return cur.fetchone()  # type: ignore[return-value]


def set_state(
    slug: str,
    state: str,
    *,
    suspended_at: datetime | None = None,
    archived_at: datetime | None = None,
    purge_after: datetime | None = None,
    activated_at: datetime | None = None,
) -> None:
    fields: list[str] = ["state = %s"]
    args: list[Any] = [state]
    if suspended_at is not None:
        fields.append("suspended_at = %s")
        args.append(suspended_at)
    if archived_at is not None:
        fields.append("archived_at = %s")
        args.append(archived_at)
    if purge_after is not None:
        fields.append("purge_after = %s")
        args.append(purge_after)
    if activated_at is not None:
        fields.append("activated_at = %s")
        args.append(activated_at)
    args.append(slug)

    with master_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE tenant_registry.tenants SET {', '.join(fields)} WHERE slug = %s",
            args,
        )
        if cur.rowcount == 0:
            raise LookupError(f"Tenant '{slug}' not found")


def update_backup_meta(
    slug: str, *, last_backup_at: datetime, last_backup_size_bytes: int, last_backup_id: str
) -> None:
    with master_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE tenant_registry.tenants
                  SET last_backup_at = %s,
                      last_backup_size_bytes = %s,
                      last_backup_id = %s
                WHERE slug = %s""",
            (last_backup_at, last_backup_size_bytes, last_backup_id, slug),
        )


def heartbeat(slug: str) -> None:
    with master_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE tenant_registry.tenants SET last_seen_at = clock_timestamp() WHERE slug = %s",
            (slug,),
        )


# ---------------------------------------------------------------------------
# Action log (append-only, hash-chained — triggers handle chain)
# ---------------------------------------------------------------------------


def log_action(
    tenant_slug: str | None,
    action: str,
    actor: str,
    detail: dict[str, Any] | None,
    outcome: str,
    error: str | None = None,
) -> None:
    """Insert a row into ``tenant_registry.action_log``.

    Triggers on the table compute ``hash`` and ``prev_hash`` automatically —
    we don't supply them.
    """
    tenant_id = None
    if tenant_slug:
        t = get_tenant(tenant_slug)
        if t:
            tenant_id = t["id"]
    with master_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO tenant_registry.action_log
                   (tenant_id, tenant_slug, action, actor, detail, outcome, error)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)""",
            (
                tenant_id,
                tenant_slug,
                action,
                actor,
                json.dumps(detail or {}),
                outcome,
                error,
            ),
        )


# ---------------------------------------------------------------------------
# Backup ledger
# ---------------------------------------------------------------------------


def record_backup_start(slug: str, kind: str) -> int:
    """Insert a 'pending' backup row, return its id."""
    t = get_tenant(slug)
    if not t:
        raise LookupError(slug)
    with master_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO tenant_registry.backups
                   (tenant_id, tenant_slug, kind, outcome)
                VALUES (%s, %s, %s, 'pending')
                RETURNING id""",
            (t["id"], slug, kind),
        )
        return cur.fetchone()[0]  # type: ignore[index]


def record_backup_done(
    backup_id: int,
    *,
    size_bytes: int,
    s3_key: str,
    filestore_key: str | None,
    checksum_sha256: str,
    expires_at: datetime,
) -> None:
    with master_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE tenant_registry.backups
                  SET finished_at = clock_timestamp(),
                      size_bytes = %s,
                      s3_key = %s,
                      filestore_key = %s,
                      checksum_sha256 = %s,
                      outcome = 'success',
                      expires_at = %s
                WHERE id = %s""",
            (size_bytes, s3_key, filestore_key, checksum_sha256, expires_at, backup_id),
        )


def record_backup_failed(backup_id: int, error: str) -> None:
    with master_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE tenant_registry.backups
                  SET finished_at = clock_timestamp(),
                      outcome = 'failure',
                      error = %s
                WHERE id = %s""",
            (error, backup_id),
        )


def list_backups(slug: str, limit: int = 100) -> list[dict[str, Any]]:
    t = get_tenant(slug)
    if not t:
        return []
    with master_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT * FROM tenant_registry.backups
                WHERE tenant_id = %s
              ORDER BY started_at DESC
                LIMIT %s""",
            (t["id"], limit),
        )
        return cur.fetchall()


def expired_backups(now: datetime) -> list[dict[str, Any]]:
    with master_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT * FROM tenant_registry.backups
                WHERE outcome = 'success'
                  AND expires_at IS NOT NULL
                  AND expires_at < %s""",
            (now,),
        )
        return cur.fetchall()


def delete_backup_row(backup_id: int) -> None:
    with master_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM tenant_registry.backups WHERE id = %s", (backup_id,))
