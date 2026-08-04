"""The slug grammar is the boundary that stops command/path injection.

CodeQL reports py/command-line-injection and py/path-injection across
backup.py and odoo_admin.py because it cannot model ``assert_valid_slug`` as a
sanitizer. These tests pin down what that sanitizer actually does, so the
claim rests on evidence rather than on a comment.

Two things are asserted:
  1. the grammar rejects every shape that could escape an argv or a directory;
  2. the check runs BEFORE any subprocess or filesystem call -- a hostile value
     never reaches pg_dump/pg_restore/docker exec at all.
"""

from __future__ import annotations

import pytest

from app import backup, odoo_admin
from app.validators import assert_valid_slug, is_valid_slug

# Every one of these is a real escape attempt against argv, a shell, a path or
# an SQL identifier. None may pass.
HOSTILE = [
    "../../etc/passwd",  # path traversal
    "a/../../b",  # traversal mid-string
    "/etc/passwd",  # absolute path
    "a/b",  # any separator at all
    "a\\b",  # windows separator
    "tenant; rm -rf /",  # shell metachar
    "tenant$(id)",  # command substitution
    "tenant`id`",  # backtick substitution
    "tenant|cat",  # pipe
    "tenant&whoami",  # background
    "tenant\nDROP DATABASE x",  # newline injection
    "tenant\x00suffix",  # NUL truncation
    "--help",  # argv option injection
    "-d other_db",  # argv option with value
    'tenant"',  # quote breaking an identifier
    "tenant'",
    "TENANT",  # uppercase is outside the grammar
    "1tenant",  # must start with a letter
    "a",  # too short
    "a" * 64,  # too long
    "",
    "tenant space",
    "tenant-dash",  # hyphen is not in [a-z0-9_]
]

LEGITIMATE = ["prd_levis", "rnd_wms", "tenant_a", "ab", "a" * 63, "x9_9"]


@pytest.mark.parametrize("value", HOSTILE)
def test_grammar_rejects_hostile_slugs(value):
    assert not is_valid_slug(value), f"{value!r} must not pass the slug grammar"
    with pytest.raises(ValueError):
        assert_valid_slug(value)


@pytest.mark.parametrize("value", LEGITIMATE)
def test_grammar_accepts_real_slugs(value):
    assert is_valid_slug(value)
    assert_valid_slug(value)  # must not raise


def _explode(*_a, **_kw):  # pragma: no cover - only runs if the guard fails
    raise AssertionError("a hostile value reached a subprocess call")


@pytest.mark.parametrize("value", HOSTILE)
def test_pg_dump_validates_before_spawning(value, monkeypatch, tmp_path):
    monkeypatch.setattr(backup.subprocess, "run", _explode)
    with pytest.raises(ValueError):
        backup._pg_dump(value, tmp_path / "out.dump")


@pytest.mark.parametrize("value", HOSTILE)
def test_pg_restore_validates_before_spawning(value, monkeypatch, tmp_path):
    monkeypatch.setattr(backup.subprocess, "run", _explode)
    with pytest.raises(ValueError):
        backup._pg_restore(value, tmp_path / "in.dump")


@pytest.mark.parametrize("value", HOSTILE)
def test_run_backup_validates_before_touching_the_registry(value, monkeypatch):
    # get_tenant would be the first side effect after the guard.
    monkeypatch.setattr(backup.registry, "get_tenant", _explode)
    monkeypatch.setattr(backup.subprocess, "run", _explode)
    with pytest.raises(ValueError):
        backup.run_backup(value)


@pytest.mark.parametrize("value", HOSTILE)
def test_restore_backup_validates_both_slug_and_target_db(value, monkeypatch):
    monkeypatch.setattr(backup.registry, "get_tenant", _explode)
    monkeypatch.setattr(backup.subprocess, "run", _explode)
    with pytest.raises(ValueError):
        backup.restore_backup(value, "some/key.dump")
    # A valid slug with a hostile target_db must fail too.
    with pytest.raises(ValueError):
        backup.restore_backup("prd_levis", "some/key.dump", target_db=value)


def test_module_names_are_pinned_too():
    """`--init <mods>` joins user-supplied module names into the same argv."""
    assert odoo_admin._MODULE_NAME_RE.match("custom_core")
    for bad in ("base,--stop-after-init", "a b", "../x", "a;b", "-d", ""):
        assert not odoo_admin._MODULE_NAME_RE.match(bad), f"{bad!r} must not pass"
