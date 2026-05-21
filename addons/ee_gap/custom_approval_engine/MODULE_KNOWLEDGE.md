---
status: draft
generated_at: 2026-05-21T00:00:00Z
generator: claude-code-bootstrap-v1
module: custom_approval_engine
manifest_version: 19.0.0.1.0
---

# custom_approval_engine

## Purpose
The canonical generic multi-tier approval workflow for the platform. Any model can opt in by inheriting `approval.mixin`; the engine handles matrix resolution, ordered tier traversal, multi-approver / require-all logic, manual delegation, OOO auto-delegation from `hr.leave`, SLA + escalation cron, immutable audit history, and portal access for external approvers.

This is the SINGLE source of truth for approvals. Any BRD requirement involving "approval matrix", "approval levels", "multi-step approval", "approver groups", "delegation", "out-of-office", "SLA escalation", "auto-approve on timeout", or "approval audit trail" maps here — do NOT propose a new module. Already wired into `account.move` (post gate), `purchase.order` (confirm gate), `sale.order` (confirm gate), and `hr.leave` (OOO source).

## Business Flow
- **Matrix definition**: an `approval.matrix` declares `model_id` (any `ir.model`, transient excluded), `condition_domain` (Python list literal, evaluated against the candidate record), `priority` (higher wins on ambiguity), `trigger` ∈ manual/on_create/on_state_change, and an ordered set of `approval.matrix.tier` rows.
- **Tier definition**: each `approval.matrix.tier` has `sequence`, `approver_type` ∈ `user`/`group`/`manager_of_creator`/`domain`, `require_all` (Boolean), `sla_hours` (Float, default 24h), and `on_overdue` ∈ `auto_approve`/`escalate_to_next`/`escalate_to_user`/`none` + optional `escalation_user_id`.
- **Matrix resolution**: `approval.matrix._resolve_for(record)` filters by `model_name == record._name` + matching `company_id` + `_domain_matches(condition_domain, record)`, returns highest-priority active match.
- **Request lifecycle**: `approval.request._create_for_record(record, matrix=None)` produces a draft request (idempotent — returns existing draft/pending). `action_submit()` advances to first tier (sorted by `sequence`), stamps `due_at = now + sla_hours`, calls `_refresh_pending_approvers` and `_notify_pending`. Approver calls `action_approve(comment)` — records line, checks `require_all` (if set, waits until all `pending_approver_ids` have approved at this tier), then `_advance_to_next_tier`. If last tier, state → `approved`, stamps `final_decision_user_id` + `decided_at`. `action_reject(comment)` → state `rejected`. `action_cancel(reason)` allowed from draft/pending.
- **Approver resolution** per tier: `_resolve_approvers(record)` returns the raw approver set based on `approver_type`. Then `_refresh_pending_approvers` walks each user: (1) if active `approval.ooo` with `auto_delegate_to_id` → use delegate; (2) else if active `approval.delegation` (`_find_delegated_to`) for this `res_model` → use `delegate_to_id`; (3) else use user. The final `pending_approver_ids` is the effective list at this tier.
- **Delegation**: `approval.delegation` (manual) has `user_id` (delegator), `delegate_to_id`, `valid_from`/`valid_until`, optional `model_ids` to restrict scope. Lookups: `_find_delegated_to(user)` (user is delegator), `_find_delegating(user)` (user is delegate — used to record `delegated_from_id` on history line).
- **OOO**: `approval.ooo` (often auto-created from `hr.leave`) has `user_id`, `leave_id`, `date_from`/`date_to`, `auto_delegate_to_id`. `_active_for(user)` returns the first active OOO at `now`.
- **SLA cron**: `_cron_check_escalations` (every 15 min via `ir.cron`) finds `state='pending' AND overdue=True` (where `overdue` computes `due_at < now`); per request `_handle_overdue()` dispatches on `tier.on_overdue`: `auto_approve` records line as `base.user_root` + advances tier; `escalate_to_next` records escalation line + advances; `escalate_to_user` rewrites `pending_approver_ids = [escalation_user_id]` + resets `due_at`; `none` just re-notifies.
- **Mixin gate**: downstream models inherit `approval.mixin` and call `_approval_check_required()` from `button_confirm` / `_post`. Returns True if no matrix matches OR request is `approved`; raises `UserError` for draft/pending/rejected/cancelled with a helpful message.

## Key Models
- `approval.matrix` — Top-level matrix; `priority desc, sequence asc, id asc` resolution order.
- `approval.matrix.tier` — Ordered tier with approver-resolution config + SLA + overdue action.
- `approval.request` — One per (record × matrix) lifecycle. Inherits `mail.thread`, `mail.activity.mixin`, `pdp.audited.mixin`. Stores `res_model`/`res_id` + computed `res_ref` Reference.
- `approval.request.line` — Immutable history (write/unlink raise UserError unless context flag set); one row per submit/approve/reject/delegate/escalate/cancel/comment action.
- `approval.delegation` — Manual delegation (`user_id` → `delegate_to_id`), optional `model_ids` scope.
- `approval.ooo` — Out-of-office record (often auto from `hr.leave`).
- `approval.mixin` — `AbstractModel`; mix into any downstream model to add `x_custom_approval_request_id` + `x_custom_approval_state` related/computed fields + `action_request_approval`/`action_cancel_approval`/`action_open_approval_request` + `_approval_check_required()` gate.
- `account.move` / `purchase.order` / `sale.order` / `hr.leave` (inherited) — built-in integration points.

## Important Fields
- `approval.matrix.condition_domain` (Char, default `"[]"`) — Python literal list, eval'd via `ast.literal_eval`, applied as `search_count([('id','=',record.id), *domain])`.
- `approval.matrix.priority` (Integer, default 10) — higher wins; used for "specific override on top of broad default".
- `approval.matrix.model_name` (Char, stored related from `model_id.model`, indexed) — fast lookup key.
- `approval.matrix.trigger` (Selection manual/on_create/on_state_change) — when to auto-create requests (manual = button-driven; the others are hooks for downstream extensions).
- `approval.matrix.tier.approver_type` (Selection user/group/manager_of_creator/domain) — determines `_resolve_approvers`.
- `approval.matrix.tier.require_all` (Boolean) — false = any approver suffices; true = every approver in the resolved set must approve before tier advances.
- `approval.matrix.tier.sla_hours` (Float, default 24, must be > 0) — drives `due_at`.
- `approval.matrix.tier.on_overdue` (Selection auto_approve/escalate_to_next/escalate_to_user/none) — drives `_handle_overdue`.
- `approval.matrix.tier.escalation_user_id` (M2o `res.users`) — required when `on_overdue='escalate_to_user'`.
- `approval.request.state` (Selection draft/pending/approved/rejected/cancelled, tracking, indexed).
- `approval.request.current_tier_id` (M2o `approval.matrix.tier`).
- `approval.request.due_at` (Datetime, tracking) — `now + sla_hours` at each tier advance.
- `approval.request.overdue` (Boolean, computed + searchable via `_search_overdue`) — `state=='pending' AND due_at<now`.
- `approval.request.pending_approver_ids` (M2m `res.users`) — effective list AFTER OOO + delegation resolution.
- `approval.request.history_ids` (O2m `approval.request.line`) — immutable audit.
- `approval.request.final_decision_user_id` / `decided_at` — set on approve/reject.
- `approval.request.line.action` (Selection submitted/approved/rejected/delegated/escalated/cancelled/commented).
- `approval.request.line.delegated_from_id` (M2o `res.users`) — set when actor was acting via active delegation.
- `approval.delegation.model_ids` (M2m `ir.model`) — empty = applies to all models; otherwise restricts.
- `approval.ooo.auto_delegate_to_id` (M2o `res.users`) — required for effective auto-delegation.
- `approval.mixin.x_custom_approval_request_id` (M2o `approval.request`, computed, stored) — latest non-cancelled request.
- `approval.mixin.x_custom_approval_state` (Selection, related, stored) — exposes request state for view-level domain filtering.

## Public Methods
- `approval.matrix._resolve_for(record)` (`@api.model`) — returns best-match matrix or None.
- `approval.matrix._domain_matches(domain_str, record)` (`@api.model`).
- `approval.matrix.tier._resolve_approvers(record)` — returns `res.users` recordset.
- `approval.request._create_for_record(record, matrix=None)` (`@api.model`) — idempotent draft creation.
- `approval.request.action_submit()` / `action_approve(comment=None)` / `action_reject(comment=None)` / `action_cancel(reason=None)`.
- `approval.request._advance_to_next_tier()` / `_refresh_pending_approvers()` / `_notify_pending()` / `_handle_overdue()`.
- `approval.request._cron_check_escalations()` (`@api.model`) — every-15-min cron entry.
- `approval.delegation._find_delegated_to(user, model_name=None)` / `_find_delegating(user, model_name=None)` (`@api.model`).
- `approval.ooo._active_for(user)` (`@api.model`).
- `approval.mixin.action_request_approval()` / `action_cancel_approval()` / `action_open_approval_request()`.
- `approval.mixin._approval_check_required()` — the gate; raises `UserError` unless approved or no matrix matches.

## Integration Points
- **Depends on:** `custom_core`, `custom_pdp_core`, `custom_pdp_audit`, `mail`, `hr_holidays`, `account`, `purchase`, `sale`, `portal`.
- **Inherits from:** `pdp.audited.mixin` + `mail.thread` + `mail.activity.mixin` on `approval.request`. Downstream `account.move`/`purchase.order`/`sale.order`/`hr.leave` mix `approval.mixin` directly (see `models/account_move_inherit.py`, etc.).
- **Extended by:** any module that opts into approvals (e.g. `custom_expenses` mixes `approval.mixin` on `hr.expense` and `custom.expense.report`). Vertical modules should mix the mixin rather than reimplementing.
- **External calls:** mail notifications via `mail.template_id` (`custom_approval_engine.mail_template_approval_pending`); WhatsApp/Telegram via `custom_ai_bridge` hook (opt-in per tenant).
- **Cross-vertical:** generic — every approval requirement maps here.

## Gotchas
- **`approval.request.line` is immutable** — both `write` and `unlink` raise UserError unless context `approval_line_internal_write` is set. Audit cannot be edited post-hoc.
- **`condition_domain` is `ast.literal_eval` then applied as `search_count`**. Domain syntax errors fail loud at constraint time, but a domain that matches by mistake silently routes the wrong matrix.
- **`approver_type='manager_of_creator'`** uses `hr.employee.parent_id.user_id`; if creator has no employee record or no parent, the resolved set is empty — request will stall.
- **`require_all` waiting logic** loops `continue` inside `action_approve` — when approval is partial, request stays at current tier and the next approver's action triggers re-check.
- **`_handle_overdue` records system actions as `base.user_root`** — audit attributes timeouts to OdooBot, not the original approver.
- **`escalate_to_user` rewrites `pending_approver_ids` to a single user** but does NOT clear history — multiple escalations on the same tier each reset the due_at and append history rows.
- **No transitive delegation** — if A delegates to B and B has an active OOO to C, only one hop is resolved per pass (`continue` short-circuits the loop after the OOO branch).
- **Matrix `company_id`** can be False (cross-company) or set; resolution `IN [False, record.company_id.id]`. A record without `company_id` field uses `False` — verify the matrix has `company_id=False` for non-company models.
- **`_compute_approval_request`** picks the LATEST `state != 'cancelled'` request. If a record has both rejected AND a fresh pending, the freshest wins by `create_date desc`.
- **`approval.mixin._approval_check_required` is a GATE, not a write** — downstream code must explicitly call it from `button_confirm`/`_post`. Forgetting to call it bypasses the engine silently.
- **OOO is a separate model**, not a flag on `res.users` — `hr.leave` must trigger creation of an `approval.ooo` record explicitly (the `leave_id` back-ref).

## Out of Scope
- **Parallel-tier branching** — tiers are strictly sequential by `sequence`; no AND/OR DAG.
- **Conditional skip of a tier** based on record values — entire matrix matches once; no per-tier `condition_domain`.
- **Amount-based escalation tables** — encode this in `priority` + multiple matrices with `condition_domain` (e.g. `[('amount_total', '>', 1_000_000)]`).
- **Approval history export to PDF** — not built in; use `pdp.audit_log` exports or render `history_ids` via custom QWeb.
- **Re-submission after rejection** — the model raises UserError on re-submit of a rejected request; user must cancel + create a new one.
- **Signature capture on approval** — comment only.
