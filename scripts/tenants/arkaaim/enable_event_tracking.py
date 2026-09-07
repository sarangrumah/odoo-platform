# -*- coding: utf-8 -*-
"""Turn on per-event analytic tracking (custom_arka_show_date >= 19.0.1.7.0).

``x_custom_event_tracking_enabled`` is what makes a sales order, a purchase
order or a bill resolve its event to an analytic account. It is set on BOTH
sister companies on purpose: the event analytic account carries no company, so
ARKA's revenue and AIM's cost for one show land on the same account and the
Profit & Loss per Event nets them.

It is deliberately a different flag from ``x_custom_show_date_enabled``, which
stays ARKA-only — that one makes the Show Date required on sales orders and
re-anchors customer-invoice due dates, and switching it on for AIM would block
every AIM order that has no show.

Idempotent.
"""

companies = env["res.company"].sudo().search([])
for company in companies:
    if not company.x_custom_event_tracking_enabled:
        company.x_custom_event_tracking_enabled = True
        print("enabled event tracking on %s (id %s)" % (company.display_name, company.id))
    else:
        print("already on: %s (id %s)" % (company.display_name, company.id))

plan = env.ref("custom_arka_show_date.analytic_plan_arka_event", raise_if_not_found=False)
print("Event analytic plan:", plan.display_name if plan else "MISSING — module not upgraded?")

env.cr.commit()
for company in companies:
    print(
        "VERIFY %-40s show_date=%s event_tracking=%s"
        % (company.display_name, company.x_custom_show_date_enabled, company.x_custom_event_tracking_enabled)
    )
