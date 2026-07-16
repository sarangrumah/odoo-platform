# Arsitektur PPOB — Migrasi H2H → Odoo (Odoo sebagai Transaction Engine)

**Konteks bisnis:** Erajaya Value-Added Services (VAS) — PPOB / bill-payment & top-up, model **mitra prepaid**
**Owner:** Product Owner VAS · Platform Team
**Status:** Design / target-state architecture (kelanjutan dari mirror baseline)
**Tanggal:** 2026-07-16
**Companion dari:** [`ppob-eraspace-h2h-architecture.md`](./ppob-eraspace-h2h-architecture.md) (current state / mirror)
**Terkait kode:** `addons/verticals/custom_ppob_*` (suite native, 8 modul, terverifikasi 51/51 test di Odoo 19)

---

## 0. Tujuan dokumen

Dokumen sebelumnya membekukan **current state**: ERASPACE POS + H2H switcher yang **own** transaksi, Odoo hanya *mirror ledger* (dua feed, di-join `pos_trx_ref`). Dokumen ini menggambarkan **arah evolusinya**: bagaimana **Odoo secara bertahap menggantikan H2H** sampai Odoo menjadi **transaction engine** (mesin switching biller) yang authoritative — memakai suite `custom_ppob_*` dalam **mode native** (bukan lagi mirror).

Dua pertanyaan yang dijawab:
1. **Alur integrasi data** Odoo ↔ ERASPACE POS ↔ H2H — sekarang & sesudah cutover.
2. **Apa yang berpindah** saat H2H di-*replace* Odoo, dan **bagaimana migrasinya** aman (strangler-fig, dual-run, reconcile-parity gate, rollback).

---

## 1. Tiga fase evolusi (peta besar)

```mermaid
flowchart LR
    subgraph P1["FASE 1 — MIRROR (sekarang)"]
        direction TB
        A1[ERASPACE POS<br/>SoR saldo mitra + jual] --> A2[H2H Switcher<br/>SoR dispatch + deposit]
        A1 -.feed POS.-> A3[(Odoo<br/>mirror ledger)]
        A2 -.feed H2H.-> A3
    end
    subgraph P2["FASE 2 — ODOO GANTIKAN H2H (target utama)"]
        direction TB
        B1[ERASPACE POS<br/>SoR saldo mitra + jual] --> B2[(Odoo = Transaction Engine<br/>dispatch + deposit + adapter biller)]
        B2 --> B3[Biller / Aggregator]
    end
    subgraph P3["FASE 3 — FULL NATIVE (opsional/ultimate)"]
        direction TB
        C1[ERASPACE POS<br/>UI tipis] --> C2[(Odoo<br/>saldo mitra + deposit + dispatch)]
        C2 --> C3[Biller]
    end
    P1 ==> P2 ==> P3
```

| | Fase 1 — Mirror | **Fase 2 — Odoo gantikan H2H** | Fase 3 — Full native |
|---|---|---|---|
| Saldo mitra (otoritas) | ERASPACE POS | ERASPACE POS | **Odoo wallet** |
| Deposit biller (otoritas) | H2H | **Odoo bucket** | Odoo bucket |
| Dispatch / pay ke biller | H2H | **Odoo adapter** | Odoo adapter |
| Status polling | H2H | **Odoo reaper** | Odoo reaper |
| Peran Odoo | ledger hilir | **switching engine + ledger** | full engine + ledger |
| Modul kunci | `custom_ppob_eraspace_bridge` | `custom_ppob_sale/provider/wallet` (native) | seluruh suite native |

> **Fokus dokumen:** Fase 2 = "H2H di-replace Odoo". Fase 3 disertakan sebagai arah akhir; keputusan menyerap saldo mitra ke Odoo bersifat bisnis, bukan teknis (suite sudah mendukung keduanya).

---

## 2. Current state (Fase 1) — ringkas

Detail penuh di [dokumen mirror](./ppob-eraspace-h2h-architecture.md). Intinya: **arah data satu arah** (POS/H2H → Odoo), Odoo non-authoritative, dua feed HMAC di-join `pos_trx_ref`, GL diproyeksikan per feed (`_mirror_debit`/`_mirror_credit` + COGS/deposit `account.move`), rekonsiliasi 4-kontrol.

```mermaid
sequenceDiagram
    participant POS as ERASPACE POS
    participant H2H as H2H Switcher
    participant B as Biller
    participant O as Odoo (mirror)
    POS->>H2H: request (pos_trx_ref, produk, harga)
    H2H->>B: inquiry + pay
    B-->>H2H: SUCCESS + token + harga modal
    H2H-->>POS: SUCCESS
    POS->>POS: debit saldo mitra (authoritative)
    par feed POS (revenue + wallet mirror)
        POS-->>O: event FINAL
    and feed H2H (COGS + deposit mirror)
        H2H-->>O: event FINAL
    end
    O->>O: JOIN pos_trx_ref → margin, faktur, laporan
```

Batasan mirror: Odoo **tidak** mengeksekusi biller, **tidak** menahan saldo, **tidak** memutuskan refund. Latensi Odoo **tidak** di jalur kritis penjualan.

---

## 3. Target state (Fase 2) — Odoo menggantikan H2H

**Perubahan inti:** H2H switcher dinonaktifkan; **ERASPACE POS memanggil Odoo secara sinkron** untuk fulfillment. Odoo menjadi **mesin switching**: menahan **deposit biller (authoritative)**, memilih biller (failover), memanggil biller lewat **adapter**, mem-poll status, dan mengembalikan hasil ke POS. Saldo mitra **tetap** di ERASPACE POS (POS men-debit dulu sebelum memanggil Odoo).

### 3.1 Context diagram (target)

```mermaid
flowchart TB
    M[Mitra prepaid / outlet] --> POS
    subgraph POSsys["ERASPACE POS (standalone)"]
        POS[UI jual + saldo mitra<br/>SoR saldo mitra prepaid]
    end
    POS -- "1. fulfillment request (sinkron)<br/>pos_trx_ref, produk, target, harga modal" --> ODOO
    subgraph ODOOsys["ODOO 19 — Transaction Engine (custom_ppob_*)"]
        ODOO[custom.ppob.transaction<br/>state machine + dispatch]
        BKT[(Provider Bucket<br/>deposit biller AUTHORITATIVE)]
        ADP[Adapter registry<br/>ppob_http_json / oracle_bridge]
        REAP[Reaper cron<br/>status polling]
        GL[GL + wallet mirror + rollup faktur]
        ODOO --> BKT
        ODOO --> ADP
        ODOO --> GL
        REAP -.-> ODOO
    end
    ADP -- "2. inquiry / pay / status (HMAC)" --> BILLER[Biller / Aggregator<br/>Digiflazz · IAK · PLN · dst]
    ODOO -- "3. hasil FINAL (token/serial/status)" --> POS
    POS -- "opsional: konfirmasi/refund saldo mitra" --> M
```

### 3.2 Sequence (target, happy path)

```mermaid
sequenceDiagram
    participant M as Mitra
    participant POS as ERASPACE POS
    participant O as Odoo (engine)
    participant BKT as Provider Bucket
    participant ADP as Adapter
    participant B as Biller

    M->>POS: Jual token PLN 100k
    POS->>POS: cek + hold saldo mitra (authoritative di POS)
    POS->>O: POST fulfillment (pos_trx_ref, produk, IDPEL, idempotency_key)
    O->>O: _resolve_provider() (failover by priority) + _check_caps()
    O->>BKT: _atomic_debit(cost) SELECT..FOR UPDATE (deposit authoritative)
    O->>ADP: pay(transaction)  (single POST, no-retry → tidak double-sell)
    ADP->>B: pay
    B-->>ADP: SUCCESS + token + serial
    ADP-->>O: AdapterResult.ok
    O->>O: _mark_success + post GL (Dr COGS / Cr Deposit)
    O-->>POS: FINAL (token, serial, status=success)
    POS->>POS: commit debit saldo mitra + cetak struk
    Note over O: reaper cron handle in_progress stale (status() dulu, never blind-refund)
    Note over O: nightly rollup → summary faktur per mitra → Coretax
```

### 3.3 Yang berubah vs mirror

| Aspek | Mirror (Fase 1) | **Target (Fase 2)** |
|---|---|---|
| Pemanggil biller | H2H | **Odoo adapter** (`custom_ppob_provider`) |
| Deposit biller | H2H (Odoo cermin) | **Odoo bucket, authoritative** (atomic drawdown + FOR UPDATE) |
| Pemilihan biller / failover | H2H | **Odoo** (`_resolve_provider` by `sku_map.priority` + provider status) |
| Status transaksi | terima dari H2H | **Odoo reaper** poll `status()` (never blind-refund) |
| Refund sisi biller | H2H | **Odoo** `_refund_subledgers` (reversal deposit) |
| Feed ke Odoo | 2 feed async (POS + H2H) | **1 panggilan sinkron POS→Odoo** (H2H feed hilang) |
| Latensi Odoo | di luar jalur kritis | **di jalur kritis penjualan** (lihat §6 NFR) |
| GL penjualan | 2 jurnal dari 2 feed | Dr COGS/Cr Deposit (biller) langsung; wallet mitra tetap mirror dari POS |

---

## 4. Ownership flip — apa yang berpindah dari H2H ke Odoo

```mermaid
flowchart LR
    subgraph H2Hown["Dimiliki H2H (Fase 1)"]
        h1[Inquiry & pay biller]
        h2[Saldo deposit biller]
        h3[Failover antar biller]
        h4[Status & reversal]
        h5[Katalog/SKU biller]
    end
    subgraph Odooown["Berpindah ke Odoo (Fase 2)"]
        o1["Adapter registry<br/>ppob_http_json + HMAC + call log"]
        o2["Provider bucket<br/>atomic drawdown + GL"]
        o3["_resolve_provider<br/>sku_map.priority + status"]
        o4["Reaper + _refund_subledgers"]
        o5["provider + sku_map master"]
    end
    h1 --> o1
    h2 --> o2
    h3 --> o3
    h4 --> o4
    h5 --> o5
```

### 4.1 Matriks aktivasi modul (bypass → active)

| Modul suite | Peran di Mirror | **Peran saat H2H di-replace (Fase 2)** |
|---|---|---|
| `custom_ppob_provider` | master + SKU map + AP topup (bucket **bypass**) | **AKTIF penuh**: bucket authoritative + `_atomic_debit`/`_atomic_credit`, DP-100% topup deposit riil |
| `custom_ppob_sale` | model wadah mirror (engine **bypass**) | **AKTIF penuh**: `_dispatch_one`, `_resolve_provider`, `_refund_subledgers`, reaper cron |
| adapter (`ppob_http_json`) | tidak dipakai | **AKTIF**: panggil biller (single-POST no-retry, pay-safe), kredensial per tenant via `custom.adapter.config`, log ke `custom.adapter.call.log` |
| `custom_ppob_wallet` | mirror saldo mitra (`eraspace_mirror`) | tetap **mirror** dari POS (Fase 2) → **authoritative** (Fase 3) |
| `custom_ppob_core` | COA + product class + price tier + mapping | **REUSE penuh** (tak berubah) |
| `custom_ppob_rollup` | summary faktur per mitra → Coretax | **REUSE penuh** (tak berubah) |
| `custom_ppob_commission` | rebate + PPh 23 | opsional (tak berubah) |
| `custom_ppob_va` | top-up saldo mitra (bank VA) | **REUSE**: jalur langsung Odoo bila top-up pindah ke Odoo, atau tetap POS-feed |
| `custom_ppob_eraspace_bridge` | ingest 2-feed + join + mirror GL | **berkurang perannya**: feed H2H mati; feed POS bisa berubah jadi *fulfillment request* sinkron (bukan mirror). Dipertahankan untuk dual-run + rekonsiliasi paritas selama migrasi |
| `custom_ppob_oracle_bridge` | jalur legacy Oracle EVShop | tetap opsional (bila sebagian mitra masih via EVShop) |

**Konsekuensi:** engine native yang selama mirror di-*bypass* (wallet ceiling, bucket atomic-drawdown, dispatch/adapter/reaper) kini **diaktifkan** — persis yang sudah dibangun & lulus 51/51 test.

---

## 5. Strategi migrasi — strangler-fig, aman & reversible

Jangan *big-bang*. Alihkan trafik dari H2H ke Odoo **per irisan** dengan gerbang paritas rekonsiliasi.

```mermaid
flowchart TB
    S0[Fase 1: Mirror penuh<br/>H2H authoritative, Odoo cermin] --> S1
    S1["Dual-run (shadow):<br/>POS tetap ke H2H, Odoo TERIMA fulfillment request<br/>+ eksekusi ke biller sandbox/paralel, TIDAK dipakai POS"] --> GATE1{Paritas ≥ N hari?<br/>margin, status, deposit, faktur match}
    GATE1 -- tidak --> S1
    GATE1 -- ya --> S2["Canary cutover per irisan:<br/>1 biller / 1 produk / 1 wilayah mitra → POS panggil Odoo"]
    S2 --> GATE2{Recon break = 0?<br/>SLA latensi OK?}
    GATE2 -- rollback --> S1
    GATE2 -- ya --> S3["Perluas irisan bertahap<br/>(biller demi biller, produk demi produk)"]
    S3 --> S4["H2H dinonaktifkan (Fase 2 selesai):<br/>Odoo = switching engine authoritative"]
    S4 -.opsional.-> S5["Fase 3: serap saldo mitra ke Odoo<br/>POS jadi UI tipis"]
```

**Irisan cutover yang aman (pilih dimensi):** per **biller** (mulai biller paling stabil/volume rendah), per **produk/kategori** (pulsa dulu, tagihan belakangan), per **wilayah/segmen mitra**. Idempotency key + `UNIQUE(mitra_id, idempotency_key)` menjamin request yang sama tak dieksekusi ganda saat POS retry di masa transisi.

**Gerbang paritas (parity gate) sebelum naik fase:**
- Margin per transaksi Odoo == margin dari join H2H (selisih 0).
- Status final Odoo == status H2H (tak ada mismatch).
- Snapshot deposit biller Odoo (bucket) == saldo riil biller/H2H.
- Summary faktur per mitra identik.
- p95 latensi fulfillment Odoo ≤ SLA yang disepakati.

**Rollback:** karena mirror bridge dipertahankan selama migrasi, cutover per irisan bisa dibalik ke H2H tanpa kehilangan data (Odoo kembali jadi cermin untuk irisan itu).

---

## 6. Perubahan Non-Functional saat H2H di-replace

| Aspek | Implikasi | Mitigasi (sudah tersedia di suite) |
|---|---|---|
| **Latensi kritis** | Panggilan biller kini di jalur penjualan POS (sebelumnya H2H yang menanggung) | Adapter timeout per `custom.adapter.config`; `_dispatch_one` sinkron tapi ringan; produk 2-langkah pakai `inquiry_required` |
| **Double-sell** | Retry di jalur pay bisa jual dua kali | `ppob_http_json` **single-POST tanpa retry** (pay-safe); idempotency key unik; reaper `status()` sebelum refund |
| **Deposit habis** | Odoo kini penjaga saldo deposit | `bucket._atomic_debit` (SELECT..FOR UPDATE) tolak saldo kurang; low-water-mark alert; DP-100% topup (PMK 131) |
| **Biller down** | Tak ada H2H sebagai buffer | Failover `_resolve_provider` by priority + provider `status=maintenance/disabled`; circuit-breaker via `custom_adapter_framework` |
| **Transaksi menggantung** | Butuh resolusi otomatis | Reaper per-provider `stale_threshold_minutes`, poll `status()`, **never blind-refund** |
| **Concurrency** | Debit paralel bucket/wallet | Row-lock atomic helpers (teruji); rekomendasi test konkura 2-cursor sebelum go-live |
| **Throughput** | Volume tinggi | Posting GL via queue-job (`_vendor/queue_job`); reaper fan-out per provider |
| **Keamanan biller** | Kredensial biller kini di Odoo | Per-tenant `custom.adapter.config` (base_url/secret via `ir.config_parameter`, Fernet); HMAC signing |

Semua kontrol di atas **sudah ada** di modul yang dibangun — cutover mengubah *konfigurasi & routing*, bukan menulis engine baru.

---

## 7. Kontrak antarmuka POS ↔ Odoo (target)

Saat H2H di-replace, kontrak berubah dari **2 feed async (mirror)** menjadi **1 request/response sinkron (fulfillment)** + tetap event untuk saldo/refund.

**Request (POS → Odoo) — fulfillment sinkron:**

| Field | Guna |
|---|---|
| `pos_trx_ref` | idempotency + korelasi (map → `idempotency_key`) |
| `mitra_ref` | map → partner mitra (untuk dimensi + faktur; POS sudah cek saldo) |
| `product_code` | map → `custom.ppob.product` + provider via SKU map |
| `target` (MSISDN/IDPEL, masked) | dikirim ke biller |
| `amount` / denom | validasi + harga |
| `inquiry_ref` (opsional) | untuk produk 2-langkah |
| `signature`, `timestamp`, `nonce` | HMAC (reuse secure-endpoint, `auth='public'` + `readonly=False`) |

**Response (Odoo → POS):** `status` (success/failed/pending), `provider_ref`, `serial/token`, `error_code`. POS meng-commit/rollback debit saldo mitra berdasarkan ini.

**Event yang tetap ada:** top-up saldo mitra (VA/POS feed), refund saldo mitra (bila POS yang berinisiatif), snapshot saldo untuk rekonsiliasi.

> Catatan implementasi: endpoint fulfillment mengikuti pola controller VA yang sudah diperbaiki untuk Odoo 19 — **`auth='public'` + `readonly=False`** (route yang menulis butuh transaksi read-write; `auth='none'` tak punya `env.user` sehingga `account.move._post` gagal). Lihat memory *odoo19-module-port-gotchas*.

---

## 8. Model GL — perbandingan

**Mirror (Fase 1):** dua jurnal terpisah dari dua feed (revenue dari POS, COGS/deposit dari H2H), margin dari join.

**Target (Fase 2):** POS masih membukukan saldo mitra (feed/mirror), Odoo membukukan sisi biller saat eksekusi:
```
  Dr  COGS PPOB                 cost      ← saat pay sukses (adapter)
        Cr  Deposit Biller (bucket)   cost      ← drawdown deposit authoritative
```
Revenue + drawdown saldo mitra tetap dari POS (mirror) sampai Fase 3. PPN tetap diakui di **summary faktur per mitra** (`custom_ppob_rollup` → Coretax), tidak per transaksi.

**Full native (Fase 3):** satu compound posting via atomic helpers (wallet debit → revenue, bucket debit → COGS/deposit), persis `custom_ppob_sale._dispatch_one`.

---

## 9. Keputusan terbuka (khusus replace-H2H)

1. **Batas replace.** Fase 2 saja (Odoo = biller switch, saldo mitra tetap di POS) atau lanjut Fase 3 (Odoo serap saldo mitra)? Menentukan apakah wallet Odoo tetap `mirror` atau jadi authoritative.
2. **Sinkron vs async fulfillment.** POS tunggu response Odoo (sinkron, UX lebih ketat SLA) atau POS async + callback? Rekomendasi: **sinkron dengan timeout + fallback ke pending + reaper**.
3. **Adapter biller riil.** Implementasi adapter konkret per biller (Digiflazz/IAK/dst) sebagai subclass `PPOBProviderAdapter` — belum ada; `ppob_http_json` generik jadi basis.
4. **Sumber saldo deposit awal.** Migrasi saldo deposit dari H2H ke bucket Odoo (opening balance + rekon) di titik cutover per biller.
5. **Idempotency saat dual-run.** Pastikan `pos_trx_ref` konsisten dipakai sebagai `idempotency_key` agar shadow-run tak bentrok dengan produksi.
6. **Window mundur.** Berapa lama mirror bridge dipertahankan pasca cutover untuk rollback & audit paritas.

---

## 10. Ringkasan satu kalimat

**Dari posisi Odoo sebagai *mirror ledger* (dua feed POS+H2H di-join), migrasi menonaktifkan H2H secara bertahap (strangler-fig, dual-run + gerbang paritas, cutover per biller/produk) sampai Odoo menjadi *transaction engine* yang authoritative — deposit biller di provider bucket, dispatch/pay/status via adapter + reaper, refund via `_refund_subledgers` — memakai suite `custom_ppob_*` mode native yang sudah dibangun & lulus 51/51 test, sementara ERASPACE POS tetap memegang saldo mitra (Fase 2) hingga opsi Fase 3 menyerapnya ke Odoo.**

---

*Referensi kode: `custom_ppob_sale` (`_dispatch_one`/`_resolve_provider`/reaper), `custom_ppob_provider` (bucket atomic + adapter registry + DP-100%), `custom_ppob_wallet` (atomic vs `_mirror_*`), `custom_ppob_rollup` (summary faktur), `custom_ppob_eraspace_bridge` (mirror ingest 2-feed). Companion: `docs/projects/ppob/ppob-eraspace-h2h-architecture.md`.*
