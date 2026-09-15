#!/usr/bin/env bash
# ============================================================
# install-ppob.sh — buat database PPOB/PPS dan pasang modulnya.
#
# Dijalankan DI VPS PPOB, dari root repo, SETELAH bootstrap.sh.
#
#   bash deploy/ppob-node/install-ppob.sh
#
# Urutan di bawah bukan selera — ini menghindari dua jebakan yang
# sudah pernah menjatuhkan DB rnd_ppob:
#
#  1. `-i l10n_id` HARUS lebih dulu dari modul PPOB. Di DB tanpa CoA,
#     hook custom_ppob_core membuat 19 akun sendiri; di akhir load_modules
#     modul `account` menjalankan _auto_install_template yang meng-unlink
#     akun placeholder -> ForeignKeyViolation pada
#     custom_ppob_account_mapping_account_id_fkey.
#  2. Mata uang perusahaan diset IDR SEBELUM ada jurnal. Sesudah ada
#     jurnal, currency perusahaan tidak bisa diubah lagi.
# ============================================================
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[[ -f .env ]] || { echo "[ERR ] .env tidak ada di $(pwd). Jalankan bootstrap.sh dulu."; exit 1; }
# Baca .env tanpa `source`: nilai bisa memuat spasi/karakter shell
# (mis. GRAFANA_ADMIN_PASSWORD) dan `.` akan mencoba mengeksekusinya.
envget() { grep -m1 "^${1}=" .env | cut -d= -f2- ; }
POSTGRES_USER="$(envget POSTGRES_USER)";         POSTGRES_USER="${POSTGRES_USER:-odoo}"
POSTGRES_PASSWORD="$(envget POSTGRES_PASSWORD)"
PPOB_DB_NAME="$(envget PPOB_DB_NAME)"
ODOO_HTTP_PORT="$(envget ODOO_HTTP_PORT)"
PPOB_INSTALL_ORACLE_BRIDGE="$(envget PPOB_INSTALL_ORACLE_BRIDGE)"
PPOB_ORACLE_DSN="$(envget PPOB_ORACLE_DSN)"

DB="${PPOB_DB_NAME:-ppob}"
COMPOSE=(docker compose -f docker-compose.yml -f deploy/ppob-node/docker-compose.ppob.yml)

color() { printf '\033[%sm%s\033[0m\n' "$1" "$2"; }
info()  { color "1;34" "[INFO ] $*"; }
ok()    { color "1;32" "[ OK  ] $*"; }
die()   { color "1;31" "[ERR  ] $*" >&2; exit 1; }

# custom_ppob_oracle_bridge sengaja TIDAK default: 3 cron-nya jalan tiap
# menit dan gagal terus selama DSN Oracle EVShop belum ada.
MODULES="custom_ppob_core,custom_ppob_wallet,custom_ppob_provider,custom_ppob_sale,custom_ppob_va,custom_ppob_commission,custom_ppob_rollup,custom_ppob_sla,custom_ppob_biller_digiflazz,custom_ppob_pps_gateway,custom_ppob_eraspace_bridge"
if [[ "${PPOB_INSTALL_ORACLE_BRIDGE:-0}" == "1" ]]; then
  [[ -n "${PPOB_ORACLE_DSN:-}" ]] || die "PPOB_INSTALL_ORACLE_BRIDGE=1 tapi PPOB_ORACLE_DSN kosong."
  MODULES="${MODULES},custom_ppob_oracle_bridge"
  info "oracle_bridge ikut dipasang (DSN terisi)."
fi

odoo_cli() { "${COMPOSE[@]}" exec -T -u odoo odoo odoo "$@"; }

pg() {
  "${COMPOSE[@]}" exec -T -e PGPASSWORD="${POSTGRES_PASSWORD}" postgres \
    psql -v ON_ERROR_STOP=1 -qtAX -U "${POSTGRES_USER:-odoo}" "$@"
}

# ------------------------------------------------------------
# 0. DB sudah ada?
# ------------------------------------------------------------
if [[ "$(pg -d postgres -c "SELECT 1 FROM pg_database WHERE datname='${DB}'")" == "1" ]]; then
  die "Database '${DB}' sudah ada. Hapus dulu (dropdb) atau ganti PPOB_DB_NAME — skrip ini tidak menimpa."
fi

# ------------------------------------------------------------
# 1. DB kosong: base saja, tanpa demo. `account` belum ikut,
#    jadi _auto_install_template belum bisa memuat generic_coa.
# ------------------------------------------------------------
info "Membuat database '${DB}' dengan modul base..."
odoo_cli -d "${DB}" -i base --without-demo=all --stop-after-init --no-http \
  || die "Init base gagal."
ok "Database '${DB}' dibuat."

# ------------------------------------------------------------
# 2. IDR sebelum CoA / jurnal apa pun.
# ------------------------------------------------------------
info "Menyetel mata uang perusahaan ke IDR..."
"${COMPOSE[@]}" exec -T -u odoo odoo odoo shell -d "${DB}" --no-http <<'PY'
idr = env['res.currency'].with_context(active_test=False).search([('name', '=', 'IDR')], limit=1)
assert idr, "IDR tidak ada di res.currency"
idr.active = True
company = env['res.company'].search([], limit=1, order='id')
company.currency_id = idr
company.country_id = env.ref('base.id')
env.cr.commit()
print("company=%s currency=%s country=%s" % (company.name, company.currency_id.name, company.country_id.code))
PY
ok "Mata uang IDR terpasang."

# ------------------------------------------------------------
# 3. CoA Indonesia — WAJIB sebelum modul PPOB.
# ------------------------------------------------------------
info "Memasang l10n_id (CoA Indonesia)..."
odoo_cli -d "${DB}" -i l10n_id --without-demo=all --stop-after-init --no-http \
  || die "Install l10n_id gagal."

tmpl=$(pg -d "${DB}" -c "SELECT chart_template FROM res_company ORDER BY id LIMIT 1")
# Di Odoo 19 kode chart template Indonesia adalah 'id' (kode negara), bukan
# literal 'l10n_id'. Yang harus DITOLAK adalah kasus rnd_ppob: 'generic_coa'
# (atau kosong), yang tak bisa dikoreksi setelah ada jurnal.
case "${tmpl}" in
  ""|generic*|*generic_coa*)
    die "chart_template = '${tmpl}' bukan CoA Indonesia. Jangan lanjut — hasilnya akan seperti rnd_ppob (generic_coa, tak bisa dikoreksi setelah ada jurnal)." ;;
esac
ok "chart_template = ${tmpl}"

# ------------------------------------------------------------
# 4. Modul PPOB.
# ------------------------------------------------------------
info "Memasang modul PPOB: ${MODULES}"
odoo_cli -d "${DB}" -i "${MODULES}" --without-demo=all --stop-after-init --no-http \
  || die "Install modul PPOB gagal — lihat log di atas."

# ------------------------------------------------------------
# 5. Verifikasi
# ------------------------------------------------------------
info "Verifikasi hasil..."
pg -d "${DB}" -c "
  SELECT name, latest_version, state
  FROM ir_module_module
  WHERE name LIKE 'custom_ppob%' OR name IN ('l10n_id','account')
  ORDER BY name;" | sed 's/^/    /'

echo "    -- ringkasan --"
pg -d "${DB}" -c "SELECT 'akun', count(*) FROM account_account
                  UNION ALL SELECT 'account_mapping', count(*) FROM custom_ppob_account_mapping
                  UNION ALL SELECT 'jurnal', count(*) FROM account_journal
                  UNION ALL SELECT 'cron aktif', count(*) FROM ir_cron WHERE active;" | sed 's/^/    /'

"${COMPOSE[@]}" restart odoo >/dev/null
ok "Selesai. Buka http://<ip-vps>:${ODOO_HTTP_PORT:-18069}/  (database: ${DB})"
echo
echo "Login admin awal: admin / admin — GANTI SEKARANG."
echo "Master password Odoo ada di .env (ODOO_ADMIN_PASSWD)."
