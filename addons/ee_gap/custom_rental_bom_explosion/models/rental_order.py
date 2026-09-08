# -*- coding: utf-8 -*-
"""Explode a rental bundle's BOM into the documents *and* the stock moves.

A bundle is rented as ONE line — "Sewa Drone Show 1500 Unit", qty 1 — because
that is how the deal is priced and how the PO reads. The physical reality
behind that line is 1500 serial-tracked drones plus their batteries and
controllers, and those units really do have to leave the shelf and really do
have to come back.

So the BOM is the bridge between the commercial line and the physical one:

* ``_prepare_move_vals_list`` emits one stock.move per exploded component, so
  a qty-1 bundle moves every unit it is made of. Without this the picking
  would move a single unit of the bundle product and the serial reconciliation
  on return would have nothing to check.
* ``_bast_lines_vals`` lists those same components on the handover document.

Both fall back to the un-exploded base behaviour when the rented product has
no BOM, so every existing non-bundle rental is untouched.
"""

from __future__ import annotations

from odoo import models


class RentalOrder(models.Model):
    _inherit = "rental.order"

    # ------------------------------------------------------------------
    # BOM resolution
    # ------------------------------------------------------------------
    def _resolve_bundle_bom(self):
        """Return the BOM backing this order's rented product, or empty.

        Serial mode delegates to ``rental.asset`` so an asset-level explicit
        ``bom_id`` still wins. Bulk mode resolves straight off the product,
        preferring a phantom (kit) BOM.
        """
        self.ensure_one()
        Bom = self.env["mrp.bom"].sudo()
        if self.asset_id:
            return self.asset_id._resolve_bom()
        product = self._resolve_rental_product()
        if not product:
            return Bom
        phantom = Bom.search(
            [
                ("product_tmpl_id", "=", product.product_tmpl_id.id),
                ("type", "=", "phantom"),
            ],
            limit=1,
        )
        if phantom:
            return phantom
        return Bom.search([("product_tmpl_id", "=", product.product_tmpl_id.id)], limit=1)

    def _explode_bundle(self, qty=1.0):
        """Return ``[{product, qty, uom}, ...]`` for ``qty`` bundles, or ``[]``.

        Empty list means "no BOM" and every caller reads that as "fall back to
        the plain single-product behaviour".
        """
        self.ensure_one()
        if self.asset_id:
            return self.asset_id._explode_components(qty=qty)
        bom = self._resolve_bundle_bom()
        product = self._resolve_rental_product()
        if not bom or not product:
            return []
        results = []
        try:
            _boms, lines = bom.explode(product, qty)
            for line, line_data in lines:
                results.append(
                    {
                        "product": line.product_id,
                        "qty": line_data.get("qty", line.product_qty),
                        "uom": line.product_uom_id or line.product_id.uom_id,
                    }
                )
        except Exception:
            # Fallback: direct line iteration (mirrors rental.asset behaviour).
            for line in bom.bom_line_ids:
                results.append(
                    {
                        "product": line.product_id,
                        "qty": line.product_qty * qty,
                        "uom": line.product_uom_id or line.product_id.uom_id,
                    }
                )
        return results

    # ------------------------------------------------------------------
    # Stock moves
    # ------------------------------------------------------------------
    def _prepare_move_vals_list(self, product, loc_src, loc_dst):
        """One move per exploded component instead of one move for the bundle.

        The spare/loan quantity is exploded too: ``loan_qty`` counts bundles,
        not units, so N spare bundles put N x each component on the picking
        flagged ``is_loan``.
        """
        self.ensure_one()
        components = self._explode_bundle(qty=float(self.qty or 1))
        if not components:
            return super()._prepare_move_vals_list(product, loc_src, loc_dst)

        moves = []
        for comp in components:
            comp_product = comp["product"]
            if not comp_product:
                continue
            moves.append(
                self._stock_move_vals(
                    comp_product,
                    comp["qty"],
                    loc_src,
                    loc_dst,
                    is_loan=False,
                    uom=comp["uom"],
                )
            )
        if self.loan_qty and self.loan_qty > 0:
            for comp in self._explode_bundle(qty=float(self.loan_qty)):
                comp_product = comp["product"]
                if not comp_product:
                    continue
                moves.append(
                    self._stock_move_vals(
                        comp_product,
                        comp["qty"],
                        loc_src,
                        loc_dst,
                        is_loan=True,
                        uom=comp["uom"],
                    )
                )
        return moves

    # ------------------------------------------------------------------
    # BAST lines
    # ------------------------------------------------------------------
    def _bast_lines_vals(self):
        """List the exploded components on the handover document.

        Base ``custom_rental`` already fills BAST lines at creation time, so
        overriding here (rather than appending after the fact) keeps a single
        code path and works for pickup and return alike.
        """
        self.ensure_one()
        components = self._explode_bundle(qty=float(self.qty or 1))
        if not components:
            return super()._bast_lines_vals()

        lines = []
        for comp in components:
            product = comp["product"]
            if not product:
                continue
            lines.append(
                {
                    "item_description": product.display_name,
                    "product_id": product.id,
                    "qty": float(comp["qty"]),
                    "uom_id": (comp["uom"] or product.uom_id).id,
                    "is_loan": False,
                    "condition": "good",
                }
            )
        if self.loan_qty and self.loan_qty > 0:
            for comp in self._explode_bundle(qty=float(self.loan_qty)):
                product = comp["product"]
                if not product:
                    continue
                lines.append(
                    {
                        "item_description": "[LOAN] " + product.display_name,
                        "product_id": product.id,
                        "qty": float(comp["qty"]),
                        "uom_id": (comp["uom"] or product.uom_id).id,
                        "is_loan": True,
                        "condition": "good",
                        "note": "Cadangan / loan unit — must be returned in full.",
                    }
                )
        return [(0, 0, v) for v in lines]

    # ------------------------------------------------------------------
    # Legacy hook
    # ------------------------------------------------------------------
    def _populate_bast_from_bom(self, bast):
        """Fill an EMPTY BAST from the bundle BOM.

        Kept for BAST documents created outside ``action_generate_bast_*``
        (which now get their lines from ``_bast_lines_vals`` at creation).
        Idempotent — skips a BAST that already has lines.
        """
        self.ensure_one()
        if not bast or bast.line_ids:
            return
        components = self._explode_bundle(qty=float(self.qty or 1))
        if not components:
            return
        Line = self.env["custom.bast.line"].sudo()
        seq = 10
        for comp in components:
            product = comp["product"]
            if not product:
                continue
            Line.create(
                {
                    "bast_id": bast.id,
                    "sequence": seq,
                    "item_description": product.display_name,
                    "product_id": product.id,
                    "qty": comp["qty"],
                    "uom_id": (comp["uom"] or product.uom_id).id,
                    "condition": "good",
                }
            )
            seq += 10
        bast.message_post(body="BAST lines auto-populated from bundle BOM.")

    def action_generate_bast_pickup(self):
        res = super().action_generate_bast_pickup()
        for rec in self:
            if rec.bast_pickup_id:
                rec._populate_bast_from_bom(rec.bast_pickup_id)
        return res

    def action_generate_bast_return(self):
        res = super().action_generate_bast_return()
        for rec in self:
            if rec.bast_return_id:
                rec._populate_bast_from_bom(rec.bast_return_id)
        return res
