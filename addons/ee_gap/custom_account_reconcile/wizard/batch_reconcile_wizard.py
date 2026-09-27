# -*- coding: utf-8 -*-
"""Clearing massal untuk akun dengan ribuan baris terbuka (sheet #61).

The complaint is precise: *"data gr/ir ribuan sehingga odoo stuck saat akan di
proses"*. Two separate things hang, and both are fixed here.

1. ``reconcile.overview.action_open_lines`` opened an **unbounded** list. On
   ``prd_levis_begbal`` that was 63,240 lines for one account; even after the
   GR/IR netting landed it is still 7,314. The action now carries a limit.
2. The existing ``custom.account.reconcile.wizard`` loads every selected line
   into ``line_ids`` as a ``Command.set``. Selecting thousands of lines is what
   actually freezes the browser. **This wizard holds no lines at all** — it
   works from a domain and reports counts.

🔴 **Scope is mandatory, and it is not cosmetic.** Plain FIFO over this data
settles to about three open lines, which means 7,314 lines would be tied into
**one** ``account.full.reconcile``: quadratic to create, and a nightmare the
first time anybody resets one of those entries to draft. Grouping by partner or
by month keeps each reconciliation the size of a real business event.

The run is synchronous but bounded by ``max_groups``: a wizard that commits in a
loop is how you get a half-finished ledger and no way to tell. Run it again to
continue — the groups already closed are simply no longer open.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools.fifo import match_fifo


class BatchReconcileWizard(models.TransientModel):
    _name = "custom.account.reconcile.batch.wizard"
    _description = "Clearing Massal"

    account_id = fields.Many2one(
        "account.account",
        string="Account",
        required=True,
        domain="[('reconcile', '=', True)]",
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    date_to = fields.Date(string="Sampai Tanggal", required=True, default=fields.Date.context_today)
    partner_id = fields.Many2one("res.partner", string="Partner", help="Opsional; kosong = semua partner.")
    scope = fields.Selection(
        [("partner", "Per Partner"), ("month", "Per Bulan"), ("partner_month", "Per Partner per Bulan")],
        string="Kelompokkan",
        default="partner_month",
        required=True,
        help="Satu rekonsiliasi dibuat per kelompok. Tanpa pengelompokan, "
        "ribuan baris terikat menjadi satu full reconcile raksasa.",
    )
    max_groups = fields.Integer(
        string="Maksimal Kelompok",
        default=200,
        required=True,
        help="Batas per jalan. Jalankan lagi untuk melanjutkan.",
    )
    dry_run = fields.Boolean(string="Simulasi saja", default=True)

    open_lines = fields.Integer(string="Baris terbuka", readonly=True)
    group_count = fields.Integer(string="Kelompok", readonly=True)
    matched_lines = fields.Integer(string="Baris ter-match", readonly=True)
    matched_amount = fields.Monetary(string="Nilai ter-match", readonly=True, currency_field="currency_id")
    remaining_lines = fields.Integer(string="Sisa terbuka", readonly=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    result_note = fields.Text(readonly=True)

    # ------------------------------------------------------------------
    def _line_domain(self):
        self.ensure_one()
        domain = [
            ("account_id", "=", self.account_id.id),
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("date", "<=", self.date_to),
        ]
        if self.partner_id:
            domain.append(("partner_id", "=", self.partner_id.id))
        return domain

    def _group_key(self, line):
        self.ensure_one()
        partner = line.partner_id.id or 0
        month = line.date.strftime("%Y-%m") if line.date else ""
        if self.scope == "partner":
            return (partner,)
        if self.scope == "month":
            return (month,)
        return (partner, month)

    @api.onchange("account_id", "date_to", "partner_id")
    def _onchange_preview(self):
        for wizard in self:
            if not wizard.account_id:
                wizard.open_lines = 0
                continue
            wizard.open_lines = self.env["account.move.line"].search_count(wizard._line_domain())

    # ------------------------------------------------------------------
    def action_run(self):
        self.ensure_one()
        if not self.account_id.reconcile:
            raise UserError(_("Account %s does not allow reconciliation.", self.account_id.display_name))
        AML = self.env["account.move.line"]
        lines = AML.search(self._line_domain(), order="date, id")
        self.open_lines = len(lines)

        groups = {}
        for line in lines:
            key = self._group_key(line)
            groups[key] = groups.get(key, AML) | line
        self.group_count = len(groups)

        currency = self.company_id.currency_id
        matched_lines = 0
        matched_amount = 0.0
        touched_groups = 0
        skipped_single_sided = 0

        for key in sorted(groups, key=lambda k: tuple(str(part) for part in k)):
            if touched_groups >= self.max_groups:
                break
            group = groups[key]
            debits = [(line.id, line.amount_residual) for line in group if line.amount_residual > 0]
            credits = [(line.id, -line.amount_residual) for line in group if line.amount_residual < 0]
            if not debits or not credits:
                # Nothing to net: a one-sided group is a real open position,
                # not a reconciliation waiting to happen.
                skipped_single_sided += 1
                continue
            pairs = match_fifo(debits, credits, tolerance=currency.rounding / 2 or 0.005)
            if not pairs:
                continue
            touched_groups += 1
            ids = {pair[0] for pair in pairs} | {pair[1] for pair in pairs}
            matched_lines += len(ids)
            matched_amount += sum(pair[2] for pair in pairs)
            if not self.dry_run:
                AML.browse(sorted(ids)).reconcile()

        if self.dry_run:
            self.remaining_lines = self.open_lines - matched_lines
        else:
            self.env.flush_all()
            self.remaining_lines = AML.search_count(self._line_domain())

        self.matched_lines = matched_lines
        self.matched_amount = matched_amount
        self.result_note = _(
            "%(mode)s — %(groups)s kelompok diproses dari %(total)s; "
            "%(single)s kelompok satu sisi dilewati (posisi terbuka yang sah).\n"
            "%(matched)s baris ter-match, sisa %(remaining)s baris terbuka.%(more)s",
            mode=_("SIMULASI") if self.dry_run else _("DIJALANKAN"),
            groups=touched_groups,
            total=self.group_count,
            single=skipped_single_sided,
            matched=matched_lines,
            remaining=self.remaining_lines,
            more=_("\nBatas kelompok tercapai — jalankan lagi untuk melanjutkan.")
            if touched_groups >= self.max_groups
            else "",
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": self.env.context,
        }
