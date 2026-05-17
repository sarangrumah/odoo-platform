"""Postgres DB lifecycle operations (CREATE / DROP / RENAME / kill-conns).

All identifiers passed to these helpers MUST be validated upstream
(``app.validators.is_valid_slug``) — DB / role names cannot be parameterised
in psycopg, so we rely on the regex-validated input *plus* psycopg's
``sql.Identifier`` quoting to defeat injection.
"""

from __future__ import annotations

import psycopg
from psycopg import sql

from .db import superuser_connection


def _quote_ident(name: str) -> sql.Identifier:
    return sql.Identifier(name)


def terminate_connections(db_name: str) -> None:
    """Kill all backends on ``db_name`` so we can DROP/RENAME atomically."""
    with superuser_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT pg_terminate_backend(pid)
              FROM pg_stat_activity
             WHERE datname = %s
               AND pid <> pg_backend_pid()
            """,
            (db_name,),
        )


def db_exists(db_name: str) -> bool:
    with superuser_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        return cur.fetchone() is not None


def create_database(db_name: str, owner_role: str) -> None:
    """Create an empty DB owned by ``owner_role`` (typically 'odoo')."""
    if db_exists(db_name):
        raise FileExistsError(f"Database '{db_name}' already exists")
    with superuser_connection() as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'").format(
                _quote_ident(db_name),
                _quote_ident(owner_role),
            )
        )


def drop_database(db_name: str) -> None:
    if not db_exists(db_name):
        return
    terminate_connections(db_name)
    with superuser_connection() as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(_quote_ident(db_name)))


def rename_database(old: str, new: str) -> None:
    if not db_exists(old):
        raise LookupError(old)
    if db_exists(new):
        raise FileExistsError(new)
    terminate_connections(old)
    with superuser_connection() as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
                _quote_ident(old),
                _quote_ident(new),
            )
        )


def install_extensions(db_name: str, extensions: list[str]) -> None:
    """Run CREATE EXTENSION IF NOT EXISTS on each extension inside the tenant DB."""
    with superuser_connection(db=db_name) as conn, conn.cursor() as cur:
        for ext in extensions:
            cur.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS {}").format(_quote_ident(ext)))


def apply_pdp_schema(db_name: str, schema_sql_path: str) -> None:
    """Apply ``02-pdp-schema.sql`` into a freshly created tenant DB.

    The init script in /docker-entrypoint-initdb.d only runs on first cluster
    bootstrap — subsequent tenant DBs need explicit application.
    """
    with open(schema_sql_path, encoding="utf-8") as f:
        body = f.read()
    with superuser_connection(db=db_name) as conn, conn.cursor() as cur:
        cur.execute(body)


def apply_roles(db_name: str, roles_sql_path: str) -> None:
    with open(roles_sql_path, encoding="utf-8") as f:
        body = f.read()
    with superuser_connection(db=db_name) as conn, conn.cursor() as cur:
        cur.execute(body)
