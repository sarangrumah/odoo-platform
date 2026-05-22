"""Postgres connection helpers — separate pools for master vs ad-hoc tenant DBs."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

from .config import get_settings

_master_pool: ConnectionPool | None = None


def _build_dsn(db: str | None = None, user: str | None = None, password: str | None = None) -> str:
    s = get_settings()
    return (
        f"host={s.pg_host} port={s.pg_port} "
        f"dbname={db or s.pg_master_db} "
        f"user={user or s.pg_orchestrator_user} "
        f"password={password or s.pg_orchestrator_password} "
        f"sslmode=prefer"
    )


def master_pool() -> ConnectionPool:
    """Pool against the master DB using the orchestrator role."""
    global _master_pool
    if _master_pool is None:
        _master_pool = ConnectionPool(
            conninfo=_build_dsn(),
            min_size=1,
            max_size=8,
            open=True,
        )
    return _master_pool


@contextmanager
def master_connection() -> Iterator[psycopg.Connection]:
    with master_pool().connection() as conn:
        yield conn


@contextmanager
def superuser_connection(db: str | None = None) -> Iterator[psycopg.Connection]:
    """Ad-hoc connection as POSTGRES_USER (CREATEDB privilege).

    Used for: CREATE DATABASE, DROP DATABASE, ALTER DATABASE RENAME — operations
    that the orchestrator role can technically do (it has CREATEDB) but that we
    explicitly route via superuser when the operation touches DBs owned by
    other roles. Default: autocommit (required for CREATE DATABASE).
    """
    s = get_settings()
    conn = psycopg.connect(
        _build_dsn(db=db, user=s.pg_super_user, password=s.pg_super_password),
        autocommit=True,
    )
    try:
        yield conn
    finally:
        conn.close()


def close_all() -> None:
    global _master_pool
    if _master_pool is not None:
        _master_pool.close()
        _master_pool = None
