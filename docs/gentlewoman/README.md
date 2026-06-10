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

---

## Release 1.0 — Business Package (Storefront × Odoo)

A versioned, sign-off-ready package focused on the **Storefront↔Odoo integration**, with
mandays by role (PMO / IT BA / IT Developer / QA) and a mandays-derived timeline. Bilingual
(Bahasa Indonesia + English). Authored by **Product Owner — Value-Added Services (Erajaya)**.

| # | Document | Source (markdown) | Rendered artifact |
|---|---|---|---|
| GW-PRES-001 | Business Presentation | *(built by script)* | [PPTX](GentleWoman-Business-Presentation-v1.0.pptx) · [PDF](GentleWoman-Business-Presentation-v1.0.pdf) |
| GW-TSD-001 | Technical Specification (TSD) | [11-TSD-v1.0.md](11-TSD-v1.0.md) | [PDF](GentleWoman-TSD-v1.0.pdf) |
| GW-BP-001 | Solution Blueprint | [12-Blueprint-v1.0.md](12-Blueprint-v1.0.md) | [PDF](GentleWoman-Blueprint-v1.0.pdf) |
| GW-FSD-001 | Functional Specification (FSD) | [13-FSD-v1.0.md](13-FSD-v1.0.md) | [PDF](GentleWoman-FSD-v1.0.pdf) |

**Rebuild the artifacts**

```bash
python tools/build_gentlewoman_deck.py    # -> Business-Presentation .pptx + .pdf
python tools/build_gentlewoman_docs.py     # -> TSD / Blueprint / FSD .pdf (pandoc + Chrome)
```

**Make them downloadable in Odoo** (requires the platform up — Docker running):

```bash
python tools/publish_gentlewoman_docs.py            # XML-RPC upload to db `gentlewoman`
# or, when XML-RPC isn't reachable:
python tools/publish_gentlewoman_docs.py --print-shell   # paste into `odoo shell -d gentlewoman`
```

The publish step uploads each PDF as a **public `ir.attachment`** (PPTX too) and prints, per
document, both `/web/content/<id>?download=true` (native) and `/api/docs/<id>` (public PDF
proxy) links, writing the id map to `_release-1.0-attachments.json`. Update this table with the
emitted ids after the first publish. In Odoo you can also fetch them via
`Settings ▸ Technical ▸ Attachments` → filter name "GentleWoman".
