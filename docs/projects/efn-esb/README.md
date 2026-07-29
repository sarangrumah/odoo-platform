# EFN — Erajaya F&B × ESB Core

Stock Opname, Demand Forecasting and Auto Replenishment for EFN's F&B outlets,
integrated with **ESB Core** (esb.co.id).

**Status:** build complete and tested; blocked on ESB credentials for staging
validation.

## Documents

| # | Document | Audience |
|---|---|---|
| [00](00-BOD-presentation.md) | **Board presentation** — pain points, plan, workflows, architecture, mandays | Board of Directors |
| [01](01-BRD-management.md) | **BRD — Management Level** | Sponsor, Business Owner, Finance, Operations |
| [02](02-BRD-technical.md) | **BRD — Technical Level** | Architect, Technical Lead, ESB PIC, QA |
| [03](03-FSD.md) | **Functional Specification** | Product Owner, BA, QA, key users, trainers |
| [04](04-TSD.md) | **Technical Specification** | Developers, DevOps, QA automation |
| [05](05-workflows.md) | **Workflows & Diagrams** — the visual index | Everyone |

Deliverable formats are built from these sources: `.pptx` for the board deck,
`.docx` with rendered diagrams for the rest.

## The one-paragraph version

ESB Core stays the system of record for stock, purchasing and finance. Odoo mirrors
ESB's master data and stock, adds the intelligence ESB does not provide — physical
counting, demand forecasting, replenishment planning — and writes its conclusions
back as native ESB documents. Nothing reaches ESB without a human approving it.

## Owned modules

| Module | Tier | Purpose |
|---|---|---|
| [`custom_esb_connector`](../../../addons/ee_gap/custom_esb_connector/) | `ee_gap` | ESB integration engine — reusable across F&B customers on ESB |
| [`custom_fnb_stock_ops`](../../../addons/verticals/custom_fnb_stock_ops/) | `verticals` | The three business capabilities |

Plus fixes to the shared `custom_wms_cycle_count` — see [TSD §10](04-TSD.md#10-odoo-19-api-drift-encountered).

## Related

- [ESB Core / OMS API reference](../../integrations/esb-core-api.md) — base URLs,
  authentication, response envelope, endpoint map
- [Captured API specification](../../integrations/esb/) — verbatim, version-controlled
- Test database: `rnd_esb` (disposable)

## Immediate next step

Resolve **Q1 and Q2** in [BRD Technical §7](02-BRD-technical.md#7-open-items-for-the-esb-pic):
a dedicated ESB integration account (ideally a static API key) and staging
credentials. Everything else is ready.
