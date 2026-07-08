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

import json
import logging
from collections import defaultdict
from datetime import datetime

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BATCH = 200
LINE_BATCH = 500


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

    # ------------------------------------------------------------------
    # X101 product-type classification
    # ------------------------------------------------------------------
    def _x101_service_matchers(self):
        """Config-driven markers that flag an X101 row as a *service* (e.g. the
        "Original cut" tailoring/alteration item) rather than storable
        merchandise. Editable as data via ir.config_parameter, no code change:

          retail_import.service_category_keywords  (comma-sep, matched as a
              case-insensitive substring against category/class/subclass/name)
          retail_import.service_product_codes      (comma-sep, exact product code)

        Default keyword list is EMPTY on purpose: substring keywords like "TAILOR"
        false-match real merchandise ("TAILORED BUSTIER", "TAILORED CLASSIC" shirts,
        jeans named "…TAILOR"). Everything is storable merchandise by default; pin
        the actual "Original cut" tailoring service by exact code (or a carefully
        chosen keyword) via the config parameters above once its marker is known.
        """
        icp = self.env["ir.config_parameter"].sudo()
        kw_raw = icp.get_param("retail_import.service_category_keywords", "")
        code_raw = icp.get_param("retail_import.service_product_codes", "")
        keywords = [k.strip().upper() for k in (kw_raw or "").split(",") if k.strip()]
        codes = {c.strip().upper() for c in (code_raw or "").split(",") if c.strip()}
        return keywords, codes

    def _x101_is_service(self, meta, keywords, codes):
        """True when an X101 template should be a non-storable service product."""
        if codes and str(meta.get("code") or "").strip().upper() in codes:
            return True
        if not keywords:
            return False
        haystack = " ".join(
            str(meta.get(k) or "") for k in ("cat", "cls", "subcls", "name")
        ).upper()
        return any(kw in haystack for kw in keywords)

    # ------------------------------------------------------------------
    # Row-level backtracking helpers
    # ------------------------------------------------------------------
    def _persist_lines(self, log, records):
        """Create retail.import.line for every parsed row before aggregation.

        Returns a {row_number: line_record} dict for post-load target linking.
        Batched in LINE_BATCH creates to avoid ORM memory spikes on large files.
        """
        Line = self.env["retail.import.line"]
        row_to_line = {}
        for start in range(0, len(records), LINE_BATCH):
            batch = records[start : start + LINE_BATCH]
            created = Line.create([
                {
                    "log_id": log.id,
                    "row_number": r.get("_row"),
                    "raw_data_json": json.dumps(r, default=str),
                }
                for r in batch
            ])
            for r, ln in zip(batch, created):
                row_to_line[r.get("_row")] = ln
        return row_to_line

    def _link_lines(self, row_to_line, row_nums, target_model, target_res_id, aggregate_key=None, state="ok"):
        """Batch-write target linkage onto a group of source lines."""
        line_ids = [row_to_line[rn].id for rn in row_nums if rn in row_to_line]
        if not line_ids:
            return
        vals = {"state": state, "target_model": target_model, "target_res_id": target_res_id}
        if aggregate_key is not None:
            vals["aggregate_key"] = aggregate_key
        self.env["retail.import.line"].browse(line_ids).write(vals)

    # ==================================================================
    # X101 — Products (categories / attributes / templates / variants)
    # ==================================================================
    def _load_x101(self, profile, file_b64, log):
        ns = profile.namespace
        data = profile.read_records(file_b64)
        records = data["records"]
        log.line_count = len(records)

        row_to_line = self._persist_lines(log, records)

        # ---- aggregate (mirror of 01_extract_x101.py) ----
        sku_best = {}  # sku -> (eff, dict)
        sku_gtins = defaultdict(set)  # sku -> {all GTINs} (a variant may have several)
        tmpl_meta = {}  # code -> dict
        sizes, inseams = set(), set()
        tmpl_variants = defaultdict(set)
        tmpl_rows = defaultdict(list)   # pc -> [row_nums] for post-load line linking
        skipped_row_nums = []
        for r in records:
            pc = r.get("product_code")
            sku = r.get("sku")
            row_num = r.get("_row")
            if not pc or not sku:
                if row_num is not None:
                    skipped_row_nums.append(row_num)
                continue
            size = (r.get("size") or "").strip()
            inseam_raw = r.get("inseam")
            inseam = (str(inseam_raw).strip() if inseam_raw not in (None, "-", "") else "")
            gtin = str(r.get("gtin") or "").strip()
            if gtin:
                sku_gtins[sku].add(gtin)  # keep EVERY GTIN so all scanned codes resolve
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
            tmpl_rows[pc].append(row_num)
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
        svc_keywords, svc_codes = self._x101_service_matchers()
        bad_quality = defaultdict(list)  # pc -> [data-quality messages] for line flagging
        items = sorted(tmpl_meta.items())
        for start in range(0, len(items), BATCH):
            for pc, m in items[start:start + BATCH]:
                txid = self._safe_xid("tmpl_", pc)
                vset = tmpl_variants[pc]
                t_sizes = sorted({s for s, _ in vset if s})
                t_inseams = sorted({i for _, i in vset if i})
                if txid in tmpl_xid_to_id:
                    # Fix B: template already registered — backfill any newly-appearing
                    # size/inseam values so the missing variants get generated. The
                    # variant-match loop below then assigns their default_code/barcode.
                    self._x101_backfill_template_attrs(
                        tmpl_xid_to_id[txid], t_sizes, t_inseams, attr_by_name, attr_value_id)
                    continue
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
                # Data-quality flags (surface bad source rows in the import log).
                if not categ_id:
                    bad_quality[pc].append("missing category")
                if not m["retail"] or m["retail"] <= 0:
                    bad_quality[pc].append("invalid/zero price")
                # Merchandise (jeans, tops, paperbag, ...) is storable & qty-tracked;
                # the "Original cut" tailoring/alteration item is a service. Odoo 19
                # carries the distinction on is_storable, not on type.
                is_service = self._x101_is_service(m, svc_keywords, svc_codes)
                vals = {
                    "name": m["name"] or pc,
                    "default_code": pc,
                    "list_price": m["retail"],
                    "type": "service" if is_service else "consu",
                    "sale_ok": True,
                    "purchase_ok": True,
                }
                if not is_service:
                    vals["is_storable"] = True
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
            var_by_tmpl = defaultdict(list)
            used_by_tmpl = defaultdict(set)  # attribute-value ids that actually distinguish variants
            for vp in variants:
                ids = vp.product_template_variant_value_ids.product_attribute_value_id.ids
                var_index[(vp.product_tmpl_id.id, frozenset(ids))] = vp
                var_by_tmpl[vp.product_tmpl_id.id].append(vp)
                used_by_tmpl[vp.product_tmpl_id.id].update(ids)
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
                    # Odoo omits SINGLE-value attributes from a variant's combo (e.g. a
                    # jeans template with one inseam "32", or an "OS" accessory). Restrict
                    # ``wanted`` to the values that actually distinguish this template's
                    # variants so the size-only / empty combo still resolves.
                    wanted_eff = frozenset(wanted & used_by_tmpl.get(tid, set()))
                    vp = var_index.get((tid, wanted_eff))
                    if not vp:
                        # Last resort: a lone-variant template that contributes a single
                        # sku — assign it directly.
                        tvars = var_by_tmpl.get(tid, [])
                        if len(tvars) == 1 and len(by_tmpl[txid]) == 1:
                            vp = tvars[0]
                        else:
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
                    # Fix A: register EVERY GTIN of this sku as an alternate barcode so a
                    # POS scan of any of them resolves (the variant's single ``barcode``
                    # field only holds one). Dedup against primary + existing aliases.
                    self._x101_register_gtins(vp, sku_gtins.get(v["sku"], ()))
                    matched += 1
            self.env.cr.commit()
        log.records_matched = matched
        log.records_skipped = unmatched
        _logger.info("x101 done: created=%s matched=%s unmatched=%s", created, matched, unmatched)

        # Link source rows to the product.template they contributed to
        if row_to_line:
            for pc, row_nums in tmpl_rows.items():
                txid = self._safe_xid("tmpl_", pc)
                tmpl_id = tmpl_xid_to_id.get(txid)
                if tmpl_id:
                    self._link_lines(row_to_line, row_nums, "product.template", tmpl_id, aggregate_key=pc)
            if skipped_row_nums:
                skip_ids = [row_to_line[rn].id for rn in skipped_row_nums if rn in row_to_line]
                if skip_ids:
                    self.env["retail.import.line"].browse(skip_ids).write({"state": "skipped"})
            self.env.cr.commit()

        # Flag data-quality issues on the contributing source lines (runs AFTER
        # linking so it overrides the "ok" state set above). Bumps error_count,
        # which marks the log "partial" so the user reviews it.
        errors = []
        for pc, msgs in bad_quality.items():
            msg = "; ".join(sorted(set(msgs)))
            row_nums = tmpl_rows.get(pc, [])
            line_ids = [row_to_line[rn].id for rn in row_nums if rn in row_to_line]
            if line_ids:
                self.env["retail.import.line"].browse(line_ids).write(
                    {"state": "error", "error_message": msg}
                )
            for rn in row_nums:
                errors.append((rn, f"{pc}: {msg}"))
        log.set_errors(errors)
        self.env.cr.commit()

    # ------------------------------------------------------------------
    # X101 helpers — multi-GTIN (Fix A) + variant backfill (Fix B)
    # ------------------------------------------------------------------
    def _x101_register_gtins(self, variant, gtins):
        """Register every GTIN of a sku as a product.barcode alternate on ``variant``.

        The variant's single ``barcode`` field only holds one code; a Levi's SKU has
        several GTINs and POS may scan any of them. Reuses custom_product_barcode's
        ``product.barcode`` (resolved via ``product.product._resolve_barcode``). Dedup
        against the primary barcode and existing aliases; idempotent + sudo (write on
        product.barcode is group_system)."""
        if not gtins:
            return
        Barcode = self.env["product.barcode"].sudo()
        have = set(variant.barcode_ids.mapped("barcode"))
        if variant.barcode:
            have.add(variant.barcode)
        for g in gtins:
            g = (g or "").strip()
            if not g or g in have:
                continue
            try:
                Barcode.create({"product_id": variant.id, "barcode": g, "note": "X101 GTIN"})
                have.add(g)
            except Exception as e:  # unique(product_id,barcode) race / bad value
                _logger.debug("x101 gtin alias skip %s on %s: %s", g, variant.id, e)

    def _x101_backfill_template_attrs(self, tmpl_id, t_sizes, t_inseams, attr_by_name, attr_value_id):
        """Add newly-appearing Size/Inseam values to an EXISTING template so Odoo
        regenerates the missing variants (create_variant='always'). Only writes when
        there is something to add, so re-runs are no-ops (idempotent).

        Adding a value to an existing attribute line is safe (just more variants).
        Creating a brand-new attribute line restructures the variant matrix — acceptable
        here because imported POS is financial-only (no stock on these products)."""
        tmpl = self.env["product.template"].browse(tmpl_id)
        if not tmpl.exists():
            return
        want = {
            "Size": [attr_value_id[("Size", s)] for s in t_sizes if ("Size", s) in attr_value_id],
            "Inseam": [attr_value_id[("Inseam", i)] for i in t_inseams if ("Inseam", i) in attr_value_id],
        }
        for attr_name, wanted_ids in want.items():
            if not wanted_ids:
                continue
            attr = attr_by_name[attr_name]
            line = tmpl.attribute_line_ids.filtered(lambda l: l.attribute_id == attr)[:1]
            if line:
                missing = [i for i in wanted_ids if i not in line.value_ids.ids]
                if missing:
                    try:
                        line.write({"value_ids": [(4, i) for i in missing]})
                    except Exception as e:
                        _logger.warning("x101 backfill add-value tmpl %s %s: %s", tmpl_id, attr_name, e)
            else:
                try:
                    tmpl.write({"attribute_line_ids": [(0, 0, {
                        "attribute_id": attr.id, "value_ids": [(6, 0, wanted_ids)]})]})
                except Exception as e:
                    _logger.warning("x101 backfill add-line tmpl %s %s: %s", tmpl_id, attr_name, e)

    # ==================================================================
    # CoA — account.account
    # ==================================================================
    def _load_coa(self, profile, file_b64, log):
        ns = profile.namespace
        data = profile.read_records(file_b64)
        records = data["records"]
        log.line_count = len(records)
        row_to_line = self._persist_lines(log, records)
        valid_types = dict(self.env["account.account"]._fields["account_type"].selection)
        company = profile.company_id
        created = skipped = 0
        errors = []
        Account = self.env["account.account"]
        for r in records:
            rn = r.get("_row")
            code = str(r.get("code") or "").strip()
            name = (r.get("account_name") or r.get("name") or "").strip()
            atype = str(r.get("account_type") or "").strip()
            if not code or not name:
                if rn in row_to_line:
                    row_to_line[rn].write({"state": "skipped"})
                continue
            if atype not in valid_types:
                errors.append((rn, f"invalid account_type {atype!r} for {code}"))
                if rn in row_to_line:
                    row_to_line[rn].write({"state": "error", "error_message": f"invalid account_type {atype!r}"})
                continue
            xid = self._safe_xid("coa_", code)
            existing_id = self._xid_get(ns, xid, "account.account")
            if existing_id:
                skipped += 1
                if rn in row_to_line:
                    row_to_line[rn].write({"state": "skipped", "aggregate_key": code, "target_model": "account.account", "target_res_id": existing_id})
                continue
            existing = Account.with_company(company).search(
                [("code", "=", code), ("company_ids", "in", company.id)], limit=1
            )
            if existing:
                self._xid_set(ns, xid, "account.account", existing.id)
                skipped += 1
                if rn in row_to_line:
                    row_to_line[rn].write({"state": "skipped", "aggregate_key": code, "target_model": "account.account", "target_res_id": existing.id})
                continue
            try:
                acc = Account.with_company(company).create(
                    {"code": code, "name": name, "account_type": atype, "company_ids": [(4, company.id)]}
                )
                self._xid_set(ns, xid, "account.account", acc.id)
                created += 1
                if rn in row_to_line:
                    row_to_line[rn].write({"aggregate_key": code, "target_model": "account.account", "target_res_id": acc.id})
            except Exception as e:
                errors.append((rn, f"{code}: {e}"))
                if rn in row_to_line:
                    row_to_line[rn].write({"state": "error", "error_message": f"{code}: {e}"})
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
        row_to_line = self._persist_lines(log, records)
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
        quant_vals = []   # (prod, loc, qty, row_num, agg_key)
        for r in records:
            rn = r.get("_row")
            store = r.get("store_code")
            ean = str(r.get("ean") or "").strip()
            item_id = str(r.get("item_id") or "").strip()
            qty = float(profile._parse_amount(r.get("onhand_qty")))
            if not store or qty <= 0:
                if rn in row_to_line:
                    row_to_line[rn].write({"state": "skipped"})
                continue
            loc = resolve_location(store)
            if not loc:
                errors.append((rn, f"store {store} -> no warehouse (run store loader first)"))
                if rn in row_to_line:
                    row_to_line[rn].write({"state": "error", "error_message": f"store {store}: no warehouse"})
                continue
            prod = False
            if ean:
                if ean not in prod_by_barcode:
                    prod_by_barcode[ean] = Product._resolve_barcode(ean)
                prod = prod_by_barcode[ean]
            if not prod and item_id:
                if item_id not in prod_by_code:
                    prod_by_code[item_id] = Product.search([("default_code", "=", item_id)], limit=1)
                prod = prod_by_code[item_id]
            if not prod:
                errors.append((rn, f"no product for ean={ean!r} item={item_id!r}"))
                skipped += 1
                if rn in row_to_line:
                    row_to_line[rn].write({"state": "error", "error_message": f"no product ean={ean!r} item={item_id!r}"})
                continue
            quant_vals.append((prod, loc, qty, rn, f"{store}|{item_id or ean}"))

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

        for i, (prod, loc, qty, rn, agg_key) in enumerate(quant_vals):
            try:
                q = Quant.with_context(inventory_mode=True).create(
                    {"product_id": prod.id, "location_id": loc.id, "inventory_quantity": qty}
                )
                q.action_apply_inventory()
                applied += 1
                if rn in row_to_line:
                    row_to_line[rn].write({
                        "aggregate_key": agg_key,
                        "target_model": "stock.quant",
                        "target_res_id": q.id,
                    })
            except Exception as e:
                errors.append((None, f"{prod.default_code}: {e}"))
                if rn in row_to_line:
                    row_to_line[rn].write({"state": "error", "error_message": str(e)})
            if (i + 1) % 500 == 0:
                self.env.cr.commit()
        self.env.cr.commit()
        log.records_created = applied
        log.records_skipped = skipped
        log.set_errors(errors)

    # ==================================================================
    # X24 — Retail sales -> pos.order (financial, no stock move)
    # ==================================================================
    # --- Phase-5 X24 configuration (see docs/PHASE5_X24_DESIGN.md) ---------
    # Locked defaults (2026-07-05):
    #   A: store->pos.config via ir.model.data xid ``posconfig_<STORE>``
    #   B: no stock (import posts financial pos.order only; sessions may be closed)
    #   C: one pos.session per (config, trans_date)
    #   D: tender_type == pos.payment.method.name; OFFLINE_OTHER_CARD folds in
    #   E: tax_rate 0.11 -> account.tax "12% (Non-Luxury Good)" (amount 11.0, sale)
    #   F: one pos.order per (store, date, register, transnum)
    _X24_TENDER_FOLD = {"OFFLINE_OTHER_CARD": "OFFLINE_OTHER_CREDITCARD"}
    _X24_SEED_TENDERS = ("OFFLINE_AMEX", "OFFLINE_OVO", "SODEXO")
    _X24_BALANCE_TOL = 1.0  # currency units; parks orders whose tenders != line total

    def _x24_post_enabled(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "retail_import.x24_post_enabled", "0"
        ) in ("1", "true", "True")

    def _x24_strict_product_enabled(self):
        """Strict mode: never lazy-create a product for an X24/X48 row whose SKU is
        absent from the X101 master. The transaction is parked instead, forcing the
        team to register the product via X101 first. Gated (default OFF) so other
        tenants keep the legacy auto-stub behaviour."""
        return self.env["ir.config_parameter"].sudo().get_param(
            "retail_import.x24_strict_product", "0"
        ) in ("1", "true", "True")

    def _x24_decouple_enabled(self):
        """Decouple mode: post X24 sales fully paid against a POS Suspense Clearing
        account (single SUSPENSE payment) instead of joining X70D tenders, so sales
        post regardless of whether payment data exists yet. X70D, when imported, posts
        a transfer entry (Dr per-tender receivable / Cr Suspense) and reconciles the
        suspense lines. Gated (default OFF). Requires x24_close_sessions=1 (the GL is
        only produced at session close)."""
        return self.env["ir.config_parameter"].sudo().get_param(
            "retail_import.x24_decouple_payment", "0"
        ) in ("1", "true", "True")

    def _x24_close_sessions_enabled(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "retail_import.x24_close_sessions", "0"
        ) in ("1", "true", "True")

    def _load_x24(self, profile, file_b64, log):
        """Phase-5: post pos.order when ``retail_import.x24_post_enabled``, else stage.

        Staging (flag off, default) is the legacy behaviour: parse + persist lines
        marked 'skipped' with a ``store|date|sku`` aggregate_key, no model writes.
        Posting (flag on) creates one pos.order per (store,date,register,transnum)
        with payments joined from X70D. See docs/PHASE5_X24_DESIGN.md.
        """
        data = profile.read_records(file_b64)
        records = data["records"]
        log.line_count = len(records)
        if not records:
            log.records_skipped = 0
            return
        row_to_line = self._persist_lines(log, records)
        if self._x24_post_enabled():
            self._post_x24(profile, records, log, row_to_line)
        else:
            self._stage_x24(profile, records, log, row_to_line)

    def _stage_x24(self, profile, records, log, row_to_line):
        log.records_skipped = len(records)
        log.error_message = (
            "X24DN POS sales: staged (Phase-5 gated — set retail_import.x24_post_enabled=1 to post)."
        )
        agg = self._aggregate_x24_by_sku_day(records)
        for (store, date, sku), vals in agg.items():
            agg_key = f"{store}|{date}|{sku}"
            line_ids = [row_to_line[rn].id for rn in vals["row_nums"] if rn in row_to_line]
            if line_ids:
                self.env["retail.import.line"].browse(line_ids).write({
                    "state": "skipped", "aggregate_key": agg_key,
                })
        self.env.cr.commit()
        _logger.info("x24: %s rows -> %s daily-SKU aggregates (staged)", len(records), len(agg))

    # ------------------------------------------------------------------
    # Phase-5 posting helpers
    # ------------------------------------------------------------------
    def _x24_resolve_tax(self):
        """account.tax for the X24 11% rate (Decision E). Configurable via param."""
        icp = self.env["ir.config_parameter"].sudo()
        tid = icp.get_param("retail_import.x24_tax_id")
        Tax = self.env["account.tax"]
        if tid and Tax.browse(int(tid)).exists():
            return Tax.browse(int(tid))
        return Tax.search(
            [("type_tax_use", "=", "sale"), ("amount", "=", 11.0), ("amount_type", "=", "percent")],
            limit=1,
        )

    def _x24_tender_index(self, profile):
        """Build {(store,date,reg,txn): [(tender_type, amount)]} from staged X70D lines.

        Sourced from the most recent imported X70D log so X70D must be synced before
        X24 posting. Rows with a blank tender_type (file totals) are ignored.
        """
        Log = self.env["retail.import.log"].sudo()
        x70d_profile = self.env["retail.import.profile"].search(
            [("file_type", "=", "x70d"), ("company_id", "=", profile.company_id.id)], limit=1
        )
        idx = defaultdict(list)
        if not x70d_profile:
            return idx
        log = Log.search([("profile_id", "=", x70d_profile.id)], order="id desc", limit=1)
        if not log:
            return idx
        lines = self.env["retail.import.line"].sudo().search([("log_id", "=", log.id)])
        for ln in lines:
            try:
                r = json.loads(ln.raw_data_json or "{}")
            except Exception:
                continue
            tt = str(r.get("tender_type") or "").strip()
            if not tt:
                continue
            key = (
                str(r.get("store_code") or "").strip(), str(r.get("trans_date") or "").strip(),
                str(r.get("register") or "").strip(), str(r.get("transnum") or "").strip(),
            )
            try:
                amt = float(r.get("tender_amount") or 0)
            except Exception:
                amt = 0.0
            idx[key].append((tt, amt))
        return idx

    def _x24_group_orders(self, records):
        orders = defaultdict(list)
        for r in records:
            store = str(r.get("store_code") or "").strip()
            txn = str(r.get("transnum") or "").strip()
            if not store or not txn:
                continue
            key = (store, str(r.get("trans_date") or "").strip(),
                   str(r.get("register") or "").strip(), txn)
            orders[key].append(r)
        return orders

    def _post_x24(self, profile, records, log, row_to_line):
        ns = profile.namespace
        Product = self.env["product.product"]
        Order = self.env["pos.order"]
        Line = self.env["retail.import.line"]
        icp = self.env["ir.config_parameter"].sudo()

        # Whole-file idempotency guard (mirror _load_x20).
        prior = self.env["retail.import.log"].search(
            [("profile_id", "=", profile.id), ("state", "=", "imported"), ("id", "!=", log.id)], limit=1
        )
        if prior:
            raise UserError(
                _("X24 already posted (log #%s). Archive it before re-posting to avoid duplicate sales.")
                % prior.id
            )

        # Ensure each tender method books to its own GL receivable account so the
        # session-close journal splits cash / card / e-wallet instead of piling every
        # tender into the single company-default Trade Receivables. Idempotent.
        self._x24_ensure_method_gl_split()

        # Decouple mode: post each order fully paid against a POS Suspense Clearing
        # account (single SUSPENSE payment), ignoring X70D tenders. GL only forms at
        # session close, so decouple requires x24_close_sessions=1.
        decouple = self._x24_decouple_enabled()
        suspense_method = None
        if decouple:
            if not self._x24_close_sessions_enabled():
                raise UserError(_(
                    "Decouple mode (retail_import.x24_decouple_payment=1) requires "
                    "retail_import.x24_close_sessions=1 — the GL is only produced at "
                    "POS session close."))
            suspense_method = self._x24_ensure_suspense_method()

        tax = self._x24_resolve_tax()
        tenders = {} if decouple else self._x24_tender_index(profile)
        orders = self._x24_group_orders(records)
        strict_products = self._x24_strict_product_enabled()

        cfg_cache, sess_cache, method_cache = {}, {}, {}
        prod_bc, prod_dc = {}, {}
        created = skipped = 0
        errors = []

        def resolve_config(store):
            if store not in cfg_cache:
                cid = self._xid_get(ns, self._safe_xid("posconfig_", store), "pos.config")
                cfg_cache[store] = self.env["pos.config"].browse(cid) if cid else False
            return cfg_cache[store]

        def get_session(cfg):
            # ONE session per config for the whole import: Odoo forbids >1 open
            # session per pos.config, so a multi-date file cannot open a session per
            # (config, date). Orders keep their real date_order; the close move can be
            # backdated to the latest order date.
            k = cfg.id
            if k not in sess_cache:
                s = self.env["pos.session"].create({"config_id": cfg.id, "user_id": self.env.uid})
                # Decision B: imported POS is financial-only and must NOT move stock.
                # Merchandise is now storable (is_storable=True), so without this the
                # close would create pickings/stock moves and double-count on-hand
                # (the X20 snapshot already sets opening quantities). pos.session.create
                # forces this flag from company config, so override it post-create.
                if s.update_stock_at_closing:
                    s.update_stock_at_closing = False
                if s.state != "opened":
                    # Proper opening (cash control) so the close can book cash to
                    # Cash-on-hand instead of Cash Difference Loss.
                    try:
                        s.set_opening_control(0, None)
                    except Exception:
                        pass
                    if s.state != "opened":
                        s.write({"state": "opened"})
                sess_cache[k] = s
            return sess_cache[k]

        def resolve_product(r):
            ean = str(r.get("ean") or "").strip()
            code = str(r.get("item_code") or "").strip()
            if ean:
                if ean not in prod_bc:
                    prod_bc[ean] = Product._resolve_barcode(ean)
                if prod_bc[ean]:
                    return prod_bc[ean]
            if code:
                if code not in prod_dc:
                    prod_dc[code] = Product.search([("default_code", "=", code)], limit=1)
                if prod_dc[code]:
                    return prod_dc[code]
            # Strict mode: refuse to invent a product for an unregistered SKU — return
            # empty so the caller parks the whole transaction until X101 is synced.
            if strict_products:
                return Product.browse()
            # Lazy-create a non-merchandise product (carrier bags, vouchers, etc. sold at
            # POS but absent from the X101 master) so the order is complete and balances
            # against the X70D tender. Idempotent by xid. Parity with legacy 8548b52.
            key = code or ean
            if not key:
                return Product.browse()
            xid = self._safe_xid("x24prod_", key)
            pid = self._xid_get(ns, xid, "product.product")
            if pid:
                p = Product.browse(pid)
            else:
                tmpl = self.env["product.template"].with_context(
                    tracking_disable=True, mail_create_nolog=True).create({
                        "name": (str(r.get("item_description") or "").strip() or key)[:200],
                        "default_code": code or False, "type": "consu", "sale_ok": True,
                        "list_price": float(profile._parse_amount(r.get("retail_price")) or 0),
                    })
                p = tmpl.product_variant_id
                if ean and not p.barcode and not Product.search_count([("barcode", "=", ean)]):
                    try:
                        p.barcode = ean
                    except Exception:
                        pass
                self._xid_set(ns, xid, "product.product", p.id)
            if code:
                prod_dc[code] = p
            if ean:
                prod_bc[ean] = p
            return p

        def map_method(cfg, tender_type):
            tt = self._X24_TENDER_FOLD.get(tender_type, tender_type)
            k = (cfg.id, tt)
            if k not in method_cache:
                method_cache[k] = cfg.payment_method_ids.filtered(lambda m: (m.name or "") == tt)[:1]
            return method_cache[k]

        def fail_rows(rows, msg):
            for r in rows:
                rn = r.get("_row")
                if rn in row_to_line:
                    row_to_line[rn].write({"state": "error", "error_message": msg[:250]})
            errors.append((rows[0].get("_row"), msg))

        for key, rows in orders.items():
            store, date, reg, txn = key
            oxid = self._safe_xid("posorder_", f"{store}_{date}_{reg}_{txn}")
            if self._xid_get(ns, oxid, "pos.order"):
                continue  # already posted
            cfg = resolve_config(store)
            if not cfg:
                fail_rows(rows, f"store {store}: no pos.config (map xid posconfig_{store})")
                skipped += len(rows)
                continue

            line_cmds, order_net, order_incl, missing = [], 0.0, 0.0, []
            for r in rows:
                prod = resolve_product(r)
                if not prod:
                    missing.append(str(r.get("item_code") or r.get("ean") or "?"))
                    rn = r.get("_row")
                    if rn in row_to_line:
                        row_to_line[rn].write({
                            "state": "error",
                            "error_message": f"not in X101 master: ean={r.get('ean')!r} code={r.get('item_code')!r}"[:250],
                        })
                    continue
                qty = float(profile._parse_amount(r.get("net_qty")))
                incl = float(profile._parse_amount(r.get("total_amount")))
                gross = float(profile._parse_amount(r.get("gross_price")) or 0)
                rate = str(r.get("tax_rate") or "").strip()
                taxed = bool(tax) and rate not in ("", "None")
                # Derive the untaxed base from the PAID total and the tax rate so POS'
                # tax recomputation grosses back to exactly ``incl`` (net*(1+rate)==incl).
                # Using the source net_amount instead leaves a residual that POS plugs to
                # "Cash Difference Loss" (the source total/net ratio is blended, not flat).
                rate_val = (tax.amount / 100.0) if taxed else 0.0
                gl_net = incl / (1.0 + rate_val)
                tax_ids = [tax.id] if taxed else []
                # The sale tax is PRICE-INCLUDED, so POS extracts net from price_unit and
                # ignores a forced price_subtotal. price_unit must therefore carry the
                # tax-INCLUSIVE amount (the paid ``incl``) — POS then derives net = incl/(1+rate)
                # and recognised incl == incl == tender, so nothing plugs to Cash Difference.
                unit = incl / qty if qty else incl
                line_cmds.append((0, 0, {
                    "product_id": prod.id, "qty": qty,
                    "price_unit": unit, "discount": 0.0,
                    "tax_ids": [(6, 0, tax_ids)],
                    "price_subtotal": gl_net, "price_subtotal_incl": incl,
                }))
                order_net += gl_net
                order_incl += incl

            # Strict mode / any unresolved line: park the WHOLE transaction rather than
            # posting a partial order (which would later fail the tender-balance check).
            if missing:
                sku_list = ", ".join(sorted(set(missing))[:10])
                fail_rows(rows, f"store {store} txn {txn}: produk belum teregister di master X101 ({sku_list}) — sync X101 dulu")
                skipped += len(rows)
                continue
            if not line_cmds:
                fail_rows(rows, f"store {store} txn {txn}: no resolvable product")
                skipped += len(rows)
                continue

            if not decouple:
                tlist = tenders.get(key, [])
                pay_total = sum(a for _, a in tlist)
                if not tlist:
                    fail_rows(rows, f"store {store} txn {txn}: no X70D tender (sync X70D first)")
                    skipped += len(rows)
                    continue
                if abs(pay_total - order_incl) > self._X24_BALANCE_TOL:
                    fail_rows(rows, f"store {store} txn {txn}: unbalanced lines={order_incl:.2f} tenders={pay_total:.2f}")
                    skipped += len(rows)
                    continue

            d = profile._parse_date(date)
            dt = datetime(d.year, d.month, d.day, 12, 0, 0) if d else datetime.now()
            # Session is created outside the per-order savepoint so a single bad
            # order does not roll back the shared session.
            sess = get_session(cfg)
            try:
                with self.env.cr.savepoint():
                    order = Order.create({
                        "session_id": sess.id, "company_id": cfg.company_id.id,
                        "pricelist_id": cfg.pricelist_id.id or False, "date_order": dt,
                        "pos_reference": f"{store}-{reg}-{txn}",
                        "lines": line_cmds,
                        "amount_tax": order_incl - order_net, "amount_total": order_incl,
                        "amount_paid": 0.0, "amount_return": 0.0,
                    })
                    if decouple:
                        # Pay the full amount to the POS Suspense Clearing method; X70D
                        # reconciliation later transfers it to the real tender receivables.
                        order.add_payment({
                            "pos_order_id": order.id,
                            "payment_method_id": suspense_method[cfg.company_id.id].id,
                            "amount": order_incl, "payment_date": dt,
                        })
                    else:
                        for tt, amt in tlist:
                            m = map_method(cfg, tt)
                            if not m:
                                errors.append((rows[0].get("_row"), f"{store}/{txn}: no method for tender {tt}"))
                                continue
                            order.add_payment({
                                "pos_order_id": order.id, "payment_method_id": m.id,
                                "amount": amt, "payment_date": dt,
                            })
                    # ``pos.order.amount_paid`` is a plain stored field (no @api.depends)
                    # in Odoo 19: writing pos.payment rows does NOT refresh it (the UI
                    # relies on an onchange). Recompute from payments before the paid gate
                    # so orders are actually marked paid (mirrors fix b68559b).
                    order.invalidate_recordset(["payment_ids", "amount_paid"])
                    order.amount_paid = sum(order.payment_ids.mapped("amount"))
                    if order.amount_total > 0 and order.amount_paid >= order.amount_total:
                        order.action_pos_order_paid()
                    self._xid_set(ns, oxid, "pos.order", order.id)
            except Exception as e:  # per-order savepoint rolled back; keep going
                fail_rows(rows, f"store {store} txn {txn}: post failed: {e}")
                skipped += len(rows)
                continue
            for r in rows:
                rn = r.get("_row")
                if rn in row_to_line:
                    row_to_line[rn].write({
                        "state": "ok", "target_model": "pos.order",
                        "target_res_id": order.id, "aggregate_key": f"{store}|{date}|{txn}",
                    })
            created += 1
            if created % 200 == 0:
                self.env.cr.commit()

        self._pos_close_and_backdate(sess_cache.values(), errors, "x24")

        self.env.cr.commit()
        log.records_created = created
        log.records_skipped = skipped
        log.set_errors(errors)
        _logger.info("x24 POST: %s orders created, %s rows skipped, %s errors",
                     created, skipped, len(errors))

    def _pos_close_and_backdate(self, sessions, errors, tag):
        """Close each open POS session (cash-control aware) and re-stamp its GL move to
        the latest order date. Gated by ``retail_import.x24_close_sessions``. Shared by
        X24 sales and X48 refunds. POS dates the close move at ``context_today`` and
        re-applies it on _post, so the backdate is done via SQL (safe within the same
        fiscal year — the annual sequence stays valid). Guards against stock moves
        (Decision B: imported POS must not touch inventory)."""
        icp = self.env["ir.config_parameter"].sudo()
        if icp.get_param("retail_import.x24_close_sessions", "0") not in ("1", "true", "True"):
            return
        for s in sessions:
            try:
                try:
                    s.post_closing_cash_details(s.cash_register_balance_end)
                    s.close_session_from_ui()
                except Exception:
                    s.action_pos_session_closing_control()
                moves = s.order_ids.picking_ids.mapped("move_ids")
                if moves:
                    msg = (f"session {s.id}: UNEXPECTED {len(moves)} stock move(s) on close "
                           f"(products became storable?) — inventory may be double-counted")
                    _logger.error("%s POST: %s", tag, msg)
                    errors.append((None, msg))
                elif s.move_id:
                    try:
                        dates = [d for d in s.order_ids.mapped("date_order") if d]
                        mv = s.move_id
                        if dates and mv.date and max(dates).date().year == mv.date.year:
                            gl = max(dates).date()
                            self.env.cr.execute(
                                "UPDATE account_move SET date=%s WHERE id=%s", (gl, mv.id))
                            self.env.cr.execute(
                                "UPDATE account_move_line SET date=%s WHERE move_id=%s", (gl, mv.id))
                            mv.invalidate_recordset(["date"])
                            mv.line_ids.invalidate_recordset(["date"])
                    except Exception as be:
                        _logger.warning("%s POST: session %s backdate skipped: %s", tag, s.id, be)
                    _logger.info("%s POST: session %s closed, journal %s dated %s (no stock moves)",
                                 tag, s.id, s.move_id.name, s.move_id.date)
            except Exception as e:
                errors.append((None, f"session {s.id} close failed: {e}"))

    # ------------------------------------------------------------------
    # Decision A — store_code -> pos.config mapping (posconfig_<store> xids)
    # ------------------------------------------------------------------
    @staticmethod
    def _norm_store_name(name):
        """Normalise a store/config label to its bare mall name for matching.

        Strips the outlet-type prefix ('OLS SES -', 'OLS SCU -', 'OLS -', 'OLS')
        and collapses whitespace/case so 'OLS SES - TUNJUNGAN PLAZA 3' and
        'OLS SCU - TUNJUNGAN PLAZA 3' both reduce to 'TUNJUNGAN PLAZA 3'.
        """
        s = " ".join(str(name or "").upper().split())
        for pre in ("OLS SES -", "OLS SCU -", "OLS SES", "OLS SCU", "OLS -", "OLS"):
            if s.startswith(pre):
                s = s[len(pre):].strip()
                break
        return " ".join(s.split())

    def _x24_stores_from_staged(self):
        """Distinct {store_code: (sap, store_name)} from the latest staged X24 log."""
        Prof = self.env["retail.import.profile"]
        p24 = Prof.search([("file_type", "=", "x24")], limit=1)
        Log = self.env["retail.import.log"].sudo()
        log = Log.search([("profile_id", "=", p24.id)], order="id desc", limit=1) if p24 else Log
        stores = {}
        if not log:
            return stores
        for ln in self.env["retail.import.line"].sudo().search([("log_id", "=", log.id)]):
            try:
                r = json.loads(ln.raw_data_json or "{}")
            except Exception:
                continue
            sc = str(r.get("store_code") or "").strip()
            if not sc or not sc.isdigit():
                continue
            stores[sc] = (str(r.get("sap_store_code") or "").strip(),
                          str(r.get("store_name") or "").strip())
        return stores

    def _x24_map_stores_to_configs(self, stores=None, commit=False):
        """Map store codes to pos.config by normalised name; write posconfig_<code> xids.

        Two-tier, correctness-first: (1) unique **exact** normalised-name match;
        (2) unique **containment** match (one config whose bare name contains, or is
        contained by, the store's) flagged 'fuzzy'; otherwise 'ambiguous'/'unmatched'
        and left for a human. Returns a list of
        (store_code, store_name, config_id, config_name, method). Writes xids only
        for exact+fuzzy matches when ``commit`` (idempotent — skips existing).
        """
        p24 = self.env["retail.import.profile"].search([("file_type", "=", "x24")], limit=1)
        ns = p24.namespace if p24 else "levis"
        if stores is None:
            stores = self._x24_stores_from_staged()
        norm_cfg = defaultdict(list)
        for c in self.env["pos.config"].search([]):
            norm_cfg[self._norm_store_name(c.name)].append(c)

        report, written = [], 0
        for code in sorted(stores):
            _sap, name = stores[code]
            sn = self._norm_store_name(name)
            cfg, method = False, "unmatched"
            if sn and len(norm_cfg.get(sn, [])) == 1:
                cfg, method = norm_cfg[sn][0], "exact"
            elif sn:
                cands = {c.id: c for nn, cs in norm_cfg.items() if nn
                         and (nn.startswith(sn) or sn.startswith(nn)) for c in cs}
                if len(cands) == 1:
                    cfg, method = list(cands.values())[0], "fuzzy"
                elif len(cands) > 1:
                    method = "ambiguous"
            report.append((code, name, cfg.id if cfg else None,
                           cfg.name if cfg else None, method))
            if commit and cfg:
                xn = self._safe_xid("posconfig_", code)
                if not self._xid_get(ns, xn, "pos.config"):
                    self._xid_set(ns, xn, "pos.config", cfg.id)
                    written += 1
        if commit:
            self.env.cr.commit()
            _logger.info("x24 store->config: %s xids written", written)
        return report

    def _x24_seed_payment_methods(self):
        """Idempotently create the 4 tender methods missing from the seed (Decision D).

        Creates AMEX/OVO/SODEXO (+ folds OTHER_CARD into OFFLINE_OTHER_CREDITCARD) per
        company that already has POS methods, and links them to that company's configs.
        Returns a summary dict. Safe to call repeatedly.
        """
        Method = self.env["pos.payment.method"]
        created = {}
        companies = self.env["pos.config"].search([]).mapped("company_id")
        for company in companies:
            existing = Method.search([("company_id", "=", company.id)])
            names = set(existing.mapped("name"))
            template = existing.filtered(lambda m: m.name == "OFFLINE_OTHER_CREDITCARD")[:1] or existing[:1]
            for tname in self._X24_SEED_TENDERS:
                if tname in names:
                    continue
                vals = {"name": tname, "company_id": company.id}
                if template and template.journal_id:
                    vals["journal_id"] = template.journal_id.id
                m = Method.create(vals)
                created.setdefault(company.id, []).append(tname)
                # attach to that company's configs so map_method finds it
                cfgs = self.env["pos.config"].search([("company_id", "=", company.id)])
                for c in cfgs:
                    c.write({"payment_method_ids": [(4, m.id)]})
        # newly-seeded methods must also get their own GL receivable
        self._x24_ensure_method_gl_split()
        return created

    # ------------------------------------------------------------------
    # GL payment separation — one receivable account per tender type
    # ------------------------------------------------------------------
    def _x24_next_free_account_code(self, company, base):
        """First unused account code at/after ``base`` for ``company`` (codes are
        company-dependent in Odoo 19, so search under with_company)."""
        Account = self.env["account.account"].sudo().with_company(company)
        try:
            start = int(str(base)) + 100
        except (TypeError, ValueError):
            start = 1106000101
        for i in range(start, start + 5000):
            code = str(i)
            if not Account.search([("code", "=", code)], limit=1):
                return code
        raise UserError(_("Could not allocate a free account code near %s") % base)

    def _x24_recv_account_for(self, company, tender):
        """Get/create a distinct POS-receivable account for a tender type (reuse-first).

        Cloned from the company's default POS receivable (same account_type, reconcile)
        so it behaves identically but keeps each tender on its own GL line.
        """
        Account = self.env["account.account"].sudo().with_company(company)
        label = "POS Receivable - %s" % tender
        acc = Account.search([("name", "=", label)], limit=1)
        if acc:
            return acc
        default_recv = company.account_default_pos_receivable_account_id
        base = default_recv.with_company(company).code if default_recv else "1106000001"
        return Account.create({
            "name": label,
            "code": self._x24_next_free_account_code(company, base),
            "account_type": (default_recv.account_type if default_recv else "asset_receivable"),
            "reconcile": True,
            "company_ids": [(4, company.id)],
        })

    def _x24_ensure_method_gl_split(self):
        """Give every non-cash POS tender method its own receivable account so card /
        e-wallet settlements rest on distinct GL lines (awaiting bank settlement /
        X70T reconciliation) instead of the single shared default Trade Receivables.

        CASH is skipped on purpose: cash settles to its cash journal (Cash-on-hand) at
        close, so forcing a receivable on a cash method leaves the cash receivable
        uncleared and books a spurious Cash Difference. Auto per tender type
        (grouped by method name), reuse-first, idempotent.
        """
        Method = self.env["pos.payment.method"].sudo()
        summary = {}
        for company in self.env["pos.config"].search([]).mapped("company_id"):
            default_recv = company.account_default_pos_receivable_account_id
            acc_by_tender = {}
            for m in Method.search([("company_id", "=", company.id)]):
                if m.is_cash_count:
                    # Leave cash on the default POS receivable: POS' cash-control close
                    # settles it via the cash statement, and pointing a cash method at its
                    # own Cash-on-hand account instead makes the close hang in
                    # closing_control (move unbalanced by the cash amount).
                    continue
                if m.receivable_account_id and m.receivable_account_id != default_recv:
                    continue  # already separated
                tender = (m.name or "").strip() or "OTHER"
                if tender not in acc_by_tender:
                    acc_by_tender[tender] = self._x24_recv_account_for(company, tender)
                m.receivable_account_id = acc_by_tender[tender].id
                summary.setdefault(company.id, {})[tender] = \
                    summary.get(company.id, {}).get(tender, 0) + 1
        return summary

    # ------------------------------------------------------------------
    # Decouple mode — POS Suspense Clearing (sales posted before payment)
    # ------------------------------------------------------------------
    _X24_SUSPENSE_METHOD = "SUSPENSE"
    _X24_SUSPENSE_LABEL = "POS Suspense Clearing"

    def _x24_suspense_account(self, company):
        """Get/create the reconcilable POS Suspense Clearing account for a company.

        Sales in decouple mode book Dr Suspense / Cr Revenue+Tax at session close; the
        later X70D transfer credits it back per tender and reconciles. Cloned from the
        default POS receivable (same account_type, reconcile=True). Reuse-first by name.
        Mirrors _x24_recv_account_for."""
        Account = self.env["account.account"].sudo().with_company(company)
        acc = Account.search([("name", "=", self._X24_SUSPENSE_LABEL)], limit=1)
        if acc:
            return acc
        default_recv = company.account_default_pos_receivable_account_id
        base = default_recv.with_company(company).code if default_recv else "1106000001"
        return Account.create({
            "name": self._X24_SUSPENSE_LABEL,
            "code": self._x24_next_free_account_code(company, base),
            "account_type": (default_recv.account_type if default_recv else "asset_receivable"),
            "reconcile": True,
            "company_ids": [(4, company.id)],
        })

    def _x24_ensure_suspense_method(self):
        """Get/create a non-cash SUSPENSE pos.payment.method per company, backed by the
        POS Suspense Clearing account, attached to every config. Idempotent. Mirrors
        _x24_seed_payment_methods. Must NOT be is_cash_count (else the cash-control
        close misbehaves and _x24_ensure_method_gl_split would skip it)."""
        Method = self.env["pos.payment.method"].sudo()
        by_company = {}
        for company in self.env["pos.config"].search([]).mapped("company_id"):
            m = Method.search([("company_id", "=", company.id),
                               ("name", "=", self._X24_SUSPENSE_METHOD)], limit=1)
            if not m:
                existing = Method.search([("company_id", "=", company.id)])
                template = existing.filtered(
                    lambda x: x.name == "OFFLINE_OTHER_CREDITCARD")[:1] or existing[:1]
                vals = {"name": self._X24_SUSPENSE_METHOD, "company_id": company.id}
                if template and template.journal_id:
                    vals["journal_id"] = template.journal_id.id
                m = Method.create(vals)
            # Non-cash + own reconcilable suspense receivable.
            susp = self._x24_suspense_account(company)
            if m.receivable_account_id != susp:
                m.receivable_account_id = susp.id
            for c in self.env["pos.config"].search([("company_id", "=", company.id)]):
                if m not in c.payment_method_ids:
                    c.write({"payment_method_ids": [(4, m.id)]})
            by_company[company.id] = m
        return by_company

    def _aggregate_x24_by_sku_day(self, records):
        """Aggregate X24 rows to (store_code, closing_date, item_code) level.

        Multiple transactions (different transnum) on the same day for the same SKU
        are summed here. Returns a dict keyed by (store, date, sku) with aggregated
        qty, amount, unit price, and the source row_numbers for backtracking.
        """
        agg = {}
        for r in records:
            store = str(r.get("store_code") or "").strip()
            date = str(r.get("trans_date") or "").strip()
            sku = str(r.get("item_code") or r.get("sku") or "").strip()
            if not store or not sku:
                continue
            key = (store, date, sku)
            if key not in agg:
                agg[key] = {"qty": 0.0, "amount": 0.0, "unit_price": 0.0, "row_nums": []}
            entry = agg[key]
            qty = float(r.get("net_qty") or 0)
            amt = float(r.get("net_amount") or 0)
            entry["qty"] += qty
            entry["amount"] += amt
            if qty:
                entry["unit_price"] = amt / qty   # last non-zero row wins; close enough for staging
            entry["row_nums"].append(r.get("_row"))
        return agg

    def _group_x24(self, profile, file_b64):
        """Parse X24 and group rows into individual transactions (Phase-5 internal use).

        Returns {(store, date, register, transnum): [rows]} — one pos.order per key.
        For line-level aggregation use _aggregate_x24_by_sku_day() instead.
        """
        data = profile.read_records(file_b64)
        orders = defaultdict(list)
        for r in data["records"]:
            key = (r.get("store_code"), r.get("trans_date"), r.get("register"), r.get("transnum"))
            orders[key].append(r)
        return orders

    # ==================================================================
    # X70D — Tender detail (Phase 5, staged until X24 is enabled)
    # ==================================================================
    def _load_x70d(self, profile, file_b64, log):
        # Decouple mode: X70D drives the settlement — post the tender transfer
        # (Dr per-tender receivable / Cr Suspense) and reconcile the suspense lines.
        if self._x24_decouple_enabled():
            self._post_x70d_reconcile(profile, file_b64, log)
        else:
            self._stage_only(
                profile, file_b64, log,
                "X70D tender detail: staged (Phase-5 gated — depends on X24 enablement).",
            )

    def _post_x70d_reconcile(self, profile, file_b64, log):
        """Decouple-mode settlement: transfer POS Suspense Clearing to the real per-tender
        receivables and reconcile the suspense lines against the session-close debits.

        Prereq: X24 was posted in decouple mode (sales already sit on Suspense). Posts one
        RIREC ``account.move`` (Dr per-tender receivable / Cr Suspense) dated at the latest
        tender date, then reconciles all open suspense lines. Residual on the suspense
        account = sales whose payment never arrived (surfaced in the log note)."""
        ns = profile.namespace
        company = profile.company_id
        AML = self.env["account.move.line"].sudo()

        # Whole-file idempotency guard (mirror _post_x24 / _post_x31): refuse to re-run a
        # second X70D transfer over the same suspense balance — archive the prior first.
        prior = self.env["retail.import.log"].search(
            [("profile_id", "=", profile.id), ("state", "=", "imported"), ("id", "!=", log.id)], limit=1
        )
        if prior:
            raise UserError(
                _("X70D already reconciled (log #%s). Archive it before re-posting to "
                  "avoid double-crediting the suspense account.") % prior.id
            )

        # Stage the rows (audit trail) exactly like _stage_only, without the early return.
        data = profile.read_records(file_b64)
        records = data["records"]
        log.line_count = len(records)
        row_to_line = self._persist_lines(log, records) if records else {}
        if row_to_line:
            self.env["retail.import.line"].browse(
                [ln.id for ln in row_to_line.values()]).write({"state": "skipped"})
        self.env.cr.commit()

        susp = self._x24_suspense_account(company)
        by_tender = defaultdict(float)
        dates = []
        x70d_keys = set()
        for r in records:
            tt = str(r.get("tender_type") or "").strip()
            if not tt:
                continue  # blank tender_type = file total, not a payment
            tt = self._X24_TENDER_FOLD.get(tt, tt)
            try:
                amt = float(profile._parse_amount(r.get("tender_amount")) or 0)
            except Exception:
                amt = 0.0
            by_tender[tt] += amt
            d = profile._parse_date(r.get("trans_date"))
            if d:
                dates.append(d)
            x70d_keys.add(self._safe_xid("posorder_", "%s_%s_%s_%s" % (
                str(r.get("store_code") or "").strip(), str(r.get("trans_date") or "").strip(),
                str(r.get("register") or "").strip(), str(r.get("transnum") or "").strip())))

        by_tender = {t: round(a, 2) for t, a in by_tender.items() if round(a, 2)}
        if not by_tender:
            log.records_skipped = len(records)
            log.error_message = "X70D: no postable tenders (empty/zero amounts)."
            self.env.cr.commit()
            return

        # Transfer entry: Dr each per-tender receivable / Cr Suspense (total). RIREC journal.
        Journal = self.env["account.journal"].sudo()
        journal = Journal.search([("code", "=", "RIREC"), ("company_id", "=", company.id)], limit=1)
        if not journal:
            journal = Journal.create({
                "name": "Retail Import Reconciliation", "code": "RIREC",
                "type": "general", "company_id": company.id,
            })
        total = round(sum(by_tender.values()), 2)
        line_ids = []
        for tender, amt in sorted(by_tender.items()):
            recv = self._x24_recv_account_for(company, tender)
            line_ids.append((0, 0, {"account_id": recv.id, "debit": amt, "credit": 0.0,
                                    "partner_id": False, "name": f"X70D settlement {tender}"}))
        line_ids.append((0, 0, {"account_id": susp.id, "debit": 0.0, "credit": total,
                                "partner_id": False, "name": "X70D settlement (Suspense clearing)"}))
        gl_date = max(dates) if dates else datetime.now().date()
        move = self.env["account.move"].sudo().create({
            "move_type": "entry", "journal_id": journal.id, "date": gl_date,
            "company_id": company.id,
            "ref": f"X70D settlement transfer (log {log.id})", "line_ids": line_ids,
        })
        move.action_post()
        # Odoo bumps a past-dated entry to today on post; re-stamp within the same FY.
        try:
            if gl_date and move.date and gl_date.year == move.date.year and gl_date != move.date:
                newname = move.name
                mtag = "/%02d/" % move.date.month
                if newname and mtag in newname:
                    cand = newname.replace(mtag, "/%02d/" % gl_date.month)
                    if not self.env["account.move"].search_count(
                        [("journal_id", "=", journal.id), ("name", "=", cand), ("id", "!=", move.id)]):
                        newname = cand
                self.env.cr.execute("UPDATE account_move SET date=%s, name=%s WHERE id=%s",
                                    (gl_date, newname, move.id))
                self.env.cr.execute("UPDATE account_move_line SET date=%s WHERE move_id=%s",
                                    (gl_date, move.id))
                move.invalidate_recordset(["date", "name"])
                move.line_ids.invalidate_recordset(["date"])
        except Exception as be:
            _logger.warning("x70d reconcile: backdate skipped: %s", be)
        self._xid_set(ns, self._safe_xid("x70dreconcile_", str(log.id)), "account.move", move.id)

        # Reconcile all open suspense lines (session-close debits + this credit). Group by
        # partner because reconcile requires a single partner per receivable batch; POS
        # close lines are normally partner-less, matching our partner_id=False credit.
        open_lines = AML.search([
            ("account_id", "=", susp.id), ("company_id", "=", company.id),
            ("parent_state", "=", "posted"), ("reconciled", "=", False),
        ])
        by_partner = defaultdict(lambda: AML.browse())
        for ln in open_lines:
            by_partner[ln.partner_id.id] += ln
        reconciled_groups = 0
        for grp in by_partner.values():
            if len(grp) > 1:
                try:
                    grp.reconcile()
                    reconciled_groups += 1
                except Exception as re:
                    _logger.warning("x70d reconcile: group reconcile skipped: %s", re)

        # Per-transaction "sales without payment" report: posted X24 orders whose txn key
        # has no matching X70D tender (both sides run through the same _safe_xid transform).
        posted_xids = set(self.env["ir.model.data"].sudo().search([
            ("module", "=", ns), ("model", "=", "pos.order"),
            ("name", "=like", "posorder_%"),
        ]).mapped("name"))
        unpaid = posted_xids - x70d_keys
        # Re-read post-reconcile: fully-matched lines drop out; the sum of remaining
        # residuals is the true net open balance on the suspense account.
        still_open = AML.search([
            ("account_id", "=", susp.id), ("company_id", "=", company.id),
            ("parent_state", "=", "posted"), ("reconciled", "=", False),
        ])
        residual = round(sum(still_open.mapped("amount_residual")), 2)

        log.records_created = 1
        log.records_skipped = len(records)
        note = (f"X70D settlement: transfer move {move.name} posted "
                f"(Dr {len(by_tender)} tender receivables {total:.2f} / Cr Suspense); "
                f"reconciled {reconciled_groups} suspense group(s); "
                f"suspense residual {residual:.2f}.")
        if unpaid:
            note += (f" WARNING: {len(unpaid)} posted X24 sale(s) have no matching X70D "
                     f"tender (unpaid/unreconciled).")
        log.error_message = note
        self.env.cr.commit()
        _logger.info("x70d reconcile: move %s, %s tenders, total %.2f, residual %.2f, %s unpaid",
                     move.name, len(by_tender), total, residual, len(unpaid))

    # ==================================================================
    # Staged / reference-only loaders (parse + count + keep attachment)
    # ==================================================================
    def _stage_only(self, profile, file_b64, log, note):
        data = profile.read_records(file_b64)
        records = data["records"]
        log.line_count = len(records)
        log.records_skipped = len(records)
        log.error_message = note
        if records:
            row_to_line = self._persist_lines(log, records)
            line_ids = [ln.id for ln in row_to_line.values()]
            if line_ids:
                self.env["retail.import.line"].browse(line_ids).write({"state": "skipped"})
            self.env.cr.commit()
        _logger.info("%s: staged %s rows (no model writes)", profile.file_type, len(records))

    def _load_x70t(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X70T settlement: staged for reconciliation (Phase 5 decision).")

    def _x31_post_enabled(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "retail_import.x31_post_enabled", "0"
        ) in ("1", "true", "True")

    def _load_x31(self, profile, file_b64, log):
        """Post X31 promo discounts as a contra-revenue reclassification when
        ``retail_import.x31_post_enabled``; otherwise stage (legacy default)."""
        data = profile.read_records(file_b64)
        records = data["records"]
        log.line_count = len(records)
        if not records:
            log.records_skipped = 0
            return
        row_to_line = self._persist_lines(log, records)
        if self._x31_post_enabled():
            self._post_x31(profile, records, log, row_to_line)
        else:
            log.records_skipped = len(records)
            log.error_message = (
                "X31 discount journal: staged (set retail_import.x31_post_enabled=1 to post)."
            )
            self.env["retail.import.line"].search([("log_id", "=", log.id)]).write({"state": "skipped"})
            self.env.cr.commit()

    def _x31_income_account(self, company, prod):
        """The product's sale income account (the Gross Sales-<category> account X24
        posts revenue to). Use the full POS/accounting resolution chain (product →
        category → company fallback) via ``_get_product_accounts`` — the bare property
        is often unset and relies on that fallback."""
        p = prod.with_company(company)
        acc = p.property_account_income_id or p.categ_id.property_account_income_categ_id
        if not acc:
            try:
                acc = p._get_product_accounts().get("income")
            except Exception:
                acc = False
        if not acc:
            # Same generic fallback POS uses at close for products with no income
            # account (Gross Sales - Others), so the reclass grosses up the account
            # X24 actually credited.
            Account = self.env["account.account"].sudo().with_company(company)
            acc = (Account.search([("account_type", "=", "income"),
                                   ("name", "ilike", "gross sales"), ("name", "ilike", "other")], limit=1)
                   or Account.search([("account_type", "=", "income"),
                                      ("name", "ilike", "gross sales")], limit=1))
        return acc

    def _x31_discount_account(self, company, income_acct):
        """Category Sales-Discount contra account matching a Gross Sales income account
        (textile / footwear / accessories / miscellaneous)."""
        Account = self.env["account.account"].sudo().with_company(company)
        nm = (income_acct.name or "").lower()
        kw = ("textile" if "textile" in nm else
              "footwear" if ("footwear" in nm or "shoe" in nm) else
              "accessor" if "access" in nm else "misc")
        return (Account.search([("name", "ilike", "sales discount"), ("name", "ilike", kw)], limit=1)
                or Account.search([("name", "ilike", "sales discount"), ("name", "ilike", "misc")], limit=1)
                or Account.search([("name", "ilike", "sales discount")], limit=1))

    def _post_x31(self, profile, records, log, row_to_line):
        """Post X31 promo discounts as a NET-NEUTRAL contra-revenue reclassification:
        per category, Dr ``Sales Discount-<cat>`` / Cr ``Gross Sales-<cat>`` for the
        ex-VAT discount. This grosses revenue back up to list price and books the
        discount as a category contra-revenue, so the P&L shows gross sales + discounts
        by category WITHOUT double-counting X24's net sales (X24 stays unchanged).
        One journal entry per import, dated at the latest discount date; idempotent via
        the whole-file guard + an ``x31entry_<log>`` xid."""
        ns = profile.namespace
        company = profile.company_id
        Product = self.env["product.product"]

        prior = self.env["retail.import.log"].search(
            [("profile_id", "=", profile.id), ("state", "=", "imported"), ("id", "!=", log.id)], limit=1
        )
        if prior:
            raise UserError(
                _("X31 already posted (log #%s). Archive it before re-posting to avoid duplicate reclass.")
                % prior.id
            )
        # Dedicated journal so the (period-dated) reclass is not bumped to today by
        # Odoo's sequence-date monotonicity against unrelated later moves in MISC.
        Journal = self.env["account.journal"].sudo()
        journal = Journal.search([("code", "=", "RIADJ"), ("company_id", "=", company.id)], limit=1)
        if not journal:
            journal = Journal.create({
                "name": "Retail Import Adjustments", "code": "RIADJ",
                "type": "general", "company_id": company.id,
            })
        tax = self._x24_resolve_tax()
        rate_val = (tax.amount / 100.0) if tax else 0.0

        prod_cache, by_pair, dates, ok_rows, errors = {}, defaultdict(float), [], [], []
        skipped = 0
        for r in records:
            code = str(r.get("product_code") or "").strip()
            disc = float(profile._parse_amount(r.get("discount_amount")) or 0)
            if not disc or not code:
                skipped += 1
                continue
            if code not in prod_cache:
                prod_cache[code] = Product.search([("default_code", "=", code)], limit=1)
            prod = prod_cache[code]
            inc = self._x31_income_account(company, prod) if prod else False
            dacc = self._x31_discount_account(company, inc) if inc else False
            if not prod or not inc or not dacc:
                skipped += 1
                rn = r.get("_row")
                if rn in row_to_line:
                    row_to_line[rn].write({
                        "state": "error",
                        "error_message": (f"X31: unpostable (product/income/discount acct) code={code}")[:250],
                    })
                errors.append((r.get("_row"), f"X31: no income/discount account for {code}"))
                continue
            by_pair[(inc.id, dacc.id)] += disc / (1.0 + rate_val)
            raw_dt = str(r.get("trans_date") or "").strip()
            d = profile._parse_date(raw_dt)
            if not d and raw_dt:
                try:
                    d = datetime.strptime(raw_dt[:10], "%Y-%m-%d").date()
                except ValueError:
                    d = None
            if d:
                dates.append(d)
            ok_rows.append(r.get("_row"))

        if not by_pair:
            log.records_skipped = len(records)
            log.error_message = "X31: no postable discounts (no resolvable products / amounts)."
            self.env.cr.commit()
            return

        line_ids = []
        for (inc_id, dacc_id), amt in by_pair.items():
            amt = round(amt, 2)
            line_ids.append((0, 0, {"account_id": dacc_id, "debit": amt, "credit": 0.0,
                                    "name": "POS promo discount (X31)"}))
            line_ids.append((0, 0, {"account_id": inc_id, "debit": 0.0, "credit": amt,
                                    "name": "POS promo discount gross-up (X31)"}))
        gl_date = max(dates) if dates else datetime.now().date()
        move = self.env["account.move"].create({
            "move_type": "entry", "journal_id": journal.id, "date": gl_date,
            "ref": f"X31 promo discount reclass (log {log.id})", "line_ids": line_ids,
        })
        move.action_post()
        # Odoo bumps a past-dated entry to today on post (sequence-date monotonicity).
        # Re-stamp the move + lines to the discount period via SQL within the same
        # fiscal year, aligning the sequence name's month so it stays consistent.
        try:
            if gl_date and move.date and gl_date.year == move.date.year and gl_date != move.date:
                newname = move.name
                mtag = "/%02d/" % move.date.month
                if newname and mtag in newname:
                    cand = newname.replace(mtag, "/%02d/" % gl_date.month)
                    if not self.env["account.move"].search_count(
                        [("journal_id", "=", journal.id), ("name", "=", cand), ("id", "!=", move.id)]):
                        newname = cand
                self.env.cr.execute("UPDATE account_move SET date=%s, name=%s WHERE id=%s",
                                    (gl_date, newname, move.id))
                self.env.cr.execute("UPDATE account_move_line SET date=%s WHERE move_id=%s",
                                    (gl_date, move.id))
                move.invalidate_recordset(["date", "name"])
                move.line_ids.invalidate_recordset(["date"])
        except Exception as be:
            _logger.warning("x31 POST: backdate skipped: %s", be)
        self._xid_set(ns, self._safe_xid("x31entry_", str(log.id)), "account.move", move.id)
        for rn in ok_rows:
            if rn in row_to_line:
                row_to_line[rn].write({"state": "ok", "target_model": "account.move",
                                       "target_res_id": move.id})
        log.records_created = 1
        log.records_skipped = skipped
        log.set_errors(errors)
        self.env.cr.commit()
        _logger.info("x31 POST: reclass move %s posted (%s categories, %s rows, %s skipped)",
                     move.name, len(by_pair), len(ok_rows), skipped)

    def _load_x32p(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X32P stock movement: reference/audit only (not replayed; see plan).")

    def _load_store_master(self, profile, file_b64, log):
        self._stage_only(
            profile, file_b64, log,
            "Store Master: warehouse creation is handled by the Track A odoo-shell loader "
            "(header-wise store columns). This profile is for row-wise enrichment only.",
        )

    def _load_x70(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X70 tender breakdown: staged for settlement reconciliation.")

    def _load_x26(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X26 shipping: staged for transfer-order mapping.")

    def _load_x29(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X29 inventory adjustment: staged for stock adjustment mapping.")

    def _x48_post_enabled(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "retail_import.x48_post_enabled", "0"
        ) in ("1", "true", "True")

    def _load_x48(self, profile, file_b64, log):
        """Post X48 customer returns as refund pos.orders when
        ``retail_import.x48_post_enabled``; otherwise stage (legacy default)."""
        data = profile.read_records(file_b64)
        records = data["records"]
        log.line_count = len(records)
        if not records:
            log.records_skipped = 0
            return
        row_to_line = self._persist_lines(log, records)
        if self._x48_post_enabled():
            self._post_x48(profile, records, log, row_to_line)
        else:
            log.records_skipped = len(records)
            log.error_message = (
                "X48 customer return: staged (set retail_import.x48_post_enabled=1 to post refunds)."
            )
            self.env["retail.import.line"].search([("log_id", "=", log.id)]).write({"state": "skipped"})
            self.env.cr.commit()

    def _post_x48(self, profile, records, log, row_to_line):
        """Post X48 customer returns as refund (negative) pos.orders, paid by a negative
        cash refund. Mirrors _post_x24 (product resolution + lazy-create, price-included
        tax, one session/config, close + backdate, idempotency). X48 carries no tender,
        so the refund is booked to the store CASH method by default."""
        ns = profile.namespace
        Product = self.env["product.product"]
        Order = self.env["pos.order"]

        prior = self.env["retail.import.log"].search(
            [("profile_id", "=", profile.id), ("state", "=", "imported"), ("id", "!=", log.id)], limit=1
        )
        if prior:
            raise UserError(
                _("X48 already posted (log #%s). Archive it before re-posting to avoid duplicate refunds.")
                % prior.id
            )

        self._x24_ensure_method_gl_split()
        tax = self._x24_resolve_tax()
        orders = self._x24_group_orders(records)

        cfg_cache, sess_cache, prod_bc, prod_dc = {}, {}, {}, {}
        created = skipped = 0
        errors = []
        strict_products = self._x24_strict_product_enabled()

        def resolve_config(store):
            if store not in cfg_cache:
                cid = self._xid_get(ns, self._safe_xid("posconfig_", store), "pos.config")
                cfg_cache[store] = self.env["pos.config"].browse(cid) if cid else False
            return cfg_cache[store]

        def get_session(cfg):
            if cfg.id not in sess_cache:
                s = self.env["pos.session"].create({"config_id": cfg.id, "user_id": self.env.uid})
                # Decision B: imported refunds are financial-only, no stock move
                # (matches X24). Override the company-derived flag post-create.
                if s.update_stock_at_closing:
                    s.update_stock_at_closing = False
                if s.state != "opened":
                    try:
                        s.set_opening_control(0, None)
                    except Exception:
                        pass
                    if s.state != "opened":
                        s.write({"state": "opened"})
                sess_cache[cfg.id] = s
            return sess_cache[cfg.id]

        def resolve_product(r):
            ean = str(r.get("ean") or "").strip()
            code = str(r.get("product_code") or r.get("item_code") or "").strip()
            if ean:
                if ean not in prod_bc:
                    prod_bc[ean] = Product._resolve_barcode(ean)
                if prod_bc[ean]:
                    return prod_bc[ean]
            if code:
                if code not in prod_dc:
                    prod_dc[code] = Product.search([("default_code", "=", code)], limit=1)
                if prod_dc[code]:
                    return prod_dc[code]
            # Strict mode: refuse to invent a product for an unregistered SKU — return
            # empty so the caller parks the whole refund until X101 is synced.
            if strict_products:
                return Product.browse()
            key = code or ean
            if not key:
                return Product.browse()
            xid = self._safe_xid("x24prod_", key)
            pid = self._xid_get(ns, xid, "product.product")
            if pid:
                p = Product.browse(pid)
            else:
                tmpl = self.env["product.template"].with_context(
                    tracking_disable=True, mail_create_nolog=True).create({
                        "name": (str(r.get("item_description") or "").strip() or key)[:200],
                        "default_code": code or False, "type": "consu", "sale_ok": True,
                    })
                p = tmpl.product_variant_id
                if ean and not p.barcode and not Product.search_count([("barcode", "=", ean)]):
                    try:
                        p.barcode = ean
                    except Exception:
                        pass
                self._xid_set(ns, xid, "product.product", p.id)
            if code:
                prod_dc[code] = p
            if ean:
                prod_bc[ean] = p
            return p

        def fail_rows(rows, msg):
            for r in rows:
                rn = r.get("_row")
                if rn in row_to_line:
                    row_to_line[rn].write({"state": "error", "error_message": msg[:250]})
            errors.append((rows[0].get("_row"), msg))

        rate_val = (tax.amount / 100.0) if tax else 0.0
        for key, rows in orders.items():
            store, date, reg, txn = key
            oxid = self._safe_xid("posreturn_", f"{store}_{date}_{reg}_{txn}")
            if self._xid_get(ns, oxid, "pos.order"):
                continue
            cfg = resolve_config(store)
            if not cfg:
                fail_rows(rows, f"store {store}: no pos.config (map xid posconfig_{store})")
                skipped += len(rows)
                continue
            cash = cfg.payment_method_ids.filtered(lambda m: m.is_cash_count)[:1]
            if not cash:
                fail_rows(rows, f"store {store}: no cash method for refund")
                skipped += len(rows)
                continue

            line_cmds, order_net, order_incl, missing = [], 0.0, 0.0, []
            for r in rows:
                prod = resolve_product(r)
                if not prod:
                    missing.append(str(r.get("product_code") or r.get("item_code") or r.get("ean") or "?"))
                    rn = r.get("_row")
                    if rn in row_to_line:
                        row_to_line[rn].write({
                            "state": "error",
                            "error_message": f"not in X101 master: ean={r.get('ean')!r} code={r.get('product_code')!r}"[:250],
                        })
                    continue
                qty = float(profile._parse_amount(r.get("net_qty")))        # negative
                incl = float(profile._parse_amount(r.get("total_amount")))  # negative (refund)
                gl_net = incl / (1.0 + rate_val)
                unit = incl / qty if qty else incl                          # positive unit price
                line_cmds.append((0, 0, {
                    "product_id": prod.id, "qty": qty,
                    "price_unit": unit, "discount": 0.0,
                    "tax_ids": [(6, 0, [tax.id] if tax else [])],
                    "price_subtotal": gl_net, "price_subtotal_incl": incl,
                }))
                order_net += gl_net
                order_incl += incl

            # Strict mode / any unresolved line: park the WHOLE refund rather than
            # posting a partial return.
            if missing:
                sku_list = ", ".join(sorted(set(missing))[:10])
                fail_rows(rows, f"store {store} txn {txn}: produk belum teregister di master X101 ({sku_list}) — sync X101 dulu")
                skipped += len(rows)
                continue
            if not line_cmds:
                fail_rows(rows, f"store {store} txn {txn}: no resolvable product")
                skipped += len(rows)
                continue

            d = profile._parse_date(date)
            dt = datetime(d.year, d.month, d.day, 12, 0, 0) if d else datetime.now()
            sess = get_session(cfg)
            try:
                with self.env.cr.savepoint():
                    order = Order.create({
                        "session_id": sess.id, "company_id": cfg.company_id.id,
                        "pricelist_id": cfg.pricelist_id.id or False, "date_order": dt,
                        "pos_reference": f"RET-{store}-{reg}-{txn}",
                        "lines": line_cmds,
                        "amount_tax": order_incl - order_net, "amount_total": order_incl,
                        "amount_paid": 0.0, "amount_return": 0.0,
                    })
                    order.add_payment({
                        "pos_order_id": order.id, "payment_method_id": cash.id,
                        "amount": order_incl, "payment_date": dt,
                    })
                    order.invalidate_recordset(["payment_ids", "amount_paid"])
                    order.amount_paid = sum(order.payment_ids.mapped("amount"))
                    if order.amount_total and abs(order.amount_paid - order.amount_total) <= self._X24_BALANCE_TOL:
                        order.action_pos_order_paid()
                    self._xid_set(ns, oxid, "pos.order", order.id)
            except Exception as e:
                fail_rows(rows, f"store {store} txn {txn}: refund post failed: {e}")
                skipped += len(rows)
                continue
            for r in rows:
                rn = r.get("_row")
                if rn in row_to_line:
                    row_to_line[rn].write({
                        "state": "ok", "target_model": "pos.order",
                        "target_res_id": order.id, "aggregate_key": f"RET|{store}|{date}|{txn}",
                    })
            created += 1
            if created % 200 == 0:
                self.env.cr.commit()

        self._pos_close_and_backdate(sess_cache.values(), errors, "x48")

        self.env.cr.commit()
        log.records_created = created
        log.records_skipped = skipped
        log.set_errors(errors)
        _logger.info("x48 POST: %s refund orders created, %s rows skipped, %s errors",
                     created, skipped, len(errors))

    def _load_x53(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X53 RTV: staged for vendor return mapping.")

    def _load_x53_ebr(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X53-EBR RTV (alternate format): staged for vendor return mapping.")

    def _load_x21(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X21 payment summary: staged for payment reconciliation.")

    def _load_x25n(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X25N receiving: staged for PO receipt mapping.")
