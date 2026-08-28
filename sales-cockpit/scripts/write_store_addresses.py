# =============================================================================
# Write the 23 store addresses into Odoo.
#
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal \
#       --no-http --log-level=warn < scripts/write_store_addresses.py
#
# Creates one res.partner per store and links it to operating_unit.partner_id,
# which is NULL on all 25 units. pos_config.id == operating_unit.id one-for-one
# in this database, so the cockpit reaches an address as
# pos_config -> operating_unit -> res_partner and the "Konteks Pasar" table on
# /cockpit/actions fills itself in with no further change.
#
# Addresses collected from public sources on 20-Aug-2026. Two of them corrected
# the hand-written area mapping in sql/002 (already applied as sql/003):
#   * AEON BSD City is in Pagedangan, KABUPATEN Tangerang (15345), not Kota
#     Tangerang Selatan — BSD City straddles the boundary.
#   * Trans Studio Cibubur is at Jatikarya, Jatisampurna, KOTA BEKASI (17435);
#     several listing sites place it in Cimanggis, Depok. The kelurahan decides.
#
# Idempotent: a unit that already has a partner has that partner updated instead
# of a second one being created. Ends with env.cr.commit(), because odoo shell
# rolls back otherwise.
#
# Dump taken before the first run:
#   /home/odoo-erp/backups/pre-address-write-20260820/pre-address-write.sql
#   (res_partner, operating_unit, cockpit_area, cockpit_store_area)
# =============================================================================

ADDR = {
    2: ("Jl. Basuki Rahmat No. 8-12", "Kedungdoro, Kec. Tegalsari", "Surabaya", "60261", "JI"),
    3: ("Jl. Metro Pondok Indah Kav. IV", "Pondok Pinang, Kec. Kebayoran Lama", "Jakarta Selatan", "12310", "JK"),
    4: ("Jl. Metro Pondok Indah Blok III B", "Pondok Pinang, Kec. Kebayoran Lama", "Jakarta Selatan", "12310", "JK"),
    5: ("Jl. Boulevard Raya", "Kelapa Gading Timur, Kec. Kelapa Gading", "Jakarta Utara", "14240", "JK"),
    6: ("Jl. Asia Afrika Lot 19", "Gelora, Kec. Tanah Abang", "Jakarta Pusat", "10270", "JK"),
    7: ("Jl. M.H. Thamrin No. 1", "Menteng, Kec. Menteng", "Jakarta Pusat", "10310", "JK"),
    8: ("Jl. Gatot Subroto No. 289", "Cibangkong, Kec. Batununggal", "Bandung", "40273", "JB"),
    9: ("Jl. Letjen S. Parman Kav. 28", "Tanjung Duren Selatan, Kec. Grogol Petamburan", "Jakarta Barat", "11470", "JK"),
    10: ("Jl. Prof. Dr. Satrio Kav. 3-5", "Karet Kuningan, Kec. Setiabudi", "Jakarta Selatan", "12940", "JK"),
    11: ("Jl. KH. Noer Ali No. 1A", "Pekayon Jaya, Kec. Bekasi Selatan", "Bekasi", "17148", "JB"),
    12: ("Jl. BSD Raya Utama", "Pagedangan, Kec. Pagedangan", "Kabupaten Tangerang", "15345", "BT"),
    13: ("Jl. Sukajadi No. 131-139", "Cipedes, Kec. Sukajadi", "Bandung", "40162", "JB"),
    14: ("Jl. Puncak Indah Lontar No. 2", "Lidah Kulon, Kec. Lakarsantri", "Surabaya", "60227", "JI"),
    15: ("Jl. Jend. Sudirman Kav. 52-53, SCBD", "Senayan, Kec. Kebayoran Baru", "Jakarta Selatan", "12190", "JK"),
    16: ("Jl. Alternatif Cibubur", "Jatikarya, Kec. Jatisampurna", "Bekasi", "17435", "JB"),
    17: ("Jl. Dharmahusada Indah Timur No. 35-37", "Mulyorejo, Kec. Mulyorejo", "Surabaya", "60115", "JI"),
    18: ("Jl. KH. Noer Ali No. 1", "Kayuringin Jaya, Kec. Bekasi Selatan", "Bekasi", "17148", "JB"),
    19: ("Jl. Boulevard Barat Raya No. 12", "Kelapa Gading Barat, Kec. Kelapa Gading", "Jakarta Utara", "14240", "JK"),
    20: ("Jl. Asia Afrika No. 8", "Gelora, Kec. Tanah Abang", "Jakarta Pusat", "10270", "JK"),
    21: ("Jl. Pasir Kaliki No. 25-27", "Ciroyom, Kec. Andir", "Bandung", "40181", "JB"),
    22: ("Jl. Sultan Iskandar Muda No. 8", "Gandaria Utara, Kec. Kebayoran Lama", "Jakarta Selatan", "12240", "JK"),
    23: ("Jl. Magna Timur No. 1", "Rancabolang, Kec. Gedebage", "Bandung", "40296", "JB"),
    24: ("Jl. Merdeka No. 56", "Citarum, Kec. Bandung Wetan", "Bandung", "40115", "JB"),
}

ID = env["res.country"].search([("code", "=", "ID")], limit=1)
states = {s.code: s for s in env["res.country.state"].search([("country_id", "=", ID.id)])}

created, updated, skipped = 0, 0, 0
for ou_id, (street, street2, city, zip_code, state_code) in ADDR.items():
    ou = env["operating.unit"].browse(ou_id)
    if not ou.exists():
        print("SKIP: operating unit %s not found" % ou_id)
        skipped += 1
        continue

    vals = {
        "name": ou.name,
        "is_company": True,
        "street": street,
        "street2": street2,
        "city": city,
        "zip": zip_code,
        "state_id": states[state_code].id,
        "country_id": ID.id,
        "ref": "STORE-%s" % ou_id,
        "company_id": ou.company_id.id if ou.company_id else False,
        "comment": "Alamat toko, dihimpun dari sumber publik 20-Agu-2026 untuk analitik wilayah.",
    }

    if ou.partner_id:
        ou.partner_id.write(vals)
        updated += 1
    else:
        ou.partner_id = env["res.partner"].create(vals).id
        created += 1

env.cr.commit()
print("RESULT created=%s updated=%s skipped=%s" % (created, updated, skipped))
