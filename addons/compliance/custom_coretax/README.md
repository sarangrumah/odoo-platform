# Custom Coretax (Indonesia DJP)

Implements the Coretax DJP compliance surface aligned with PER-11/PJ/2025
(effective 22 May 2025): NSFP lifecycle, e-Faktur and Bukti Potong XML
export/import, Sertifikat Elektronik storage, and an adapter abstraction
ready for future H2H ASPP integration.

## Models

- `custom.coretax.config` — per-company DJP config: NPWP, KPP, address,
  Sertel attachment ref, adapter type.
- `account.move` extension — adds `nsfp` (17-digit) and
  `coretax_status` (`draft` / `submitted` / `approved` / `rejected_djp`).
  NSFP is empty on draft and assigned by DJP after portal approval.
- `custom.coretax.bukti.potong` — header record for incoming /
  outgoing Bukti Potong (PPh 21 / 23 / 26 / Unifikasi). Reconciles to
  `account.move.line` PPh receivable.
- `custom.coretax.adapter.base` — abstract H2H adapter. Methods:
  `submit_xml(xml)`, `query_status(uuid)`, `download_response(uuid)`.
  Default `ManualAdapter` is a no-op (operators paste NSFP from the
  portal manually).

## Wizards

- "Export e-Faktur / Bupot" (`wizards/coretax_export_wizard_views.xml`)
  — pick period + document type → generate validated XML batch.
- "Import Faktur / Bupot" (`wizards/coretax_import_wizard_views.xml`)
  — upload XML, parse, match to `res.partner` by NPWP/NIK, create
  Bukti Potong records.
- "Upload Sertel" (`wizards/coretax_sertel_upload_views.xml`) — upload
  `.p12`, encrypt at rest with Fernet via `custom.ir.config`. Master
  key from env `CORETAX_SERTEL_MASTER_KEY`.

## XSD Validation

XML payloads are validated against XSDs in `data/xsd/` before submission
using the `xmlschema` Python library. **The XSDs are NOT bundled** —
operators must download official files from
<https://www.pajak.go.id/reformdjp/coretax/template-xml-dan-converter-excel-ke-xml>
and place them in `data/xsd/` post-install. See `data/xsd/README.md`.

## Document Types Covered

- e-Faktur Keluaran, Faktur Masukan
- Bupot PPh 21 (Pegawai Tetap & Bukan Pegawai Tetap)
- Bupot PPh 23
- Bupot PPh 26
- Bupot Unifikasi

## Audit

Every export / import / sertel access is written to `pdp.audit_log`
with `action='xml_export'` / `'xml_import'` / `'sertel_access'`
respectively.

## Security Groups

- `coretax.group_admin` — manage config, upload sertel.
- `coretax.group_user` — run export / import wizards, view records.

## Dependencies

- `custom_core`, `account`
- Python: `lxml`, `xmlschema`, `cryptography`

## Install

1. Set `CORETAX_SERTEL_MASTER_KEY` (32-byte Fernet key, base64) in
   `.env` before first boot.
2. Place official DJP XSDs into `data/xsd/`.
3. Install via Apps menu.
4. Configure NPWP / KPP / Sertel under Settings → Custom Platform →
   Coretax.

## Notes

A public REST API for DJP Coretax B2B integration is not confirmed as
of May 2026. The default workflow uses XML upload through the official
Coretax portal. The adapter abstraction is ready for a host-to-host
adapter when an ASPP subscription is in place.

## Reference

- `docs/coretax.md`
- PER-11/PJ/2025 (NSFP format)
