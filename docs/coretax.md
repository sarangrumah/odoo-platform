# Coretax DJP Integration

This document describes how the platform integrates with **Coretax DJP** (the
new core tax administration system of Direktorat Jenderal Pajak), based on
**PER-11/PJ/2025**.

> **Reality check (per Mei 2026):** DJP belum menyediakan public REST API B2B
> umum untuk wajib pajak. Integrasi resmi dilakukan via **upload manual ke
> portal Coretax** (atau via penyalur ASP/PJAP yang ditunjuk). Dokumen ini
> mendeskripsikan jalur yang sah hari ini dan menyiapkan adapter abstrak agar
> nanti tinggal swap ke H2H ASPP saat tersedia.

## Contents

- [Regulatory anchor: PER-11/PJ/2025](#regulatory-anchor-per-11pj2025)
- [NSFP format and lifecycle](#nsfp-format-and-lifecycle)
- [Status codes](#status-codes)
- [XML export workflow per template](#xml-export-workflow-per-template)
- [XSD source of truth](#xsd-source-of-truth)
- [Manual upload via Coretax portal](#manual-upload-via-coretax-portal)
- [Future: H2H ASPP via abstract adapter](#future-h2h-aspp-via-abstract-adapter)
- [Sertel storage and encryption](#sertel-storage-and-encryption)
- [Bukti potong import workflow](#bukti-potong-import-workflow)
- [Operator checklist](#operator-checklist)

## Regulatory anchor: PER-11/PJ/2025

- Mengatur format e-Faktur dan e-Bupot yang berlaku di Coretax.
- Menetapkan **17 digit NSFP** dengan format `KKSSYYNNNNNNNNNNN` dimana:
  - `KK` = kode transaksi (2 digit, mis. `01` untuk PPN biasa, `04` untuk DPP
    nilai lain, dll.).
  - `SS` = kode status (2 digit, lihat tabel di bawah).
  - `YY` = dua digit tahun.
  - `NNNNNNNNNNN` = 11 digit nomor urut yang **diberikan oleh DJP setelah XML
    di-upload dan diterima**.
- NSFP **tidak lagi diminta dimuka** (range jatah). Setiap faktur valid
  setelah Coretax meng-assign NSFP balik.

## NSFP format and lifecycle

```
+------------+----------+--------+
|    KKSS    |   YY     |  NNNN..|
| transaksi  |  tahun   |  urut  |
| + status   |          | (DJP)  |
+------------+----------+--------+
        2+2 = 4    +2     +11    = 17
```

Lifecycle in Odoo:

1. Issue invoice (`account.move`) inside `custom_coretax`.
2. Generate XML (template-31 family, see below).
3. Submit (today: manual upload; later: H2H).
4. Receive Coretax response with NSFP -> stored on
   `account.move.x_custom_coretax_nsfp`.
5. Print/email faktur with NSFP shown.

If submission is rejected, the invoice transitions to
`coretax_state = "rejected"` and an activity is raised to the AR clerk.

## Status codes

| Code | Meaning | Notes |
| --- | --- | --- |
| `00` | Normal | Default for new faktur. |
| `01` | Pengganti | Replaces a previously valid faktur. Carries reference to old NSFP. |
| `02` | Pembatalan | Cancellation. Must be filed before pelaporan masa SPT. |
| `03..` | Reserved by DJP | See PER-11/PJ/2025 attachment. |

The complete table lives in
`addons/compliance/custom_coretax/data/coretax_status_code.csv` and is loaded into
`coretax.status.code` for reference in selection fields.

## XML export workflow per template

PER-11/PJ/2025 references **31 templat XML** (faktur normal, pengganti,
pembatalan, faktur retur, bukti potong PPh 21/23/26/4(2)/15, SPT masa,
dll.). Operator workflow:

1. Open the document in Odoo (e.g. `account.move`, `hr.payslip`).
2. Action menu -> **Coretax -> Export XML**.
3. The wizard `custom.coretax.export.wizard` selects the matching template based on
   document type and resolves XSD from
   `addons/compliance/custom_coretax/data/xsd/<template>.xsd`.
4. The wizard validates locally against the XSD before download (avoid
   round-trips with malformed XML).
5. XML is attached to the document AND mirrored to
   `filestore/coretax/<yyyy>/<mm>/<doc>.xml`.

Bulk export: `Coretax -> Batch Export` accepts a date range and produces a
single ZIP per template.

## XSD source of truth

- Download from <https://pajak.go.id/coretax> (section "Skema XML").
- Mirror into `addons/compliance/custom_coretax/data/xsd/`.
- Update procedure: `make coretax-xsd-refresh` fetches and diffs against
  current files; commit only if checksum changes.
- Each XSD file ships with a `*.sha256` sibling for tamper detection.

## Manual upload via Coretax portal

Today this is the only sanctioned channel for most WP. Steps:

1. Login to <https://coretaxdjp.pajak.go.id/> with NPWP + password + OTP.
2. Navigate to **e-Faktur -> Upload Faktur**.
3. Upload the XML produced by the export wizard (single file or ZIP for batch).
4. Wait for processing (typically minutes; SLA bisa lebih lama saat akhir masa).
5. Download the response file (CSV) listing assigned NSFP and any rejections.
6. In Odoo: **Coretax -> Import Response**, upload the CSV; the importer
   updates `x_custom_coretax_nsfp` and `coretax_state` per line.

## Future: H2H ASPP via abstract adapter

The export and import wizards delegate to `custom.coretax.adapter` (abstract
model). Implementations:

| Adapter | Status | Path |
| --- | --- | --- |
| `coretax.adapter.manual` | Active | `addons/compliance/custom_coretax/adapters/manual.py` |
| `coretax.adapter.h2h` | Skeleton | `addons/compliance/custom_coretax/adapters/h2h.py` |

When DJP/PJAP membuka kanal H2H resmi, only the H2H adapter needs filling in:

1. Implement `submit(xml_bytes) -> submission_id`.
2. Implement `poll(submission_id) -> response_payload`.
3. Set system parameter `custom_coretax.adapter = "h2h"` and restart.

No business code changes required.

## Sertel storage and encryption

Sertifikat Elektronik (sertel) milik WP wajib dilindungi.

- Storage: `addons/compliance/custom_coretax/sertel/` is a **gitignored** path mounted
  from a host volume. Files are AES-256-GCM encrypted at rest using a key in
  Vault (`secret/custom/coretax/sertel_key`).
- Access: only the technical user `coretax_signer` may decrypt; all other
  Odoo users see metadata only.
- Rotation: replace sertel before its DJP expiry; record the new fingerprint
  in `coretax.sertel.history`.
- Backup: include Vault snapshot in the daily backup; never copy plaintext
  sertel to S3.

## Bukti potong import workflow

Counterparty bukti potong (PPh 23, 4(2), 26) datang sebagai XML/PDF via email.

1. Operator menjalankan **Coretax -> Import Bupot** dan memilih file XML.
2. Wizard memvalidasi XSD dan mencocokkan NPWP pemotong + nomor bupot.
3. Sistem membuat `account.move` jenis `entry` dengan tag
   `coretax_bupot_id` dan melampirkan PDF asli.
4. Bupot terhubung ke faktur jual yang relevan via `partner_id` + periode.
5. Saat rekonsiliasi PPh, saldo `Uang Muka PPh` ditarik dari kumpulan bupot.

PDF-only bupot harus diketik manual atau diparse via OCR (lihat
`addons/compliance/custom_coretax/wizards/bupot_ocr.py` - opt-in).

## Operator checklist

- [ ] Sertel valid dan ter-mount; expiry > 30 hari.
- [ ] XSD checksums match upstream (run `make coretax-xsd-refresh`).
- [ ] Adapter aktif sesuai kanal yang berlaku (manual atau h2h).
- [ ] Cron `custom_coretax.cron_resync_status` hijau.
- [ ] Backup sertel terverifikasi bulanan.
