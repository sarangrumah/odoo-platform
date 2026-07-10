#!/usr/bin/env python3
"""Fill placeholder secrets in a .env file with strong generated values.

Idempotent: only replaces values that still contain the literal ``changeme``
(the placeholder marker the Odoo entrypoint fail-fasts on). Already-set values
and intentionally-empty external credentials (API keys, SMTP, S3, ACME, Vault)
are left untouched.

Secret types per key:
  * fernet  — 32-byte urlsafe base64 (44 chars), required by cryptography.Fernet
              for MASTER_WRAPPING_KEY and CORETAX_SERTEL_MASTER_KEY.
  * hex32   — openssl-style 64 hex chars for shared secrets / HMAC keys.
  * passwd  — 24-char alphanumeric, satisfies the >=16/12/8 length checks.

Usage:
  python3 scripts/gen-env-secrets.py [path/to/.env]   # default: ./.env
A timestamped backup (<file>.bak-YYYYmmdd_HHMMSS) is written before changes.
"""

from __future__ import annotations

import base64
import os
import secrets
import shutil
import string
import sys
from datetime import datetime

# key -> generator type
SECRET_TYPES = {
    # Fernet master keys (must be valid cryptography.Fernet keys)
    "MASTER_WRAPPING_KEY": "fernet",
    "CORETAX_SERTEL_MASTER_KEY": "fernet",
    # Shared secrets / HMAC (hex-32 = 64 hex chars, >= 32 length check)
    "GATEWAY_SHARED_SECRET": "hex32",
    "BAILEYS_SHARED_SECRET": "hex32",
    "STOREFRONT_HMAC_SECRET": "hex32",
    "ORCHESTRATOR_SHARED_SECRET": "hex32",
    # Passwords (24-char alnum; covers POSTGRES>=16, ODOO>=12, REDIS>=16, MINIO>=8)
    "POSTGRES_PASSWORD": "passwd",
    "REDIS_PASSWORD": "passwd",
    "ODOO_ADMIN_PASSWD": "passwd",
    "PG_ORCHESTRATOR_PASSWORD": "passwd",
    "MINIO_ROOT_PASSWORD": "passwd",
    "GRAFANA_ADMIN_PASSWORD": "passwd",
    "PGADMIN_PASSWORD": "passwd",
}


def gen(kind: str) -> str:
    if kind == "fernet":
        return base64.urlsafe_b64encode(os.urandom(32)).decode()
    if kind == "hex32":
        return secrets.token_hex(32)
    if kind == "passwd":
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(24))
    raise ValueError(kind)


def main(path: str) -> int:
    if not os.path.isfile(path):
        print(f"FATAL: {path} not found", file=sys.stderr)
        return 1
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()

    changed = []
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key not in SECRET_TYPES:
            continue
        # value is everything after the first '=' (env files: no inline comment on secrets)
        value = line.split("=", 1)[1]
        if "changeme" not in value:
            continue  # already set or intentionally empty -> leave it
        lines[i] = f"{key}={gen(SECRET_TYPES[key])}\n"
        changed.append(key)

    if not changed:
        print("No 'changeme' placeholders found — nothing to do.")
        return 0

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{path}.bak-{ts}"
    shutil.copy2(path, backup)
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    print(f"Backup: {backup}")
    print(f"Filled {len(changed)} secret(s): {', '.join(changed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ".env"))
