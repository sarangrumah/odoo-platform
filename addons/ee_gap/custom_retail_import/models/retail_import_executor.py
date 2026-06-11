# -*- coding: utf-8 -*-
"""Retail import executor — turns parsed rows into Odoo records, per file type.

This is the business logic behind ``retail.import.wizard`` / ``retail.import.feed``.
Each ``_load_<type>`` method consumes the dicts produced by
``retail.import.profile.read_records`` and writes Odoo records with batched
commits + ``ir.model.data`` external IDs (under ``profile.namespace``) for
idempotency.

Coverage:
  x101         — FULL. Port of the proven era_busana 2-script pipeline (products).
  coa          — FULL. account.account from a clean code/name/account_type file.
  company      — FULL. res.company / its partner from the SES legal-entity sheet.
  x20          — FULL. stock.quant opening on-hand (one-shot, guarded).
  x24          — POS sales -> pos.order (no stock move). Needs pos.config + session
                 + payment methods to exist; fails loudly with guidance otherwise.
  x70d         — pos.payment, joined to x24 orders by (store,date,register,trans).
  x70t/x31/x32p/store_master — STAGED: parsed, counted, attachment kept; no model
                 writes yet (reference/decision-gated per plan Phase 3/5). Warehouse
                 creation is done by the Track A odoo-shell loader.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BATCH = 200


class RetailImportExecutor(models.AbstractModel):
    _name = "retail.import.executor"
    _description = "Retail Import Executor"

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    def run(self, log):
        """Process the file stored on ``log`` (an ir.attachment). Updates counters
        + state on the log. Returns the log."""
        log.ensure_one()
        profile = log.profile_id
        file_b64 = log.source_b64()
        if not file_b64:
            log.write({"state": "failed", "error_message": "No stored source file on log."})
            return log
        log.state = "running"
        self.env.cr.commit()
        handler = getattr(self, f"_load_{profile.file_type}", None)
        if handler is None:
            log.write(
                {"state": "failed", "error_message": f"No executor for file_type {profile.file_type!r}."}
            )
            return log
        try:
            handler(profile, file_b64, log)
        except UserError:
            self.env.cr.rollback()
            raise
        except Exception as e:  # pragma: no cover - defensive
            self.env.cr.rollback()
            _logger.exception("Retail import failed (log %s)", log.id)
            log.write({"state": "failed", "error_message": str(e)})
            self.env.cr.commit()
            return log
        if log.state == "running":
            log.state = "partial" if log.error_count else "imported"
        self.env.cr.commit()
        return log

    # ------------------------------------------------------------------
    # External-ID helpers (idempotency)
    # ------------------------------------------------------------------
    def _xid_get(self, namespace, name, model):
        ext = self.env["ir.model.data"].search(
            [("module", "=", namespace), ("name", "=", name), ("model", "=", model)], limit=1
        )
        return ext.res_id if ext else False

    def _xid_set(self, namespace, name, model, res_id):
        self.env["ir.model.data"].create(
            {"module": namespace, "name": name, "model": model, "res_id": res_id, "noupdate": True}
        )

    @staticmethod
    def _safe_xid(prefix, value):
        return prefix + "".join(c if c.isalnum() else "_" for c in str(value)).upper()

    # ==================================================================
    # X101 — Products (categories / attributes / templates / variants)
    # ==================================================================
    def _load_x101(self, profile, file_b64, log):
        ns = profile.namespace
        data = profile.read_records(file_b64)
        records = data["records"]
        log.line_count = len(records)

        # ---- aggregate (mirror of 01_extract_x101.py) ----
        sku_best = {}  # sku -> (eff, dict)
        tmpl_meta = {}  # code -> dict
        sizes, inseams = set(), set()
        tmpl_variants = defaultdict(set)
        for r in records:
            pc = r.get("product_code")
            sku = r.get("sku")
            if not pc or not sku:
                continue
            size = (r.get("size") or "").strip()
            inseam_raw = r.get("inseam")
            inseam = (str(inseam_raw).strip() if inseam_raw not in (None, "-", "") else "")
            gtin = str(r.get("gtin") or "").strip()
            retail = float(profile._parse_amount(r.get("retail_price")))
            eff = profile._parse_date(r.get("price_eff")) or None

            prev = sku_best.get(sku)
            prev_eff = prev[0] if prev else None
            if prev is None or (eff and (prev_eff is None or eff > prev_eff)):
                sku_best[sku] = (eff, {"sku": sku, "tmpl_code": pc, "size": size, "inseam": inseam, "gtin": gtin})

            m = tmpl_meta.get(pc)
            if m is None or (eff and (m.get("eff") is None or eff > m["eff"])):
                tmpl_meta[pc] = {
                    "code": pc,
                    "name": (r.get("description") or pc),
                    "cat": (r.get("category") or "").strip(),
                    "cls": (r.get("klass") or "").strip(),
                    "subcls": (r.get("subclass") or "").strip(),
                    "retail": retail,
                    "eff": eff,
                }
            tmpl_variants[pc].add((size, inseam))
            if size:
                sizes.add(size)
            if inseam:
                inseams.add(inseam)

        _logger.info(
            "x101: %s rows -> %s templates, %s skus, %s sizes, %s inseams",
            len(records), len(tmpl_meta), len(sku_best), len(sizes), len(inseams),
        )

        # ---- categories (3-level) ----
        def cat_xid(name):
            return self._safe_xid("cat_l1_", name)

        def cls_xid(cat, cls):
            return self._safe_xid("cat_l2_", f"{cat}_{cls}")

        def sub_xid(cat, cls, sub):
            return self._safe_xid("cat_l3_", f"{cat}_{cls}_{sub}")

        xid_to_cat = {}
        # build the parent->child sequence
        l1 = {m["cat"] for m in tmpl_meta.values() if m["cat"]}
        l2 = {(m["cat"], m["cls"]) for m in tmpl_meta.values() if m["cat"] and m["cls"]}
        l3 = {(m["cat"], m["cls"], m["subcls"]) for m in tmpl_meta.values() if m["cat"] and m["cls"] and m["subcls"]}
        for c in sorted(l1):
            xid = cat_xid(c)
            rid = self._xid_get(ns, xid, "product.category")
            if not rid:
                rid = self.env["product.category"].create({"name": c}).id
                self._xid_set(ns, xid, "product.category", rid)
            xid_to_cat[xid] = rid
        for cat, cls in sorted(l2):
            xid = cls_xid(cat, cls)
            rid = self._xid_get(ns, xid, "product.category")
            if not rid:
                rid = self.env["product.category"].create(
                    {"name": cls, "parent_id": xid_to_cat.get(cat_xid(cat))}
                ).id
                self._xid_set(ns, xid, "product.category", rid)
            xid_to_cat[xid] = rid
        for cat, cls, sub in sorted(l3):
            xid = sub_xid(cat, cls, sub)
            rid = self._xid_get(ns, xid, "product.category")
            if not rid:
                rid = self.env["product.category"].create(
                    {"name": sub, "parent_id": xid_to_cat.get(cls_xid(cat, cls))}
                ).id
                self._xid_set(ns, xid, "product.category", rid)
            xid_to_cat[xid] = rid
        self.env.cr.commit()

        # ---- attributes ----
        attr_by_name = {}
        for attr_name in ("Size", "Inseam"):
            attr = self.env["product.attribute"].search([("name", "=", attr_name)], limit=1)
            if not attr:
                attr = self.env["product.attribute"].create(
                    {"name": attr_name, "create_variant": "always", "display_type": "radio"}
                )
            attr_by_name[attr_name] = attr
        attr_value_id = {}
        for attr_name, vals in (("Size", sorted(sizes)), ("Inseam", sorted(inseams))):
            attr = attr_by_name[attr_name]
            for v in vals:
                av = self.env["product.attribute.value"].search(
                    [("attribute_id", "=", attr.id), ("name", "=", v)], limit=1
                )
                if not av:
                    av = self.env["product.attribute.value"].create({"attribute_id": attr.id, "name": v})
                attr_value_id[(attr_name, v)] = av.id
        self.env.cr.commit()

        # ---- templates ----
        tmpl_xid_to_id = {}
        for ext in self.env["ir.model.data"].search([("module", "=", ns), ("model", "=", "product.template")]):
            tmpl_xid_to_id[ext.name] = ext.res_id
        created = 0
        items = sorted(tmpl_meta.items())
        for start in range(0, len(items), BATCH):
            for pc, m in items[start:start + BATCH]:
                txid = self._safe_xid("tmpl_", pc)
                if txid in tmpl_xid_to_id:
                    continue
                vset = tmpl_variants[pc]
                t_sizes = sorted({s for s, _ in vset if s})
                t_inseams = sorted({i for _, i in vset if i})
                attr_lines = []
                if t_sizes:
                    attr_lines.append((0, 0, {
                        "attribute_id": attr_by_name["Size"].id,
                        "value_ids": [(6, 0, [attr_value_id[("Size", s)] for s in t_sizes])],
                    }))
                if t_inseams:
                    attr_lines.append((0, 0, {
                        "attribute_id": attr_by_name["Inseam"].id,
                        "value_ids": [(6, 0, [attr_value_id[("Inseam", i)] for i in t_inseams])],
                    }))
                categ_id = (
                    xid_to_cat.get(sub_xid(m["cat"], m["cls"], m["subcls"]))
                    or xid_to_cat.get(cls_xid(m["cat"], m["cls"]))
                    or xid_to_cat.get(cat_xid(m["cat"]))
                )
                vals = {
                    "name": m["name"] or pc,
                    "default_code": pc,
                    "list_price": m["retail"],
                    "type": "consu",
                    "sale_ok": True,
                    "purchase_ok": True,
                }
                if categ_id:
                    vals["categ_id"] = categ_id
                if attr_lines:
                    vals["attribute_line_ids"] = attr_lines
                tmpl = self.env["product.template"].create(vals)
                self._xid_set(ns, txid, "product.template", tmpl.id)
                tmpl_xid_to_id[txid] = tmpl.id
                created += 1
            self.env.cr.commit()
        log.records_created = created

        # ---- variants: match auto-generated by (size, inseam) and set sku/barcode ----
        size_val_id = {v: i for (a, v), i in attr_value_id.items() if a == "Size"}
        inseam_val_id = {v: i for (a, v), i in attr_value_id.items() if a == "Inseam"}
        by_tmpl = defaultdict(list)
        for _eff, v in sku_best.values():
            by_tmpl[self._safe_xid("tmpl_", v["tmpl_code"])].append(v)
        matched = unmatched = 0
        tkeys = list(by_tmpl.keys())
        for start in range(0, len(tkeys), 100):
            batch_xids = tkeys[start:start + 100]
            tmpl_ids = [tmpl_xid_to_id[x] for x in batch_xids if x in tmpl_xid_to_id]
            if not tmpl_ids:
                unmatched += sum(len(by_tmpl[x]) for x in batch_xids)
                continue
            variants = self.env["product.product"].search([("product_tmpl_id", "in", tmpl_ids)])
            var_index = {}
            for vp in variants:
                combo = frozenset(vp.product_template_variant_value_ids.product_attribute_value_id.ids)
                var_index[(vp.product_tmpl_id.id, combo)] = vp
            for txid in batch_xids:
                tid = tmpl_xid_to_id.get(txid)
                if not tid:
                    unmatched += len(by_tmpl[txid])
                    continue
                for v in by_tmpl[txid]:
                    wanted = set()
                    if v["size"] and size_val_id.get(v["size"]):
                        wanted.add(size_val_id[v["size"]])
                    if v["inseam"] and inseam_val_id.get(v["inseam"]):
                        wanted.add(inseam_val_id[v["inseam"]])
                    vp = var_index.get((tid, frozenset(wanted)))
                    if not vp:
                        unmatched += 1
                        continue
                    updates = {}
                    if vp.default_code != v["sku"]:
                        updates["default_code"] = v["sku"]
                    if v["gtin"] and vp.barcode != v["gtin"]:
                        updates["barcode"] = v["gtin"]
                    if updates:
                        try:
                            vp.write(updates)
                        except Exception:
                            if "barcode" in updates:
                                vp.write({k: x for k, x in updates.items() if k != "barcode"})
                    matched += 1
            self.env.cr.commit()
        log.records_matched = matched
        log.records_skipped = unmatched
        _logger.info("x101 done: created=%s matched=%s unmatched=%s", created, matched, unmatched)

    # ==================================================================
    # CoA — account.account
    # ==================================================================
    def _load_coa(self, profile, file_b64, log):
        ns = profile.namespace
        data = profile.read_records(file_b64)
        records = data["records"]
        log.line_count = len(records)
        valid_types = dict(self.env["account.account"]._fields["account_type"].selection)
        company = profile.company_id
        created = skipped = 0
        errors = []
        Account = self.env["account.account"]
        for r in records:
            code = str(r.get("code") or "").strip()
            name = (r.get("account_name") or r.get("name") or "").strip()
            atype = str(r.get("account_type") or "").strip()
            if not code or not name:
                continue
            if atype not in valid_types:
                errors.append((r.get("_row"), f"invalid account_type {atype!r} for {code}"))
                continue
            xid = self._safe_xid("coa_", code)
            if self._xid_get(ns, xid, "account.account"):
                skipped += 1
                continue
            existing = Account.with_company(company).search(
                [("code", "=", code), ("company_ids", "in", company.id)], limit=1
            )
            if existing:
                self._xid_set(ns, xid, "account.account", existing.id)
                skipped += 1
                continue
            try:
                acc = Account.with_company(company).create(
                    {"code": code, "name": name, "account_type": atype, "company_ids": [(4, company.id)]}
                )
                self._xid_set(ns, xid, "account.account", acc.id)
                created += 1
            except Exception as e:
                errors.append((r.get("_row"), f"{code}: {e}"))
        self.env.cr.commit()
        log.records_created = created
        log.records_skipped = skipped
        log.set_errors(errors)

    # ==================================================================
    # Company — res.company / partner (SES legal entity)
    # ==================================================================
    def _load_company(self, profile, file_b64, log):
        data = profile.read_records(file_b64)
        records = data["records"]
        log.line_count = len(records)
        company = profile.company_id
        vals = {}
        # SES sheet is a key/value layout; the profile maps a 'label'/'value' pair
        # OR direct fields. Support both: if a record carries 'field'/'value', set by label.
        label_to_field = {
            "nama": "name", "name": "name",
            "npwp": "vat", "vat": "vat",
            "alamat": "street", "address": "street",
            "telepon": "phone", "phone": "phone",
            "email": "email",
        }
        for r in records:
            raw_field = r.get("field")
            raw_value = r.get("value")
            # SES sheet often packs "Label : Value" into one cell -> split it.
            if raw_field and (raw_value is None or str(raw_value).strip() == "") and ":" in str(raw_field):
                label, _sep, val = str(raw_field).partition(":")
                raw_field, raw_value = label, val
            if raw_field is not None and raw_value is not None and str(raw_value).strip():
                key = str(raw_field or "").strip().lower().split(":")[0].strip()
                f = label_to_field.get(key)
                if f and str(raw_value).strip():
                    vals[f] = str(raw_value).strip()
            else:
                for src, dst in (("name", "name"), ("vat", "vat"), ("street", "street"),
                                 ("phone", "phone"), ("email", "email")):
                    if r.get(src):
                        vals[dst] = str(r.get(src)).strip()
        if vals:
            company.write({k: v for k, v in vals.items() if k in ("name",)})
            company.partner_id.write({k: v for k, v in vals.items() if k != "name"})
            log.records_matched = 1
        log.set_errors([])

    # ==================================================================
    # X20 — Opening on-hand stock -> stock.quant (one-shot, guarded)
    # ==================================================================
    def _load_x20(self, profile, file_b64, log):
        ns = profile.namespace
        data = profile.read_records(file_b64)
        records = data["records"]
        log.line_count = len(records)
        Product = self.env["product.product"]
        Quant = self.env["stock.quant"]
        # store-code -> internal stock location (warehouse lot_stock_id), resolved by xid
        loc_cache = {}

        def resolve_location(store_code):
            sc = str(store_code or "").strip()
            if sc in loc_cache:
                return loc_cache[sc]
            wh_id = self._xid_get(ns, self._safe_xid("wh_", sc), "stock.warehouse")
            loc = self.env["stock.warehouse"].browse(wh_id).lot_stock_id if wh_id else False
            loc_cache[sc] = loc
            return loc

        prod_by_barcode = {}
        prod_by_code = {}
        applied = skipped = 0
        errors = []
        quant_vals = []
        for r in records:
            store = r.get("store_code")
            ean = str(r.get("ean") or "").strip()
            item_id = str(r.get("item_id") or "").strip()
            qty = float(profile._parse_amount(r.get("onhand_qty")))
            if not store or qty <= 0:
                continue
            loc = resolve_location(store)
            if not loc:
                errors.append((r.get("_row"), f"store {store} -> no warehouse (run store loader first)"))
                continue
            prod = False
            if ean:
                if ean not in prod_by_barcode:
                    prod_by_barcode[ean] = Product.search([("barcode", "=", ean)], limit=1)
                prod = prod_by_barcode[ean]
            if not prod and item_id:
                if item_id not in prod_by_code:
                    prod_by_code[item_id] = Product.search([("default_code", "=", item_id)], limit=1)
                prod = prod_by_code[item_id]
            if not prod:
                errors.append((r.get("_row"), f"no product for ean={ean!r} item={item_id!r}"))
                skipped += 1
                continue
            quant_vals.append((prod, loc, qty))

        # Guard: refuse to re-apply if this profile already applied opening stock.
        prior = self.env["retail.import.log"].search(
            [("profile_id", "=", profile.id), ("state", "=", "imported"), ("id", "!=", log.id)], limit=1
        )
        if prior:
            raise UserError(
                _("Opening stock for profile %s was already applied (log #%s). "
                  "Re-applying would double the on-hand. Archive the prior log to override.")
                % (profile.code, prior.id)
            )

        for i, (prod, loc, qty) in enumerate(quant_vals):
            try:
                q = Quant.with_context(inventory_mode=True).create(
                    {"product_id": prod.id, "location_id": loc.id, "inventory_quantity": qty}
                )
                q.action_apply_inventory()
                applied += 1
            except Exception as e:
                errors.append((None, f"{prod.default_code}: {e}"))
            if (i + 1) % 500 == 0:
                self.env.cr.commit()
        self.env.cr.commit()
        log.records_created = applied
        log.records_skipped = skipped
        log.set_errors(errors)

    # ==================================================================
    # X24 — Retail sales -> pos.order (financial, no stock move)
    # ==================================================================
    def _load_x24(self, profile, file_b64, log):
        """Create historical pos.order grouped by (store, date, register, trans).

        Requires, per store: a pos.config with at least one payment method, and the
        company's accounting periods open for the dates loaded. Tax is taken from the
        product's sale taxes when present. Stock is NOT moved (config picking is
        skipped) so this does not double-count against X20 opening stock.

        This loader is decision-gated (plan Phase 5): validate against a live DB and
        confirm history depth + tax mapping before a full run.
        """
        raise UserError(
            _("X24 POS history import is decision-gated (Phase 5): confirm history depth, "
              "per-store pos.config, payment-method map (from X70D) and tax mapping, then enable. "
              "The parser + grouping are ready in retail.import.executor._group_x24().")
        )

    def _group_x24(self, profile, file_b64):
        """Parse X24 and group rows into transactions. Returned for Phase-5 wiring."""
        data = profile.read_records(file_b64)
        orders = defaultdict(list)
        for r in data["records"]:
            key = (r.get("store_code"), r.get("trans_date"), r.get("register"), r.get("transnum"))
            orders[key].append(r)
        return orders

    # ==================================================================
    # X70D — Tender detail -> pos.payment (Phase 5, joined to x24)
    # ==================================================================
    def _load_x70d(self, profile, file_b64, log):
        raise UserError(
            _("X70D tender import attaches payments to X24 pos.orders; enable together with X24 (Phase 5).")
        )

    # ==================================================================
    # Staged / reference-only loaders (parse + count + keep attachment)
    # ==================================================================
    def _stage_only(self, profile, file_b64, log, note):
        data = profile.read_records(file_b64)
        log.line_count = len(data["records"])
        log.records_skipped = len(data["records"])
        log.error_message = note
        _logger.info("%s: staged %s rows (no model writes)", profile.file_type, len(data["records"]))

    def _load_x70t(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X70T settlement: staged for reconciliation (Phase 5 decision).")

    def _load_x31(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X31 discount journal: staged for promo-accrual mapping (Phase 5).")

    def _load_x32p(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X32P stock movement: reference/audit only (not replayed; see plan).")

    def _load_store_master(self, profile, file_b64, log):
        self._stage_only(
            profile, file_b64, log,
            "Store Master: warehouse creation is handled by the Track A odoo-shell loader "
            "(header-wise store columns). This profile is for row-wise enrichment only.",
        )
