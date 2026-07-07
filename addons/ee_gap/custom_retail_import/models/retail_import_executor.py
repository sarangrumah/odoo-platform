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

from psycopg2.extras import execute_values

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BATCH = 200
RAW_JSON_CAP = 8000

# Size values that mean "one size" / no real size — treated as NO size so the
# product stays plain (no Size attribute / no configurable variant). Mirrors how
# inseam already maps "-" to "". Caps, backpacks, beanies etc. use "OS".
ONE_SIZE_TOKENS = {"OS", "ONE SIZE", "ONESIZE", "O/S", "OSFA", "FREE", "F", "NS", "N/S", "-", ""}


class _LineBuffer:
    """Accumulate per-row log lines and flush them in bulk.

    Flushing just ``create()``s the lines; the surrounding loader's existing
    ``cr.commit()`` calls persist them. Flush is automatic every ``flush_every``
    rows (to bound memory) and must be called once more at the end via ``flush()``.
    ``raw_json`` is kept only for error/duplicate rows to bound storage.
    """

    def __init__(self, log, flush_every=2000, keep_statuses=None):
        self.log = log
        self.flush_every = flush_every
        self.pending = []
        self.counts = defaultdict(int)
        # None -> store every row; a set -> store only those statuses (counts stay
        # exact regardless). Used to skip created/updated rows on huge imports.
        self.keep = keep_statuses

    def add(self, status, row=0, ref_key=None, message=None, model_name=None, res_id=None, raw=None):
        self.counts[status] += 1
        if self.keep is not None and status not in self.keep:
            return
        vals = {"status": status, "row": int(row or 0)}
        if ref_key:
            vals["ref_key"] = str(ref_key)[:255]
        if message:
            vals["message"] = str(message)
        if model_name:
            vals["model_name"] = model_name
        if res_id:
            vals["res_id"] = res_id
        if raw is not None and status in ("error", "duplicate"):
            vals["raw_json"] = json.dumps(raw, default=str, ensure_ascii=False)[:RAW_JSON_CAP]
        self.pending.append(vals)
        if len(self.pending) >= self.flush_every:
            self.flush()

    def flush(self):
        if self.pending:
            self.log._log_lines(self.pending)
            self.pending = []


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
            log.write(
                {
                    "state": "failed",
                    "error_message": "No stored source file on log.",
                    "finished_at": fields.Datetime.now(),
                }
            )
            log._notify_failure()
            return log
        log.write({"state": "running", "started_at": fields.Datetime.now()})
        self._checkpoint()
        handler = getattr(self, f"_load_{profile.file_type}", None)
        if handler is None:
            log.write(
                {
                    "state": "failed",
                    "error_message": f"No executor for file_type {profile.file_type!r}.",
                    "finished_at": fields.Datetime.now(),
                }
            )
            self._checkpoint()
            log._notify_failure()
            return log
        try:
            handler(profile, file_b64, log)
        except UserError:
            self.env.cr.rollback()
            raise
        except Exception as e:  # pragma: no cover - defensive
            self.env.cr.rollback()
            _logger.exception("Retail import failed (log %s)", log.id)
            log.write({"state": "failed", "error_message": str(e), "finished_at": fields.Datetime.now()})
            self._checkpoint()
            log._notify_failure()
            return log
        if log.state == "running":
            log.state = "partial" if log.error_count else "imported"
        log.finished_at = fields.Datetime.now()
        self._checkpoint()
        return log

    @staticmethod
    def _tick(log, processed):
        """Update the live row-progress counter (committed by the caller's commit)."""
        log.processed_count = processed

    # Statuses always worth storing as detail rows, even on huge imports.
    _EXCEPTION_STATUSES = {"error", "duplicate", "skipped", "archived"}

    def _line_buffer(self, log, n_rows):
        """Build a line buffer; on large imports keep only exception rows.

        Above ``retail_import.line_detail_threshold`` (default 20000) we stop
        storing created/updated detail rows — they are the bulk of a master-data
        file — and keep only errors/duplicates/skipped/archived. Headline counters
        (records_created/updated/...) stay exact either way. Set the threshold to 0
        to always store every row.
        """
        thr = self.env["ir.config_parameter"].sudo().get_param("retail_import.line_detail_threshold", "20000")
        try:
            thr = int(thr)
        except (TypeError, ValueError):
            thr = 20000
        keep = None if (thr <= 0 or n_rows <= thr) else set(self._EXCEPTION_STATUSES)
        return _LineBuffer(log, keep_statuses=keep)

    def _checkpoint(self):
        """Commit if allowed; inside a queue job (commits forbidden) flush instead.

        The executor commits in batches (large X101 imports + live progress). Under
        queue_job, commits are forbidden unless the job function has Allow Commit and
        the worker honors it; to stay robust across workers/containers we fall back to
        flushing. The work then stays in the job's single transaction, which queue_job
        commits once at the end. In synchronous runs (wizard / sync feed) this is a
        real commit, so batched progress remains visible.
        """
        try:
            self.env.cr.commit()
        except RuntimeError:
            self.env.flush_all()

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
        # Skip chatter/tracking/recompute overhead for the bulk product writes.
        self = self.with_context(
            tracking_disable=True,
            mail_create_nolog=True,
            mail_create_nosubscribe=True,
            mail_notrack=True,
        )
        data = profile.read_records(file_b64)
        records = data["records"]
        log.line_count = len(records)
        buf = self._line_buffer(log, len(records))

        # ---- aggregate (mirror of 01_extract_x101.py) ----
        sku_best = {}  # sku -> (eff, dict)  (primary = latest by price_eff)
        sku_first_row = {}  # sku -> source row of its first occurrence
        sku_gtins = defaultdict(set)  # sku -> {all distinct GTINs seen for it}
        seen_sku_gtin = set()  # (sku, gtin) pairs, for precise duplicate detection
        tmpl_meta = {}  # code -> dict
        sizes, inseams = set(), set()
        tmpl_variants = defaultdict(set)
        for r in records:
            pc = r.get("product_code")
            sku = r.get("sku")
            if not pc or not sku:
                buf.add("skipped", row=r.get("_row"), ref_key=sku or pc, message="Missing product_code or sku")
                continue
            size = (r.get("size") or "").strip()
            if size.upper() in ONE_SIZE_TOKENS:
                size = ""  # one-size (e.g. "OS") -> no Size attribute -> plain product
            inseam_raw = r.get("inseam")
            inseam = str(inseam_raw).strip() if inseam_raw not in (None, "-", "") else ""
            gtin = str(r.get("gtin") or "").strip()
            if sku not in sku_first_row:
                sku_first_row[sku] = r.get("_row")
            if gtin:
                sku_gtins[sku].add(gtin)
            # A row is a TRUE duplicate only when the same (SKU, GTIN) repeats. Same
            # SKU with a DIFFERENT GTIN is an alternate barcode of the same variant,
            # not a duplicate -> kept and stored as product.barcode below.
            sg = (sku, gtin)
            if sg in seen_sku_gtin:
                buf.add(
                    "duplicate",
                    row=r.get("_row"),
                    ref_key=sku,
                    message=f"Duplicate (same SKU+GTIN) of row {sku_first_row[sku]}",
                    raw=r,
                )
            else:
                seen_sku_gtin.add(sg)
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
            len(records),
            len(tmpl_meta),
            len(sku_best),
            len(sizes),
            len(inseams),
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
                rid = self.env["product.category"].create({"name": cls, "parent_id": xid_to_cat.get(cat_xid(cat))}).id
                self._xid_set(ns, xid, "product.category", rid)
            xid_to_cat[xid] = rid
        for cat, cls, sub in sorted(l3):
            xid = sub_xid(cat, cls, sub)
            rid = self._xid_get(ns, xid, "product.category")
            if not rid:
                rid = (
                    self.env["product.category"]
                    .create({"name": sub, "parent_id": xid_to_cat.get(cls_xid(cat, cls))})
                    .id
                )
                self._xid_set(ns, xid, "product.category", rid)
            xid_to_cat[xid] = rid
        self._checkpoint()

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
        self._checkpoint()

        # ---- templates ----
        tmpl_xid_to_id = {}
        for ext in self.env["ir.model.data"].search([("module", "=", ns), ("model", "=", "product.template")]):
            tmpl_xid_to_id[ext.name] = ext.res_id
        created = 0
        created_txids = set()
        items = sorted(tmpl_meta.items())
        n_items = max(1, len(items))
        Template = self.env["product.template"]
        IMD = self.env["ir.model.data"]
        for start in range(0, len(items), BATCH):
            batch_vals, batch_txids = [], []
            seen_in_batch = set()
            for pc, m in items[start : start + BATCH]:
                txid = self._safe_xid("tmpl_", pc)
                if txid in tmpl_xid_to_id or txid in seen_in_batch:
                    continue
                seen_in_batch.add(txid)
                vset = tmpl_variants[pc]
                t_sizes = sorted({s for s, _ in vset if s})
                t_inseams = sorted({i for _, i in vset if i})
                attr_lines = []
                if t_sizes:
                    attr_lines.append(
                        (
                            0,
                            0,
                            {
                                "attribute_id": attr_by_name["Size"].id,
                                "value_ids": [(6, 0, [attr_value_id[("Size", s)] for s in t_sizes])],
                            },
                        )
                    )
                if t_inseams:
                    attr_lines.append(
                        (
                            0,
                            0,
                            {
                                "attribute_id": attr_by_name["Inseam"].id,
                                "value_ids": [(6, 0, [attr_value_id[("Inseam", i)] for i in t_inseams])],
                            },
                        )
                    )
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
                    "is_storable": True,  # track stock (X20 opening, X24 sales reduce on-hand)
                    "sale_ok": True,
                    "purchase_ok": True,
                }
                if categ_id:
                    vals["categ_id"] = categ_id
                if attr_lines:
                    vals["attribute_line_ids"] = attr_lines
                batch_vals.append(vals)
                batch_txids.append(txid)
            if batch_vals:
                # Idempotency / concurrency guard: skip any external id already in the
                # DB right now (created by a prior partial run or a parallel worker),
                # not just the start-of-run snapshot. Prevents the unique-constraint
                # crash on re-runs and lets an interrupted import resume cleanly.
                existing = set(
                    IMD.search(
                        [
                            ("module", "=", ns),
                            ("model", "=", "product.template"),
                            ("name", "in", batch_txids),
                        ]
                    ).mapped("name")
                )
                if existing:
                    for ext in IMD.search(
                        [
                            ("module", "=", ns),
                            ("model", "=", "product.template"),
                            ("name", "in", list(existing)),
                        ]
                    ):
                        tmpl_xid_to_id[ext.name] = ext.res_id
                new = [(t, v) for t, v in zip(batch_txids, batch_vals) if t not in existing]
                if new:
                    tmpls = Template.create([v for _, v in new])
                    imd_vals = []
                    for (txid, _v), tmpl in zip(new, tmpls):
                        tmpl_xid_to_id[txid] = tmpl.id
                        created_txids.add(txid)
                        imd_vals.append(
                            {
                                "module": ns,
                                "name": txid,
                                "model": "product.template",
                                "res_id": tmpl.id,
                                "noupdate": True,
                            }
                        )
                    IMD.create(imd_vals)
                    created += len(tmpls)
            self._tick(log, int(log.line_count * 0.5 * min(1.0, (start + BATCH) / n_items)))
            buf.flush()
            self._checkpoint()
        # records_created is set per-variant at the end (see below); ``created`` here
        # counts product.template rows and is used only for logging.

        # ---- variants: match auto-generated by (size, inseam) and set sku/barcode ----
        size_val_id = {v: i for (a, v), i in attr_value_id.items() if a == "Size"}
        inseam_val_id = {v: i for (a, v), i in attr_value_id.items() if a == "Inseam"}
        by_tmpl = defaultdict(list)
        for _eff, v in sku_best.values():
            by_tmpl[self._safe_xid("tmpl_", v["tmpl_code"])].append(v)
        matched = unmatched = 0
        alt_total = 0
        uid = self.env.uid
        tkeys = list(by_tmpl.keys())
        n_tkeys = max(1, len(tkeys))
        for start in range(0, len(tkeys), 100):
            batch_xids = tkeys[start : start + 100]
            tmpl_ids = [tmpl_xid_to_id[x] for x in batch_xids if x in tmpl_xid_to_id]
            if not tmpl_ids:
                for x in batch_xids:
                    for v in by_tmpl[x]:
                        buf.add(
                            "skipped",
                            row=sku_first_row.get(v["sku"]),
                            ref_key=v["sku"],
                            message="No template for this SKU",
                        )
                    unmatched += len(by_tmpl[x])
                continue
            variants = self.env["product.product"].search([("product_tmpl_id", "in", tmpl_ids)])
            var_index = {}
            cur_code, cur_bc = {}, {}
            for vp in variants:
                combo = frozenset(vp.product_template_variant_value_ids.product_attribute_value_id.ids)
                var_index[(vp.product_tmpl_id.id, combo)] = vp.id
                cur_code[vp.id] = vp.default_code
                cur_bc[vp.id] = vp.barcode
            # Collect SKU/barcode assignments and apply them with ONE bulk SQL UPDATE
            # per batch instead of ~160k per-variant ORM writes. Keyed by variant id
            # (last write wins, matching the old per-row behavior).
            var_updates = {}
            alt_rows = set()  # {(variant_id, alt_gtin)} -> product.barcode upsert
            for txid in batch_xids:
                tid = tmpl_xid_to_id.get(txid)
                is_new = txid in created_txids
                if not tid:
                    for v in by_tmpl[txid]:
                        buf.add(
                            "skipped",
                            row=sku_first_row.get(v["sku"]),
                            ref_key=v["sku"],
                            message="No template for this SKU",
                        )
                    unmatched += len(by_tmpl[txid])
                    continue
                for v in by_tmpl[txid]:
                    wanted = set()
                    if v["size"] and size_val_id.get(v["size"]):
                        wanted.add(size_val_id[v["size"]])
                    if v["inseam"] and inseam_val_id.get(v["inseam"]):
                        wanted.add(inseam_val_id[v["inseam"]])
                    vid = var_index.get((tid, frozenset(wanted)))
                    if not vid:
                        unmatched += 1
                        buf.add(
                            "skipped",
                            row=sku_first_row.get(v["sku"]),
                            ref_key=v["sku"],
                            message=f"No variant for size={v['size']!r} inseam={v['inseam']!r}",
                        )
                        continue
                    bc = v["gtin"] or None
                    code_change = cur_code.get(vid) != v["sku"]
                    bc_change = bool(bc) and cur_bc.get(vid) != bc
                    if code_change or bc_change:
                        var_updates[vid] = (v["sku"], bc if bc_change else None)
                    matched += 1
                    buf.add(
                        "created" if is_new else "updated",
                        row=sku_first_row.get(v["sku"]),
                        ref_key=v["sku"],
                        model_name="product.product",
                        res_id=vid,
                    )
                    # Extra GTINs of this SKU become scannable alternate barcodes on
                    # the SAME variant (one shared inventory; see X32P analysis).
                    for alt in sku_gtins.get(v["sku"], ()):
                        if alt and alt != v["gtin"]:
                            alt_rows.add((vid, alt))
            if var_updates:
                # barcode has no DB unique constraint (Python-only check); SQL is safe.
                # COALESCE keeps the existing barcode when the new one is NULL.
                execute_values(
                    self.env.cr,
                    "UPDATE product_product AS p SET "
                    "default_code = d.code::varchar, "
                    "barcode = COALESCE(d.barcode::varchar, p.barcode) "
                    "FROM (VALUES %s) AS d(id, code, barcode) WHERE p.id = d.id::integer",
                    [(vid, code, bc) for vid, (code, bc) in var_updates.items()],
                )
                self.env["product.product"].invalidate_model(["default_code", "barcode", "display_name"])
            if alt_rows:
                # Idempotent via the (product_id, barcode) unique index: re-imports
                # don't duplicate. Set audit columns explicitly (raw INSERT).
                execute_values(
                    self.env.cr,
                    "INSERT INTO product_barcode "
                    "(product_id, barcode, active, create_uid, create_date, write_uid, write_date) "
                    "VALUES %s ON CONFLICT (product_id, barcode) DO NOTHING",
                    [(vid, alt, uid, uid) for (vid, alt) in alt_rows],
                    template="(%s, %s, true, %s, now(), %s, now())",
                )
                alt_total += len(alt_rows)
            self._tick(log, int(log.line_count * (0.5 + 0.5 * min(1.0, (start + 100) / n_tkeys))))
            buf.flush()
            self._checkpoint()
        buf.flush()
        # Report counters per *variant* (SKU) so they line up with the row table:
        # a SKU under a newly-created template is "created", under a pre-existing
        # template "updated". ``created`` (templates) is kept only for the log line.
        log.records_created = buf.counts.get("created", 0)
        log.records_updated = buf.counts.get("updated", 0)
        log.records_matched = matched  # deprecated: total variants touched
        log.records_skipped = unmatched
        log.duplicate_count = buf.counts.get("duplicate", 0)
        log.processed_count = log.line_count
        if alt_total:
            self.env["product.barcode"].invalidate_model()
        self._checkpoint()
        _logger.info(
            "x101 done: templates=%s created=%s updated=%s unmatched=%s dup=%s alt_barcodes=%s",
            created,
            buf.counts.get("created", 0),
            buf.counts.get("updated", 0),
            unmatched,
            buf.counts.get("duplicate", 0),
            alt_total,
        )

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
        seen_codes = {}
        buf = self._line_buffer(log, len(records))
        Account = self.env["account.account"]
        for i, r in enumerate(records):
            code = str(r.get("code") or "").strip()
            name = (r.get("account_name") or r.get("name") or "").strip()
            atype = str(r.get("account_type") or "").strip()
            if not code or not name:
                buf.add("skipped", row=r.get("_row"), ref_key=code, message="Missing code or name")
                continue
            if code in seen_codes:
                buf.add(
                    "duplicate", row=r.get("_row"), ref_key=code, message=f"Duplicate of row {seen_codes[code]}", raw=r
                )
                continue
            seen_codes[code] = r.get("_row")
            if atype not in valid_types:
                errors.append((r.get("_row"), f"invalid account_type {atype!r} for {code}"))
                buf.add("error", row=r.get("_row"), ref_key=code, message=f"Invalid account_type {atype!r}", raw=r)
                continue
            xid = self._safe_xid("coa_", code)
            if self._xid_get(ns, xid, "account.account"):
                skipped += 1
                buf.add("skipped", row=r.get("_row"), ref_key=code, message="Already imported")
                continue
            existing = Account.with_company(company).search(
                [("code", "=", code), ("company_ids", "in", company.id)], limit=1
            )
            if existing:
                self._xid_set(ns, xid, "account.account", existing.id)
                skipped += 1
                buf.add(
                    "skipped",
                    row=r.get("_row"),
                    ref_key=code,
                    message="Account already exists",
                    model_name="account.account",
                    res_id=existing.id,
                )
                continue
            try:
                acc = Account.with_company(company).create(
                    {"code": code, "name": name, "account_type": atype, "company_ids": [(4, company.id)]}
                )
                self._xid_set(ns, xid, "account.account", acc.id)
                created += 1
                buf.add("created", row=r.get("_row"), ref_key=code, model_name="account.account", res_id=acc.id)
            except Exception as e:
                errors.append((r.get("_row"), f"{code}: {e}"))
                buf.add("error", row=r.get("_row"), ref_key=code, message=str(e), raw=r)
            if (i + 1) % 200 == 0:
                self._tick(log, i + 1)
        buf.flush()
        self._checkpoint()
        log.records_created = created
        log.records_skipped = skipped
        log.duplicate_count = buf.counts.get("duplicate", 0)
        log.processed_count = log.line_count
        # set_errors records error lines via _log_lines; CoA error lines were already
        # added above, so only update the counter + legacy summary here.
        log.error_count = len(errors)
        if errors:
            log.raw_payload = "\n".join(f"row {n}: {m}" for n, m in errors[:200])

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
            "nama": "name",
            "name": "name",
            "npwp": "vat",
            "vat": "vat",
            "alamat": "street",
            "address": "street",
            "telepon": "phone",
            "phone": "phone",
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
                for src, dst in (
                    ("name", "name"),
                    ("vat", "vat"),
                    ("street", "street"),
                    ("phone", "phone"),
                    ("email", "email"),
                ):
                    if r.get(src):
                        vals[dst] = str(r.get(src)).strip()
        if vals:
            company.write({k: v for k, v in vals.items() if k in ("name",)})
            company.partner_id.write({k: v for k, v in vals.items() if k != "name"})
            log.records_matched = 1
            log.records_updated = 1
            log._log_lines(
                [
                    {
                        "status": "updated",
                        "row": 0,
                        "ref_key": company.name,
                        "message": "Company / partner fields updated: " + ", ".join(sorted(vals)),
                        "model_name": "res.company",
                        "res_id": company.id,
                    },
                ]
            )
        log.processed_count = log.line_count
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
        applied = skipped = error_count = 0
        buf = self._line_buffer(log, len(records))
        quant_vals = []  # (prod, loc, qty, row, key)
        for r in records:
            store = r.get("store_code")
            ean = str(r.get("ean") or "").strip()
            item_id = str(r.get("item_id") or "").strip()
            key = ean or item_id
            qty = float(profile._parse_amount(r.get("onhand_qty")))
            if not store or qty <= 0:
                buf.add("skipped", row=r.get("_row"), ref_key=key, message="No store or qty <= 0")
                skipped += 1
                continue
            loc = resolve_location(store)
            if not loc:
                buf.add(
                    "error",
                    row=r.get("_row"),
                    ref_key=store,
                    message=f"Store {store} has no warehouse (run store loader first)",
                    raw=r,
                )
                error_count += 1
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
                # Row references a product that is not registered in the system.
                buf.add(
                    "error",
                    row=r.get("_row"),
                    ref_key=key,
                    message=_("Item produk tidak teregister: ean=%s item=%s") % (ean or "-", item_id or "-"),
                    raw=r,
                )
                error_count += 1
                continue
            quant_vals.append((prod, loc, qty, r.get("_row"), key))

        # Guard: refuse to re-apply if this profile already applied opening stock.
        prior = self.env["retail.import.log"].search(
            [("profile_id", "=", profile.id), ("state", "=", "imported"), ("id", "!=", log.id)], limit=1
        )
        if prior:
            raise UserError(
                _(
                    "Opening stock for profile %s was already applied (log #%s). "
                    "Re-applying would double the on-hand. Archive the prior log to override."
                )
                % (profile.code, prior.id)
            )

        for i, (prod, loc, qty, row, key) in enumerate(quant_vals):
            try:
                q = Quant.with_context(inventory_mode=True).create(
                    {"product_id": prod.id, "location_id": loc.id, "inventory_quantity": qty}
                )
                q.action_apply_inventory()
                applied += 1
                buf.add("created", row=row, ref_key=prod.default_code or key, model_name="stock.quant", res_id=q.id)
            except Exception as e:
                buf.add("error", row=row, ref_key=prod.default_code or key, message=str(e))
                error_count += 1
            if (i + 1) % 500 == 0:
                self._tick(log, len(records) - len(quant_vals) + i + 1)
                buf.flush()
                self._checkpoint()
        buf.flush()
        self._checkpoint()
        log.records_created = applied
        log.records_skipped = skipped
        log.error_count = error_count
        log.processed_count = log.line_count

    # ==================================================================
    # POS bootstrap + helpers (shared by X24 / X70D)
    # ==================================================================
    def _pos_bootstrap_store(self, profile, store_code, store_name):
        """Idempotently ensure POS infra for one store. Returns (config, ensure_pm)
        where ensure_pm(tender_type) creates+links a pos.payment.method and returns id.
        All artifacts are guarded by 'levis' external IDs so re-runs are no-ops."""
        ns = profile.namespace
        company = profile.company_id
        env = self.env
        # --- company-level (once) ---
        if company.point_of_sale_update_stock_quantities != "closing":
            company.point_of_sale_update_stock_quantities = "closing"
        if not company.account_default_pos_receivable_account_id:
            acc = env["account.account"].search(
                [("account_type", "=", "asset_receivable"), ("company_ids", "in", company.id)], limit=1
            )
            if acc:
                company.account_default_pos_receivable_account_id = acc.id
        # --- pricelist ---
        pl_id = self._xid_get(ns, "pricelist_idr", "product.pricelist")
        if not pl_id:
            pl = env["product.pricelist"].create(
                {"name": "Public Pricelist (IDR)", "currency_id": company.currency_id.id, "company_id": company.id}
            )
            self._xid_set(ns, "pricelist_idr", "product.pricelist", pl.id)
            pl_id = pl.id
        # --- journals ---
        cj_id = self._xid_get(ns, "journal_cash", "account.journal")
        if not cj_id:
            cj = env["account.journal"].search([("type", "=", "cash"), ("company_id", "=", company.id)], limit=1)
            if not cj:
                cj = env["account.journal"].create(
                    {"name": "Cash (POS)", "type": "cash", "code": "CSHPS", "company_id": company.id}
                )
            self._xid_set(ns, "journal_cash", "account.journal", cj.id)
            cj_id = cj.id
        cash_journal = env["account.journal"].browse(cj_id)
        bank_journal = env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", company.id)], limit=1)
        sale_journal = env["account.journal"].search([("type", "=", "sale"), ("company_id", "=", company.id)], limit=1)
        # --- warehouse (shared with X20 via wh_<store>) ---
        wh_xid = self._safe_xid("wh_", store_code)
        wh_id = self._xid_get(ns, wh_xid, "stock.warehouse")
        if not wh_id:
            code = ("S" + "".join(c for c in str(store_code) if c.isalnum()))[:5].upper()
            wh = env["stock.warehouse"].create(
                {"name": (store_name or str(store_code))[:60], "code": code, "company_id": company.id}
            )
            self._xid_set(ns, wh_xid, "stock.warehouse", wh.id)
            wh_id = wh.id
        warehouse = env["stock.warehouse"].browse(wh_id)

        # --- cash payment method (config needs >=1) ---
        def _make_pm(tender):
            xid = self._safe_xid("pm_", tender)
            pid = self._xid_get(ns, xid, "pos.payment.method")
            if not pid:
                journal = cash_journal if str(tender).upper() == "CASH" else (bank_journal or cash_journal)
                pm = env["pos.payment.method"].create(
                    {
                        "name": str(tender),
                        "journal_id": journal.id,
                        "company_id": company.id,
                        "split_transactions": False,
                    }
                )
                self._xid_set(ns, xid, "pos.payment.method", pm.id)
                pid = pm.id
            return pid

        cash_pm_id = _make_pm("CASH")
        # --- pos.config ---
        cfg_xid = self._safe_xid("pos_cfg_", store_code)
        cfg_id = self._xid_get(ns, cfg_xid, "pos.config")
        if not cfg_id:
            cfg = env["pos.config"].create(
                {
                    "name": store_name or ("Store %s" % store_code),
                    "company_id": company.id,
                    "journal_id": sale_journal.id,
                    "invoice_journal_id": sale_journal.id,
                    "picking_type_id": warehouse.out_type_id.id,
                    "payment_method_ids": [(4, cash_pm_id)],
                    "use_pricelist": True,
                    "pricelist_id": pl_id,
                    "available_pricelist_ids": [(6, 0, [pl_id])],
                }
            )
            self._xid_set(ns, cfg_xid, "pos.config", cfg.id)
            cfg_id = cfg.id
        config = env["pos.config"].browse(cfg_id)

        def ensure_pm(tender):
            pid = _make_pm(tender)
            if pid not in config.payment_method_ids.ids:
                # pos.config.write blocks payment-method changes while a session is open;
                # link directly via the m2m table (safe for this historical import).
                env.cr.execute(
                    "INSERT INTO pos_config_pos_payment_method_rel "
                    "(pos_config_id, pos_payment_method_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (config.id, pid),
                )
                config.invalidate_recordset(["payment_method_ids"])
            return pid

        ensure_pm("CASH")
        return config, ensure_pm, pl_id

    def _x24_product(self, ns, item_code, ean, desc, price):
        """Resolve an X24 line's product; lazy-create a non-merchandise product (carrier
        bags, vouchers, etc. sold at POS but absent from the X101 master) so the order
        is complete and its total balances against the X70D tender. Idempotent by xid."""
        P = self.env["product.product"]
        prod = P._resolve_barcode(ean) if ean else P.browse()
        if not prod and item_code:
            prod = P.search([("default_code", "=", item_code)], limit=1)
        if prod:
            return prod
        key = item_code or ean
        xid = self._safe_xid("x24prod_", key)
        pid = self._xid_get(ns, xid, "product.product")
        if pid:
            return P.browse(pid)
        tmpl = (
            self.env["product.template"]
            .with_context(tracking_disable=True, mail_create_nolog=True)
            .create(
                {
                    "name": (desc or key)[:200],
                    "default_code": item_code or False,
                    "type": "consu",
                    "list_price": price,
                    "sale_ok": True,
                }
            )
        )
        prod = tmpl.product_variant_id
        if ean and not prod.barcode and not P.search_count([("barcode", "=", ean)]):
            try:
                prod.barcode = ean
            except Exception:
                pass
        self._xid_set(ns, xid, "product.product", prod.id)
        return prod

    def _pos_tax_for_rate(self, company, rate):
        """Map an X24 tax_rate (e.g. 0.11) to a sale account.tax. None/0 -> empty list."""
        try:
            pct = round(float(rate or 0) * 100)
        except (TypeError, ValueError):
            pct = 0
        if pct <= 0:
            return self.env["account.tax"].browse()
        return self.env["account.tax"].search(
            [("type_tax_use", "=", "sale"), ("amount", "=", pct), ("company_id", "=", company.id)], limit=1
        )

    def _pos_session(self, profile, config, store_code):
        """Get/create ONE open pos.session per store. Odoo forbids >1 open session per
        config, so all of a store's historical orders share a single session; the GL
        move is retargeted to the latest order date when the session is closed (X70D)."""
        ns = profile.namespace
        sxid = self._safe_xid("pos_sess_", str(store_code))
        sid = self._xid_get(ns, sxid, "pos.session")
        if sid:
            return self.env["pos.session"].browse(sid)
        session = self.env["pos.session"].create({"config_id": config.id})  # auto-opens
        self._xid_set(ns, sxid, "pos.session", session.id)
        return session

    # ==================================================================
    # X24 — Retail sales -> historical pos.order (draft; paid by X70D)
    # ==================================================================
    def _load_x24(self, profile, file_b64, log):
        ns = profile.namespace
        company = profile.company_id
        self = self.with_context(tracking_disable=True, mail_create_nolog=True, mail_create_nosubscribe=True)
        orders = self._group_x24(profile, file_b64)
        log.line_count = sum(len(v) for v in orders.values())
        buf = self._line_buffer(log, log.line_count)
        Order = self.env["pos.order"]
        Product = self.env["product.product"]
        cfg_cache, processed, created = {}, 0, 0

        # Pre-flight lock-date check on the earliest date.
        days = sorted({profile._parse_date(k[1]) for k in orders if profile._parse_date(k[1])})
        if days:
            try:
                violated = company._get_violated_lock_dates(days[0], False)
            except Exception:
                violated = None
            if violated:
                raise UserError(
                    _(
                        "Accounting is locked on/before %s — open the period (or clear the lock date) "
                        "for the X24 history dates before importing."
                    )
                    % violated
                )

        for (store_code, trans_date_raw, register, transnum), rows in orders.items():
            day = profile._parse_date(trans_date_raw)
            if not store_code or not day:
                buf.add("skipped", ref_key=str(transnum), message="Missing store or date")
                processed += len(rows)
                continue
            store_name = (rows[0].get("store_name") or "").strip()
            if store_code not in cfg_cache:
                cfg_cache[store_code] = self._pos_bootstrap_store(profile, store_code, store_name)
            config, _ensure_pm, pl_id = cfg_cache[store_code]
            oref = "%s_%s_%s" % (store_code, register, transnum)
            oxid = self._safe_xid("pos_", oref)
            if self._xid_get(ns, oxid, "pos.order"):
                buf.add("skipped", ref_key=oref, message="Order already imported")
                processed += len(rows)
                continue
            # build lines
            line_vals, amt_total, amt_tax, bad = [], 0.0, 0.0, None
            for r in rows:
                ean = str(r.get("ean") or "").strip()
                item = str(r.get("item_code") or "").strip()
                prod = self._x24_product(
                    ns, item, ean, r.get("item_description"), float(profile._parse_amount(r.get("retail_price")) or 0)
                )
                if not prod:
                    bad = _("Item produk tidak teregister: ean=%s item=%s") % (ean or "-", item or "-")
                    break
                qty = float(profile._parse_amount(r.get("net_qty")) or 0)
                net = float(profile._parse_amount(r.get("net_amount")) or 0)  # ex-tax base
                total = float(profile._parse_amount(r.get("total_amount")) or 0)  # incl tax
                tax_amt = float(profile._parse_amount(r.get("tax_amount")) or 0)
                tax = self._pos_tax_for_rate(company, r.get("tax_rate"))
                if abs((total - net) - tax_amt) > max(2.0, qty):
                    bad = _("Line amounts inconsistent (net=%s total=%s tax=%s)") % (net, total, tax_amt)
                    break
                line_vals.append(
                    (
                        0,
                        0,
                        {
                            "product_id": prod.id,
                            "qty": qty,
                            "price_unit": (net / qty) if qty else net,  # ex-tax (tax 28 is price-excluded)
                            "discount": 0.0,
                            "tax_ids": [(6, 0, tax.ids)],
                            "price_subtotal": net,
                            "price_subtotal_incl": total,
                            "full_product_name": (r.get("item_description") or prod.display_name),
                        },
                    )
                )
                amt_total += total
                amt_tax += tax_amt
            if bad:
                buf.add("error", ref_key=oref, message=bad, raw=rows[0])
                processed += len(rows)
                continue
            session = self._pos_session(profile, config, store_code)
            order = Order.create(
                {
                    "company_id": company.id,
                    "session_id": session.id,
                    "config_id": config.id,
                    "pricelist_id": pl_id,
                    "partner_id": False,
                    "date_order": datetime.combine(day, datetime.min.time()).replace(hour=12),
                    "pos_reference": "Order %s" % oref,
                    "tracking_number": str(transnum),
                    "amount_tax": amt_tax,
                    "amount_total": amt_total,
                    "amount_paid": 0.0,
                    "amount_return": 0.0,
                    "lines": line_vals,
                    "state": "draft",
                    "to_invoice": False,
                }
            )
            self._xid_set(ns, oxid, "pos.order", order.id)
            buf.add("created", ref_key=oref, model_name="pos.order", res_id=order.id)
            created += 1
            processed += len(rows)
            if created % 50 == 0:
                self._tick(log, processed)
                buf.flush()
                self._checkpoint()
        buf.flush()
        log.records_created = created
        log.records_skipped = buf.counts.get("skipped", 0)
        log.error_count = buf.counts.get("error", 0)
        log.processed_count = log.line_count
        self._checkpoint()
        _logger.info("x24 done: %s orders created across %s stores", created, len(cfg_cache))

    def _group_x24(self, profile, file_b64):
        """Parse X24 and group rows into transactions (store, date, register, transnum)."""
        data = profile.read_records(file_b64)
        orders = defaultdict(list)
        for r in data["records"]:
            if not r.get("store_code") or str(r.get("store_code")).strip().lower().startswith("grand"):
                continue
            key = (r.get("store_code"), r.get("trans_date"), r.get("register"), r.get("transnum"))
            orders[key].append(r)
        return orders

    def _group_x70d(self, profile, file_b64):
        """Parse X70D and group tender rows by (store, date, register, transnum)."""
        data = profile.read_records(file_b64)
        groups = defaultdict(list)
        for r in data["records"]:
            if not r.get("store_code") or str(r.get("store_code")).strip().lower().startswith("grand"):
                continue
            key = (r.get("store_code"), r.get("trans_date"), r.get("register"), r.get("transnum"))
            groups[key].append(r)
        return groups

    # ==================================================================
    # X70D — Tender detail -> pos.payment; then close the day's session (GL)
    # ==================================================================
    def _load_x70d(self, profile, file_b64, log):
        ns = profile.namespace
        company = profile.company_id
        self = self.with_context(tracking_disable=True, mail_create_nolog=True, mail_create_nosubscribe=True)
        groups = self._group_x70d(profile, file_b64)
        log.line_count = sum(len(v) for v in groups.values())
        buf = self._line_buffer(log, log.line_count)
        Payment = self.env["pos.payment"]
        cfg_cache, touched, paid_n, processed = {}, set(), 0, 0

        for (store_code, trans_date_raw, register, transnum), tenders in groups.items():
            day = profile._parse_date(trans_date_raw)
            oref = "%s_%s_%s" % (store_code, register, transnum)
            oid = self._xid_get(ns, self._safe_xid("pos_", oref), "pos.order")
            if not oid:
                buf.add("error", ref_key=oref, message="No X24 order for this tender (upload X24 first)")
                processed += len(tenders)
                continue
            order = self.env["pos.order"].browse(oid)
            if store_code not in cfg_cache:
                store_name = (tenders[0].get("store_name") or "").strip()
                cfg_cache[store_code] = self._pos_bootstrap_store(profile, store_code, store_name)
            config, ensure_pm, _pl = cfg_cache[store_code]
            for seq, t in enumerate(tenders):
                pmt_xid = self._safe_xid("pmt_", "%s_%s" % (oref, seq))
                if self._xid_get(ns, pmt_xid, "pos.payment"):
                    continue
                tender_type = (t.get("tender_type") or "CASH").strip() or "CASH"
                pm_id = ensure_pm(tender_type)
                amount = float(profile._parse_amount(t.get("tender_amount")) or 0)
                pay = Payment.create(
                    {
                        "pos_order_id": order.id,
                        "payment_method_id": pm_id,
                        "amount": amount,
                        "payment_date": order.date_order,
                        "name": str(t.get("auth") or t.get("voucher") or ""),
                    }
                )
                self._xid_set(ns, pmt_xid, "pos.payment", pay.id)
            # mark paid if balanced
            if order.state == "draft":
                order._compute_amount_all() if hasattr(order, "_compute_amount_all") else None
                if abs((order.amount_paid or 0) - (order.amount_total or 0)) <= 1.0:
                    try:
                        order.action_pos_order_paid()
                        buf.add("created", ref_key=oref, model_name="pos.order", res_id=order.id)
                        paid_n += 1
                    except Exception as e:
                        buf.add("error", ref_key=oref, message="paid failed: %s" % e)
                else:
                    buf.add(
                        "error",
                        ref_key=oref,
                        message="Tenders %s != order total %s" % (order.amount_paid, order.amount_total),
                    )
            touched.add(store_code)
            processed += len(tenders)
            if processed % 50 == 0:
                self._tick(log, processed)
                buf.flush()
                self._checkpoint()

        # close each store's session -> posts GL; retarget move date to latest order day
        closed = 0
        for store_code in sorted(touched, key=str):
            sid = self._xid_get(ns, self._safe_xid("pos_sess_", str(store_code)), "pos.session")
            if not sid:
                continue
            session = self.env["pos.session"].browse(sid)
            if session.state in ("closed", "closing_control"):
                continue
            if any(o.state == "draft" for o in session.order_ids):
                buf.add("skipped", ref_key=str(store_code), message="Session has unpaid orders; not closed")
                continue
            dates = [d for d in session.order_ids.mapped("date_order") if d]
            gl_date = max(dates).date() if dates else fields.Date.context_today(self)
            try:
                self._close_session_backdated(session, gl_date)
                closed += 1
            except Exception as e:
                _logger.exception("session close failed store %s", store_code)
                buf.add("error", ref_key=str(store_code), message="close failed: %s" % e)
            self._checkpoint()

        buf.flush()
        log.records_created = paid_n
        log.records_matched = closed  # sessions posted to GL
        log.error_count = buf.counts.get("error", 0)
        log.processed_count = log.line_count
        self._checkpoint()
        _logger.info("x70d done: %s orders paid, %s day-sessions closed", paid_n, closed)

    def _close_session_backdated(self, session, day):
        """Close an open POS session and re-stamp its GL move(s) to the historical day.
        Odoo hardcodes the session move date to 'today', so we draft->rewrite date->post."""
        session.action_pos_session_closing_control()  # cash_control off -> validates + posts
        target = day
        moves = session.move_id
        for pk in session.picking_ids:
            moves |= pk.move_ids.account_move
        for m in moves:
            if not m or m.state != "posted":
                continue
            m = m.with_context(check_move_validity=False)
            m.button_draft()
            m.write({"date": target})
            if m.line_ids:
                m.line_ids.write({"date": target})
            m._post()
        return True

    # ==================================================================
    # Staged / reference-only loaders (parse + count + keep attachment)
    # ==================================================================
    def _stage_only(self, profile, file_b64, log, note):
        data = profile.read_records(file_b64)
        records = data["records"]
        log.line_count = len(records)
        log.records_skipped = len(records)
        log.error_message = note
        buf = self._line_buffer(log, len(records))
        for r in records:
            buf.add("skipped", row=r.get("_row"), message="Staged (no model writes)")
        buf.flush()
        log.processed_count = log.line_count
        _logger.info("%s: staged %s rows (no model writes)", profile.file_type, len(records))

    def _load_x70t(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X70T settlement: staged for reconciliation (Phase 5 decision).")

    def _load_x31(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X31 discount journal: staged for promo-accrual mapping (Phase 5).")

    def _load_x32p(self, profile, file_b64, log):
        self._stage_only(profile, file_b64, log, "X32P stock movement: reference/audit only (not replayed; see plan).")

    def _load_store_master(self, profile, file_b64, log):
        self._stage_only(
            profile,
            file_b64,
            log,
            "Store Master: warehouse creation is handled by the Track A odoo-shell loader "
            "(header-wise store columns). This profile is for row-wise enrichment only.",
        )
