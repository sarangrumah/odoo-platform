"""APScheduler wiring — periodic backups + housekeeping.

Each tenant has its own ``backup_schedule_cron`` in the registry. On startup,
we read the active tenants and register one cron job per tenant. When a
tenant is added/suspended/archived, we reload the schedule (simple approach:
poll every minute, sync jobs to current tenant list).
"""

from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import backup as backup_svc
from . import provisioner, registry

log = structlog.get_logger()

_scheduler: AsyncIOScheduler | None = None
_JOB_PREFIX = "tenant-backup:"


def _job_id_for(slug: str) -> str:
    return f"{_JOB_PREFIX}{slug}"


def _add_backup_job(slug: str, cron_expr: str) -> None:
    s = _scheduler
    if s is None:
        return
    job_id = _job_id_for(slug)
    try:
        trigger = CronTrigger.from_crontab(cron_expr)
    except Exception as e:
        log.warning("scheduler.cron_invalid", slug=slug, cron=cron_expr, err=str(e))
        return
    s.add_job(
        backup_svc.run_backup,
        trigger=trigger,
        args=[slug, "daily", "scheduler"],
        id=job_id,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )


def _sync_jobs() -> None:
    """Reconcile registered jobs with current registry state."""
    if _scheduler is None:
        return

    desired: dict[str, str] = {}
    for row in registry.list_tenants():
        if row["state"] in ("active", "suspended"):  # suspended still gets backups (for safety)
            desired[row["slug"]] = row["backup_schedule_cron"] or "0 2 * * *"

    existing = {j.id for j in _scheduler.get_jobs() if j.id.startswith(_JOB_PREFIX)}
    desired_ids = {_job_id_for(slug) for slug in desired}

    # Remove jobs for tenants that no longer exist / are archived
    for jid in existing - desired_ids:
        _scheduler.remove_job(jid)
        log.info("scheduler.job_removed", id=jid)

    # Add / update
    for slug, cron_expr in desired.items():
        _add_backup_job(slug, cron_expr)


def _housekeeping() -> None:
    """Prune expired backups + purge archived tenants past their retention."""
    try:
        backup_svc.prune_expired()
    except Exception:
        log.exception("scheduler.prune_failed")
    try:
        provisioner.purge_due()
    except Exception:
        log.exception("scheduler.purge_failed")


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    # Initial sync
    _sync_jobs()
    # Re-sync every minute to pick up new/removed tenants
    _scheduler.add_job(
        _sync_jobs,
        trigger=IntervalTrigger(minutes=1),
        id="scheduler-sync",
        max_instances=1,
    )
    # Housekeeping every hour
    _scheduler.add_job(
        _housekeeping,
        trigger=IntervalTrigger(hours=1),
        id="scheduler-housekeeping",
        max_instances=1,
    )
    _scheduler.start()
    log.info("scheduler.started")


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("scheduler.stopped")
