---
status: draft
generated_at: 2026-05-21T00:00:00Z
generator: claude-code-bootstrap-v1
module: custom_coretax_bupot
manifest_version: 19.0.0.1.0
---

# custom_coretax_bupot

## Purpose
Implements **e-Bupot Unifikasi v2** (PPh 22 / 23 / 4(2) / 15 / 26 in a single SPT) on top of `custom_coretax`. Per-period header (`custom.bupot.unifikasi`) + per-cut line (`custom.bupot.unifikasi.line`), an XML export wizard producing the DJP Coretax v2 schema, a CSV upload wizard for ingesting DJP-assigned bupot numbers after acceptance, and a QWeb PDF report "Bukti Potong PPh Unifikasi". Both header and line inherit `pdp.audited.mixin`.

This is the unified-bupot companion to `custom_coretax` (which itself models the more generic `custom.coretax.bukti.potong` plus PPh 21 documents).

## Business Flow
- Operator creates `custom.bupot.unifikasi(company_id, month, year)` — `name` auto-computed as `BPU/<year>/<month>`. Uniqueness `period_unique` on `(company_id, month, year)`.
- Operator adds `custom.bupot.unifikasi.line` rows (pph_type, cuttee NPWP/NITKU/name, gross/dpp/withheld, rate, optional `doc_ref` Reference to `account.move` / `account.payment`). `internal_ref` is auto-assigned from `ir.sequence` `custom.bupot.unifikasi.line`. NPWP must match `^\d{15,16}$`; amounts non-negative; rate 0..100.
- Operator runs `action_generate_xml` → opens `custom.bupot.xml.export.wizard`. The wizard's `action_generate` builds the XML in-memory (manual `BytesIO` + `xml.sax.saxutils.escape`, NOT lxml), creates an `ir.attachment` on the period, and bumps `state: draft → generated`.
- Operator uploads the XML to the DJP Coretax portal, then runs `action_mark_submitted` (state `submitted`).
- DJP returns a CSV mapping internal-ref → DJP-assigned bupot number. Operator runs `action_open_number_upload` → `custom.bupot.number.upload.wizard` parses the CSV (headers `internal_ref,bupot_number` required, UTF-8 BOM tolerant), writes `bupot_number` on matched lines, surfaces missing/ambiguous refs in the `report` field. If all lines are filled and the header was `submitted`, auto-promotes to `accepted`.
- On rejection: `action_mark_rejected` (free state); `action_reset_draft` returns to `draft`; `action_mark_accepted` is a manual override (only allowed from `submitted`).

## Key Models
- `custom.bupot.unifikasi` — Period header (1 per company per month). Inherits `pdp.audited.mixin`, `mail.thread`, `mail.activity.mixin`.
- `custom.bupot.unifikasi.line` — One withholding cut. Inherits `pdp.audited.mixin`.
- `custom.bupot.xml.export.wizard` (TransientModel) — XML generation + attachment + state promote.
- `custom.bupot.number.upload.wizard` (TransientModel) — CSV-driven number assignment + auto-promote.

## Important Fields
- `custom.bupot.unifikasi.month` (Selection `"1"`..`"12"`, required) — stored as string with two-digit display.
- `custom.bupot.unifikasi.year` (Char size=4, required) — 4-char string year.
- `custom.bupot.unifikasi.state` (Selection: draft/generated/submitted/accepted/rejected, tracked) — workflow gate.
- `custom.bupot.unifikasi.line_ids` (O2m → `custom.bupot.unifikasi.line`) — period lines.
- `custom.bupot.unifikasi.line_count` (Integer, computed) / `total_withheld` (Float, computed sum of line withheld_amount).
- `custom.bupot.unifikasi.line.internal_ref` (Char, sequence `custom.bupot.unifikasi.line`, fallback `"/"`) — pre-DJP-acceptance reference; the CSV upload joins on this.
- `custom.bupot.unifikasi.line.bupot_number` (Char) — DJP-assigned number filled by the upload wizard.
- `custom.bupot.unifikasi.line.pph_type` (Selection: 23/22/4_2/15/26, required) — note: no `21` (PPh21 lives in `custom_coretax` and HR).
- `custom.bupot.unifikasi.line.cuttee_npwp` (Char) — validated by `_NPWP_RE = ^\d{15,16}$`.
- `custom.bupot.unifikasi.line.cuttee_nitku` (Char) — NITKU (Nomor Identitas Tempat Kegiatan Usaha) for sub-locations.
- `custom.bupot.unifikasi.line.doc_ref` (Reference: `account.move` | `account.payment`) — back-link to source transaction.
- `custom.bupot.unifikasi.line.gross_amount` / `dpp_amount` / `withheld_amount` (Float 16,2, required, non-negative).
- `custom.bupot.unifikasi.line.rate` (Float 6,4, required, 0..100).

## Public Methods
- `custom.bupot.unifikasi.action_generate_xml()` — opens the export wizard (raises if no lines).
- `custom.bupot.unifikasi.action_mark_submitted()` — draft/generated → submitted; raises otherwise.
- `custom.bupot.unifikasi.action_mark_accepted()` — submitted → accepted; raises otherwise.
- `custom.bupot.unifikasi.action_mark_rejected()` / `action_reset_draft()` — free transitions.
- `custom.bupot.unifikasi.action_open_number_upload()` — opens CSV upload wizard.
- `custom.bupot.xml.export.wizard.action_generate()` / `_build_xml(period)`.
- `custom.bupot.number.upload.wizard.action_apply()` — match-by-`internal_ref`, write `bupot_number`, report missing/ambiguous, auto-promote header.

## Integration Points
- **Depends on:** `custom_core`, `custom_pdp_audit`, `custom_coretax`, `account`, `mail`.
- **Inherits from:** `pdp.audited.mixin` (both models), `mail.thread`, `mail.activity.mixin` (header only).
- **Extended by:** `custom_pph_witholding` writes `custom.bupot.unifikasi.line` records via `bupot_line_id` link on `custom.witholding.application`.
- **External calls:** none (manual portal flow).
- **Cross-vertical:** generic Indonesian tax compliance.

## Gotchas
- **XML is built with raw `BytesIO` + `xml.sax.saxutils.escape`, NOT lxml.** That means no XSD validation here (the export wizard does not call `xmlschema`); it produces a payload that is structurally close to the DJP "BuktiPotongUnifikasi" v2 template but not formally verified against the schema. Validate externally before submitting to production.
- **`pph_type` selection excludes `21`** — PPh21 (`bupot_21_tetap`/`bupot_21_bukan_tetap`) flows through `custom_coretax` instead. If a downstream module tries to log PPh21 here, it will raise a Selection error.
- **`internal_ref` join is case-sensitive** — `BPU0000123` ≠ `bpu0000123`; operators feeding CSVs from spreadsheets must preserve case.
- **CSV upload auto-promotes header to `accepted`** as soon as every line has a `bupot_number` AND header is `submitted`. If you upload a partial CSV that happens to fill the last gap, the header jumps to `accepted` without explicit confirmation.
- **NITKU is a Char with no format validation** — DJP rules around NITKU length/format are not enforced; bad values will be rejected by DJP, not at write time.
- **`doc_ref` is `fields.Reference`, not Many2one** — meaning the linked record can be deleted out from under the bupot line silently; no FK enforcement.
- **`month` selection values are Char `"1".."12"`** (not zero-padded), so `int(period.month):02d` is used everywhere to render — code must not blindly compare `period.month == "01"`.

## Out of Scope
- **PPh21 (Pegawai Tetap / Bukan Tetap)** — handled by `custom_coretax` + HR modules, not here.
- **Automated number assignment** — DJP issues numbers; this module ingests them via CSV.
- **XSD-formal validation** — the export wizard generates XML but does not validate against a Coretax XSD. Add validation by routing through the `custom_coretax` export wizard's `_validate_xml` if needed.
- **Direct host-to-host submission to DJP** — manual portal upload only.
- **Per-line attachments (e.g. payment receipt scans)** — only `doc_ref` to an Odoo record is supported.
- **Multi-currency bupot** — `currency_id` field exists on both models but the XML serialises raw amounts with no currency tag; only IDR is realistic.
