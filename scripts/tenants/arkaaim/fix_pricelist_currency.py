# -*- coding: utf-8 -*-
"""Re-stamp the company "Default" pricelist to the company currency, and repair
the sales orders / draft invoices that inherited the wrong currency from it.

WHY THIS IS NEEDED
------------------
Client complaint: "sales order di ARKA-AIM pakai dollar, harusnya rupiah."

On prd_arkaaim every sales order of company 1 (PT Aero Inovasi Media) is
stamped USD even though the company currency is IDR and the figures typed by
the user are plainly rupiah ("Sewa Drone Show 1500 Unit" = 800.000.000).

The cause is a single data row. ``product_pricelist`` id 1 "Default", owned by
company 1, has ``currency_id = USD``. Core Odoo decides the order currency in
``sale/models/sale_order.py``::

    def _compute_currency_id(self):
        for order in self:
            order.currency_id = order.pricelist_id.currency_id or order.company_id.currency_id

— the pricelist wins over the company. Company 2 (ARKA)'s pricelist is already
IDR, which is why only AIM orders are affected.

That pricelist is USD because ``product`` creates ``product.list0`` at install
time in the then-current base currency (USD), while
``custom_arka_aim_seed/hooks.py`` only flips the company to IDR afterwards in
its post-init hook — and nothing ever re-stamps the pricelist. The hook is
patched separately so new ARKA tenants do not repeat this; this script repairs
the databases that already have it.

WHAT IS AND IS NOT WRONG
------------------------
Only the LABEL is wrong. The rupiah figures are correct and must NOT be
converted. Every ``price_unit`` / ``price_subtotal`` / ``amount_total`` has to
come out of this script byte-identical; the script asserts that and aborts if
anything moved.

The damage is in the derived company-currency values. On prd_arkaaim the draft
invoice of SO/AIM/2026/09/001 carries ``amount_total`` 120.000.000 "USD" and
``amount_total_signed`` 2.126.640.000.000 — posting it would add Rp 2,13
triliun to the general ledger.

Vendor bills in a genuine foreign currency (company 2 has USD purchases of
20.000 and 75.000) are NOT touched: this only realigns pricelists with their
own company's currency, and only rewrites records whose currency disagrees
with their company.

WHEN TO RUN
-----------
Once per affected ARKA database. Idempotent: a second run prints only OK lines
and changes nothing.

Posted moves are deliberately left alone — they are only reported. There are
none on prd_arkaaim; trn_arkaaim has some and is out of scope by decision.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d scratch_aimcur --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < fix_pricelist_currency.py

Defaults to PREVIEW (nothing written). Set COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = False  # True to persist
# Draft invoice lines sometimes sit on an account that was archived when the
# PSAK chart replaced the generic one. Any write to such a move is refused by
# ``_check_constrains_account_id_journal_id``, so the currency cannot be fixed
# until the account is. Leave this None to only REPORT those moves; set it to
# an account code once Accounting has confirmed which revenue account applies
# (on prd_arkaaim the precedent for drone-show revenue is 5122000000
# "Gross Sales-Rental Asset", used by the opening entry MISC/2026/05/0001).
REVENUE_ACCOUNT_CODE = None
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

Pricelist = env["product.pricelist"].sudo()
SaleOrder = env["sale.order"].sudo()
Move = env["account.move"].sudo()

companies = env["res.company"].sudo().search([], order="id")

print("=" * 78)
print("Pricelist currency alignment — %s" % ("COMMIT" if COMMIT else "PREVIEW"))
print("=" * 78)

changed = 0
failures = []


def money(val):
    return "{:,.2f}".format(val).replace(",", "_").replace(".", ",").replace("_", ".")


# ---------------------------------------------------------------- stage A --
# The pricelist itself. Only ever touched when it is EMPTY: a pricelist that
# carries fixed prices would silently reprice everything if its currency
# changed, so that case stops the script instead of guessing.
print("\n--- A. product.pricelist vs company currency " + "-" * 33)
for company in companies:
    lists = Pricelist.with_company(company).search([("company_id", "=", company.id)])
    for pl in lists:
        want = company.currency_id
        if pl.currency_id == want:
            print("OK    pricelist %-3s %-20s company %s: already %s" % (pl.id, pl.display_name, company.id, want.name))
            continue
        if pl.item_ids:
            msg = "pricelist %s has %d price rule(s) — changing its currency would reprice them; fix by hand" % (
                pl.id,
                len(pl.item_ids),
            )
            print("ABORT %s" % msg)
            failures.append(msg)
            continue
        print(
            "SET   pricelist %-3s %-20s company %s: %s -> %s (0 price rules)"
            % (pl.id, pl.display_name, company.id, pl.currency_id.name, want.name)
        )
        if COMMIT:
            pl.currency_id = want.id
        changed += 1

# ---------------------------------------------------------------- stage B --
# Sales orders already stamped with the old currency. sale.order.currency_id is
# compute+store with @api.depends('pricelist_id', 'company_id') — it does NOT
# depend on pricelist_id.currency_id, so stage A alone leaves existing orders
# untouched. Force the recompute, then prove no amount moved.
print("\n--- B. sale.order currency re-stamp " + "-" * 42)
for company in companies:
    orders = SaleOrder.search(
        [
            ("company_id", "=", company.id),
            "|",
            ("currency_id", "!=", company.currency_id.id),
            ("order_line.currency_id", "!=", company.currency_id.id),
        ],
        order="id",
    )
    if not orders:
        print("OK    company %s (%s): no mis-stamped sale orders" % (company.id, company.name))
        continue

    before = {o.id: (o.name, o.state, o.amount_untaxed, o.amount_tax, o.amount_total) for o in orders}
    for oid, (name, state, unt, tax, tot) in before.items():
        print(
            "SET   SO %-4s %-22s %-6s total %s (was %s)"
            % (oid, name, state, money(tot), orders.browse(oid).currency_id.name)
        )

    if COMMIT:
        env.add_to_compute(SaleOrder._fields["currency_id"], orders)
        env.add_to_compute(SaleOrder._fields["currency_rate"], orders)
        orders.flush_recordset()
        # sale.order.line.currency_id is related='order_id.currency_id' with
        # store=True, and add_to_compute writes the order field WITHOUT marking
        # its dependents dirty — so the lines keep the old currency and the
        # order still shows USD per line in the form view even though the header
        # is right. modified() is what propagates to the stored dependents.
        orders.modified(["currency_id"])
        orders.order_line.flush_recordset()
        env.invalidate_all()

        for order in orders:
            name, state, unt, tax, tot = before[order.id]
            if (order.amount_untaxed, order.amount_tax, order.amount_total) != (unt, tax, tot):
                msg = (
                    "SO %s (%s): amounts moved %s/%s/%s -> %s/%s/%s — the figures must "
                    "NOT change, only the currency label"
                    % (order.id, name, unt, tax, tot, order.amount_untaxed, order.amount_tax, order.amount_total)
                )
                print("FAIL  %s" % msg)
                failures.append(msg)
            elif order.currency_id != company.currency_id:
                msg = "SO %s (%s): still %s after recompute" % (order.id, name, order.currency_id.name)
                print("FAIL  %s" % msg)
                failures.append(msg)
            elif order.order_line.filtered(lambda l: l.currency_id != order.currency_id):
                msg = "SO %s (%s): %d order line(s) still on the old currency" % (
                    order.id,
                    name,
                    len(order.order_line.filtered(lambda l: l.currency_id != order.currency_id)),
                )
                print("FAIL  %s" % msg)
                failures.append(msg)
            else:
                print(
                    "      SO %-4s %-22s now %s rate %s, %d line(s) aligned, "
                    "total unchanged %s"
                    % (
                        order.id,
                        name,
                        order.currency_id.name,
                        order.currency_rate,
                        len(order.order_line),
                        money(order.amount_total),
                    )
                )
    changed += len(orders)

# ---------------------------------------------------------------- stage C --
# Draft invoices carrying the old currency. Draft moves recompute their lines'
# balance from the move currency, so re-stamping is enough — but that is
# verified, not assumed. Posted moves are only reported.
#
# A move whose line sits on an ARCHIVED account cannot be written at all (core
# raises "The account ... is archived." on every write), so it is reported as
# BLOCKED rather than silently skipped — and it does not roll back stages A/B,
# which are what actually stops new bad invoices from being created.
print("\n--- C. account.move currency re-stamp " + "-" * 40)
blocked = []
for company in companies:
    moves = Move.search(
        [
            ("company_id", "=", company.id),
            ("currency_id", "!=", company.currency_id.id),
        ],
        order="id",
    )

    posted = moves.filtered(lambda m: m.state != "draft")
    for m in posted:
        # A genuine foreign-currency purchase looks exactly like this, so never
        # touch it — just make it visible.
        print(
            "SKIP  move %-4s %-22s %-11s %s %s (posted; left as-is)"
            % (m.id, m.name or "(no number)", m.move_type, m.currency_id.name, money(m.amount_total))
        )

    drafts = moves - posted
    if not drafts:
        if not posted:
            print("OK    company %s (%s): no mis-stamped moves" % (company.id, company.name))
        continue

    replacement = None
    if REVENUE_ACCOUNT_CODE:
        replacement = (
            env["account.account"].sudo().with_company(company).search([("code", "=", REVENUE_ACCOUNT_CODE)], limit=1)
        )
        if not replacement:
            msg = "REVENUE_ACCOUNT_CODE %s not found in company %s" % (REVENUE_ACCOUNT_CODE, company.id)
            print("FAIL  %s" % msg)
            failures.append(msg)
            continue
        if not replacement.active:
            msg = "REVENUE_ACCOUNT_CODE %s is itself archived" % REVENUE_ACCOUNT_CODE
            print("FAIL  %s" % msg)
            failures.append(msg)
            continue

    for m in drafts:
        stale = m.line_ids.filtered(lambda l: l.account_id and not l.account_id.active)
        print(
            "SET   move %-4s %-22s %-11s %s %s  signed %s -> expect %s"
            % (
                m.id,
                m.name or "(no number)",
                m.move_type,
                m.currency_id.name,
                money(m.amount_total),
                money(m.amount_total_signed),
                money(m.amount_total),
            )
        )

        if stale and not replacement:
            for line in stale:
                print(
                    "BLKD    line %s %r sits on ARCHIVED account %s (%s) — the move "
                    "cannot be written until this is repointed"
                    % (line.id, line.name, line.account_id.code, line.account_id.display_name)
                )
            blocked.append(m.id)
            continue

        if not COMMIT:
            continue

        total_before = m.amount_total
        for line in stale:
            print(
                "      line %s: account %s -> %s (%s)"
                % (line.id, line.account_id.code, replacement.code, replacement.display_name)
            )
            line.account_id = replacement.id
        m.currency_id = company.currency_id.id
        # move.invoice_currency_rate is a stored compute that @api.depends on
        # currency_id, so it drops to 1 by itself. The line balance does not: it
        # only follows through the onchange core uses in the form view. Call that
        # same method rather than hand-computing, so the result is identical to
        # what a user editing the invoice in the UI would get. Its first branch is
        # exactly our case — currency now equals the company currency, so
        # balance := amount_currency.
        m.line_ids._inverse_amount_currency()
        m.line_ids.flush_recordset()
        env.invalidate_all()

        bad = m.line_ids.filtered(lambda l: l.balance != l.amount_currency)
        if m.amount_total != total_before:
            msg = "move %s: amount_total moved %s -> %s" % (m.id, total_before, m.amount_total)
        elif m.amount_total_signed != m.amount_total:
            msg = (
                "move %s: amount_total_signed %s != amount_total %s — the balance "
                "did not follow the currency; do NOT patch this in SQL, delete the "
                "draft and regenerate it from the sales order instead" % (m.id, m.amount_total_signed, m.amount_total)
            )
        elif bad:
            msg = "move %s: %d line(s) still have balance != amount_currency" % (m.id, len(bad))
        else:
            msg = None

        if msg:
            print("FAIL  %s" % msg)
            failures.append(msg)
        else:
            print(
                "      move %-4s now %s, total %s, signed %s, balances aligned"
                % (m.id, m.currency_id.name, money(m.amount_total), money(m.amount_total_signed))
            )
    changed += len(drafts) - len([m for m in drafts if m.id in blocked])

print("\n" + "-" * 78)
print("%d record(s) %s" % (changed, "updated" if COMMIT else "would change"))
if blocked:
    print(
        "!! %d draft move(s) BLOCKED by an archived account and left untouched: %s"
        % (len(blocked), ", ".join(str(i) for i in blocked))
    )
    print("   Confirm the revenue account with Accounting, set REVENUE_ACCOUNT_CODE,")
    print("   and re-run. Stages A and B above are unaffected.")

# odoo shell rolls back on exit, so the write only survives an explicit commit.
if failures:
    print("!! %d FAILURE(S) — rolling back, nothing persisted:" % len(failures))
    for f in failures:
        print("   - %s" % f)
    env.cr.rollback()
    print("ROLLED BACK.")
elif COMMIT:
    env.cr.commit()
    print("COMMITTED.")
else:
    env.cr.rollback()
    print("PREVIEW only — rolled back. Set COMMIT = True to persist.")
print("=" * 78)
