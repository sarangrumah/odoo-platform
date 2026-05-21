---
status: draft
generated_at: 2026-05-21T00:00:00Z
generator: claude-code-bootstrap-v1
module: custom_pdp_masking
manifest_version: 19.0.0.2.0
---

# custom_pdp_masking

## Purpose
Provides **read-time PII masking** for UU 27/2022. Two parallel masking paths are active simultaneously:

1. **Classification-driven mixin** (`pdp.masked.mixin`) — applied per model that opts in; reads `x_pdp_classification_id` on `ir.model.fields` and routes through `pdp.masking._mask` which picks a strategy by field name (`email`/`phone`/`mobile`/`nik`/`vat`/`name`/`display_name`) or by classification.
2. **Registry-driven base hook** (`pdp_registry_hook.BaseMaskingHook` inheriting `"base"`) — applies to **every model in the registry** via a global `read()` override that consults `custom.pdp.field.registry` for explicit `(model, field) → pattern` rules. Patterns are `full / last4 / first_letter / email_domain / hash / redacted`.

A reason-audited `pdp.unmask.wizard` lets privileged users view records in the clear by passing record ids + reason through `pdp_unmasked_ids` context. A discovery wizard scans `ir.model.fields` for likely-PII names and suggests registry entries.

## Business Flow
- Operator/admin configures the masking policy via `res.config.settings.pdp_masking_policy` (stored at `ir.config_parameter` key `pdp.masking.policy`): `always_mask` / `mask_in_export_only` / `unmask_with_reason` (default).
- `pdp.masked.mixin.read()` postprocesses rows: if `policy == "always_mask"` always masks; if `mask_in_export_only` always returns clear (export pathway masks elsewhere); if `unmask_with_reason` returns clear only when the user has `custom_pdp_masking.group_view_pii`. Records whose id is in `context["pdp_unmasked_ids"]` are always returned in the clear (after wizard sign-off).
- `pdp_registry_hook.BaseMaskingHook.read()` (mixed into `base`) consults `custom.pdp.field.registry._registry_for(model)` (env-cached); for each applicable rule whose `mask_groups` the current user is NOT in, it overwrites the row value via `_apply_pattern(value, pattern)`. Then it best-effort logs a `pii_mask` row to `pdp.audit_log` aggregating which fields were masked how many times.
- Discovery: `custom.pdp.field.discovery.wizard.action_scan` regex-scans every stored char/text/date(time)/selection field on non-transient models for tokens like `email|phone|nik|npwp|passport|birth|salary|account|iban|swift|address|street|zip|tax_id|gender|marital`, suggests a `(pii_category, mask_pattern)` per `_PATTERN_TO_CATEGORY`. `action_create_selected` materialises the selected suggestions into `custom.pdp.field.registry` rows.
- Unmask flow: a user with the right access opens `pdp.unmask.wizard` for a `(model, csv-of-ids, reason)`, `action_unmask` writes one `unmask` audit row per id with the reason, then opens the act_window with `context["pdp_unmasked_ids"]=ids`.
- `res.partner` is opted into `pdp.masked.mixin` by default.
- `data/pdp_field_registry_seed.xml` calls `custom.pdp.field.registry._seed_optional_hr_fields()` post-install to populate HR PII rules if `hr`/`hr_recruitment` are present.

## Key Models
- `pdp.masking` (AbstractModel) — Stateless masking service; field-name-keyed strategy table.
- `pdp.masked.mixin` (AbstractModel) — Per-model opt-in `read()` override using `x_pdp_classification_id`.
- `custom.pdp.field.registry` — Per-`(model_name, field_name)` masking rule with `pii_category`, `mask_pattern`, and bypass `mask_groups`. Inherits `pdp.audited.mixin`.
- `base` (inherited via `BaseMaskingHook`) — Global `read()` override consulting the registry for all models.
- `pdp.unmask.wizard` (TransientModel) — Reason-audited unmasking request.
- `custom.pdp.field.discovery.wizard` + `.suggestion` (TransientModels) — Heuristic PII scanner.
- `res.config.settings` (inherited) — Adds `pdp_masking_policy` config.
- `res.partner` (inherited) — Adds `pdp.masked.mixin`.

## Important Fields
- `custom.pdp.field.registry.model_id` (M2o `ir.model`, required, cascade) + `model_name` (Char related, stored, indexed) + `field_name` (Char, required, indexed) — keyed pair, unique via `model_field_unique` SQL constraint.
- `custom.pdp.field.registry.pii_category` (Selection: nik/npwp/phone/email/address/dob/account_no/passport/bank_account/medical/biometric/salary/other) — informational tag.
- `custom.pdp.field.registry.mask_pattern` (Selection: full/last4/first_letter/email_domain/hash/redacted) — drives `_apply_pattern`.
- `custom.pdp.field.registry.mask_groups` (M2m `res.groups`) — users in any of these groups see the value in the clear (bypass).
- `pdp.unmask.wizard.model_name` (Char, readonly) / `res_ids_csv` (Char, required) / `reason` (Text, required).
- `res.config.settings.pdp_masking_policy` (Selection at `ir.config_parameter` `pdp.masking.policy`) — three-level policy.
- `pdp.masking._STRATEGY_BY_FIELD_NAME` (module-level dict, not a field) — name→fn mapping for `email/phone/mobile/nik/vat/name/display_name`.

## Public Methods
- `pdp.masking._mask(value, classification_code, user=None, field_name=None)` — main strategy dispatch; falls back to `[REDACTED]`.
- `pdp.masking._policy()` / `_user_can_view_pii(user=None)` — reads the policy and the `group_view_pii` membership.
- `pdp.masked.mixin.read(fields, load)` — postprocesses every read with the classification map.
- `custom.pdp.field.registry._registry_for(model_name)` (`@api.model`) — returns cached list of `{field, category, pattern, groups}` dicts.
- `custom.pdp.field.registry._user_bypasses(group_ids)` / `_apply(value, pattern)` — helpers used by the base hook.
- `custom.pdp.field.registry._seed_optional_hr_fields()` (`@api.model`) — bulk seed; idempotent.
- `BaseMaskingHook.read(fields, load)` — global hook on `"base"`, masks per registry, audits aggregated counts.
- `pdp.unmask.wizard.action_unmask()` — audit + open act_window with `pdp_unmasked_ids` context.
- `custom.pdp.field.discovery.wizard.action_scan()` / `action_create_selected()` — discovery + bulk-create.

## Integration Points
- **Depends on:** `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `account`, `custom_coretax_bupot`, `custom_pph_witholding`.
- **Inherits from:** `base` (global `read()` override), `res.partner` (adds masked mixin), `res.config.settings`, `pdp.audited.mixin` (on registry model).
- **Extended by:** vertical modules that want field-level rules — they just create `custom.pdp.field.registry` rows; no Python subclassing needed.
- **External calls:** none.
- **Cross-vertical:** generic.

## Gotchas
- **Two masking mechanisms run in parallel.** Both `pdp.masked.mixin` and `BaseMaskingHook` override `read()` and may both fire on the same row — registry-driven first (because it's on `base`), then mixin-driven for opted-in models. If both apply to the same field, the registry pattern wins because the mixin sees the already-masked value and matches no `_STRATEGY_BY_FIELD_NAME` (so it falls back to `_mask_generic` → `[REDACTED]` over a `[REDACTED]`, which is a no-op only by accident).
- **`account`, `custom_coretax_bupot`, `custom_pph_witholding` are HARD dependencies** for what is logically a generic masking module. Removing them needs a manifest change; the only on-disk linkage is through the field-registry seed XML referencing those models.
- **The `base` inheritance applies to literally every `read()` in the system**, including transient models and `ir.*` infra. Performance cost is a single env-cached lookup per model per request — acceptable but not free.
- **Audit `pii_mask` writes happen for every read with masked fields** — high-traffic models (e.g. list views over `res.partner`) will fill `pdp.audit_log` rapidly. The chain table is append-only by design.
- **`group_view_pii` bypasses the mixin path entirely** but does NOT bypass the registry path unless the user is in one of the rule's `mask_groups`. Inconsistency: a "view PII" user still sees registry-masked fields.
- **`mask_in_export_only` policy is partly aspirational** — the mixin returns the clear value in this mode, but there is no actual "export" detection that triggers masking on `export_data`. Document carefully before relying on it.
- **`_apply_pattern("hash", v)` truncates to 12 hex chars** — collision-prone if used as a stable id.
- **Discovery wizard's `_PATTERN` regex matches substring**, so `phone_number` and `birthday_reminder_email` both match; review suggestions before bulk-creating.

## Out of Scope
- **Export-time masking** — the policy `mask_in_export_only` is wired in name only; actual export interception is not implemented here.
- **Format-preserving encryption / reversible masking** — all patterns are one-way display transforms.
- **Per-row / contextual masking** (e.g. mask salary for the employee themselves but show to HR) — only group-based bypass exists.
- **UI for managing `mask_groups`** beyond stock M2m widget — bulk reassignment requires CSV/import.
- **Masking inside computed/related fields whose source is unmasked** — mask is applied to the read row, not the underlying value, so other code paths (computes, reports run in cron) see clear values.
