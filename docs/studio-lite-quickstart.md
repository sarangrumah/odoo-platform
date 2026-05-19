# Studio-Lite Quickstart

`custom_studio_lite` is the platform's declarative customisation layer.
It is **not** a clone of Odoo Enterprise's visual Studio: it does the
two things 90 % of EE Studio users actually use (add a custom field,
inherit a view) via metadata records you can version-control.

---

## Concept

| Aspect          | EE Studio                                   | `custom_studio_lite`                              |
| --------------- | ------------------------------------------- | ------------------------------------------------- |
| Authoring       | Visual drag/drop                            | Form record (`custom.studio.field`, `custom.studio.view.inherit`) |
| Storage         | `ir.model.fields` + `ir.ui.view` directly   | Same Odoo tables, but provenance tracked on a studio record       |
| Versioning      | DB-only                                     | Records exportable as XML, commitable to a tenant overlay branch  |
| Risk on upgrade | Custom fields persist; views may break      | Studio records reapply after module upgrade        |

Every studio record creates a corresponding `ir.model.fields` or
`ir.ui.view` entry. Deleting the studio record removes the underlying
entry too.

---

## Add a custom field

Navigate: **Custom Platform → Studio Lite → Custom Fields → New**.

Example: add an "Internal Project Code" char field on `sale.order`.

| Field         | Value                          |
| ------------- | ------------------------------ |
| Model         | `sale.order`                   |
| Field name    | `x_studio_project_code`        |
| Field type    | `char`                         |
| Label         | `Internal Project Code`        |
| Required      | unchecked                      |
| Help          | `Internal cross-reference used by PMO.` |

On save:

1. `custom.studio.field` row is created.
2. The Studio engine creates an `ir.model.fields` row with the same
   `name`, `model_id`, `ttype`, etc.
3. The field is immediately available in domain expressions, ORM
   reads, and through `studio.view.inherit` records.

Programmatic equivalent (XML data file):

```xml
<record id="studio_field_sale_proj_code" model="custom.studio.field">
    <field name="model_id" ref="sale.model_sale_order"/>
    <field name="field_name">x_studio_project_code</field>
    <field name="field_type">char</field>
    <field name="label">Internal Project Code</field>
    <field name="required" eval="False"/>
    <field name="help_text">Internal cross-reference used by PMO.</field>
</record>
```

**Naming rule**: field name MUST start with `x_studio_`. Other
prefixes are rejected at validation time to make studio-managed
fields easy to grep and to avoid clashes with shipped modules.

---

## Add a view extension

Navigate: **Custom Platform → Studio Lite → View Extensions → New**.

Example: show the new field in the `sale.order` form, next to
`client_order_ref`.

| Field                | Value                                              |
| -------------------- | -------------------------------------------------- |
| Target view          | `sale.view_order_form` (External ID picker)        |
| Inheritance type     | `xpath`                                            |
| Xpath expression     | `//field[@name='client_order_ref']`                |
| Position             | `after`                                            |
| Arch fragment        | `<field name="x_studio_project_code"/>`             |

On save:

1. `custom.studio.view.inherit` row is created.
2. The engine creates an `ir.ui.view` row of type `inherited` with
   the assembled arch:

```xml
<data>
    <xpath expr="//field[@name='client_order_ref']" position="after">
        <field name="x_studio_project_code"/>
    </xpath>
</data>
```

Programmatic equivalent:

```xml
<record id="studio_view_sale_proj_code" model="custom.studio.view.inherit">
    <field name="target_view_id" ref="sale.view_order_form"/>
    <field name="inheritance_type">xpath</field>
    <field name="xpath_expr">//field[@name='client_order_ref']</field>
    <field name="position">after</field>
    <field name="arch_fragment">
        <![CDATA[<field name="x_studio_project_code"/>]]>
    </field>
</record>
```

---

## Reset / uninstall

To safely remove a studio modification:

1. Open the studio record (field or view extension).
2. Click **Action → Deactivate** first. The engine archives the
   underlying `ir.model.fields` / `ir.ui.view` row but keeps stored
   data so you can revert.
3. After observing 1 business day with no regressions, click
   **Action → Delete Permanently**. Both the studio record and the
   underlying ORM/view row are removed.

**Never** drop columns via raw SQL — orphaned `ir.model.fields` rows
will block module upgrades. Always use the Deactivate → Delete flow.

Uninstall of `custom_studio_lite` cascades: all `x_studio_` columns
are dropped automatically (the module's `uninstall_hook` walks every
`custom.studio.field` and removes the underlying ORM field cleanly).

---

## Limitations vs EE Studio

- No visual drag-drop form editor. Planned Phase 2 (`custom_studio_visual`).
- No automated test recorder.
- No "App Builder" (creating a brand-new menu/model graph with one
  click). Use a real custom module for that; studio-lite is for
  *deltas* on existing models/views.
- No automated workflow editor — use `custom_approval_engine` for
  multi-step business approvals, or `base.automation` for ECA rules.
- Computed fields are supported (`field_type = computed`) but the
  compute expression is restricted to safe-eval (no arbitrary
  Python). For richer compute logic, ship a real module.

---

## Permissions

Only members of the `group_studio_admin` group can create, modify, or
delete `custom.studio.field` and `custom.studio.view.inherit` records.

By default this group is empty — assign it explicitly to a small set
of trusted users (typically the tenant's super-admin + one BA).
Studio changes are recorded on `pdp.audit_log` (append-only, hash-chained)
so every change is traceable.

Note: end-users automatically *see* studio-managed fields and view
extensions through normal record rules; they just cannot author them.
