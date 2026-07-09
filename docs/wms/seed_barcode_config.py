# -*- coding: utf-8 -*-
# Seed barcode/label/printer configuration for guide screenshots.

log = []


def note(m):
    log.append(m)
    print("[seedbc]", m)


def safe(label, fn):
    try:
        with env.cr.savepoint():
            fn()
        note("OK " + label)
    except Exception as e:
        note("SKIP %s: %s" % (label, e))


company = env.company
prod_model = env["ir.model"]._get("product.product")
loc_model = env["ir.model"]._get("stock.location")


def seed_formats():
    F = env["custom.barcode.format"]
    if F.search([]):
        return
    F.create({"name": "Internal Product Code", "code": "Code128", "prefix": "LV-", "company_id": company.id})
    F.create({"name": "Location Bin Code", "code": "Code128", "prefix": "BIN-", "company_id": company.id})
    F.create({"name": "Retail EAN-13", "code": "EAN13", "company_id": company.id})
    # best-effort: scope first format to products if the m2m exists
    f0 = F.search([], limit=1)
    if "applied_models" in f0._fields and prod_model:
        try:
            f0.applied_models = [(6, 0, [prod_model.id])]
        except Exception:
            pass
    note("formats: %d" % F.search_count([]))


safe("barcode formats", seed_formats)


def seed_labels():
    L = env["custom.label.template"]
    if L.search([]):
        return
    zpl_prod = "^XA^FO20,20^A0N,28,28^FD{{product.display_name}}^FS^FO20,60^BCN,80,Y,N,N^FD{{barcode}}^FS^XZ"
    zpl_pallet = "^XA^FO30,30^A0N,40,40^FDPALLET {{pallet.name}}^FS^FO30,90^BCN,120,Y,N,N^FD{{sscc}}^FS^XZ"
    L.create(
        {
            "name": "Product Label (Zebra 2x1)",
            "paper_format": "zebra_2x1",
            "output_mode": "zpl",
            "template_source": zpl_prod,
            "applies_to": prod_model.id if prod_model else False,
            "company_id": company.id,
        }
    )
    L.create(
        {
            "name": "Pallet / SSCC (Zebra 4x6)",
            "paper_format": "zebra_4x6",
            "output_mode": "zpl",
            "template_source": zpl_pallet,
            "company_id": company.id,
        }
    )
    L.create(
        {
            "name": "Bin Location (Thermal 50x30)",
            "paper_format": "thermal_50x30",
            "output_mode": "escpos",
            "template_source": "[BIN] {{location.complete_name}}",
            "applies_to": loc_model.id if loc_model else False,
            "company_id": company.id,
        }
    )
    note("labels: %d" % L.search_count([]))


safe("label templates", seed_labels)


def seed_printers():
    P = env["custom.printer.config"]
    L = env["custom.label.template"]
    if P.search([]):
        return
    prod_lbl = L.search([("name", "ilike", "Product Label")], limit=1)
    pallet_lbl = L.search([("name", "ilike", "Pallet")], limit=1)
    P.create(
        {
            "name": "Receiving Dock - Zebra ZD420",
            "printer_type": "zebra_network",
            "host": "10.20.0.50",
            "port": 9100,
            "label_template_id": prod_lbl.id if prod_lbl else False,
            "company_id": company.id,
        }
    )
    P.create(
        {
            "name": "Pack Bench - Zebra ZT411",
            "printer_type": "zebra_network",
            "host": "10.20.0.51",
            "port": 9100,
            "label_template_id": pallet_lbl.id if pallet_lbl else False,
            "company_id": company.id,
        }
    )
    P.create(
        {
            "name": "Office - CUPS Queue",
            "printer_type": "cups",
            "cups_queue": "HP_LaserJet_Office",
            "company_id": company.id,
        }
    )
    note("printers: %d" % P.search_count([]))


safe("printers", seed_printers)

print("\n===== BARCODE CONFIG SEED =====")
for m in log:
    print(" -", m)
print("===============================")
