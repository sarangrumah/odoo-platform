"""Per-tenant backup + restore (pg_dump → MinIO/S3)."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import boto3
import structlog
from botocore.client import Config as BotoConfig

from . import dbops, registry
from .config import get_settings

log = structlog.get_logger()


# ----- S3 helper ---------------------------------------------------------


def _s3():
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name=s.s3_region,
        config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 5, "mode": "standard"}),
        use_ssl=s.s3_use_ssl,
    )


def ensure_bucket() -> None:
    s = get_settings()
    client = _s3()
    try:
        client.head_bucket(Bucket=s.s3_bucket)
    except client.exceptions.ClientError:
        log.info("backup.bucket.create", bucket=s.s3_bucket)
        # MinIO accepts CreateBucket with default region; S3 needs LocationConstraint
        # for non-us-east-1 — we use us-east-1 so empty body is fine.
        client.create_bucket(Bucket=s.s3_bucket)


# ----- pg_dump / restore helpers ----------------------------------------


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pg_dump(db_name: str, out_path: Path) -> None:
    s = get_settings()
    env = os.environ.copy()
    env["PGPASSWORD"] = s.pg_super_password
    cmd = [
        "pg_dump",
        "-h", s.pg_host,
        "-p", str(s.pg_port),
        "-U", s.pg_super_user,
        "-d", db_name,
        "-F", "c",        # custom format — supports parallel restore
        "-Z", "6",
        "-f", str(out_path),
    ]
    log.info("backup.pg_dump", db=db_name, out=str(out_path))
    res = subprocess.run(cmd, env=env, capture_output=True, check=False, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"pg_dump failed (rc={res.returncode}): {res.stderr[:500]}")


def _pg_restore(db_name: str, in_path: Path) -> None:
    s = get_settings()
    env = os.environ.copy()
    env["PGPASSWORD"] = s.pg_super_password
    cmd = [
        "pg_restore",
        "-h", s.pg_host,
        "-p", str(s.pg_port),
        "-U", s.pg_super_user,
        "-d", db_name,
        "--no-owner",
        "--no-acl",
        "--clean",
        "--if-exists",
        str(in_path),
    ]
    log.info("backup.pg_restore", db=db_name, src=str(in_path))
    res = subprocess.run(cmd, env=env, capture_output=True, check=False, text=True)
    if res.returncode != 0:
        # pg_restore exits non-zero on harmless warnings — surface stderr for review
        log.warning("backup.pg_restore.warnings", stderr=res.stderr[:500])
        if "FATAL" in res.stderr or "ERROR:  could not" in res.stderr:
            raise RuntimeError(f"pg_restore failed: {res.stderr[:500]}")


# ----- Retention --------------------------------------------------------


def _compute_expiry(kind: str, started_at: datetime, tenant_row: dict) -> datetime:
    if kind == "daily":
        return started_at + timedelta(days=tenant_row.get("backup_retention_daily", 30))
    if kind == "monthly":
        return started_at + timedelta(days=30 * tenant_row.get("backup_retention_monthly", 12))
    if kind == "yearly":
        return started_at + timedelta(days=365 * tenant_row.get("backup_retention_yearly", 5))
    # manual / one-off → keep 90 days by default
    return started_at + timedelta(days=90)


# ----- Public API -------------------------------------------------------


def run_backup(slug: str, kind: str = "manual", actor: str = "system") -> dict:
    """Take a backup, upload it, record in registry."""
    s = get_settings()
    t = registry.get_tenant(slug)
    if not t:
        raise LookupError(slug)
    if t["state"] not in ("active", "suspended"):
        raise ValueError(f"Cannot backup tenant in state '{t['state']}'")

    ensure_bucket()
    started_at = datetime.now(timezone.utc)
    bid = registry.record_backup_start(slug, kind)

    tmp_dir = Path(s.backup_tmp_dir) / slug / started_at.strftime("%Y%m%dT%H%M%SZ")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dump_path = tmp_dir / f"{slug}.dump"
    s3_key = f"{slug}/{started_at.strftime('%Y/%m/%d')}/{slug}-{started_at.strftime('%H%M%SZ')}.dump"

    try:
        _pg_dump(t["db_name"], dump_path)
        size = dump_path.stat().st_size
        checksum = _sha256_file(dump_path)

        _s3().upload_file(
            Filename=str(dump_path),
            Bucket=s.s3_bucket,
            Key=s3_key,
            ExtraArgs={
                "Metadata": {
                    "tenant-slug": slug,
                    "kind": kind,
                    "sha256": checksum,
                    "started-at": started_at.isoformat(),
                },
                "ServerSideEncryption": "AES256",
            },
        )

        expires_at = _compute_expiry(kind, started_at, t)
        registry.record_backup_done(
            bid,
            size_bytes=size,
            s3_key=s3_key,
            filestore_key=None,  # filestore handled by separate volume snapshot (out of scope for P0)
            checksum_sha256=checksum,
            expires_at=expires_at,
        )
        registry.update_backup_meta(
            slug,
            last_backup_at=started_at,
            last_backup_size_bytes=size,
            last_backup_id=s3_key,
        )
        registry.log_action(
            slug, "backup", actor,
            {"kind": kind, "s3_key": s3_key, "size_bytes": size, "sha256": checksum},
            "success",
        )
        log.info("backup.done", slug=slug, kind=kind, size=size, key=s3_key)
        return {"backup_id": bid, "s3_key": s3_key, "size_bytes": size, "sha256": checksum}
    except Exception as e:
        log.exception("backup.failed", slug=slug)
        registry.record_backup_failed(bid, str(e))
        registry.log_action(slug, "backup", actor, {"kind": kind}, "failure", error=str(e))
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def restore_backup(
    slug: str,
    s3_key: str,
    *,
    target_db: Optional[str] = None,
    actor: str = "system",
) -> str:
    """Download a backup and pg_restore into ``target_db`` (or ``<slug>_staging``)."""
    s = get_settings()
    t = registry.get_tenant(slug)
    if not t:
        raise LookupError(slug)
    target = target_db or f"{slug}_staging"

    tmp_dir = Path(s.backup_tmp_dir) / slug / "restore"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    local = tmp_dir / "restore.dump"

    try:
        _s3().download_file(Bucket=s.s3_bucket, Key=s3_key, Filename=str(local))

        # Recreate target DB
        if dbops.db_exists(target):
            dbops.drop_database(target)
        dbops.create_database(target, owner_role=s.pg_tenant_owner_role)
        _pg_restore(target, local)

        registry.log_action(
            slug, "restore", actor,
            {"s3_key": s3_key, "target_db": target}, "success",
        )
        log.info("backup.restored", slug=slug, target=target, key=s3_key)
        return target
    except Exception as e:
        log.exception("backup.restore_failed", slug=slug)
        registry.log_action(
            slug, "restore", actor, {"s3_key": s3_key}, "failure", error=str(e)
        )
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def prune_expired(actor: str = "scheduler") -> int:
    """Delete expired backup objects from S3 + registry rows."""
    s = get_settings()
    client = _s3()
    expired = registry.expired_backups(datetime.now(timezone.utc))
    n = 0
    for row in expired:
        try:
            if row["s3_key"]:
                client.delete_object(Bucket=s.s3_bucket, Key=row["s3_key"])
            registry.delete_backup_row(row["id"])
            n += 1
        except Exception as e:
            log.exception("backup.prune_failed", id=row["id"])
            registry.log_action(
                row["tenant_slug"], "backup_prune", actor,
                {"backup_id": row["id"]}, "failure", error=str(e),
            )
    if n:
        log.info("backup.pruned", count=n)
    return n
