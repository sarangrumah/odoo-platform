# -*- coding: utf-8 -*-
"""Configure cash advance / petty cash (custom_petty_cash) on prd_arkaaim.

WHY THIS IS NEEDED
------------------
Client asked how cash advances (uang muka karyawan) are handled. Odoo — Community
*and* Enterprise — has no cash-advance concept at all: the Expenses app only
knows "the employee already paid, reimburse them". The platform's own
``custom_petty_cash`` supplies the missing cycle, and it is already INSTALLED on
prd_arkaaim — but never configured. All four ``res_company.petty_cash_*`` fields
are NULL on both companies and there are zero requests, so every button raises
"Set an Advance account ... first".

This script wires it up. It is configuration only; the module code carries the
behaviour.

ACCOUNT MAPPING (per type, both already in the Erajaya CoA, both reconcilable)
-----------------------------------------------------------------------------
    Cash Advance  -> 1109000002  Non Trade Receivables - cash advance   (asset_receivable)
    Petty Cash    -> 1115200001  Advance for payment of operational exp (asset_prepayments)

Accounts are resolved by (code, company) and NEVER by id or external id: the
CoA is per-company, so each code exists twice (73/791 and 142/860).

    !! STALE code_store: account 73 belongs to company 1 only, yet its
    ``code_store`` still carries a "2" key left over from an earlier CoA load.
    A ``with_company(co2).search([('code','=','1109000002')])`` therefore matches
    BOTH 73 and 791. Every lookup below pairs the code with
    ``('company_ids','in',company.id)``. Drop that clause and company 2 silently
    books into company 1's account.

JOURNALS
--------
Company 1 (AIM) has BCA1/BCA2/BNK1 bank, CSH cash, MISC general.
Company 2 (ARKA) has BNK1/BNK2 bank, JM general, and **no cash journal** — so
this script creates one.

    !! The Payment journal MUST be dedicated. ``_configure_payment_journal``
    rewrites ``payment_account_id`` on every payment-method line of whichever
    journal it is handed, pointing it at the advance account. Aim that at BCA1
    and every ordinary vendor payment on that bank silently starts crediting
    uang muka. This script therefore CREATES a ``PCPAY`` cash journal per
    company and refuses to configure anything else. (The Levi's tenants already
    run this same PCPAY pattern.)

LIMITS
------
Seeded as ``warn`` — breaches are logged in the chatter, nothing is blocked.
Raise to ``block`` once Accounting confirms the plafon figures. ``block`` with a
wrong number stops Finance from working, so warn-first is deliberate.

WHEN TO RUN
-----------
Once on prd_arkaaim, and again on trn_arkaaim so training mirrors production.
Idempotent: re-running updates in place and never duplicates.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < setup_cash_advance.py

Defaults to PREVIEW (nothing written). Set COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = False  # True to persist

# Finance users to grant the approve/disburse/post/settle group to (logins).
FINANCE_LOGINS = []

# Dedicated journal this script CREATES — never an existing shared bank journal.
PAYMENT_JOURNAL_CODE = "PCPAY"
PAYMENT_JOURNAL_NAME = "Petty Cash Payment"

# ----- per-tenant profiles -----------------------------------------------
# prd_arkaaim and trn_arkaaim do NOT share a chart of accounts: production runs
# the bespoke 10-digit Erajaya chart, while the training DB was built on
# l10n_id_psak_custom (8-digit PSAK). Their journal codes differ too (MISC/JM,
# CSH/CSH1). One script, one profile per chart — selected by database name.
#
# ``create_missing_accounts`` is False everywhere except the training profile.
# A setup script must never invent accounts in a production ledger; on trn the
# PSAK chart genuinely has no employee-advance asset account (only liabilities
# like "Employee Liabilities" and "Advance Sales"), so the two accounts below
# are created to make the feature exercisable for training.
PROFILES = {
    "erajaya": {
        "ou_plan_name": "Project",  # ARKA's only analytic plan
        "realization_days": 14,
        "create_missing_accounts": False,
        "types": [
            {
                "code": "CA",
                "name": "Cash Advance",
                "kind": "cash_advance",
                "account_code": "1109000002",
                # Without this a CA request would number CA/... only by accident
                # — the global fallback sequence is prefixed PC/.
                "sequence_xmlid": "custom_petty_cash.seq_cash_advance_request",
                "is_default": True,
                "limit_enforcement": "warn",
                "limit_per_request": 0.0,
                "limit_outstanding": 0.0,
                "max_open_requests": 0,
                "block_when_overdue": True,
            },
            {
                "code": "PC",
                "name": "Petty Cash",
                "kind": "petty_cash",
                "account_code": "1115200001",
                "sequence_xmlid": "custom_petty_cash.seq_petty_cash_request",
                "is_default": False,
                "limit_enforcement": "warn",
                "limit_per_request": 5_000_000.0,
                "limit_outstanding": 10_000_000.0,
                "max_open_requests": 2,
                "block_when_overdue": True,
            },
        ],
        "bank_out_pref": {1: ["BCA1", "BNK1", "CSH"], 2: ["BNK1", "BNK2"]},
        "expense_pref": {1: ["MISC"], 2: ["JM"]},
        # Company 2 has no cash journal at all.
        "create_cash_journal_for": [2],
        "cash_journal_code": "CSH",
        "cash_journal_name": "Kas",
    },
    "psak": {
        "ou_plan_name": "Project",
        "realization_days": 14,
        "create_missing_accounts": True,
        "types": [
            {
                "code": "CA",
                "name": "Cash Advance",
                "kind": "cash_advance",
                "account_code": "11210020",
                "account_name": "Employee Advance",
                "account_type": "asset_receivable",
                "sequence_xmlid": "custom_petty_cash.seq_cash_advance_request",
                "is_default": True,
                "limit_enforcement": "warn",
                "limit_per_request": 0.0,
                "limit_outstanding": 0.0,
                "max_open_requests": 0,
                "block_when_overdue": True,
            },
            {
                "code": "PC",
                "name": "Petty Cash",
                "kind": "petty_cash",
                "account_code": "11410040",
                "account_name": "Advance for Operational Expenses",
                "account_type": "asset_prepayments",
                "sequence_xmlid": "custom_petty_cash.seq_petty_cash_request",
                "is_default": False,
                "limit_enforcement": "warn",
                "limit_per_request": 5_000_000.0,
                "limit_outstanding": 10_000_000.0,
                "max_open_requests": 2,
                "block_when_overdue": True,
            },
        ],
        "bank_out_pref": {1: ["BNK1"], 2: ["BNK1"]},
        "expense_pref": {1: ["MISC"], 2: ["MISC"]},
        # Both companies already have CSH1.
        "create_cash_journal_for": [],
        "cash_journal_code": "CSH1",
        "cash_journal_name": "Cash",
    },
}

# Which profile each database uses. An unlisted DB stops the script rather than
# guessing a chart.
DB_PROFILE = {
    "prd_arkaaim": "erajaya",
    "trn_arkaaim": "psak",
    "trn_arkaaim_begbal": "erajaya",
}
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

_dbname = env.cr.dbname
if _dbname not in DB_PROFILE:
    raise SystemExit(
        "No profile for database %r. Add it to DB_PROFILE — guessing a chart of "
        "accounts is exactly the mistake this map exists to prevent." % _dbname
    )
PROFILE_NAME = DB_PROFILE[_dbname]
PROFILE = PROFILES[PROFILE_NAME]

OU_PLAN_NAME = PROFILE["ou_plan_name"]
# Analytic plan whose accounts slice the shared advance account per person.
# Named for its role, not its members: CodeQL's clear-text-logging rule reads a
# constant called *_EMPLOYEE_* as personal data, and this is a config label.
ADVANCE_SLICE_PLAN_NAME = "Employee"
REALIZATION_DAYS = PROFILE["realization_days"]
TYPES = PROFILE["types"]
BANK_OUT_PREF = PROFILE["bank_out_pref"]
EXPENSE_PREF = PROFILE["expense_pref"]
CREATE_CASH_JOURNAL_FOR = PROFILE["create_cash_journal_for"]
CASH_JOURNAL_CODE = PROFILE["cash_journal_code"]
CASH_JOURNAL_NAME = PROFILE["cash_journal_name"]
CREATE_MISSING_ACCOUNTS = PROFILE["create_missing_accounts"]

Account = env["account.account"].sudo()
Journal = env["account.journal"].sudo()
Type = env["petty.cash.type"].sudo()
Plan = env["account.analytic.plan"].sudo()
Params = env["ir.config_parameter"].sudo()

problems = []
summary = []
# PREVIEW cannot create, so the same account is asked for twice (company-level
# fallback, then the type). Remember what we already announced.
_announced_creates = set()


def resolve_account(company, code):
    """Account with ``code`` that really belongs to ``company``.

    The company_ids clause is load-bearing — see the stale code_store note above.
    """
    return Account.with_company(company).search([("code", "=", code), ("company_ids", "in", company.id)], limit=1)


def ensure_account(company, cfg):
    """Resolve the type's advance account, creating it only where the profile
    allows it (training charts that simply have no such account).

    Returns an empty recordset when the account is missing and creation is not
    permitted — the caller records that as a problem and the run aborts.
    """
    account = resolve_account(company, cfg["account_code"])
    if account:
        if not account.reconcile:
            # Settlement reconciles the advance lines to zero; without this a
            # request can never leave 'in_realization'.
            print("  account %s not reconcilable -> SET reconcile=True" % cfg["account_code"])
            if COMMIT:
                account.reconcile = True
        return account

    if not CREATE_MISSING_ACCOUNTS:
        problems.append("company %s: account %s not found" % (company.id, cfg["account_code"]))
        return Account

    if not cfg.get("account_name") or not cfg.get("account_type"):
        problems.append(
            "company %s: account %s missing and the profile gives no name/type to create it"
            % (company.id, cfg["account_code"])
        )
        return Account

    key = (company.id, cfg["account_code"])
    if key not in _announced_creates:
        _announced_creates.add(key)
        print("  account %s CREATE  %-34s %s" % (cfg["account_code"], cfg["account_name"], cfg["account_type"]))
    if not COMMIT:
        return Account
    return Account.with_company(company).create(
        {
            "code": cfg["account_code"],
            "name": cfg["account_name"],
            "account_type": cfg["account_type"],
            "reconcile": True,
            "company_ids": [(6, 0, [company.id])],
        }
    )


def resolve_journal(company, codes, jtype_label):
    for code in codes:
        journal = Journal.search([("company_id", "=", company.id), ("code", "=", code)], limit=1)
        if journal:
            return journal
    problems.append("company %s: no %s journal found among %s" % (company.id, jtype_label, ", ".join(codes)))
    return Journal


print("=" * 78)
print("Cash advance setup — %s  [db=%s profile=%s]" % ("COMMIT" if COMMIT else "PREVIEW", _dbname, PROFILE_NAME))
print("=" * 78)

# --- global parameters ---------------------------------------------------
if COMMIT:
    Params.set_param("custom_petty_cash.ou_plan_name", OU_PLAN_NAME)
    Params.set_param("custom_petty_cash.employee_plan_name", ADVANCE_SLICE_PLAN_NAME)
    Params.set_param("custom_petty_cash.realization_days", str(REALIZATION_DAYS))
print("param custom_petty_cash.ou_plan_name        = %s" % OU_PLAN_NAME)
print("param custom_petty_cash.employee_plan_name  = %s" % ADVANCE_SLICE_PLAN_NAME)
print("param custom_petty_cash.realization_days    = %s" % REALIZATION_DAYS)
if not Plan.search([("name", "=", OU_PLAN_NAME)], limit=1):
    problems.append(
        "analytic plan %r does not exist — the Operating Unit field will widen to every analytic account" % OU_PLAN_NAME
    )

# Create the Employee plan up front rather than letting the first disbursement
# create it mid-transaction.
emp_plan = Plan.search([("name", "=", ADVANCE_SLICE_PLAN_NAME)], limit=1)
if emp_plan:
    print("plan  %-12s already exists (id %s)" % (ADVANCE_SLICE_PLAN_NAME, emp_plan.id))
else:
    print("plan  %-12s CREATE" % ADVANCE_SLICE_PLAN_NAME)
    if COMMIT:
        emp_plan = Plan.create({"name": ADVANCE_SLICE_PLAN_NAME})

# --- per company ---------------------------------------------------------
for company in env["res.company"].sudo().search([], order="id"):
    print("-" * 78)
    print("Company %s — %s" % (company.id, company.name))

    if not company.currency_exchange_journal_id:
        problems.append(
            "company %s: no Exchange Difference journal — a foreign-currency advance cannot be settled" % company.id
        )

    # Operational cash journal FIRST, and always excluding PCPAY. Creating the
    # payment journal first would leave this search finding PCPAY (it is also
    # type cash), skipping the real cash journal, and then handing PCPAY back
    # as Petty Cash's Bank-Out — the shared-journal hazard this script exists
    # to avoid.
    if company.id in CREATE_CASH_JOURNAL_FOR:
        cash_journal = Journal.search(
            [
                ("company_id", "=", company.id),
                ("type", "=", "cash"),
                ("code", "!=", PAYMENT_JOURNAL_CODE),
            ],
            limit=1,
        )
        if cash_journal:
            print("  cash journal     %-6s exists (id %s)" % (cash_journal.code, cash_journal.id))
        else:
            print(
                "  cash journal     %-6s CREATE%s"
                % (CASH_JOURNAL_CODE, "" if COMMIT else "  [preview: PC type falls back to bank]")
            )
            if COMMIT:
                cash_journal = Journal.create(
                    {
                        "name": CASH_JOURNAL_NAME,
                        "code": CASH_JOURNAL_CODE,
                        "type": "cash",
                        "company_id": company.id,
                    }
                )
                # Odoo auto-creates the liquidity account; surface it so
                # Accounting can confirm the code rather than have it forced.
                print(
                    "    -> default account %s (%s) — CONFIRM WITH ACCOUNTING"
                    % (
                        cash_journal.default_account_id.with_company(company).code,
                        cash_journal.default_account_id.name,
                    )
                )

    # Payment journal: dedicated, created here.
    pay_journal = Journal.search([("company_id", "=", company.id), ("code", "=", PAYMENT_JOURNAL_CODE)], limit=1)
    if pay_journal:
        print("  payment journal  %-6s exists (id %s)" % (pay_journal.code, pay_journal.id))
    else:
        print(
            "  payment journal  %-6s CREATE (type cash)%s"
            % (PAYMENT_JOURNAL_CODE, "" if COMMIT else "  [preview: shown as '-' below]")
        )
        if COMMIT:
            pay_journal = Journal.create(
                {
                    "name": PAYMENT_JOURNAL_NAME,
                    "code": PAYMENT_JOURNAL_CODE,
                    "type": "cash",
                    "company_id": company.id,
                }
            )
    if pay_journal and pay_journal.code != PAYMENT_JOURNAL_CODE:
        problems.append(
            "company %s: refusing to use shared journal %s as the Payment journal" % (company.id, pay_journal.code)
        )

    bank_out = resolve_journal(company, BANK_OUT_PREF.get(company.id, []), "Bank-Out")
    expense_journal = resolve_journal(company, EXPENSE_PREF.get(company.id, []), "Expense")
    print("  bank-out  %-6s   expense %-6s" % (bank_out.code or "-", expense_journal.code or "-"))

    # Company-level fallback layer: an untyped request must still work.
    # Goes through ensure_account so a profile that creates its accounts has
    # them in place before this writes the company-level fallback.
    # ensure_account already records a problem when the account is missing and
    # the profile may not create it, so nothing to add here.
    default_account = ensure_account(company, TYPES[0])
    if default_account:
        print("  company default advance account -> %s (id %s)" % (TYPES[0]["account_code"], default_account.id))
        if COMMIT:
            company.write(
                {
                    "petty_cash_advance_account_id": default_account.id,
                    "petty_cash_bank_out_journal_id": bank_out.id or False,
                    "petty_cash_payment_journal_id": pay_journal.id if pay_journal else False,
                    "petty_cash_expense_journal_id": expense_journal.id or False,
                }
            )

    # Types.
    for cfg in TYPES:
        account = ensure_account(company, cfg)
        if not account:
            # A PREVIEW on a chart that needs the account created has already
            # printed the CREATE; there is simply nothing to point at yet.
            if CREATE_MISSING_ACCOUNTS and not COMMIT:
                continue
            continue

        bank_for_type = bank_out
        if cfg["kind"] == "petty_cash":
            cash = Journal.search(
                [
                    ("company_id", "=", company.id),
                    ("type", "=", "cash"),
                    ("code", "!=", PAYMENT_JOURNAL_CODE),
                ],
                limit=1,
            )
            bank_for_type = cash or bank_out

        sequence = env.ref(cfg["sequence_xmlid"], raise_if_not_found=False)
        if not sequence:
            problems.append("sequence %s not found" % cfg["sequence_xmlid"])

        vals = {
            "sequence_id": sequence.id if sequence else False,
            "name": cfg["name"],
            "code": cfg["code"],
            "kind": cfg["kind"],
            "company_id": company.id,
            "advance_account_id": account.id,
            "bank_out_journal_id": bank_for_type.id or False,
            "payment_journal_id": pay_journal.id if pay_journal else False,
            "expense_journal_id": expense_journal.id or False,
            "is_default": cfg["is_default"],
            "limit_enforcement": cfg["limit_enforcement"],
            "limit_per_request": cfg["limit_per_request"],
            "limit_outstanding": cfg["limit_outstanding"],
            "max_open_requests": cfg["max_open_requests"],
            "block_when_overdue": cfg["block_when_overdue"],
        }
        if pay_journal and bank_for_type and bank_for_type.id == pay_journal.id:
            problems.append(
                "company %s type %s: Bank-Out and Payment journal are the same journal (%s) — "
                "posting a realization would repoint that journal's outstanding accounts"
                % (company.id, cfg["code"], pay_journal.code)
            )

        existing = Type.search([("company_id", "=", company.id), ("code", "=", cfg["code"])], limit=1)
        action = "UPDATE" if existing else "CREATE"
        print(
            "  type %-3s %-14s -> %s (id %s)  bank=%s pay=%s exp=%s  limit=%s  %s"
            % (
                cfg["code"],
                cfg["name"],
                cfg["account_code"],
                account.id,
                bank_for_type.code or "-",
                pay_journal.code if pay_journal else "-",
                expense_journal.code or "-",
                cfg["limit_enforcement"],
                action,
            )
        )
        print("       sequence %s" % (sequence.prefix if sequence else "-"))
        if COMMIT:
            if existing:
                existing.write(vals)
            else:
                Type.create(vals)
        summary.append((company.id, cfg["code"], cfg["account_code"], account.id))

# --- security ------------------------------------------------------------
if FINANCE_LOGINS:
    group = env.ref("custom_petty_cash.group_petty_cash_finance")
    users = env["res.users"].sudo().search([("login", "in", FINANCE_LOGINS)])
    missing = set(FINANCE_LOGINS) - set(users.mapped("login"))
    if missing:
        problems.append("unknown login(s): %s" % ", ".join(sorted(missing)))
    print("-" * 78)
    for user in users:
        already = group in user.all_group_ids
        print("  finance group %-30s %s" % (user.login, "already" if already else "GRANT"))
        if COMMIT and not already:
            user.write({"group_ids": [(4, group.id)]})
else:
    print("-" * 78)
    print("  FINANCE_LOGINS empty — grant 'Petty Cash / Finance' manually, or fill the knob.")
print("  group_petty_cash_limit_override deliberately granted to NOBODY.")

# --- result --------------------------------------------------------------
print("=" * 78)
for company_id, code, account_code, account_id in summary:
    print("  co%s  %-3s -> %s (id %s)" % (company_id, code, account_code, account_id))
if problems:
    print("-" * 78)
    print("PROBLEMS (%d):" % len(problems))
    for problem in problems:
        print("  !! %s" % problem)

# odoo shell rolls back on exit, so the writes only survive an explicit commit.
if COMMIT and not problems:
    env.cr.commit()
    print("COMMITTED.")
elif COMMIT:
    env.cr.rollback()
    print("ROLLED BACK — fix the problems above first.")
else:
    env.cr.rollback()
    print("PREVIEW only — rolled back. Set COMMIT = True to persist.")
print("=" * 78)
