# Projects

One directory per customer engagement. The platform serves all of them from a
single codebase, so **the boundary matters**: a change under `addons/ee_gap/`,
`addons/core/` or `addons/compliance/` is cross-project by default, even when a
single customer asked for it.

| Project | Customer | Databases | Owned modules |
| --- | --- | --- | --- |
| [`arka-aim/`](arka-aim/) | ARKA AIM — drone rental & show | `prd_arkaaim`, `trn_arkaaim`, dev `erp_dev_aimarka` | `addons/_tenants/custom_arka_*` |
| [`levis/`](levis/) | Era Busana Retailindo (Levi's) — retail, **live** | `prd_levis_begbal`, `rnd_levis` | `addons/_tenants/custom_levis_*` |
| [`ppob/`](ppob/) | PPOB / PPS (Erajaya, Eraspace) | — | `addons/verticals/custom_ppob_*` |
| [`warehouse-jds/`](warehouse-jds/) | JDS — warehouse management | — | none (uses `ee_gap/custom_wms_*`, `core/custom_hht_bridge`) |
| [`wms-implementation/`](wms-implementation/) | Generic WMS delivery package (PID/BRD/FSD/TSD/Architecture + mandays), JDS addendum | — | none (documents `ee_gap/custom_wms_*`) |
| [`gentlewoman/`](gentlewoman/) | GentleWoman — retail fashion, **pre-implementation** | — | none yet |
| [`finance-portal/`](finance-portal/) | Finance Portal (Erajaya) | — | none (uses `ee_gap/custom_finance_portal*`) |
| [`efn-esb/`](efn-esb/) | EFN (Erajaya F&B) — ESB Core integration, **pre-pilot** | dev `rnd_esb` | `verticals/custom_fnb_stock_ops` (engine in `ee_gap/custom_esb_connector`) |

Notes:

- **Owning a module is rare.** Only Arka Aim and Levi's have `_tenants/` modules.
  Everything else runs on shared tiers — see "Module tiers" in
  [`../architecture.md`](../architecture.md).
- Some databases are **live on a VPS**. Local state is not production state.
- Cross-project material stays outside this folder: [`../runbooks/`](../runbooks/),
  [`../sops/`](../sops/), [`../compliance/`](../compliance/), [`../hht/`](../hht/).
