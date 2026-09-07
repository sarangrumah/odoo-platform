#!/usr/bin/env bash
# ============================================================
# takeover.sh — arsipkan lalu matikan stack lama di VPS tujuan,
# supaya node PPOB bisa memakai port standar.
#
# Dijalankan DI VPS TUJUAN sebagai root, SEBELUM bootstrap.sh.
#
#   sudo bash takeover.sh                 # dry-run: hanya inventaris + rencana
#   sudo CONFIRM=yes-take-over bash takeover.sh
#
# SIFAT: reversibel. Skrip ini
#   - MENDUMP semua database Postgres yang ditemukan,
#   - MENYALIN bind-mount / volume yang dipakai container lama,
#   - MENGHENTIKAN container dan menyetel restart policy ke "no",
#   - MENONAKTIFKAN unit systemd yang memegang port target.
# Skrip ini TIDAK PERNAH: docker rm, docker volume rm, docker image
# prune, dropdb, atau rm -rf apa pun. Penghapusan permanen adalah
# keputusan manusia, dilakukan manual setelah arsip diverifikasi.
# ============================================================
set -euo pipefail

ARCHIVE_ROOT="${ARCHIVE_ROOT:-/var/backups/pre-ppob-takeover}"
STAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE="${ARCHIVE_ROOT}/${STAMP}"
PORTS_WANTED="${PORTS_WANTED:-80 8069 8072 5432 6379}"

color() { printf '\033[%sm%s\033[0m\n' "$1" "$2"; }
info()  { color "1;34" "[INFO ] $*"; }
ok()    { color "1;32" "[ OK  ] $*"; }
warn()  { color "1;33" "[WARN ] $*"; }
err()   { color "1;31" "[ERR  ] $*" >&2; }
die()   { err "$*"; exit 1; }

[[ $EUID -eq 0 ]] || die "Jalankan sebagai root."
DRY=1; [[ "${CONFIRM:-}" == "yes-take-over" ]] && DRY=0
(( DRY )) && warn "DRY-RUN. Tidak ada yang diubah. Ulangi dengan CONFIRM=yes-take-over untuk eksekusi."

# ------------------------------------------------------------
# 1. Inventaris
# ------------------------------------------------------------
info "Inventaris apa yang berjalan..."
echo "  -- container --"
docker ps --format '    {{.Names}}\t{{.Image}}\t{{.Ports}}' 2>/dev/null || warn "docker tidak ada / tidak jalan"
echo "  -- pemegang port yang kita butuhkan --"
for p in ${PORTS_WANTED}; do
  holder=$(ss -ltnp 2>/dev/null | grep -E "[:.]${p}\s" || true)
  [[ -n "$holder" ]] && echo "    ${p}: ${holder}" || echo "    ${p}: bebas"
done
echo "  -- compose project --"
docker compose ls 2>/dev/null | sed 's/^/    /' || true

# ------------------------------------------------------------
# 2. Arsip
# ------------------------------------------------------------
if (( DRY )); then
  info "Rencana arsip -> ${ARCHIVE} (dump DB, salinan bind-mount, docker inspect)."
else
  info "Mengarsipkan ke ${ARCHIVE} ..."
  mkdir -p "${ARCHIVE}"/{db,mounts,meta}
  chmod 700 "${ARCHIVE_ROOT}" "${ARCHIVE}"

  docker ps -a --format '{{.Names}}' > "${ARCHIVE}/meta/containers.txt" 2>/dev/null || true
  docker inspect $(docker ps -aq) > "${ARCHIVE}/meta/inspect.json" 2>/dev/null || true
  docker compose ls --format json > "${ARCHIVE}/meta/compose-projects.json" 2>/dev/null || true
  ss -ltnp > "${ARCHIVE}/meta/listening-ports.txt" 2>/dev/null || true
  systemctl list-units --type=service --state=running --no-pager \
    > "${ARCHIVE}/meta/services.txt" 2>/dev/null || true

  # 2a. Dump setiap container Postgres yang ditemukan.
  mapfile -t pgc < <(docker ps --format '{{.Names}}\t{{.Image}}' \
                     | grep -iE 'postgres|timescale' | cut -f1 || true)
  if (( ${#pgc[@]} == 0 )); then
    warn "Tidak ada container Postgres terdeteksi — cek Postgres yang jalan di host."
  fi
  for c in "${pgc[@]}"; do
    info "  pg_dumpall dari container ${c} ..."
    # Coba superuser yang lazim; POSTGRES_USER container dipakai kalau ada.
    u=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" \
        | grep -m1 '^POSTGRES_USER=' | cut -d= -f2- || true)
    for user in "${u:-}" postgres odoo odoo18 root; do
      [[ -n "$user" ]] || continue
      if docker exec "$c" pg_dumpall -U "$user" --clean --if-exists \
           > "${ARCHIVE}/db/${c}.sql" 2>"${ARCHIVE}/db/${c}.err"; then
        gzip -9 "${ARCHIVE}/db/${c}.sql"
        ok "  dump ${c} (user ${user}): $(du -h "${ARCHIVE}/db/${c}.sql.gz" | cut -f1)"
        break
      fi
    done
    [[ -s "${ARCHIVE}/db/${c}.sql.gz" ]] \
      || die "pg_dumpall gagal untuk ${c} — JANGAN lanjut takeover tanpa dump. Lihat ${ARCHIVE}/db/${c}.err"
  done

  # 2b. Salin bind-mount host milik container yang berjalan (filestore, config,
  #     upload). Volume bernama tidak disalin — volume tidak dihapus skrip ini.
  info "  menyalin bind-mount host ..."
  docker ps -q | while read -r cid; do
    cname=$(docker inspect -f '{{.Name}}' "$cid" | tr -d '/')
    docker inspect -f '{{range .Mounts}}{{if eq .Type "bind"}}{{println .Source}}{{end}}{{end}}' "$cid" \
    | while read -r src; do
        [[ -n "$src" && -e "$src" ]] || continue
        case "$src" in /proc/*|/sys/*|/dev/*|/var/run/*|/etc/localtime|/etc/timezone) continue;; esac
        dst="${ARCHIVE}/mounts/${cname}${src}"
        mkdir -p "$(dirname "$dst")"
        cp -a "$src" "$dst" 2>/dev/null || warn "    gagal salin ${src}"
      done
  done
  du -sh "${ARCHIVE}" | sed 's/^/    total arsip: /'
  ok "Arsip selesai di ${ARCHIVE}"
fi

# ------------------------------------------------------------
# 3. Matikan (tanpa menghapus)
# ------------------------------------------------------------
info "Menghentikan container lama..."
mapfile -t running < <(docker ps --format '{{.Names}}' 2>/dev/null || true)
for c in "${running[@]}"; do
  if (( DRY )); then
    echo "    [dry] docker update --restart=no ${c} && docker stop ${c}"
  else
    docker update --restart=no "$c" >/dev/null
    docker stop -t 30 "$c" >/dev/null
    ok "  ${c} dihentikan (restart policy -> no, container TIDAK dihapus)"
  fi
done

info "Menonaktifkan unit systemd yang memegang port target..."
for p in ${PORTS_WANTED}; do
  pidprog=$(ss -ltnp 2>/dev/null | grep -E "[:.]${p}\s" \
            | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2 || true)
  [[ -n "$pidprog" ]] || continue
  unit=$(ps -o unit= -p "$pidprog" 2>/dev/null | tr -d ' ' || true)
  case "$unit" in ""|"-"|docker.service|containerd.service) continue;; esac
  if (( DRY )); then
    echo "    [dry] systemctl disable --now ${unit}  (memegang port ${p})"
  else
    systemctl disable --now "$unit" && ok "  ${unit} dinonaktifkan (port ${p})"
  fi
done

# ------------------------------------------------------------
# 4. Verifikasi
# ------------------------------------------------------------
info "Port setelah takeover:"
for p in ${PORTS_WANTED}; do
  ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${p}\$" \
    && warn "    ${p} MASIH dipakai" || echo "    ${p} bebas"
done

echo
if (( DRY )); then
  warn "Dry-run selesai. Tinjau daftar di atas, lalu: sudo CONFIRM=yes-take-over bash takeover.sh"
else
  ok "Takeover selesai. Arsip: ${ARCHIVE}"
  echo "  Container lama masih ada (stopped) dan volume-nya utuh — rollback:"
  echo "    docker update --restart=unless-stopped <nama> && docker start <nama>"
  echo "  Lanjut: sudo -E bash deploy/ppob-node/bootstrap.sh"
fi
