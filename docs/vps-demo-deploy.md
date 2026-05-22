# VPS Demo Deploy Guide

Tujuan: bikin platform ini jalan di **VPS dengan domain publik** untuk
**presentasi / demo** (bukan Go-Live). S3 backup, SAST/scans wajib, dan
DBA sign-off di-skip — fokus ke: jalan, ada TLS, ada admin yang bisa login,
ada minimal 1 tenant terbuat.

Untuk full production checklist lihat [`prod-deploy-checklist.md`](prod-deploy-checklist.md).

---

## 0. Spek VPS minimum

| Resource | Minimum demo | Recommended |
|----------|-------------|-------------|
| vCPU     | 4           | 8           |
| RAM      | 8 GB        | 16 GB       |
| Disk     | 60 GB SSD   | 120 GB SSD  |
| OS       | Ubuntu 22.04 / 24.04 LTS | Ubuntu 24.04 LTS |

Port yang perlu terbuka di firewall: **80, 443** (Caddy ACME). Port lain
(`18000`, `13000`, `15050`, dll.) tetap bind ke `127.0.0.1` lewat compose,
**jangan** dibuka ke publik.

DNS: arahkan satu A record ke IP VPS, contoh `erp.demo.example.com`.

---

## 1. Bootstrap host

```bash
# Sebagai root atau user dengan sudo
apt update && apt -y upgrade
apt -y install ca-certificates curl git make ufw

# Docker Engine + compose plugin
curl -fsSL https://get.docker.com | sh
usermod -aG docker $USER   # logout/login lagi setelah ini

# Firewall: cuma 22, 80, 443
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

---

## 2. Clone repo & siapkan `.env`

```bash
git clone https://github.com/sarangrumah/odoo-platform /opt/odoo-platform
cd /opt/odoo-platform
git checkout <tag-atau-branch>     # mis. v0.1.0-demo

cp .env.example .env
nano .env
```

Yang **wajib** diubah di `.env` (entrypoint Odoo fail-fast pada substring `changeme`):

```ini
# Secrets (generate semua, jangan dipakai apa adanya)
POSTGRES_PASSWORD=<openssl rand -base64 24>
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -base64 24)|" .env
ODOO_ADMIN_PASSWD=<openssl rand -base64 24>
sed -i "s|^ODOO_ADMIN_PASSWD=.*|ODOO_ADMIN_PASSWD=$(openssl rand -base64 24)|" .env
REDIS_PASSWORD=<openssl rand -base64 24>
sed -i "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=$(openssl rand -base64 24)|" .env
GRAFANA_ADMIN_PASSWORD=<openssl rand -base64 16>
sed -i "s|^GRAFANA_ADMIN_PASSWORD=.*|GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 16)|" .env
PGADMIN_PASSWORD=<openssl rand -base64 16>
sed -i "s|^PGADMIN_PASSWORD=.*|PGADMIN_PASSWORD=$(openssl rand -base64 16)|" .env
GATEWAY_SHARED_SECRET=<openssl rand -hex 32>
sed -i "s|^GATEWAY_SHARED_SECRET=.*|GATEWAY_SHARED_SECRET=$(openssl rand -hex 32)|" .env
CORETAX_SERTEL_MASTER_KEY=<python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())">
sed -i "s|^CORETAX_SERTEL_MASTER_KEY=.*|CORETAX_SERTEL_MASTER_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')|" .env

ORCHESTRATOR_SHARED_SECRET=<openssl rand -hex 32>
sed -i "s|^ORCHESTRATOR_SHARED_SECRET=.*|ORCHESTRATOR_SHARED_SECRET=$(openssl rand -hex 32)|" .env
PG_ORCHESTRATOR_PASSWORD=<openssl rand -base64 24>
sed -i "s|^PG_ORCHESTRATOR_PASSWORD=.*|PG_ORCHESTRATOR_PASSWORD=$(openssl rand -base64 24)|" .env
MASTER_WRAPPING_KEY=<python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())">
sed -i "s|^MASTER_WRAPPING_KEY=.*|MASTER_WRAPPING_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')|" .env
MINIO_ROOT_PASSWORD=<openssl rand -base64 16>
sed -i "s|^MINIO_ROOT_PASSWORD=.*|MINIO_ROOT_PASSWORD=$(openssl rand -base64 16)|" .env

# Runtime: prod
WORKERS=4
LIST_DB=false
WITHOUT_DEMO=all

# Domain & ACME (Caddy bakal issue cert Let's Encrypt otomatis)
DOMAIN=erp.demo.example.com
ACME_EMAIL=ops@example.com

# AI (opsional — kosongkan kalau demo tanpa AI bridge)
ANTHROPIC_API_KEY=sk-ant-...
```

S3 backup **biarkan kosong** untuk demo — service `pg-backup-s3` sudah
profile-gated, jadi nggak akan boot tanpa `--profile s3-backup`.

> **Catatan keamanan**: `.env` di-gitignore. Jangan pernah `git add -f .env`.

---

## 3. Boot stack

```bash
# Buat folder data (di-bind mount oleh compose)
mkdir -p data/{backups,odoo-filestore,nginx-cache,caddy/data,caddy/config}

# Bind-mount ownership: container user IDs di image base masing-masing tidak
# match host root. Set ownership sebelum boot supaya container nggak crash.
chown -R 101:101 data/odoo-filestore    # uid 101 = 'odoo' di odoo:19.0
chown -R 999:999 data/backups           # uid 999 = 'postgres' di pgbackup-local

# Start prod + TLS (Caddy ACME di depan nginx)
make up-tls

# Cek health
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.tls-acme.yml ps
```

Tunggu sampai `nginx` dan `caddy` healthy (~30–60 detik), lalu `odoo` healthy
(~60–120 detik first boot karena init schema).

---

## 4. Inisialisasi DB & install module

```bash
# Buat DB demo
make init-db DB=demo

# Install minimal set untuk demo (urutan penting — base dulu)
make install MODULE=custom_core DB=demo
make install MODULE=custom_adapter_framework DB=demo
make install MODULE=custom_ai_bridge DB=demo

# Tambah modul vertikal sesuai kebutuhan demo, contoh:
make install MODULE=custom_coretax DB=demo
make install MODULE=custom_pdp_core DB=demo
```

Login ke `https://<DOMAIN>/web/login` dengan admin DB yang baru dibuat.

---

## 5. (Opsional) Multi-tenant demo

Kalau presentasi mau nunjukin tenant lifecycle (provision → suspend → resume):

```bash
make up-multitenant   # tambah orchestrator + MinIO + Caddy wildcard

# Provision satu tenant contoh
make tenant-provision SLUG=acme NAME="Acme Demo" EMAIL=admin@acme.test
make tenant-list
```

Pastikan DNS wildcard `*.erp.demo.example.com` juga arahkan ke IP VPS.

---

## 6. Smoke test (sebelum presentasi)

- [ ] `https://<DOMAIN>` redirect HTTP → HTTPS, cert valid (Let's Encrypt issuer)
- [ ] Login admin sukses
- [ ] Apps menu nunjukin custom_* modules sesuai instalasi
- [ ] Buat 1 record di tiap modul yang bakal di-demo
- [ ] `docker compose logs odoo --tail 50` bersih dari ERROR
- [ ] Backup lokal jalan: `ls data/backups/` ada file `*.sql.gz` setelah 24 jam
      (atau `make backup-now` manual untuk validasi)

---

## 7. Troubleshooting cepat

| Gejala | Cek |
|--------|-----|
| Cert Let's Encrypt gagal | DNS A record propagated? Port 80 open? `docker logs <caddy>` |
| Odoo 502/504 di nginx    | `WORKERS` cukup? `docker logs <odoo>` ada OOM? |
| `changeme` fail-fast     | `grep changeme .env` — ganti semua placeholder |
| Module install error     | Cek dependency module di `__manifest__.py["depends"]` |
| Filestore 404 / CSS lama | Pastikan `./data/odoo-filestore` ada dan owned `odoo` (uid 101) |

---

## Yang TIDAK dilakukan di demo deploy ini

- ❌ S3 offsite backup (profile `s3-backup` tidak aktif)
- ❌ SOPS-encrypted secrets
- ❌ Pre-commit / Trivy / Semgrep gate (jalanin manual sebelum push)
- ❌ Grafana alerting ke Slack/email
- ❌ DBA review schema, retention policy resmi
- ❌ HA Postgres / read replica
- ❌ Audit-chain verification berkala

Semuanya **wajib** sebelum Go-Live beneran. Lihat `prod-deploy-checklist.md`.
