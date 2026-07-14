# Close the two unambiguous items from docs/levis/CONFIG_FOLLOWUPS.md.
# Run via odoo shell:  docker exec -i <odoo> odoo shell -d <db> --no-http < 72_fix_config_followups.py
#
#  1. custom_levis_localization.scrap_loss_account_code -> 7218000001 (Inventory write-off)
#     Empty until now, so validating a Scrap Batch raised instead of posting.
#
#  2. Fixed-asset group "Vehicles" -> accumulated-depreciation account 1205202000
#     The follow-up doc blamed a missing account. It is not missing: 1205202000
#     exists in the Erajaya chart. Only the mapping on the group was NULL, so
#     depreciation for vehicles could not post.
#
#  3. Depreciation journal on every asset group -> DEPRE.
#     Found while verifying (2): no group on any levis DB had default_journal_id,
#     so action_confirm() raised "depreciation journal must be set" for ALL six
#     categories, not just Vehicles. Land is skipped -- it is not depreciated.
#
# Deliberately NOT touched (needs a human decision, see the PR description):
#   - levis.mdr.bin        : needs the client's BIN/MDR table -> 73_load_mdr_bin.py
#   - go-live switches     : cron "poll SFTP feeds", x31/x48_post_enabled
#   - asset depreciation cron: still inactive on purpose; activating it posts
#     every due depreciation line at once.
#
# DRY by default. Set FIX_APPLY=1 to write.
import os

env = env  # noqa: F821 - provided by odoo shell

APPLY = os.environ.get("FIX_APPLY") == "1"
SCRAP_LOSS_CODE = "7218000001"
VEHICLES_ACCUM_DEP_CODE = "1205202000"

tag = "APPLY" if APPLY else "DRY"
log = lambda m: print(f"[{tag}] {m}")  # noqa: E731

# account.code is company-dependent on Odoo 19 -- always read it with_company,
# or the search silently misses.
company = env["res.company"].search([], limit=1)
Acc = env["account.account"].with_company(company)


def acc(code):
    a = Acc.search([("code", "=", code)], limit=1)
    if not a:
        raise SystemExit(f"FATAL: account {code} not found in {env.cr.dbname}")
    return a


changed = 0

# ------------------------------------------------- 1. scrap loss account code
Param = env["ir.config_parameter"].sudo()
KEY = "custom_levis_localization.scrap_loss_account_code"
current = (Param.get_param(KEY) or "").strip()

scrap_acc = acc(SCRAP_LOSS_CODE)
if scrap_acc.account_type != "expense":
    raise SystemExit(f"FATAL: {SCRAP_LOSS_CODE} is {scrap_acc.account_type}, expected 'expense'")

if current == SCRAP_LOSS_CODE:
    log(f"scrap_loss_account_code already = {SCRAP_LOSS_CODE} -- no change")
elif current:
    log(f"scrap_loss_account_code = {current!r} (already set to something else) -- LEFT ALONE")
else:
    log(f"scrap_loss_account_code: '' -> {SCRAP_LOSS_CODE} ({scrap_acc.name})")
    if APPLY:
        Param.set_param(KEY, SCRAP_LOSS_CODE)
    changed += 1

# ------------------------------------- 2. Vehicles accumulated depreciation
Group = env["custom.fixed.asset.group"]
veh = Group.search([("name", "ilike", "vehicle")], limit=1)

if not veh:
    log("no 'Vehicles' asset group on this DB -- skipped")
else:
    dep_acc = acc(VEHICLES_ACCUM_DEP_CODE)
    if veh.default_depreciation_account_id:
        have = veh.default_depreciation_account_id.with_company(company).code
        log(f"Vehicles accum-dep already = {have} -- no change")
    else:
        log(f"Vehicles accum-dep: (empty) -> {VEHICLES_ACCUM_DEP_CODE} ({dep_acc.name})")
        if APPLY:
            veh.default_depreciation_account_id = dep_acc.id
        changed += 1

# --------------------------------- 3. depreciation journal on asset groups
Journal = env["account.journal"]
dep_journal = Journal.search([("type", "=", "general"), ("code", "in", ("DEPRE", "DEPR"))], limit=1)
if not dep_journal:
    # rnd_levis and prd_levis_begbal already have one; prd_levis and
    # prd_detail_levis never got it. Create it rather than failing, so every
    # levis DB ends up with the same journal layout.
    log("no DEPRE journal -> creating it (type=general)")
    if APPLY:
        dep_journal = Journal.create(
            {
                "name": "Depreciation",
                "code": "DEPRE",
                "type": "general",
                "company_id": company.id,
            }
        )
    changed += 1

for g in Group.search([]):
    # Land is never depreciated -- it has no depreciation accounts, so it needs
    # no journal either. Leave it untouched rather than mapping a meaningless one.
    if not g.default_depreciation_account_id:
        log(f"asset group {g.name!r}: no depreciation account (not depreciated) -- skipped")
        continue
    if g.default_journal_id:
        log(f"asset group {g.name!r} journal already = {g.default_journal_id.code} -- no change")
        continue
    # in DRY the journal may not exist yet (we only logged that we'd create it)
    target = dep_journal.code if dep_journal else "DEPRE (to be created)"
    log(f"asset group {g.name!r} journal: (empty) -> {target}")
    if APPLY:
        g.default_journal_id = dep_journal.id
    changed += 1

# ------------------------------------------------------------------ summary
if APPLY and changed:
    env.cr.commit()
    log(f"committed {changed} change(s)")
elif APPLY:
    log("nothing to change -- already correct")
else:
    log(f"{changed} change(s) pending. Re-run with FIX_APPLY=1 to write.")
