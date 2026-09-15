# Node PPOB / PPS di server terpisah

Kit untuk memindahkan vertical **PPOB / PPS (Erajaya VAS)** dari platform
multi-tenant ke VPS sendiri, membawa seluruh repo `odoo-platform`.

## 1. Jawaban singkat: memungkinkan?

**Ya, dan ini justru cara yang benar.** Tiga alasan teknis:

| Faktor | Status |
|---|---|
| Lisensi | Image dasar `odoo:19.0` = **Community Edition**. Modul EE-gap (`addons/ee_gap/*`) buatan sendiri. Tidak ada lisensi per-server yang dilanggar. |
| Isolasi data | PPOB sudah hidup di database sendiri (`rnd_ppob`), bukan company kedua di DB tenant lain. Pindah = pindah satu database. |
| Ketergantungan runtime | Hanya Postgres + Redis + image Odoo. Tidak ada service platform lain (cockpit, orchestrator, hub-portal) yang wajib ikut. |

**Yang tidak bisa dipilah:** repo ini monorepo dan modul PPOB berdiri di atas
modul platform bersama. Menyalin `addons/verticals/custom_ppob_*` saja akan gagal.
Closure dependensinya **23 modul custom** di 4 keluarga addon:

```
verticals/   custom_ppob_{core,wallet,provider,sale,va,commission,
                          rollup,sla,biller_digiflazz,pps_gateway,
                          eraspace_bridge,oracle_bridge}
core/        custom_core, custom_adapter_framework
ee_gap/      custom_accounting_full, custom_accounting_reports,
             custom_hr_payroll_id, l10n_id_psak_custom
compliance/  custom_coretax, custom_coretax_bupot, custom_pph_witholding,
             custom_pdp_core, custom_pdp_audit
```

Karena itu **clone repo utuh** (~400 MB `.git`) dan pasang hanya modul PPOB —
itulah yang dilakukan skrip di direktori ini. Konsekuensinya yang perlu disepakati:
node PPOB tetap ikut siklus rilis repo bersama, jadi bump modul shared di sini
akan menyentuh node PPOB juga (pola yang sama sudah pernah menjatuhkan 13 DB —
lihat catatan "shared-addon version-bump drift").

## 2. Kondisi VPS tujuan 192.168.3.185 (dipindai 2026-09-08)

| Port | Isi |
|---|---|
| 80 → 3000 | nginx redirect ke Next.js |
| 3000 | Next.js UI |
| 8069 / 8071 / 8072 | **Odoo 18 CE** ("OdooHub", punya stack lain) |
| 8080 | FastAPI `OdooHub API` (Swagger di `/docs`) |
| 5433 | PostgreSQL |
| 21 | FTP |
| 22 | **tertutup — SSH tidak berjalan** |

**Keputusan: VPS ini diambil alih.** Stack OdooHub dimatikan lebih dulu oleh
`takeover.sh`, lalu node PPOB memakai port standar (8069/8072/5432/6379).

`takeover.sh` sengaja dibuat **reversibel**: ia mendump semua database,
menyalin bind-mount, menghentikan container dan menyetel restart policy ke
`no`, serta menonaktifkan unit systemd pemegang port. Ia **tidak pernah**
`docker rm`, `docker volume rm`, `dropdb`, atau `rm -rf`. Penghapusan permanen
dilakukan manual setelah arsip diverifikasi — kalau ternyata masih ada yang
memakai OdooHub, rollback-nya satu perintah `docker start`.

**SSH masih tertutup per pemindaian terakhir**, jadi urutan di bawah belum
dieksekusi. Begitu sshd hidup dan key terpasang, semuanya bisa dijalankan.

## 2b. Prasyarat: menyalakan sshd di VPS tujuan

Dari jaringan tidak ada pintu masuk (port 22 refused, FTP :21 tidak memberi shell),
jadi langkah ini **harus lewat konsol VM** — VM ini VMware (MAC `00:50:56:*`),
jadi: vSphere/ESXi → pilih VM → **Launch Web Console**.

Login sebagai root (atau user ber-sudo), lalu:

```bash
# Debian / Ubuntu
apt-get update && apt-get install -y openssh-server
systemctl enable --now ssh          # di beberapa rilis unitnya bernama sshd
systemctl status ssh --no-pager

# RHEL / Rocky / Alma
dnf install -y openssh-server
systemctl enable --now sshd
```

Kalau paketnya sudah ada tapi mati, biasanya salah satu dari ini:

```bash
systemctl is-enabled ssh sshd 2>/dev/null   # unit mana yang ada
systemctl unmask ssh; systemctl enable --now ssh
ss -ltnp | grep :22                          # sudah listen?
grep -E '^(Port|ListenAddress|PermitRootLogin)' /etc/ssh/sshd_config
ufw allow 22/tcp || firewall-cmd --add-service=ssh --permanent && firewall-cmd --reload
```

Lalu pasang public key milik host provisioning (192.168.3.140):

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJJi8WmTYIsGKR56zjl3DajnHn/A/pnAM7dBVfxvHLE/ ppob-node-provisioning@192.168.3.140' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Kalau login root via key ditolak, set `PermitRootLogin prohibit-password` di
`/etc/ssh/sshd_config` lalu `systemctl restart ssh`. Alternatif yang lebih rapi:
pakai user ber-sudo dan ubah `User` di `~/.ssh/config` host provisioning.

Uji dari 192.168.3.140: `ssh ppob-node 'hostname; docker ps --format "{{.Names}}"'`

## 3. Cara pakai

Di VPS tujuan, sebagai user ber-sudo:

```bash
# 0. lihat dulu apa yang akan dimatikan — tidak mengubah apa pun
sudo bash takeover.sh

# 1. arsipkan + matikan stack lama (reversibel, tidak menghapus)
sudo CONFIRM=yes-take-over bash takeover.sh

# 2. host prep + docker + clone repo + .env + build + up
REPO_DIR=/opt/ppob-platform sudo -E bash bootstrap.sh

# 3. buat database + pasang modul (urutan sudah dijaga skrip)
cd /opt/ppob-platform
bash deploy/ppob-node/install-ppob.sh
```

Arsip stack lama mendarat di `/var/backups/pre-ppob-takeover/<timestamp>/`
(`db/` dump `pg_dumpall`, `mounts/` salinan bind-mount, `meta/` inspect +
daftar port/service). **Verifikasi arsip itu sebelum menghapus apa pun.**

Hasil: `http://192.168.3.185:8069/`, database `ppob`, login `admin`/`admin`
(**segera ganti**). Master password ada di `.env` (`ODOO_ADMIN_PASSWD`).

Prasyarat yang harus disiapkan orang, bukan skrip:

- **Akses git ke remote** dari VPS (deploy key ke `sarangrumah/odoo-platform`),
  atau salin repo lewat `git bundle` kalau VPS tidak boleh keluar internet.
- **SSH** hidup di VPS tujuan.
- RAM ≥ 8 GiB dan disk bebas ≥ 40 GiB (skrip hanya memperingatkan, tidak menolak).

## 4. Isi kit

| Berkas | Fungsi |
|---|---|
| `takeover.sh` | Inventaris + arsip + matikan stack lama. Dry-run secara default; butuh `CONFIRM=yes-take-over`. Tidak menghapus apa pun. |
| `bootstrap.sh` | Prasyarat host, Docker, clone repo, `.env` + secret acak, direktori data, build & up. Idempotent. |
| `docker-compose.ppob.yml` | Overlay: hanya postgres/redis/odoo; Postgres & Redis loopback; Odoo dipublish ke LAN. |
| `.env.ppob.example` | Template env, port standar (dipakai setelah takeover). |
| `install-ppob.sh` | Buat DB, set IDR, `-i l10n_id`, pasang 11 modul PPOB, verifikasi. |

Compose selalu dipanggil dengan **nama service eksplisit**, karena base compose
memuat 17 service (cockpit, storefront, orchestrator, …) yang tidak diperlukan
node PPOB:

```bash
docker compose -f docker-compose.yml \
               -f deploy/ppob-node/docker-compose.ppob.yml \
               up -d postgres redis odoo
```

## 5. Dua jebakan yang sudah dikodekan ke dalam skrip

**a. CoA harus lebih dulu dari modul PPOB.** Di DB tanpa chart of accounts, hook
`custom_ppob_core` membuat 19 akunnya sendiri; di akhir `load_modules`, modul
`account` menjalankan `_auto_install_template` yang meng-`unlink()` akun
placeholder untuk memuat CoA → `ForeignKeyViolation` di
`custom_ppob_account_mapping_account_id_fkey`. `install-ppob.sh` memasang
`l10n_id` lebih dulu dan **berhenti** kalau `res_company.chart_template`
ternyata bukan `l10n_id`.

**b. Mata uang diset sebelum ada jurnal.** DB `rnd_ppob` yang lama terkunci di
`generic_coa` + **USD** (terverifikasi hari ini) dan itu tidak bisa dikoreksi
lagi setelah jurnal terbentuk. Skrip menyetel IDR saat DB baru berisi `base`.

**c. `custom_ppob_oracle_bridge` tidak dipasang default.** Tiga cron-nya jalan
tiap menit dan gagal terus selama DSN Oracle EVShop belum ada. Aktifkan lewat
`PPOB_INSTALL_ORACLE_BRIDGE=1` + `PPOB_ORACLE_DSN` di `.env`.

## 6. Memindahkan data yang sudah ada (opsional)

`rnd_ppob` per 13-Agu-2026 adalah kerangka kosong — 0 provider/produk/transaksi,
dan currency-nya salah. **Rekomendasi: bangun DB baru dengan `install-ppob.sh`,
jangan restore `rnd_ppob`.** Kalau tetap ingin membawa DB lama:

```bash
# di host lama
docker exec -e PGPASSWORD=... <pg> pg_dump -U odoo -Fc rnd_ppob > rnd_ppob.dump
tar czf rnd_ppob-filestore.tgz -C /path/data/odoo-filestore rnd_ppob
```

Filestore **wajib** ikut — backup malam platform ini hanya SQL, restore tanpa
filestore kehilangan seluruh lampiran.

## 7. Yang masih harus diputuskan

- Nama domain / TLS untuk node PPOB (kit ini berhenti di HTTP port LAN).
- Backup: node baru tidak masuk cron `pg_dump` 02:30 milik host lama.
- Kapan arsip OdooHub boleh dihapus permanen (skrip hanya menghentikan).
- Apakah ada orang lain yang masih memakai OdooHub di .185 — worth dikonfirmasi
  sebelum `CONFIRM=yes-take-over`, karena stack itu jelas dipakai seseorang.
