# Reconcile the imported POS GL against the X24DN / X48 source workbooks (run via odoo shell).
#   docker exec -i odoo19-platform-odoo odoo shell -d demo_updated_levis --no-http \
#       < scripts/tenants/levis/45_verify_x24_tax_coa.py
#
# Checks, per the three defects fixed in custom_retail_import 19.0.0.6.0:
#   1. VAT Output equals the file's TAX AMOUNT column exactly (no per-line rounding drift).
#   2. Customer returns land on Sales Return-<category>, not on Gross Sales-<category>.
#   3. Discounts land on Sales Discount-<category> at the file's NET DISCOUNT AMOUNT,
#      booked verbatim (never divided by 1 + tax rate).
#
# Env:
#   X24_FILE / X48_FILE -> override the source workbook paths
#   VERIFY_TOL          -> absolute rupiah tolerance per check (default 0.01)
import os

import openpyxl

env = env  # noqa: F821  (injected by odoo shell)

X24_FILE = os.environ.get("X24_FILE", "/srv/sftp-share/files/data/X24DN_Retail_Sales_Detail_Report.xlsx")
X48_FILE = os.environ.get("X48_FILE", "/srv/sftp-share/files/data/X48_Customer_Return_Report.xlsx")
TOL = float(os.environ.get("VERIFY_TOL", "0.01"))

FOOTERS = ("grand total", "total", "sub total", "subtotal")
failures = []


def log(msg):
    print(msg, flush=True)


def cell(row, idx):
    return row[idx - 1] if len(row) >= idx else None


def data_rows(path, sku_col, header_rows=1):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    for i, row in enumerate(wb.active.iter_rows(values_only=True)):
        if i < header_rows:
            continue
        if not str(cell(row, sku_col) or "").strip():
            continue
        if str(cell(row, 1) or "").strip().lower() in FOOTERS:
            continue
        yield row


def check(label, expected, actual):
    ok = abs(expected - actual) <= TOL
    log("%-46s expected %18s  actual %18s  %s"
        % (label, "{:,.2f}".format(expected), "{:,.2f}".format(actual),
           "OK" if ok else "MISMATCH (%s)" % "{:,.2f}".format(actual - expected)))
    if not ok:
        failures.append(label)


# ---- 1. source-file totals -------------------------------------------------------
x24 = list(data_rows(X24_FILE, sku_col=14))
src_x24_tax = sum(float(cell(r, 29) or 0) for r in x24)
src_x24_net = sum(float(cell(r, 27) or 0) for r in x24)
src_x24_disc = sum(float(cell(r, 26) or 0) for r in x24)

x48 = list(data_rows(X48_FILE, sku_col=15))
src_x48_tax = sum(float(cell(r, 30) or 0) for r in x48)
src_x48_net = sum(float(cell(r, 29) or 0) for r in x48)

log("X24DN rows %d | net %s tax %s discount %s"
    % (len(x24), "{:,.0f}".format(src_x24_net), "{:,.0f}".format(src_x24_tax),
       "{:,.0f}".format(src_x24_disc)))
log("X48   rows %d | net %s tax %s\n"
    % (len(x48), "{:,.0f}".format(src_x48_net), "{:,.0f}".format(src_x48_tax)))


# ---- 2. GL totals ----------------------------------------------------------------
AML = env["account.move.line"]
company = env.company


def balance(domain):
    """Signed sum of `balance` over posted lines. Revenue is credit => negative."""
    lines = AML.search([("parent_state", "=", "posted"),
                        ("company_id", "=", company.id)] + domain)
    return sum(lines.mapped("balance"))


def by_name(pattern):
    return [("account_id.name", "ilike", pattern)]


# VAT Output: the sale tax's repartition account.
Tax = env["retail.import.executor"]._x24_resolve_tax()
if not Tax:
    log("!! no 11% sale tax resolved; skipping VAT check")
else:
    vat_accounts = Tax.invoice_repartition_line_ids.mapped("account_id")
    log("VAT account(s): %s" % ", ".join(vat_accounts.mapped("name")))
    vat = -balance([("account_id", "in", vat_accounts.ids)])
    # X24 tax is a credit (negative balance -> positive here); X48 tax is a debit.
    check("VAT Output (X24 sales + X48 returns)", src_x24_tax + src_x48_tax, vat)

# Sales Return-<cat>: debits, so balance is positive; the file's figures are negative.
ret = balance(by_name("sales return"))
check("Sum Sales Return-<category>", -src_x48_net, ret)

# Sales Discount-<cat>: debits (contra-revenue).
disc = balance(by_name("sales discount"))
check("Sum Sales Discount-<category>", src_x24_disc, disc)

# Gross Sales-<cat>: credits. After the discount gross-up it must equal
# the file's net sales + the file's discount. X48 returns no longer touch it.
gross = -balance(by_name("gross sales"))
check("Sum Gross Sales-<category>", src_x24_net + src_x24_disc, gross)


# ---- 3. per-category breakdown ---------------------------------------------------
log("\nPer-account detail:")
for pattern in ("gross sales", "sales discount", "sales return"):
    lines = AML.search([("parent_state", "=", "posted"),
                        ("company_id", "=", company.id)] + by_name(pattern))
    seen = {}
    for ln in lines:
        seen.setdefault(ln.account_id, 0.0)
        seen[ln.account_id] += ln.balance
    for account, bal in sorted(seen.items(), key=lambda kv: kv[0].code or ""):
        if abs(bal) < TOL:
            continue
        log("  %-12s %-46s %18s" % (account.code, account.name, "{:,.2f}".format(bal)))


# ---- 4. no bogus Grand Total transaction ------------------------------------------
bogus = env["retail.import.line"].search_count([("error_message", "ilike", "grand total")])
log("\nParked rows mentioning 'Grand Total': %d %s" % (bogus, "OK" if not bogus else "<-- footer row leaked"))
if bogus:
    failures.append("Grand Total footer row leaked into the import")

log("\n%s" % ("ALL CHECKS PASSED" if not failures else "FAILED: " + "; ".join(failures)))
