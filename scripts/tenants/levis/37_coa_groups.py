# Reconcile account.group with the EBR "CoA EBR & MAPPING" table (run via odoo shell).
#   docker exec -i odoo19-platform-odoo-mgmt odoo shell -d prd_levis_begbal --no-http \
#       < scripts/tenants/levis/37_coa_groups.py
#
# Why: Finance reads Balance Sheet / Profit & Loss grouped by account-code prefix
# (GROUP 1 = first digit, GROUP 2 = first two digits), not by Odoo's account_type.
# custom_accounting_reports now renders that hierarchy from account.group, but the
# rows the erajaya chart template seeded carry placeholder names ("Aset 11",
# "Beban Pokok 65") and include four subgroups the EBR mapping does not define --
# 30 / 55 / 75 / 88 / 89 all hold real EBR accounts, and leaving them in place
# would nest those accounts under a heading Finance never asked for. Group 54
# (Sales Loyalitas Pelanggan) is missing entirely although 10 accounts use it.
#
# Source of truth is the chart template's own CSV, so a fresh chart install and an
# existing database converge on the same 29 groups:
#     addons/ee_gap/l10n_erajaya/data/template/account.group-erajaya.csv
#
# account.account.group_id is a non-stored computed field (resolved from the code
# prefix), so nothing needs recomputing after this runs.
#
# Idempotent: re-running only rewrites values that already differ.
#
# Env flags:
#   RUN_DRY=1   -> report the diff, roll back instead of committing
import csv
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[groups] " + m)

DRY = os.environ.get("RUN_DRY") == "1"
CSV_PATH = os.environ.get(
    "GROUPS_CSV",
    "/mnt/extra-addons/ee_gap/l10n_erajaya/data/template/account.group-erajaya.csv",
)

with open(CSV_PATH) as handle:
    wanted = {row["code_prefix_start"]: row for row in csv.DictReader(handle)}
log("%s defines %d groups" % (CSV_PATH, len(wanted)))

Group = env["account.group"].with_context(active_test=False)
existing = {group.code_prefix_start: group for group in Group.search([])}

created = renamed = deleted = 0

for prefix, row in sorted(wanted.items()):
    group = existing.get(prefix)
    if not group:
        Group.create(
            {
                "code_prefix_start": row["code_prefix_start"],
                "code_prefix_end": row["code_prefix_end"],
                "name": row["name"],
            }
        )
        created += 1
        log("created %-3s %s" % (prefix, row["name"]))
    elif group.name != row["name"]:
        log("rename  %-3s %r -> %r" % (prefix, group.name, row["name"]))
        group.name = row["name"]
        renamed += 1

# Subgroups the mapping does not define. Their accounts belong directly under
# their GROUP 1 parent; an extra level here would show up as a phantom heading.
all_accounts = env["account.account"].search([])
stale = [group for prefix, group in existing.items() if prefix not in wanted]
for group in stale:
    prefix = group.code_prefix_start
    # ``group_id`` is computed, not stored -- count by prefix instead of search().
    accounts = sum(1 for acc in all_accounts if (acc.code or "").startswith(prefix))
    log(
        "delete  %-3s %r (%d accounts fall back to GROUP 1)"
        % (
            prefix,
            group.name,
            accounts,
        )
    )
    env["ir.model.data"].search([("model", "=", "account.group"), ("res_id", "=", group.id)]).unlink()
    group.unlink()
    deleted += 1

log("created=%d renamed=%d deleted=%d" % (created, renamed, deleted))

# Sanity: every posting account must resolve to a GROUP 1 (a two-digit group is
# optional -- the EBR mapping leaves several GROUP 2 cells blank on purpose).
orphans = [acc.code for acc in all_accounts if not acc.group_id]
if orphans:
    log("WARNING %d accounts have no group: %s" % (len(orphans), ", ".join(orphans[:10])))
else:
    log("every account resolves to a group")

if DRY:
    env.cr.rollback()
    log("RUN_DRY=1 -> rolled back")
else:
    env.cr.commit()
    log("committed")
