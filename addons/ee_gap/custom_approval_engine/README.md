# Custom Approval Engine

Generic multi-tier approval workflow — model-agnostic via the
`approval.mixin` mixin. Ships ready-wired gates for `account.move`,
`purchase.order`, and `sale.order`. Add the mixin to any custom model
to extend.

## Models

- `approval.matrix` — declares which records of a model need approval.
  Multiple matrices per model resolved by `priority desc`.
- `approval.matrix.tier` — ordered tiers. Approver resolution by
  `user` / `group` / `manager_of_creator` / `domain`. Each tier has
  `sla_hours` and an `on_overdue` strategy.
- `approval.request` — one per `(record × matrix)`. Walks tiers in
  sequence. State machine: `draft → pending → approved | rejected |
  cancelled`. Audit-logged to `pdp.audit_log`.
- `approval.request.line` — immutable history; cannot be edited or
  unlinked.
- `approval.delegation` — manual stand-in for a date window, optionally
  scoped to specific models.
- `approval.ooo` — auto-created from approved `hr.leave`. Auto-delegates
  pending approvals to the leave taker's manager (or explicit fallback).
- `approval.mixin` — attach to any model:
  ```python
  class MyModel(models.Model):
      _name = "my.model"
      _inherit = ["my.model", "approval.mixin"]

      def my_critical_action(self):
          self._approval_check_required()
          return super().my_critical_action()
  ```

## SLA Escalation

- Cron `cron_approval_escalation` runs every **15 minutes**.
- For each `pending + overdue` request, applies the current tier's
  `on_overdue` action:
  - `auto_approve` — record approval, advance tier.
  - `escalate_to_next` — log escalation, advance to next tier.
  - `escalate_to_user` — reroute to fallback approver, reset due.
  - `none` — just re-notify.

## OOO + Delegation Resolution

When `_refresh_pending_approvers()` runs for a tier:

1. Raw approvers resolved via `_resolve_approvers()`.
2. For each raw approver:
   - If active **OOO** with `auto_delegate_to` → use the OOO target.
   - Else if active **delegation** (manual) → use the delegate.
   - Else use the original approver.

## Integration Gates

- `account.move._post()` — blocks posting until approved (if any matrix
  matches).
- `purchase.order.button_confirm()` — same gate.
- `sale.order.action_confirm()` — same gate.

The gate is implemented in `_approval_check_required()` on the mixin —
copy the pattern into any custom model that needs it.

## Security Groups

- `group_approval_user` — submit requests, see own + assigned.
- `group_approval_manager` — read/write all requests (review queue).
- `group_approval_admin` — design matrices, see all delegations + OOO.

## Audit

Every state change writes to `pdp.audit_log` via
`pdp.audited.mixin._pdp_audit_write` — chained, tamper-evident.
Action names: `approval_submit`, `approval_advance`, `approval_complete`,
`approval_reject`, `approval_cancel`, `approval_overdue`.

## Portal

`/my/approvals` — inbox for the logged-in user (must be in
`pending_approver_ids`). Approve / reject with a comment.

## Notifications

Mail templates `mail_template_approval_pending` and
`mail_template_approval_overdue` are sent via `mail.thread`. WhatsApp /
Telegram delivery is left as a hook for `custom_ai_bridge` (not wired in
this iteration).

## Dependencies

- `custom_core`, `custom_pdp_core`, `custom_pdp_audit`
- Odoo: `mail`, `hr_holidays`, `account`, `purchase`, `sale`, `portal`

## Install

```bash
make install MODULE=custom_approval_engine DB=<tenant_db>
```

## Reference

- `docs/architecture.md` — workflow layer
- `docs/pdp-compliance.md` — audit chain integration
