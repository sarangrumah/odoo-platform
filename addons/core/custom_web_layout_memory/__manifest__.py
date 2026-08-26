# -*- coding: utf-8 -*-
{
    "name": "Backend Layout Memory",
    "summary": "Remember list column widths per user and let the chatter be folded away",
    "description": """
Backend Layout Memory
=====================
Two things the Odoo backend forgets between page loads, remembered against the
user record so they survive a new browser or a new device.

List column widths
------------------
Odoo lets a user drag a column border, but `useMagicColumnWidths` keeps the
result in a closure that dies with the component -- and deliberately discards
it on a window resize or an optional-column toggle. This module snapshots the
header widths when a drag ends and replays them the next time the same view is
opened, by injecting the saved width as the column's `attrs.width` (the same
mechanism as `<field name="x" width="80px"/>` in the arch). Widths are stored
per view, keyed the way Odoo already keys remembered optional columns.

Double-clicking a resize handle still resets the view to Odoo's computed
widths, and now also forgets the saved ones.

Collapsible chatter
-------------------
`FormRenderer.mailLayout()` decides where the chatter goes from the window
width alone. This module adds a chevron to the chatter topbar that folds it
into a narrow rail, giving the form sheet the space back -- remembered per
model, so hiding it on journal entries does not hide it on contacts.

Storage
-------
Both live in a JSON blob on `res.users.settings`, fetched once per session and
written back debounced. The field is added to that model's format blacklist so
it never travels in the mail store payload or over the settings bus.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Custom Platform/Technical/UX",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["base", "web", "mail"],
    "capability_tags": ["ux", "user-preferences", "list-view", "chatter"],
    "data": [],
    "assets": {
        "web.assets_backend": [
            "custom_web_layout_memory/static/src/**/*",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
