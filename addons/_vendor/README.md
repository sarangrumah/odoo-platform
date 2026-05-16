# `_vendor/` — vendored OCA modules

Third-party Odoo modules from the [OCA](https://github.com/OCA) (Odoo Community
Association) are vendored here as plain folders rather than git submodules,
because this repo is not (yet) a git repository.

## What is vendored

| Module                | OCA repo          | Used for                                              |
| --------------------- | ----------------- | ----------------------------------------------------- |
| `queue_job`           | `OCA/queue`       | Async job runner, loaded as `server_wide_module`      |
| `auth_jwt`            | `OCA/server-auth` | JWT auth provider, used by future REST endpoints      |
| `base_rest`           | `OCA/rest-framework` | Declarative REST controller framework              |
| `base_rest_auth_jwt`  | `OCA/rest-framework` | Glue between `base_rest` and `auth_jwt`            |
| `mail_tracking`       | `OCA/social`      | Email open / bounce / failure tracking                |
| `partner_firstname`   | `OCA/partner-contact` | Split `name` into `firstname` / `lastname`        |

Source URL pattern:
`https://github.com/OCA/<repo>/archive/refs/heads/<branch>.tar.gz`

Primary branch attempted: **`19.0`**. Fallback: **`18.0`** (because OCA usually
lags an Odoo major release by several months and Odoo 19 was released
2025-10). Any module fetched from `18.0` will contain a `NEEDS_19_PORT.md`
marker file at the root of its folder; review and re-vendor once the OCA port
is published.

### Branch availability snapshot (probed 2026-05-16)

| Module               | Available on `19.0`? | Action                                       |
| -------------------- | -------------------- | -------------------------------------------- |
| `queue_job`          | yes                  | vendored from 19.0                           |
| `auth_jwt`           | no                   | falls back to 18.0 (NEEDS_19_PORT.md)        |
| `base_rest`          | yes                  | vendored from 19.0                           |
| `base_rest_auth_jwt` | no                   | falls back to 18.0 (NEEDS_19_PORT.md)        |
| `mail_tracking`      | no                   | falls back to 18.0 (NEEDS_19_PORT.md)        |
| `partner_firstname`  | yes                  | vendored from 19.0                           |

## How to (re-)fetch

Requires `bash` (Git-Bash on Windows is fine), `curl`, and `tar`:

```bash
bash addons/_vendor/fetch_oca.sh
```

To force a different branch:

```bash
OCA_BRANCH=18.0 bash addons/_vendor/fetch_oca.sh
```

The script:

1. Downloads each repo's branch tarball into a temp dir.
2. Copies the requested module subfolders into `addons/_vendor/`.
3. Falls back to `18.0` per-repo if `19.0` is unavailable, and drops a
   `NEEDS_19_PORT.md` inside the module folder.
4. Prints a summary of which modules came from which branch.

## Wiring into Odoo

The Odoo container's `addons_path` already includes `/mnt/extra-addons/_vendor`
(see `odoo/odoo.conf.tmpl`). To make `queue_job` start at server boot, the
`SERVER_WIDE_MODULES` env var includes `queue_job`:

```
SERVER_WIDE_MODULES=base,web,queue_job
```

(set in `.env.example` and `.env`).

After fetching the modules and (re)starting the stack, install them from the
Odoo Apps menu — only `queue_job` needs to be loaded server-wide; the rest are
ordinary addons installed per-database.

## License

Each OCA module retains its original license (typically AGPL-3 or LGPL-3).
See the `LICENSE` file inside each module folder.
