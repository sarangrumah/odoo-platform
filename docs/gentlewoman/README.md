# Gentle Woman — Document Package

Director-level business case and supporting specifications for the Gentle Woman
headless commerce initiative on the Odoo Platform.

| # | Document | Audience |
|---|---|---|
| ★ | [Executive One-Pager](05-one-pager.md) | Board — 60-second read |
| 00 | [Board / Director Briefing](00-board-presentation.md) | Board of Directors |
| 01 | [Project Initiation Document (PID)](01-project-initiation.md) | Sponsor, Delivery |
| 02 | [Business Requirements (BRD)](02-BRD.md) | Business stakeholders |
| 03 | [Functional Specification (FSD)](03-FSD.md) | Product, QA |
| 04 | [Technical Specification (TSD)](04-TSD.md) | Engineering, Security |

These markdown files are the source of truth. A styled **PDF** of each is published
as a **public Odoo attachment** (tenant `gentlewoman`) and downloadable two ways:

**A. Direct link (no login):**
| Document | Download |
|---|---|
| Executive One-Pager | `https://192.168.3.140:8443/api/docs/1238` |
| Board Briefing | `https://192.168.3.140:8443/api/docs/1231` |
| Project Initiation (PID) | `https://192.168.3.140:8443/api/docs/1232` |
| Business Requirements (BRD) | `https://192.168.3.140:8443/api/docs/1233` |
| Functional Spec (FSD) | `https://192.168.3.140:8443/api/docs/1234` |
| Technical Spec (TSD) | `https://192.168.3.140:8443/api/docs/1235` |

**B. In Odoo:** log into the `gentlewoman` database → `Settings ▸ Technical ▸
Attachments` → filter name "Gentle Woman" → download. (Or `/web/content/<id>?download=true`.)

> The `/api/docs/<id>` proxy serves only **public PDF** attachments from Odoo
> (non-public ids return 404), so it cannot relay arbitrary content.
> Attachment ids are stable for the current pilot; regenerating the PDFs reissues them.
