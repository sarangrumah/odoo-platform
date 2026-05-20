"""Input validators used at the API boundary."""

from __future__ import annotations

import re

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
# Pydantic models reused across routers (Track D)
# ---------------------------------------------------------------------------

try:
    from typing import Literal, Optional

    from pydantic import BaseModel, Field

    class ReplicateRequest(BaseModel):
        """Body for POST /v1/backups/{backup_id}/replicate."""

        target_tenant_slug: str = Field(min_length=2, max_length=63, pattern=SLUG_RE.pattern)
        target_env: Literal["prod", "staging", "dev"] = "staging"
        target_db: Optional[str] = Field(
            default=None,
            description="Override target DB name. Defaults to '<slug>_<env>'.",
        )

    class EnforceRetentionRequest(BaseModel):
        """Body for POST /v1/backups/enforce-retention."""

        tenant_slug: str = Field(min_length=2, max_length=63, pattern=SLUG_RE.pattern)
        retention_days: int = Field(default=30, ge=1, le=3650)

except ImportError:  # pragma: no cover — pydantic only required server-side
    ReplicateRequest = None  # type: ignore[assignment]
    EnforceRetentionRequest = None  # type: ignore[assignment]
