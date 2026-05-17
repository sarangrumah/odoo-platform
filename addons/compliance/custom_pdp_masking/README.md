# Custom PDP Masking

Strategy-based masking applied at read/export time for PDP-classified
fields. Users without `pdp.group_view_pii` see masked values; admins can
unmask with a recorded reason.

## Services

- `pdp.masking._mask(value, classification, user_groups)` — strategies:
  - `email` → `j***@d***ain.com`
  - `phone` → `08••••••1234`
  - `nik` → `327••••••••0001`
  - `name` → first 2 chars + `***`
  - default → `[REDACTED]`

## ORM Hooks

`models/pdp_masking.py` patches `Model.read`, `Model.search_read`, and
`Model.export_data` so that any field with a non-null
`x_pdp_classification_id` flagged `requires_masking` returns masked
values when the caller lacks `pdp.group_view_pii`.

## Wizards

- "Unmask With Reason" (`wizards/pdp_unmask_wizard_views.xml`) — popup
  asking for justification; on submit, opens the unmasked record and
  logs the reason to `pdp.audit_log`.

## Settings

`pdp.unmask.policy` — `always_mask` / `mask_in_export_only` /
`unmask_with_reason`. Configured per company under Settings → Custom
Platform → PDP → Masking.

## Security Groups

- `pdp.group_view_pii` — bypasses masking on read.

## Dependencies

- `custom_core`, `custom_pdp_core`, `custom_pdp_audit`

## Install

Install after `custom_pdp_audit`. Configure unmask policy in Settings.

## Reference

- `docs/pdp-compliance.md` § "Masking"
