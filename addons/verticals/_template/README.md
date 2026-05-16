# Vertical Template

This folder is the starting point for any new Custom vertical Odoo module. A "vertical"
is a domain-specific module (HR, manufacturing, logistics, etc.) that builds on top
of `custom_core` and the platform's EE-gap addons.

The reference implementation `custom_vertical_example/` is fully wired up and installs
cleanly. Copy it, rename, and extend.

## 12-Step Fork Checklist

Follow these steps in order. Each step references concrete files inside the new
vertical folder.

1. **Copy the example folder.** From the repo root:
   ```bash
   cp -r addons/verticals/_template/custom_vertical_example \
         addons/verticals/my_slug
   ```
   Use a short, lowercase, underscore-separated `my_slug` (e.g. `custom_logistics`).

2. **Rename inside files.** Replace every occurrence of `custom_vertical_example`
   with `my_slug` and every occurrence of `Custom Vertical (Example)` with the
   human-friendly name. Touch at minimum:
   - `addons/verticals/my_slug/__manifest__.py`
   - `addons/verticals/my_slug/security/example_security.xml` (XML ids)
   - `addons/verticals/my_slug/views/menu_views.xml`
   - `addons/verticals/my_slug/views/res_partner_views.xml`
   - `addons/verticals/my_slug/models/res_partner.py` (field prefix)

3. **Update `__manifest__.py`.** Set `name`, `category` (e.g. `Vertical/Logistics`),
   `summary`, `description`, and the `depends` list. Always keep `custom_core` first.
   See `__manifest__.template.py` for the canonical placeholder layout.

4. **Define security groups.** Edit `security/<slug>_security.xml`. Each vertical
   should declare at least:
   - `group_user` (read/write own records)
   - `group_manager` (full access, inherits `group_user`)
   Place both under `custom_core.module_category_custom_platform`.

5. **Declare new fields with `x_<slug>_` prefix on inherited models.** Studio-style
   prefix avoids collisions with core Odoo and other verticals. Example:
   `x_custom_logistics_route_code = fields.Char(...)`.

6. **Add views with `inherit_id`.** Never override a core view wholesale; always
   extend with xpath. Use Odoo 19 syntax (`<list>` not `<tree>`).

7. **Declare menus under `custom_core.menu_custom_root`.** All verticals attach to the
   same root menu, so the navbar stays consistent across the platform.

8. **Add `ir.model.access.csv`.** Even if you only inherit, include the header row.
   Add one access line per new model and per group.

9. **Seed demo data (optional).** Put records in `demo/<slug>_demo.xml` and list
   them under `demo` (not `data`) in the manifest. Useful for staging databases.

10. **Run the module update.** From the repo root:
    ```bash
    make update MODULE=my_slug DB=erp_dev
    ```
    This triggers `odoo -u my_slug -d erp_dev --stop-after-init` inside the
    web container.

11. **Verify in Apps list.** Open `http://localhost:8069/odoo/apps`, search for the
    vertical's `name`, confirm version, category, and dependencies render
    correctly. Install on a clean DB to catch missing data files.

12. **Document the vertical-specific runbook.** Create
    `docs/verticals/<slug>.md` covering:
    - Business purpose and owner
    - Custom fields and their semantics
    - Cron jobs / queue jobs introduced
    - Coretax or PDP touchpoints
    - Rollback procedure

## What this template ships with

| File | Purpose |
| --- | --- |
| `custom_vertical_example/__manifest__.py` | Working manifest, depends on `custom_core` |
| `custom_vertical_example/__init__.py` | Imports `models` |
| `custom_vertical_example/models/__init__.py` | Imports `res_partner` |
| `custom_vertical_example/models/res_partner.py` | Adds `x_custom_vertical_example_tag` |
| `custom_vertical_example/security/ir.model.access.csv` | Header only (no new models) |
| `custom_vertical_example/security/example_security.xml` | Declares `group_user` |
| `custom_vertical_example/views/menu_views.xml` | Top-level menu + stub action |
| `custom_vertical_example/views/res_partner_views.xml` | Form-view extension |
| `__manifest__.template.py` | Reference manifest with placeholders |

## Cross-references

- Operator guide: `docs/adding-vertical.md`
- Architecture overview: `docs/architecture.md`
- Security/PDP rules: `docs/pdp-compliance.md`
