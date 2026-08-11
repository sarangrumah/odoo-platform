# Rolling out Roles and Operating Units to a tenant

**What this delivers:** administrators pick a *role* instead of ticking group
checkboxes, and data is scoped per *Operating Unit* — a store user sees and books
only their own store, an area manager several, head office everything.

**The one thing to internalise before you start:** none of this restricts anybody
until you assign Operating Units to users. Every record rule reads
`… if user.ou_is_scoped else [(1, '=', 1)]`, and `ou_is_scoped` is false for a
user with no unit. So the modules can be installed on a live tenant during
business hours; the moment that changes what people see is step 7, and only for
the users you name.

## Modules

| Module | Installs |
|---|---|
| `custom_role_manager` | manually |
| `custom_operating_unit` | manually |
| `custom_operating_unit_docs` | auto, wherever Accounting + Inventory are |
| `custom_operating_unit_pos` | auto, wherever Point of Sale is |
| `custom_operating_unit_reports` | auto, wherever `custom_accounting_reports` is |
| `custom_levis_operating_unit` | auto, on Levi's databases |

You install the first two; the bridges follow.

## Order, and why it is not negotiable

1. **`custom_operating_unit_reports` must be installed before any user is
   scoped.** The custom reports build raw SQL over `account_move_line`, and
   `ir.rule` does not apply to raw SQL. Until the bridge is in, a scoped user's
   list views are filtered and their Trial Balance is not — a leak with no
   symptoms. The bridge auto-installs, so in practice this means: do not assign
   units on a database where `custom_accounting_reports` is installed but the
   bridge somehow is not. Check it.
2. **Backfill before switching `include_untagged` off.** Historical documents
   carry no unit until the backfill runs. While `include_untagged` is `"1"` (the
   shipped default) a scoped user still sees them, which is what keeps history
   visible on day one.
3. **Assign units last.** That is the switch.

## Steps

### 0. Take a dump. Including the filestore

    docker exec -e PGPASSWORD=$PW odoo19-platform-postgres \
        pg_dump -U odoo -Fc <db> > /opt/db-backups/manual/<db>-pre-ou.dump
    tar czf /opt/db-backups/manual/<db>-filestore.tgz \
        -C /opt/odoo-platform/data/odoo-filestore/filestore <db>

The nightly dump is SQL only — no attachments. Note the **two** `filestore`
levels in that path; see `docs/runbooks/backup-restore.md`.

### 1. Sync the code to the runtime

`/home/odoo-erp/odoo-platform` is the development checkout;
`/opt/odoo-platform/addons` is what the containers mount. Copy, do not `git pull`
in `/opt`.

### 2. Install

    docker exec odoo19-platform-odoo-mgmt odoo \
        -d <db> -i custom_role_manager,custom_operating_unit \
        --stop-after-init

Fast: the bridges' `pre_init_hook` only adds empty, partially-indexed columns.
That hook is the reason this is safe — letting the ORM create a stored computed
column makes Odoo flag the whole table for recompute in one transaction, which on
a large `account_move_line` is an outage, not a delay.

Restart **both** Odoo containers afterwards, or a stale worker keeps serving the
old registry.

### 3. Create the Operating Units

**Levi's databases:** already done by the module's post-init. To re-run after new
stores appear:

    RUN_DRY=0 docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d <db> --no-http < scripts/tenants/levis/90_migrate_operating_unit.py

Additive and idempotent: it copies `stock.warehouse.code` into the unit and never
renames a warehouse, analytic account, journal or POS config.

**Other tenants:** create them in **Settings → Operating Units**, or script
`operating.unit._ensure(code, name, company, warehouse_id=…)`. Use the warehouse
code as the unit code — every backfill pass joins on the warehouse.

### 4. Backfill the history

Outside the `-u` window, so a slow table cannot hold locks through a restart:

    RUN_DRY=0 docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d <db> --no-http < scripts/ops/backfill_operating_unit.py
    # then, in psql:
    VACUUM (ANALYZE) account_move_line;

Batched and idempotent — an interrupted run is resumed by running it again.

### 5. Check coverage

    docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d <db> --no-http < scripts/ops/report_operating_unit_coverage.py

Read-only. Rows that legitimately have no unit (head-office payments, bank
statement lines) will stay at zero coverage — that is expected, and it is why
`include_untagged` stays `"1"`.

### 6. Assign roles

**Settings → Users → Security Roles** lists the shipped positions; the matrix is
in `docs/platform/role-matrix.md`. Assign from the user form (tab **Roles**) or in
bulk from the Users list (**Actions → Assign Roles**).

Roles only *add* rights at this stage. The engine revokes strictly what it
granted itself, so groups given by hand — or by the Keycloak mapping — survive.

### 7. Assign Operating Units — the switch

On each user's **Operating Units** tab:

- store staff → their store;
- area manager → the *area* unit (every store under it comes with it, and a new
  store added to that area needs no further action);
- head office → tick **All Operating Units**, or leave the assignment empty.

Do a handful first, have those people log in, then continue.

## Verifying

As a scoped user: Journal Entries, Transfers, POS Orders and Purchase Orders show
only their unit; Trial Balance and P&L-by-branch totals match that unit only;
saving a bill on another unit is refused with *"You are not allowed to book … on
Operating Unit …"*.

As head office: everything unchanged.

Machine paths — crons, the retail import, queue_job workers, POS closing — run
elevated and are unaffected. Run the daily import once and confirm.

## Tightening later (optional)

Once coverage reports zero:

    # Settings → Technical → System Parameters
    custom_operating_unit.include_untagged = 0

Documents with no unit then disappear for scoped users. Technically correct,
operationally alarming if coverage is not actually complete — hence the report.

## Rolling back

- **Un-scope everyone**: clear `operating_unit_ids` on the affected users, or
  grant them *All Operating Units*. Instant, no data change; this is the
  emergency lever.
- **Un-role a user**: clear `role_ids`; the engine gives back the groups it
  found before it first ran (`role_baseline_group_ids` on the user form).
- **Uninstalling** the modules drops the columns and the units. The analytic
  dimension, the warehouses and the journals are untouched by design, so Levi's
  reporting keeps working — but there is no reason to uninstall rather than
  un-scope.

## Known state

Verified 11-Aug-2026 on `tst_ou`, a clone of `rnd_levis`: 68 tests green, 24
active units migrated with zero renames, 2728 journal items and 5102 POS orders
backfilled.

Not yet rolled out to any production tenant.
