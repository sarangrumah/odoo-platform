# UU PDP 27/2022 Compliance Mapping

This document maps obligations under **Undang-Undang Pelindungan Data Pribadi
No. 27 Tahun 2022** (UU PDP) onto concrete platform features and Odoo addons.
Operators should read this end-to-end before go-live and re-read it whenever a
new vertical is added.

## Contents

- [Data classification](#data-classification)
- [Audit log immutability](#audit-log-immutability)
- [Consent management](#consent-management)
- [DSAR endpoint](#dsar-endpoint)
- [View / export masking](#view--export-masking)
- [Retention policy and auto-purge](#retention-policy-and-auto-purge)
- [DPO dashboard](#dpo-dashboard)
- [Operator checklist](#operator-checklist)

## Data classification

UU PDP Pasal 4 distinguishes **data pribadi umum** (general) from **data pribadi
spesifik** (specific: health, biometrics, genetics, criminal record, child data,
finance, etc.).

- Addon: `addons/compliance/custom_pdp_core/`
- Each ORM field can declare `pdp_class="general" | "specific" | "none"` via
  the `pdp.field.mixin`. Reports and exports respect this.
- Field-class registry: `addons/compliance/custom_pdp_core/data/pdp_field_class.csv`.

Operator responsibility:

1. When adding a new vertical, audit each new field and tag it.
2. Run `make pdp-classify-report DB=erp_prod` quarterly; the report flags
   untagged personal-data-shaped fields (heuristic: `*_nik`, `*_email`,
   `*_phone`, `*_dob`, `*_address`).

## Audit log immutability

UU PDP Pasal 35 requires accountability for personal-data processing. We
implement an append-only chain.

- Addon: `addons/compliance/custom_pdp_audit/`
- Table: `custom_pdp_audit_event` with columns
  `id, ts, actor_id, action, model, res_id, fields, prev_hash, row_hash`.
- Hash chain: `row_hash = sha256(prev_hash || canonical_payload)`.
- Postgres trigger: `addons/compliance/custom_pdp_audit/data/pg_trigger.sql` defines
  `tg_custom_pdp_audit_event_no_mod` which raises on `UPDATE` or `DELETE`.
- Verifier: cron job `custom_pdp_audit.cron_verify_chain` runs nightly.
- Export: `custom_pdp_audit.wizard_export` produces a signed JSONL bundle for
  the regulator.

Operator responsibility:

1. Never run `TRUNCATE` or `DROP` on `custom_pdp_audit_event` outside of the
   documented archival rotation (see [retention](#retention-policy-and-auto-purge)).
2. Investigate any `audit_chain_broken` Prometheus alert within 1 business hour.

## Consent management

UU PDP Pasal 22 requires explicit, granular, revocable consent.

- Addon: `addons/compliance/custom_pdp_consent/`
- Model: `pdp.consent` with fields `partner_id, purpose_id, granted_at,
  revoked_at, evidence_blob, channel`.
- Purposes live in `pdp.purpose`. Each purpose is referenced by addon code
  via XML id (e.g. `custom_marketing_automation.purpose_newsletter`).
- Helper: `partner._pdp_has_consent(purpose_xmlid)` returns boolean.
- Frontend widget renders a consent receipt and stores the signed payload.

Operator responsibility:

1. Configure purpose taxonomy before onboarding tenants.
2. Train CS staff to never tick consent on behalf of a subject.

## DSAR endpoint

UU PDP Pasal 5 grants rights of access, rectification, erasure, portability.

- Addon: `addons/compliance/custom_pdp_dsar/`
- Controller route: `/pdp/dsar/request` (POST, captcha + email verification).
- Backend model: `pdp.dsar.request` with states
  `draft -> verified -> in_progress -> fulfilled | rejected`.
- SLA: 3 business days to acknowledge, 30 days to fulfill (UU PDP Pasal 13).
- Export bundle: `custom_pdp_dsar.wizard_bundle` walks all `pdp_class != "none"`
  fields and produces a ZIP (JSON + attachments).

Operator responsibility:

1. Monitor SLA via the DPO dashboard.
2. Reject only with a documented reason from the regulator-approved list at
   `addons/compliance/custom_pdp_dsar/data/rejection_reasons.csv`.

## View / export masking

UU PDP Pasal 16 requires least-privilege access.

- Addon: `addons/compliance/custom_pdp_masking/`
- Mechanism: ORM `_read_group` and `read` are wrapped; fields tagged
  `pdp_class="specific"` are masked unless the user has
  `custom_pdp_masking.group_unmask_specific`.
- Mask format: `NIK 32********1234` (first 2 / last 4 visible).
- Excel and CSV exports use the same hook; PDF reports honor
  `report.context.get("pdp_unmask")`.

Operator responsibility:

1. Never grant `group_unmask_specific` to service accounts.
2. Quarterly: review `Settings -> Users -> Group: PDP Unmask` membership.

## Retention policy and auto-purge

UU PDP Pasal 43 requires deletion when the processing purpose ends.

- Addon: `addons/compliance/custom_pdp_retention/`
- Policy table: `pdp.retention.policy` with `(model, domain, max_age_days,
  action)` where action is `purge`, `anonymize`, or `archive`.
- Cron: `custom_pdp_retention.cron_apply` runs daily at 02:00 server time.
- Anonymization replaces personal fields with `pdp_anon.<hash>` values; the
  primary key is preserved so financial records still reconcile.
- Hard purge writes a tombstone to the audit log before `unlink`.

Operator responsibility:

1. Maintain policy CSV at `addons/compliance/custom_pdp_retention/data/policies.csv`.
2. Run dry-run mode (`--dry-run`) before each policy change in production.

## DPO dashboard

- Addon: `addons/compliance/custom_pdp_audit/`
- Menu: Custom Platform -> Privacy -> DPO Dashboard.
- Widgets:
  - Open DSARs by SLA bucket.
  - Consent grants / revocations (30-day trend).
  - Audit chain status (last verification).
  - Retention purge volume.
  - Pending breach notifications (UU PDP Pasal 46: 3x24 jam to subject).

Operator responsibility:

1. DPO logs in at least weekly.
2. Breach playbook: `docs/runbooks/incident-pdp-breach.md` (TBD; track in
   `docs/plan.md`).

## Operator checklist

- [ ] All custom fields in new verticals carry a `pdp_class`.
- [ ] Postgres trigger `tg_custom_pdp_audit_event_no_mod` exists on production.
- [ ] Nightly chain-verify cron is green.
- [ ] Retention policy CSV is reviewed quarterly.
- [ ] DPO has been onboarded and has dashboard access.
