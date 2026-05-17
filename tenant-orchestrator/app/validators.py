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
