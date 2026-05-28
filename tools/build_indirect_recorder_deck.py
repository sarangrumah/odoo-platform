"""Build "Odoo as Indirect Transaction Recorder" deck (PPTX only).

Re-uses build_pptx() from build_presentation.py — same palette, same slide
kinds, just a different SLIDES list and footer.

Run:  python tools/build_indirect_recorder_deck.py
Out:  docs/presentation-odoo-indirect-recorder.pptx
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_presentation import build_pptx  # noqa: E402


FOOTER = "Erajaya  ·  Odoo Indirect Recorder (FTP-fed FICO + PO)  ·  Mei 2026"


SLIDES = [
    # 1. Cover
    {
        "kind": "title",
        "title": "Odoo as Indirect Transaction Recorder",
        "subtitle": "Principal-Led Operations  ·  FTP-fed FICO & Procurement Hub",
        "footer": "Internal Pitch Deck  ·  Product Owner VAS  ·  Mei 2026",
    },

    # 2. Executive Summary
    {
        "kind": "bullets",
        "title": "Executive Summary",
        "intro": "Aplikasi principal tetap menjadi system of record operasional. Odoo hanya mengambil dua domain: Procurement (PO) dan FICO. Data operasional disuplai via FTP, dimuat lewat fitur import bawaan Odoo.",
        "bullets": [
            "Principal pegang: Sales, GR, Inventory, POS, Invoice issuance ke pelanggan",
            "Odoo pegang: PO, Vendor Bill, GL, AR/AP, Tax (Coretax/Bupot), Reporting",
            "Transport: SFTP — Odoo sebagai pull-client, principal tidak butuh akses ke jaringan kita",
            "Import via base_import.load() — re-use Odoo CE, bukan custom pipeline",
            "Audit-ready: append-only hash-chained log, retention sesuai PSAK & UU PDP",
        ],
        "highlights": [
            ("PO + FICO", "Domain Odoo"),
            ("SFTP pull", "Transport"),
            ("~8 mgg", "Go-live"),
            ("~27 md", "Per Principal"),
        ],
    },

    # 3. Boundary Matrix
    {
        "kind": "table",
        "title": "Boundary Matrix — Siapa Pegang Apa",
        "intro": "Prinsip: principal = system of record operasional · Odoo = system of record finance + procurement upstream.",
        "headers": ["Proses / Modul", "Principal App", "Odoo"],
        "rows": [
            ["Sales Order, Customer ops, POS",                      "✓", "—"],
            ["Goods Receipt (eksekusi fisik di gudang)",            "✓", "—"],
            ["Inventory movement, stock balance",                   "✓", "—"],
            ["Customer Invoice (issuance ke pelanggan)",            "✓", "—"],
            ["Purchase Order (RFQ → release ke vendor)",            "—", "✓"],
            ["Vendor master, Vendor Bill (AP)",                     "—", "✓"],
            ["General Ledger, Bank/Cash, Rekonsiliasi",             "—", "✓"],
            ["AR posting (revenue dari principal feed)",            "—", "✓"],
            ["Tax: e-Faktur Coretax, Bupot, SPT",                   "—", "✓"],
            ["Fixed Asset, Konsolidasi, Reporting",                 "—", "✓"],
            ["Master: Customer, Product",        "✓ (authoritative)", "mirror"],
            ["Master: Vendor, CoA, Tax Code",                "mirror", "✓ (authoritative)"],
        ],
        "col_widths": [4.5, 2.4, 2.1],
    },

    # 4. System Landscape
    {
        "kind": "diagram",
        "title": "System Landscape",
        "intro": "Odoo pull dari FTP principal — zero attack surface dari principal ke jaringan internal.",
        "ascii": [
            "",
            "  ┌────────────────────┐      ┌────────────────┐      ┌────────────────────┐",
            "  │ Principal App      │ CSV  │ FTP Server     │ pull │ Odoo 19 (Hub)      │",
            "  │ Sales · GR · Stock │ ───▶ │ (SFTP / FTPS)  │ ◀─── │ PO · FICO · Tax    │",
            "  │ POS · Inv. Issue   │      │ /outbound /ack │      │ custom_ftp_ingest  │",
            "  └────────────────────┘      └────────────────┘      └────────┬───────────┘",
            "                                                                │",
            "                                                                ▼",
            "                                                    ┌──────────────────────┐",
            "                                                    │ Pajakku ASPP H2H     │",
            "                                                    │ Coretax · DJP        │",
            "                                                    └──────────────────────┘",
            "",
        ],
        "decisions": [
            "Odoo sebagai SFTP pull-client — principal tidak butuh inbound access",
            "Format CSV UTF-8 RFC4180 · header standar · external_id per row",
            "Idempotent: re-ingest file yg sama aman (dedup via external_id)",
            "Pajakku ASPP H2H langsung dari Odoo — tidak lewat principal",
            "Zero coupling: principal app tidak tahu Odoo ada di hilirnya",
        ],
    },

    # 5. Data Contract
    {
        "kind": "diagram",
        "title": "Data Contract — FTP Drop Layout",
        "intro": "Folder convention & naming. Principal drop file di /outbound, Odoo balas hasil di /ack.",
        "ascii": [
            "",
            " /erajaya/outbound/",
            "   ├── master/",
            "   │     ├── customer_YYYYMMDD.csv",
            "   │     ├── product_YYYYMMDD.csv",
            "   │     └── vendor_YYYYMMDD.csv",
            "   ├── sales/",
            "   │     ├── so_header_YYYYMMDD_NNN.csv",
            "   │     ├── so_line_YYYYMMDD_NNN.csv",
            "   │     ├── invoice_YYYYMMDD_NNN.csv",
            "   │     └── invoice_line_YYYYMMDD_NNN.csv",
            "   ├── gr/",
            "   │     └── gr_YYYYMMDD_NNN.csv     (link: po_number)",
            "   └── stock/",
            "         └── stock_balance_YYYYMMDD.csv",
            "",
            " /erajaya/ack/         ← Odoo tulis <filename>.ok | .err",
            " /erajaya/quarantine/  ← file invalid, manual review",
            " /erajaya/archive/     ← processed, retention 90 hari",
            "",
        ],
        "decisions": [
            "Encoding: UTF-8, line ending LF, separator koma, quote double",
            "Header row wajib · external_id wajib · timestamp ISO-8601",
            "Timezone: Asia/Jakarta (cut-off H-1 23:59 WIB)",
            "Numeric: desimal titik (123.45), bukan koma",
            "Filename pattern <entity>_<YYYYMMDD>_<NNN>.csv",
            "Schema versioning lewat field schema_version di header",
        ],
    },

    # 6. Ingestion Flow
    {
        "kind": "diagram",
        "title": "Ingestion Flow — Scheduled Pull (per Jam)",
        "intro": "Scheduled action Odoo run setiap jam. Komponen baru yang dibangun: custom_ftp_ingest.",
        "ascii": [
            "",
            " Cron Odoo (every 1 hour)",
            "   │",
            "   1. Connect SFTP    ← creds di ir.config_parameter (Fernet)",
            "   │",
            "   2. List /outbound/* yg belum diproses",
            "   │     (state di model ftp.ingest.file)",
            "   │",
            "   3. Download → /tmp/ingest_<uuid>/",
            "   │",
            "   4. Validate schema (CSV schema map per entity)",
            "   │",
            "   5. Stage → base_import.load() (atomic per file)",
            "   │",
            "   6. Tulis ack → /ack/<filename>.ok | .err",
            "   │",
            "   7. Notify channel + audit log (custom_pdp_audit)",
            "   │",
            "   8. Move processed → /archive/YYYYMM/",
            "",
        ],
        "decisions": [
            "Komponen NEW: custom_ftp_ingest (poller + schema map + dispatcher)",
            "Re-use: base_import.load() API — bukan custom CSV parser",
            "Re-use: custom_pdp_audit untuk audit chain hash-chained",
            "Atomic per file: savepoint rollback kalau ada row gagal",
            "Concurrency: 1 connection, sequential — hindari race ke principal",
            "Retry: exponential backoff 3 attempts untuk SFTP error",
        ],
    },

    # 7. PO ↔ GR Cross-System Flow
    {
        "kind": "diagram",
        "title": "PO ↔ GR Cross-System Flow",
        "intro": "PO milik Odoo, GR eksekusi di principal. Match lewat po_number → buka 3-way match dan Vendor Bill.",
        "ascii": [
            "",
            " [Odoo]      Create RFQ → Confirm PO → Send PDF/EDI ke vendor",
            "                                              │",
            "                                              ▼",
            " [Vendor]    Kirim barang ke gudang principal",
            "                                              │",
            "                                              ▼",
            " [Principal] Receive di gudang → Catat GR (link po_number)",
            "                                              │",
            "                                              ▼  FTP /gr/gr_*.csv per jam",
            " [Odoo]      Ingest gr_*.csv",
            "               → match purchase.order.line by po_number + sku",
            "               → create stock.picking done (informational)",
            "               → 3-way match: PO qty vs GR qty vs Bill qty",
            "               → Vendor Bill draft → approval → posted",
            "                                              │",
            "                                              ▼",
            " [Odoo]      Schedule payment → bank file → reconciliation",
            "",
        ],
        "decisions": [
            "PO = source of truth Odoo; GR = source of truth principal",
            "Match key: po_number + sku (+ optional batch/lot)",
            "Mismatch (PO tidak ada, qty over-receipt) → quarantine + alert",
            "Vendor Bill butuh approval (custom_approval_engine) sebelum posted",
            "Tax line otomatis di-resolve dari fiscal position vendor",
            "PO release dikirim ke principal juga (referensi GR expected)",
        ],
    },

    # 8. Sales → Revenue Recognition Flow
    {
        "kind": "diagram",
        "title": "Sales → Revenue Recognition Flow",
        "intro": "Principal kirim hasil akhir (invoice posted) — Odoo posting AR ledger + tax. Tidak buat sale.order di Odoo.",
        "ascii": [
            "",
            " [Principal] Sales Order → Delivery → Customer Invoice",
            "                                              │",
            "                                              ▼  FTP /sales/invoice_*.csv harian",
            " [Odoo]      Ingest invoice_*.csv",
            "               → posting account.move (AR ledger)",
            "               → revenue account (mapping per product category)",
            "               → tax line (PPN keluaran, PPh jika perlu)",
            "               → e-Faktur Coretax queue (Pajakku ASPP)",
            "                                              │",
            "                                              ▼",
            " [Odoo]      Daily reconciliation:",
            "               - sum(invoice CSV principal) vs sum(AR Odoo)",
            "               - variance > threshold → alert + approval review",
            "",
        ],
        "decisions": [
            "TIDAK dibuat di Odoo: sale.order, stock.picking outgoing",
            "Odoo terima hasil akhir saja: invoice posted (head + line)",
            "Tax mapping via account.fiscal.position per customer segment",
            "Coretax submission async — gagal masuk DLQ, retry by ops",
            "Recognition method: per invoice date (cash) atau accrual",
            "Customer mapping via external_id (= customer_code principal)",
        ],
    },

    # 9. Master Data Sync Strategy
    {
        "kind": "two_col",
        "title": "Master Data Sync Strategy",
        "left_title": "Principal Authoritative (principal wins)",
        "left_bullets": [
            "res.partner customer — key: customer_code",
            "product.product SKU — key: default_code / sku",
            "Sync harian, full snapshot di /master/",
            "Conflict policy: overwrite Odoo dgn nilai principal",
            "PII masking di Odoo: nama → hashed di log (PDP)",
            "Customer/Product baru di principal → otomatis muncul di Odoo H+1",
        ],
        "right_title": "Odoo Authoritative (append-only)",
        "right_bullets": [
            "res.partner vendor — Odoo PO butuh vendor master",
            "account.account CoA (PSAK 5-digit) — hanya finance Odoo",
            "account.tax (PPN, PPh, DPP Nilai Lain)",
            "Tax fiscal positions per segment customer",
            "Export ke /outbound-odoo/ jika principal butuh referensi",
            "Principal TIDAK BOLEH tulis ke domain ini",
        ],
        "footnote": "Mapping kode antar sistem via external_id. Sync history disimpan di model ftp.master.sync (audit per snapshot).",
    },

    # 10. Reconciliation & Control
    {
        "kind": "table",
        "title": "Reconciliation & Control — Daily Variance Engine",
        "intro": "Setiap pagi 07:00 — engine compare data principal vs posting Odoo, alert kalau variance > threshold.",
        "headers": ["Check", "Source A (Principal)", "Source B (Odoo)", "Threshold / Action"],
        "rows": [
            ["Revenue match per tgl", "sum(invoice CSV)", "sum(account.move AR)", "Alert > 0.5%"],
            ["GR match per PO",       "sum(gr CSV)",     "sum(stock.picking done)", "Alert mismatch any"],
            ["Stock balance",         "stock_balance.csv","stock.quant",        "Audit-only report"],
            ["Tax match",             "invoice tax CSV", "account.tax line",    "Alert mismatch any"],
            ["Feed liveness",         "last file ts",    "now()",               "Alert if > 24h silent"],
            ["Vendor Bill aging",     "—",               "account.move AP open","Alert if > 30 hari"],
        ],
        "col_widths": [2.4, 2.6, 2.6, 2.4],
        "footnote": "Variance > threshold → ticket otomatis via custom_approval_engine → review finance lead → resolve via correcting entry atau request resend principal.",
    },

    # 11. Error Handling & Replay
    {
        "kind": "table",
        "title": "Error Handling & Replay",
        "intro": "Klasifikasi error & jalur recovery. Semua error tercatat di model ftp.ingest.error untuk audit.",
        "headers": ["Error Class", "Detection", "Recovery"],
        "rows": [
            ["Schema invalid (header / type)",       "Validator stage step 4",            "Quarantine + alert → manual fix → replay"],
            ["Reference miss (PO/customer/product)", "base_import resolution error",       "Retry 3× (1h interval) → manual queue"],
            ["Duplicate (external_id exists)",       "Unique constraint ftp.ingest.row",   "Skip + log info (idempotent)"],
            ["Partial commit failure",               "Savepoint rollback per file",        "File tagged .err → replay setelah fix"],
            ["Feed stalled (no file > 24h)",         "Daily liveness check 09:00",         "Alert ops channel → eskalasi SPOC"],
            ["SFTP connection failure",              "Connection exception step 1",        "Exponential backoff 3× → alert if fail"],
        ],
        "col_widths": [3.2, 3.0, 3.8],
    },

    # 12. Security & Compliance
    {
        "kind": "two_col",
        "title": "Security & Compliance",
        "left_title": "Transport & Credential",
        "left_bullets": [
            "SFTP key-based auth (Ed25519), password disabled",
            "Private key SOPS-encrypted di repo, Fernet runtime",
            "Connection allow-list IP-based (principal SFTP only)",
            "TLS 1.3 wrap jika FTPS dipakai sebagai fallback",
            "Quarterly credential rotation (dual-key window, zero-downtime)",
        ],
        "right_title": "Data, Audit & Pipeline",
        "right_bullets": [
            "Append-only audit log per ingestion (custom_pdp_audit, hash-chained)",
            "PII masking di log: customer name → hash (UU PDP)",
            "Retention: file 90 hari di /archive, audit log 7 tahun",
            "DSAR ready: customer-level export Odoo + cross-ref ke principal",
            "Pre-commit: gitleaks, ruff, bandit · CI: Semgrep, pip-audit, Trivy",
            "custom_ftp_ingest pinned 19.0.x.y · CI per release",
        ],
    },

    # 13. Modules / Components
    {
        "kind": "table",
        "title": "Modules / Components in Play",
        "intro": "Build effort terkonsentrasi di 1 modul baru (custom_ftp_ingest). Sisanya re-use library Hub yang sudah ready.",
        "headers": ["Komponen", "Asal", "Peran"],
        "rows": [
            ["purchase",                       "Odoo CE",       "PO, RFQ, Vendor Bill, 3-way match"],
            ["account, account_asset",         "Odoo CE",       "GL, AR/AP, Bank, Fixed Asset"],
            ["base_import",                    "Odoo CE",       "load() API untuk CSV import"],
            ["custom_accounting_full",         "Hub repo",      "PSAK 5-digit CoA, Intercompany, Konsolidasi"],
            ["custom_coretax + coretax_bupot", "Hub repo",      "e-Faktur, Bupot, NSFP, Pajakku ASPP"],
            ["custom_approval_engine",         "Hub repo",      "Variance review workflow + escalation"],
            ["custom_pdp_audit",               "Hub repo",      "Append-only hash-chained audit log"],
            ["custom_ftp_ingest  (NEW)",       "Hub repo (build)", "SFTP poller, schema map registry, dispatcher, ack writer"],
        ],
        "col_widths": [3.0, 2.0, 4.5],
    },

    # 14. Alternative — tanpa FTP adapter, hanya import bawaan Odoo
    {
        "kind": "table",
        "title": "Alternative — Tanpa FTP Adapter (Manual Import Mode)",
        "intro": "Skenario 'lite': tidak build custom_ftp_ingest. Principal kirim CSV via email/share drive, ops Odoo upload manual lewat Settings → Technical → Import (base_import.load() di balik layar — API yang sama).",
        "headers": ["Aspek", "FTP Adapter (custom_ftp_ingest)", "Manual Import Mode"],
        "rows": [
            ["Build effort",     "~27 md (1 modul baru)",                "~15 md (template + SOP + UAT)"],
            ["Go-live time",     "~8 minggu",                            "~4–5 minggu"],
            ["Infra",            "SFTP server + credential exchange",    "Tidak ada"],
            ["Recurring ops",    "Cron otomatis + monitoring",           "~1–2 jam/hari upload manual"],
            ["Human error risk", "Rendah (otomatis, idempotent)",        "Tinggi (salah file, missed upload)"],
            ["Liveness alert",   "Otomatis >24h alert",                  "Tidak ada — telat ketahuan"],
            ["Idempotency",      "Built-in via external_id constraint",  "Tergantung disiplin ops"],
            ["Reconciliation",   "Otomatis daily 07:00",                 "Manual run oleh finance"],
            ["Audit trail",      "Hash-chained custom_pdp_audit",        "ir.attachment + login log standar"],
            ["Cocok untuk",      "Volume harian, lifetime panjang",      "Pilot / PoC / volume rendah"],
        ],
        "col_widths": [2.0, 3.6, 3.4],
        "footnote": "ROI: selisih 12 md di-recover dalam ~3 bulan operasional — ops menghabiskan ~10 jam/minggu (~65 md/tahun) untuk manual upload. Manual mode layak sebagai bridge sementara, atau untuk principal volume < 50 file/bulan.",
    },

    # 15. Mandays — breakdown per role
    {
        "kind": "table",
        "title": "Implementation Mandays — Breakdown per Role",
        "intro": "Estimasi go-live 1 principal dipecah per role: ITBP (PMO), IT Business Analyst, Developer, QA. Total 27 md.",
        "headers": ["Phase", "Activity", "ITBP (PMO)", "IT BA", "Developer", "QA", "Total"],
        "rows": [
            ["Setup",      "SFTP infra + credential exchange",            "1", "1", "1", "—", "3"],
            ["Build",      "Modul custom_ftp_ingest (poller + dispatcher)", "1", "1", "5", "1", "8"],
            ["Schema Map", "7 entitas (customer, product, vendor, SO, invoice, GR, stock)", "—", "2", "3", "1", "6"],
            ["Reconcile",  "Daily variance engine + dashboard",           "1", "1", "2", "—", "4"],
            ["UAT",        "Cross-system end-to-end (principal ↔ Odoo)",  "1", "1", "1", "3", "6"],
            ["Subtotal per Role", "",                                    "4", "6", "12", "5", "27"],
        ],
        "col_widths": [1.3, 4.0, 1.0, 0.8, 1.0, 0.7, 0.8],
        "footnote": "ITBP = governance, koordinasi, sign-off · IT BA = schema contract, mapping, UAT scenario · Developer = build modul + integrasi · QA = test plan + e2e + regression. Komparasi middleware tradisional ~80–120 md (saving ~70% lewat re-use base_import + library Hub).",
    },

    # 15. Roadmap (4 phases, 8 minggu)
    {
        "kind": "roadmap",
        "title": "Roadmap & Phasing — 8 Minggu",
        "quarters": [
            ("Phase 1 — Wk 1–2 · Foundation", [
                "SFTP handshake dengan principal",
                "Build custom_ftp_ingest skeleton",
                "Master data sync: customer, product, vendor",
                "Schema contract sign-off",
            ]),
            ("Phase 2 — Wk 3–4 · Procurement", [
                "PO export Odoo → principal (PDF/EDI)",
                "GR ingestion + 3-way match",
                "Vendor Bill draft → approval → posted",
                "AP outstanding visibility",
            ]),
            ("Phase 3 — Wk 5–6 · Revenue", [
                "Sales/Invoice CSV ingestion",
                "AR posting + tax line + Coretax queue",
                "Reconciliation engine variance check",
                "Dashboard variance daily",
            ]),
            ("Phase 4 — Wk 7–8 · Go-Live", [
                "UAT cross-system + bug-fix",
                "Hypercare ops + runbook handover",
                "Cutover plan eksekusi",
                "Sign-off & transition ke BAU",
            ]),
        ],
    },

    # 16. Risks
    {
        "kind": "table",
        "title": "Risks & Mitigations",
        "headers": ["Risk", "Mitigation"],
        "rows": [
            ["Principal schema drift (kolom berubah tanpa notice)",
             "Schema contract + schema_version di header · validator strict · alert deviasi"],
            ["Feed stalled (principal down / delay)",
             "Daily liveness + heartbeat file · eskalasi SPOC · runbook fallback"],
            ["Reconciliation gap karena timing cut-off beda",
             "Cut-off contract: principal H-1 23:59 WIB, Odoo proses 07:00 H+0"],
            ["Duplicate posting (re-send principal)",
             "Idempotency via external_id unique constraint"],
            ["Tax submission gagal (Coretax/Pajakku)",
             "Circuit breaker + manual portal fallback + ops alert"],
            ["SFTP credential rotation berisiko outage",
             "Quarterly rotation runbook · dual-key window · zero-downtime"],
        ],
        "col_widths": [3.8, 5.2],
    },

    # 17. Call to Action
    {
        "kind": "cta",
        "title": "Call to Action",
        "intro": "Approval & resource untuk pilot 1 principal — pola ini reusable untuk principal berikutnya tanpa rebuild.",
        "items": [
            ("1", "Endorsement",
             "Approve pola indirect recording sebagai blueprint integrasi dengan aplikasi principal"),
            ("2", "Pilot Funding",
             "Allocate untuk 1 principal pertama — lead candidate disepakati sebelum kick-off"),
            ("3", "SFTP Infrastructure",
             "Provision SFTP server + credential exchange dengan principal SPOC di Wk-0"),
            ("4", "Resource Lock",
             "1 backend Odoo + 1 finance SME + 1 PO untuk durasi 8 minggu"),
            ("5", "Data Contract Sign-off",
             "Tanda-tangan schema contract & cut-off timing dgn principal sebelum build start"),
        ],
    },

    # 18. Closing
    {
        "kind": "closing",
        "title": "Terima Kasih",
        "subtitle": "Diskusi & Q&A",
        "footer": "Product Owner — Value-Added Services  ·  Erajaya  ·  Mei 2026",
    },
]


def main():
    out_dir = Path(__file__).resolve().parent.parent / "docs"
    out_dir.mkdir(exist_ok=True)
    pptx_path = out_dir / "presentation-odoo-indirect-recorder.pptx"

    print(f"Building PPTX -> {pptx_path}")
    build_pptx(pptx_path, slides=SLIDES, footer_text=FOOTER)
    print(f"  OK {pptx_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
