# -*- coding: utf-8 -*-
"""
demo_wms / 20 — Product master with EAN13 barcodes, brand sections, ABC class.

Run:
    docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_wms --no-http \
        < scripts/tenants/wms_demo/20_seed_products.py

Mirrors the deck's "article" master:
  * Storage TYPE  driver -> product.category (Footwear / Apparel).
  * Storage SECTION driver -> brand (NIKE / ADIDAS / PUMA), kept in the
    product category leaf so putaway product_domain can target it.
  * EAN13 barcode (valid check digit) on every variant for handheld scanning.
  * Lot tracking + expiration enabled (product_expiry) so GR can capture
    batch + expired-date, and FEFO/cycle-count have lots to work with.
  * abc_class set so by_abc_velocity putaway + ABC cycle-count sampling work.

Idempotent: skips products that already carry a wms_demo external id.
"""

env = env  # provided by `odoo shell`
log = lambda m: print("[20-prod] " + m)

NS = "wms_demo"
MARKER = "wms_demo.products_seeded"

if env["ir.config_parameter"].sudo().get_param(MARKER):
    log("ABORT: products already seeded (marker set). Clear it to re-run.")
else:
    Cat = env["product.category"]
    Tmpl = env["product.template"]
    IMD = env["ir.model.data"]

    def xid_set(name, model, res_id):
        if IMD.search([("module", "=", NS), ("name", "=", name)], limit=1):
            return
        IMD.create({"module": NS, "name": name, "model": model, "res_id": res_id, "noupdate": True})

    def xid_get(name):
        rec = IMD.search([("module", "=", NS), ("name", "=", name)], limit=1)
        return rec.res_id if rec else False

    def ean13(prefix12):
        """Return a valid EAN13 for a 12-digit numeric string."""
        s = "".join(ch for ch in str(prefix12) if ch.isdigit())[:12].ljust(12, "0")
        total = sum((3 if i % 2 else 1) * int(d) for i, d in enumerate(s))
        check = (10 - total % 10) % 10
        return s + str(check)

    # ------------------------------------------------------------------
    # Categories: JD Sport / {Footwear, Apparel}
    # ------------------------------------------------------------------
    def ensure_cat(name, parent_id, xid):
        rid = xid_get(xid)
        if rid:
            return Cat.browse(rid)
        c = Cat.create({"name": name, "parent_id": parent_id})
        xid_set(xid, "product.category", c.id)
        return c

    root = ensure_cat("JD Sport", False, "cat_root")
    cat_foot = ensure_cat("Footwear", root.id, "cat_footwear")
    cat_appa = ensure_cat("Apparel", root.id, "cat_apparel")
    # Real-time FIFO valuation so stock moves are meaningful in the demo.
    for c in (cat_foot, cat_appa):
        c.write({"property_cost_method": "fifo", "property_valuation": "real_time"})
    log("categories ready: Footwear, Apparel")

    # ------------------------------------------------------------------
    # Products. (name, default_code, brand, categ, abc, list_price, ean12, volume_m3)
    # ------------------------------------------------------------------
    PRODUCTS = [
        ("Nike Air Zoom Pegasus", "NK-PEG-42", "NIKE", cat_foot, "A", 1899000, "899000000001", 0.012),
        ("Nike Court Vision Low", "NK-CRT-41", "NIKE", cat_foot, "B", 1099000, "899000000002", 0.012),
        ("Adidas Ultraboost 22", "AD-ULT-42", "ADIDAS", cat_foot, "A", 2799000, "899000000003", 0.012),
        ("Adidas Samba OG", "AD-SMB-43", "ADIDAS", cat_foot, "B", 1599000, "899000000004", 0.012),
        ("Puma RS-X", "PM-RSX-42", "PUMA", cat_foot, "C", 1499000, "899000000005", 0.012),
        ("Nike Dri-FIT Tee", "NK-TEE-M", "NIKE", cat_appa, "B", 399000, "899000000006", 0.002),
        ("Adidas Tiro Track Pant", "AD-TIR-M", "ADIDAS", cat_appa, "B", 699000, "899000000007", 0.003),
        ("Puma Essentials Hoodie", "PM-HOD-L", "PUMA", cat_appa, "C", 599000, "899000000008", 0.004),
    ]

    created = 0
    for name, code, brand, categ, abc, price, ean12, vol in PRODUCTS:
        xid = "prod_" + code.lower().replace("-", "_")
        if xid_get(xid):
            continue
        tmpl = Tmpl.create(
            {
                "name": name,
                "default_code": code,
                "barcode": ean13(ean12),
                "categ_id": categ.id,
                "type": "consu",
                "is_storable": True,
                "tracking": "lot",
                "use_expiration_date": True,
                "expiration_time": 720,  # informational shelf life (days)
                "list_price": price,
                "standard_price": round(price * 0.6),
                "volume": vol,
                "abc_class": abc,
                # Brand (= storage section) is encoded in default_code prefix
                # (NK-/AD-/PM-) and used by the putaway product_domain rules.
            }
        )
        xid_set(xid, "product.template", tmpl.id)
        created += 1

    log("products created: %d (lot-tracked, expiry-enabled, EAN13)" % created)
    env["ir.config_parameter"].sudo().set_param(MARKER, "1")
    env.cr.commit()
    log("DONE — product master committed.")
