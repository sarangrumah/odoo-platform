#!/usr/bin/env bash
# ============================================================
# bootstrap.sh — siapkan VPS baru sebagai node PPOB / PPS.
#
# Dijalankan DI VPS TUJUAN (mis. 192.168.3.185) sebagai user yang
# boleh sudo. Idempotent: aman diulang.
#
#   sudo bash bootstrap.sh                    # clone default ke /opt/ppob-platform
#   REPO_DIR=/srv/ppob sudo -E bash bootstrap.sh
#
# Yang dilakukan:
#   1. cek prasyarat host (RAM/disk/port bentrok)
#   2. pasang docker engine + compose plugin kalau belum ada
#   3. clone repo odoo-platform (butuh akses git ke remote)
#   4. siapkan .env dari template + generate secret acak
#   5. buat direktori data + share SFTP yang di-mount base compose
#   6. build image odoo dan menyalakan postgres/redis/odoo
#
# Setelah ini jalankan install-ppob.sh untuk membuat database.
# ============================================================
set -euo pipefail

REPO_URL="${REPO_URL:-git@github.com:sarangrumah/odoo-platform.git}"
REPO_DIR="${REPO_DIR:-/opt/ppob-platform}"
REPO_REF="${REPO_REF:-main}"
KIT_DIR_REL="deploy/ppob-node"

color() { printf '\033[%sm%s\033[0m\n' "$1" "$2"; }
info()  { color "1;34" "[INFO ] $*"; }
ok()    { color "1;32" "[ OK  ] $*"; }
warn()  { color "1;33" "[WARN ] $*"; }
err()   { color "1;31" "[ERR  ] $*" >&2; }
die()   { err "$*"; exit 1; }

[[ $EUID -eq 0 ]] || die "Jalankan sebagai root (sudo bash bootstrap.sh)."

# ------------------------------------------------------------
# 1. Prasyarat host
# ------------------------------------------------------------
info "Memeriksa kapasitas host..."
mem_gb=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 / 1024 ))
disk_gb=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
(( mem_gb >= 8 ))   || warn "RAM ${mem_gb} GiB — Odoo+Postgres di compose ini minta ~6 GiB limit. Disarankan >= 8 GiB."
(( disk_gb >= 40 )) || warn "Sisa disk ${disk_gb} GiB — repo + image + filestore realistis butuh >= 40 GiB."
ok "RAM ${mem_gb} GiB, disk bebas ${disk_gb} GiB."

# ------------------------------------------------------------
# 2. Docker
# ------------------------------------------------------------
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  ok "Docker + compose plugin sudah ada ($(docker --version))."
else
  info "Memasang Docker Engine dari repo resmi..."
  . /etc/os-release
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
                         docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
  ok "Docker terpasang: $(docker --version)"
fi

# ------------------------------------------------------------
# 3. Repo
# ------------------------------------------------------------
if [[ -d "${REPO_DIR}/.git" ]]; then
  ok "Repo sudah ada di ${REPO_DIR} (tidak di-clone ulang)."
  info "HEAD: $(git -C "${REPO_DIR}" log --oneline -1)"
else
  info "Clone ${REPO_URL} -> ${REPO_DIR} (ref ${REPO_REF})..."
  git clone --branch "${REPO_REF}" "${REPO_URL}" "${REPO_DIR}" \
    || die "Clone gagal. Pastikan host ini punya deploy key / akses ke remote."
  ok "Repo ter-clone."
fi
cd "${REPO_DIR}"

# ------------------------------------------------------------
# 4. .env
# ------------------------------------------------------------
if [[ -f .env ]]; then
  ok ".env sudah ada (tidak ditimpa)."
else
  info "Menyusun .env dari ${KIT_DIR_REL}/.env.ppob.example ..."
  cp "${KIT_DIR_REL}/.env.ppob.example" .env
  gen() { openssl rand -hex 32; }
  # Fernet key untuk CORETAX_SERTEL_MASTER_KEY = 32 byte base64-urlsafe.
  fernet() { python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())'; }
  set_kv() { sed -i "s|^${1}=.*|${1}=${2}|" .env; }
  set_kv POSTGRES_PASSWORD          "$(gen)"
  set_kv PG_ORCHESTRATOR_PASSWORD   "$(gen)"
  set_kv ODOO_ADMIN_PASSWD          "$(gen)"
  set_kv REDIS_PASSWORD             "$(gen)"
  set_kv GATEWAY_SHARED_SECRET      "$(gen)"
  set_kv ORCHESTRATOR_SHARED_SECRET "$(gen)"
  set_kv CORETAX_SERTEL_MASTER_KEY  "$(fernet)"
  chmod 600 .env
  ok ".env dibuat dengan secret acak (mode 600). Simpan salinannya di password manager."
fi

grep -vE '^[[:space:]]*#' .env | grep -q 'changeme' && die ".env masih memuat 'changeme' pada sebuah nilai — isi dulu, entrypoint akan menolak."

# ------------------------------------------------------------
# 4b. Bentrok port — dicek terhadap .env, bukan daftar hardcoded.
# Node ini memakai port standar (8069/8072/5432/6379) karena VPS
# diambil alih; kalau stack lama masih hidup, berhenti di sini.
# ------------------------------------------------------------
info "Memeriksa bentrok port..."
envget() { grep -m1 "^${1}=" .env | cut -d= -f2- | awk '{print $1}'; }
for key in ODOO_HTTP_PORT ODOO_LONGPOLL_PORT POSTGRES_PORT REDIS_PORT; do
  p="$(envget "$key")"
  [[ -n "$p" ]] || continue
  if ss -ltnp 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${p}\$"; then
    err "Port ${p} (${key}) masih dipakai:"
    ss -ltnp 2>/dev/null | grep -E "[:.]${p}\s" | sed 's/^/        /' >&2
    die "Jalankan takeover.sh dulu untuk mematikan stack lama, atau ubah ${key} di .env."
  fi
done
ok "Port dari .env semuanya bebas."

# ------------------------------------------------------------
# 5. Direktori data
# ------------------------------------------------------------
info "Menyiapkan direktori data..."
mkdir -p data/postgres data/redis data/odoo-filestore
# Base compose me-mount /srv/sftp-share/files ke /mnt/data_levis. Node PPOB
# tidak memakai feed retail, tapi bind mount ke path yang belum ada akan
# dibuat root-owned oleh Docker dan bikin warning; siapkan dengan uid odoo (101).
mkdir -p /srv/sftp-share/files
# Image odoo:19.0 menjalankan odoo sebagai uid 100 (gid 101), BUKAN 101.
# Salah chown ke 101 membuat init base gagal: PermissionError di
# /var/lib/odoo/filestore.
chown -R 100:101 /srv/sftp-share/files data/odoo-filestore
ok "Direktori data siap."

# ------------------------------------------------------------
# 6. Build + up
# ------------------------------------------------------------
COMPOSE=(docker compose -f docker-compose.yml -f "${KIT_DIR_REL}/docker-compose.ppob.yml")
info "Build image Odoo (butuh beberapa menit pada run pertama)..."
"${COMPOSE[@]}" build odoo
info "Menyalakan postgres, redis, odoo..."
"${COMPOSE[@]}" up -d postgres redis odoo

info "Menunggu Odoo sehat..."
for _ in $(seq 1 60); do
  state=$(docker inspect -f '{{.State.Health.Status}}' "$(grep -E '^COMPOSE_PROJECT_NAME=' .env | cut -d= -f2)-odoo" 2>/dev/null || echo starting)
  [[ "$state" == healthy ]] && break
  sleep 5
done
"${COMPOSE[@]}" ps

ok "Bootstrap selesai."
echo
echo "Langkah berikutnya:"
echo "  cd ${REPO_DIR}"
echo "  bash ${KIT_DIR_REL}/install-ppob.sh"
