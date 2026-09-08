# -*- coding: utf-8 -*-
{
    "name": "Custom Asset Lifecycle",
    "summary": "Damage / missing / repair / replacement lifecycle on top of the "
    "fixed-asset register, with the history attached to each serial",
    "description": """
Custom Asset Lifecycle
======================

``custom_accounting_asset`` knows how to depreciate an asset and how to dispose
of it. What it has no vocabulary for is everything that happens in between: a
unit comes back from the field broken, another one never comes back at all, a
third goes out to a vendor under warranty and returns three weeks later. This
module gives the register that vocabulary.

Condition is not state
----------------------

``condition`` (ok / damaged / in_repair / missing / written_off) is a **separate
field from** ``state``. A damaged or under-repair asset stays ``running`` and
keeps depreciating -- PSAK 16 / IAS 16.55: depreciation does not stop while an
asset is idle. Depreciation stops at exactly one point, derecognition, which is
the existing disposal wizard. ``test_depreciation_continues_while_in_repair``
pins that down.

What it adds
------------

* **Report Damage** -- flags the units, moves their serials to the damage
  location, and optionally opens a ``repair.order`` in one of three channels:
  in-house, third party (vendor required) or warranty claim (claim reference
  required). Warranty repairs are excluded from the asset's own repair cost.
* **Report Missing** -- flags the units with a BAP reference, moves the serials
  to the lost/missing location so they stop counting as on-hand, and leaves the
  asset running until Finance derecognises it. ``action_open_writeoff_wizard``
  routes to the existing disposal wizard with zero proceeds and the configured
  loss account prefilled.
* **Return To Service** -- brings a repaired unit back from the damage location
  to its home location and clears the condition.
* **Register Replacement** -- the client replaces a lost or destroyed unit. The
  new asset is created at **fair market value**, linked to the one it replaces
  through ``replaces_asset_id``, and -- this is the part that matters -- its
  acquisition journal is **posted here**.

Why the acquisition journal is posted here
------------------------------------------

``custom.fixed.asset`` never posts an acquisition entry: assets are expected to
be born from a vendor bill via ``custom_asset_from_receipt``, which is what puts
the cost in the GL. A replacement unit handed over by a client has no vendor
bill, so creating the asset alone would grow the register while the GL stood
still -- a silent register-vs-GL drift, the same class of gap that once showed up
as a 34.98m variance on the ARKA-AIM register. The replacement wizard therefore
books ``DR asset account / CR compensation income`` itself, at fair value.

Every transition is written to ``custom.asset.condition.log``, which hangs off
the asset and therefore off its serial number. Combined with
``maintenance.equipment`` (provisioned in bulk by the included wizard) the full
failure and repair history of a physical unit is readable from its asset card.
""",
    "author": "Custom Platform",
    "category": "Accounting/Accounting",
    "version": "19.0.1.2.0",
    "license": "LGPL-3",
    "depends": [
        "custom_accounting_asset",
        # stock_location_id / lot_id on the asset, plus the _action_done hook
        # that keeps the position current after the wizards move a serial
        "custom_asset_stock_link",
        # repair.order + maintenance.equipment/request, SLA and cost tracking
        "custom_repairs",
        "stock",
        "mail",
    ],
    "capability_tags": ["fixed-assets", "maintenance", "repair", "audit-trail"],
    "data": [
        "security/ir.model.access.csv",
        "views/asset_condition_log_views.xml",
        "views/fixed_asset_views.xml",
        "views/repair_order_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/asset_report_damage_wizard_views.xml",
        "wizard/asset_report_missing_wizard_views.xml",
        "wizard/asset_replacement_wizard_views.xml",
        "wizard/asset_equipment_provision_wizard_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
