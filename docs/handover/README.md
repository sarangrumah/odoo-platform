# Handover pack — EAL-Hub

Engineer handover for the whole platform, written September 2026 when the original
engineer moved to another vertical. Cross-customer material lives here; one document
per vertical covers the customers. This is the only people-facing onboarding document
in the repo — `CLAUDE.md` is deliberately terse and written for agents.

**Read `00-master.md` first.** Chapters 3–4 (environment, non-negotiables), 6 (front door,
Caddy, queue_job, PDP audit) and 12–14 (the do-not-do list in Indonesian and English, the ten
day-one checks) are the parts that keep production safe.

## Contents

| Source | Document | Scope |
| --- | --- | --- |
| `00-master.md` | `Handover-EAL-Hub-Master.docx` | environment, ways of working, repo architecture, front door/Caddy/queue_job/PDP audit, CI/CD, backup/DR, open PRs, Odoo 19 API traps, consolidated do-not-do list (ID + EN), day-one checks |
| `10-levis.md` | `Handover-Levis.docx` | PT ERA Busana Retailindo — retail import, POS clearing, bank, begbal, COGS, GR/IR, tax, go-live sheets |
| `20-arkaaim.md` | `Handover-ARKA-AIM.docx` | ARKA-AIM — drone assets, intercompany GR/IR, FX, opening balance, go-live issues |
| `30-wms.md` | `Handover-WMS.docx` | WMS — rnd/demo only, TO-engine broken |
| `40-integrasi.md` | `Handover-Integrasi-PPOB-VAS-ESB.docx` | PPOB/PPS, VAS PMO, ESB/EFN, MDM, Denso |
| `50-prospek.md` | `Handover-Pipeline-Prospek.docx` | GentleWoman, Finance Portal, JDS, PPS/Odoo-Hub, the EAA submission |

The markdown is the source of truth — diffable in git, readable without Word. The
`.docx` files are generated for hand-off to non-technical readers.

## Regenerating

```bash
python3 docs/handover/build_handover_docx.py            # all six
python3 docs/handover/build_handover_docx.py --doc levis
python3 docs/handover/build_handover_docx.py --list
```

Needs `python-docx` only (1.2.0 on this host). No network, no ai-gateway, no LLM.

The builder parses a deliberately small markdown subset: `#`/`##`/`###`, paragraphs
with `**bold**` and `` `code` ``, `-` bullets (one nesting level via two leading
spaces), numbered lists, pipe tables with a `| --- |` separator, `>` call-outs and
fenced code blocks. Keep new content inside that subset, and keep tables at five
columns or fewer so they fit A4 portrait.

**Numbered lists keep the numbers written in the source** rather than letting Word
renumber them, because other chapters cite them by number ("daftar JANGAN butir
29–30"). If you insert an item into a numbered list, fix the cross-references.

The table of contents is a Word field, so it is empty until Word populates it: open
the document, `Ctrl+A` then `F9`, or right-click the TOC and choose *Update Field*.

## Provenance

Every figure and date cites its source in parentheses — a memory-note name, a repo
path, a PR number, or a database name — because the 274 operational notes these
documents were distilled from live outside the repo and were archived and removed at
handover. The archive is `handover-eal-knowledge-20260928.zip`; it also carries the
runbook for reinstalling the `graphify` knowledge-graph tooling.

Notes that flagged themselves as stale or wrong are written up as warnings, not as
facts. No credentials appear in these documents — only where the secrets live.
