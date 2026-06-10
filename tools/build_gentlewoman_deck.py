"""Build the GentleWoman Headless Commerce business presentation (PPTX + PDF).

Reuses the layout + palette helpers from tools/build_presentation.py (slate-dominant
chrome, Erajaya red #E30613 as accent only) so the deck stays overlap-free and on-brand.

Scope  : GentleWoman storefront (Next.js) x Odoo 19 (backend) — features, the
         Storefront<->Odoo integration, mandays by role (PMO / IT BA / IT Developer / QA)
         and a mandays-derived timeline. No pricing. Erajaya VAS framing (no BCT/Bima).

Run    : python tools/build_gentlewoman_deck.py
Out    : docs/gentlewoman/GentleWoman-Business-Presentation-v1.0.pptx
         docs/gentlewoman/GentleWoman-Business-Presentation-v1.0.pdf
"""

from __future__ import annotations

from pathlib import Path

import build_presentation as bp  # same tools/ dir; reuse build_pptx / build_pdf

FOOTER = "Erajaya VAS  ·  GentleWoman Headless Commerce  ·  v1.0  ·  Juni 2026"
DOC_TITLE = "GentleWoman Headless Commerce — Business Presentation v1.0"

SLIDES = []


def add(s):
    SLIDES.append(s)


# 1 — Title
add(
    {
        "kind": "title",
        "title": "GentleWoman Headless Commerce",
        "subtitle": "Storefront (Frontend) × Odoo 19 (Backend) — Integrated Architecture",
        "footer": "Business Presentation  ·  Product Owner Value-Added Services  ·  v1.0  ·  Juni 2026",
    }
)

# 2 — Executive Summary
add(
    {
        "kind": "bullets",
        "title": "Executive Summary",
        "intro": "Headless commerce: Storefront Next.js mengontrol pengalaman brand; Odoo 19 menjadi single source of truth.",
        "bullets": [
            "Brand-controlled editorial UX (Next.js 15) — Odoo tetap pemilik catalog, stock, price, order, customer",
            "Diferensiasi pengalaman fashion: 3D Product Detail Page + AI Personal Shopper",
            "Integrasi aman 3-lapis lewat BFF: Public (CORS) · Customer (JWT) · Admin (HMAC)",
            "Delivery cepat: maksimal reuse modul platform + AI-agentic development (Claude Code)",
        ],
        "highlights": [
            ("3D", "Product Viewer"),
            ("AI", "Personal Shopper"),
            ("3-Layer", "Secure Integration"),
            ("~107", "Mandays"),
        ],
    }
)

# 3 — Solution Overview (frontend vs backend split)
add(
    {
        "kind": "two_col",
        "title": "Solution Overview — Frontend × Backend",
        "left_title": "Storefront — Frontend (Next.js 15)",
        "left_bullets": [
            "Presentasi & editorial design (Tailwind + Framer Motion)",
            "3D Product Detail Page (three.js / React-Three-Fiber)",
            "AI Personal Shopper widget",
            "Multilanguage ID/EN (URL-prefixed)",
            "BFF route handlers (server-side, inject auth + tenant)",
            "Session: sealed HttpOnly cookies (AES-256-GCM)",
        ],
        "right_title": "Odoo 19 — Backend (System of Record)",
        "right_bullets": [
            "Catalog, varian/ukuran, tags, material",
            "Pricelist & promo (strike-through, diskon %)",
            "Stock & in-store availability (per warehouse)",
            "Cart & checkout = sale.order (pajak native)",
            "Customer, address book, guest checkout",
            "Affiliate, editorial content, fulfilment & tax",
        ],
        "footnote": "Prinsip headless: Frontend mengontrol presentasi; Odoo mengontrol data & proses bisnis (single source of truth).",
    }
)

# 4 — Feature Catalog
add(
    {
        "kind": "modules_p2",
        "title": "Feature Catalog — Storefront Capabilities",
        "groups": [
            (
                "Catalog & PDP / Katalog",
                "PLP filter (kategori, tag, range harga), search, sort, pagination · PDP: galeri, varian/ukuran, material, ref/SKU, badge 'New' otomatis",
            ),
            (
                "3D Product Viewer",
                "three.js + React-Three-Fiber · gambar produk pada mesh kain · drag-rotate · toggle 2D⇄3D · CSP-safe tanpa fetch eksternal",
            ),
            (
                "AI Personal Shopper",
                "Chat stylist · intent → retrieve katalog Odoo → synthesize · anti-halusinasi (produk real) · eskalasi ke manusia (WhatsApp)",
            ),
            (
                "Cart · Checkout · Wishlist",
                "Cart = draft sale.order (pricelist/pajak native) · checkout guest & member · alamat kirim/tagih · wishlist + move-to-cart",
            ),
            (
                "Store Locator + Click & Collect",
                "Toko = stock.warehouse published (geo, jam buka) · stok per toko · ambil di toko (pickup XOR kirim)",
            ),
            (
                "Promo & Multilanguage",
                "Strike-through price dari pricelist + diskon % · ID/EN URL-prefixed, field translatable Odoo, OG tag terlokalisasi",
            ),
            (
                "Affiliate Program",
                "Link & klik tracking · atribusi ke order · komisi & payout · dashboard self-serve afiliasi",
            ),
            (
                "Editorial CMS + Newsletter",
                "Blok konten (hero/editorial/lookbook) dikelola di Odoo · newsletter subscriber · consent UU PDP",
            ),
        ],
    }
)

# 5 — 3D PDP deep dive
add(
    {
        "kind": "two_col",
        "title": "3D Product Detail Page",
        "left_title": "Bagaimana 3D PDP Bekerja",
        "left_bullets": [
            "three.js + React-Three-Fiber + drei",
            "Gambar produk dipetakan ke mesh kain (sine-drape)",
            "Drag-rotate via PresentationControls",
            "Contact shadow + HDRI environment (self-hosted)",
            "Lazy-load (SSR off), toggle 2D⇄3D di PDP",
        ],
        "right_title": "Keamanan & Performa",
        "right_bullets": [
            "CSP-safe: gambar lewat proxy /api/img (tanpa fetch eksternal)",
            "Bump map prosedural agar tekstur tidak 'plastik'",
            "Aset HDRI self-hosted (tanpa CDN pihak ketiga)",
            "Render hanya saat viewer dibuka",
            "Fallback galeri 2D bila perangkat terbatas",
        ],
        "footnote": "Fashion saat ini memakai image-on-cloth; hard goods (tas/sepatu) dapat memakai model 3D nyata pada fase berikutnya.",
    }
)

# 6 — AI Personal Shopper flow
add(
    {
        "kind": "diagram",
        "title": "AI Personal Shopper — Retrieval-Controlled",
        "intro": "Bukan free-form: jawaban & kartu produk selalu berasal dari katalog Odoo yang nyata (anti-halusinasi).",
        "ascii": [
            "  Browser",
            "    │  POST /api/shopper",
            "    ▼",
            "  Next.js BFF",
            "  (HMAC sign · inject tenant)",
            "    │",
            "    ▼",
            "  ai-gateway  /v1/shopper",
            "    │   ┌─────────────────┐",
            "    ├──►│ 1 EXTRACT intent │",
            "    ├──►│ 2 RETRIEVE  ◄────┼── Odoo katalog",
            "    ├──►│ 3 SYNTHESIZE     │",
            "    └──►│ 4 GUARD (real)   │",
            "        └─────────────────┘",
            "    │",
            "    ▼",
            "  Reply + product cards → UI",
        ],
        "decisions": [
            "EXTRACT — parse intent (occasion, budget, warna, ukuran), JSON-mode",
            "CLARIFY — jika terlalu umum, tanya balik (tidak menebak)",
            "RETRIEVE — ambil produk dari Odoo /storefront/api/products sesuai filter",
            "SYNTHESIZE — susun balasan natural dari item nyata",
            "GUARD — kartu produk hanya dari payload katalog (anti-halusinasi)",
            "ESCALATE — komplain/retur diarahkan ke manusia (WhatsApp)",
            "Provider: ai-gateway (Claude / Ollama lokal) · HMAC-signed · prompt caching",
        ],
    }
)

# 7 — Integration Architecture (centerpiece)
add(
    {
        "kind": "diagram",
        "title": "Integration Architecture — Storefront × Odoo",
        "intro": "Browser tidak pernah bicara langsung ke Odoo — semua lewat BFF server-side (aman, tenant-scoped).",
        "ascii": [
            "  ┌───────────┐  HTTPS (Caddy/TLS)",
            "  │  Browser  │──────────────┐",
            "  └───────────┘              ▼",
            "                  ┌────────────────────────┐",
            "                  │  Next.js Storefront     │",
            "                  │  ├─ UI (React,3D,i18n)  │",
            "                  │  └─ BFF route handlers  │",
            "                  └───────────┬────────────┘",
            "                   TLS-pinned │ storefront-tls",
            "                              ▼",
            "                  ┌────────────────────────┐",
            "                  │  Odoo 19 CE             │",
            "                  │  custom_storefront_api  │",
            "                  │  + affiliate/core/...   │",
            "                  └───────────┬────────────┘",
            "                              ▼",
            "                       ┌────────────┐",
            "                       │ PostgreSQL │ DB: gentlewoman",
            "                       └────────────┘",
        ],
        "decisions": [
            "Tenant resolution: BFF kirim header X-Odoo-Database: gentlewoman (dbfilter ^%d$)",
            "Single source of truth: Odoo pemilik catalog/stock/price/order/customer/promo/content",
            "BFF = security boundary: inject auth & tenant header server-side; secret tak pernah ke browser",
            "Internal hop BFF→Odoo lewat TLS sidecar (cert-pinned) — token/PII terenkripsi",
            "Reuse native: cart = website_sale sale.order · shipping = custom_ecommerce · payment = custom_payment_id",
        ],
    }
)

# 8 — 3 Auth Layers
add(
    {
        "kind": "table",
        "title": "Integration — 3 Auth Layers",
        "intro": "Tiga lapis otentikasi sesuai sensitivitas data.",
        "headers": ["Layer", "Mechanism", "Scope / Data", "Contoh Endpoint"],
        "rows": [
            [
                "Public",
                "auth=public + CORS, read-only",
                "Katalog, PDP, tags, stores, content, shipping quote",
                "GET /storefront/api/products · /categories · /stores",
            ],
            [
                "Customer",
                "JWT (HS256) bearer, sealed HttpOnly cookie",
                "Per-customer: cart, order, address, wishlist (partner-scoped)",
                "POST /auth/login · GET/POST /cart · POST /checkout",
            ],
            [
                "Admin",
                "HMAC-SHA256 (X-Signature/X-Timestamp), server-to-server",
                "Webhook BFF↔Odoo (health, product sync, order status)",
                "POST /admin/health · /admin/sync/products",
            ],
        ],
        "col_widths": [1.1, 2.5, 2.7, 2.7],
        "footnote": "JWT: partner di-resolve dari email claim → request.jwt_partner_id; body partner tak pernah dipercaya (anti-IDOR). HMAC replay window 5 menit.",
    }
)

# 9 — Data Flow (read vs write)
add(
    {
        "kind": "two_col",
        "title": "Data Flow — Read & Write Path",
        "left_title": "Read Path — Catalog / Price / Stock",
        "left_bullets": [
            "Product di-serialize: name, price (pricelist), compare_at, discount_pct",
            "Tags, material, is_new, in_stock per varian",
            "Pricelist di-resolve sekali per request (mata uang IDR)",
            "Stok: qty_available; in-store per warehouse (location-scoped)",
            "Gambar lewat proxy /api/img (anti-SSRF); lang=id|en field translatable",
        ],
        "right_title": "Write Path — Cart → Order",
        "right_bullets": [
            "Add to cart → draft sale.order (_cart_add native: pricelist + pajak)",
            "Pilih kurir (custom_ecommerce) atau pickup toko (XOR)",
            "Checkout → sale.order.action_confirm → order terkonfirmasi",
            "Bayar → payment.transaction (custom_payment_id; Eraspace adapter stub)",
            "Token JWT AES-256-GCM sealed, refresh transparan; affiliate attribution di order",
        ],
    }
)

# 10 — Odoo Backend Responsibilities
add(
    {
        "kind": "table",
        "title": "Odoo Backend Responsibilities",
        "headers": ["Module / Service", "Tanggung Jawab"],
        "rows": [
            ["custom_storefront_api", "API publik/JWT/HMAC, cart/checkout, content, store locator, PII-at-rest, guest checkout"],
            ["custom_affiliate", "Master afiliasi, link/klik/konversi/payout, atribusi order, cron harian"],
            ["custom_core", "Platform: HMAC secure-endpoint, Fernet field encryption helpers"],
            ["custom_ecommerce", "Kurir Indonesia (JNE/JNT/SiCepat/AnterAja…) + rate shipment"],
            ["custom_payment_id", "Payment gateway adapters (Midtrans/Xendit; Eraspace stub)"],
            ["custom_pdp_* (6 modul)", "Klasifikasi data, consent, audit, masking (UU PDP)"],
            ["ai-gateway (sidecar)", "Abstraksi multi-provider (Claude/Ollama), shopper retrieval, HMAC + rate limit"],
        ],
        "col_widths": [2.4, 6.6],
    }
)

# 11 — Security & Privacy
add(
    {
        "kind": "two_col",
        "title": "Security & Privacy",
        "left_title": "Application & Session",
        "left_bullets": [
            "Strict Content-Security-Policy + security headers",
            "Token HttpOnly + AES-256-GCM sealed; refresh transparan",
            "Anti-IDOR: ownership check alamat (kirim/tagih)",
            "Rate-limit + body cap pada endpoint sensitif",
            "HTML sanitize (DOMPurify) · no raw SQL (ORM only)",
        ],
        "right_title": "Transport, Data & Compliance",
        "right_bullets": [
            "HTTPS (Caddy) + internal TLS sidecar cert-pinned",
            "PII Fernet at-rest (phone/street/zip)",
            "Anti-SSRF image proxy (/api/img dikunci ke /web/image)",
            "UU PDP: consent capture + cookie banner",
            "Secrets externalized + rotation · DB-per-tenant isolation",
        ],
    }
)

# 12 — Delivery Accelerators (justify lean mandays)
add(
    {
        "kind": "two_col",
        "title": "Delivery Accelerators — Reuse + AI-Agentic",
        "left_title": "Platform Reuse — Sudah Tersedia",
        "left_bullets": [
            "custom_storefront_api — scaffolding API headless (3-lapis auth)",
            "custom_core — HMAC & Fernet encryption helpers",
            "custom_pdp_* — consent, audit, masking (UU PDP)",
            "custom_ecommerce — kurir & rate shipment Indonesia",
            "custom_payment_id — adapter payment gateway",
            "website_sale native — cart, pricelist, pajak",
            "ai-gateway — multi-provider (Claude/Ollama) siap pakai",
        ],
        "right_title": "AI-Agentic Delivery (Claude Code)",
        "right_bullets": [
            "Generate controller, model, boilerplate API",
            "Scaffolding komponen Next.js & unit test",
            "Drafting dokumentasi & spec",
            "Refactor & review berbantuan AI",
            "Lebih sedikit kode tulis-tangan → mandays Developer turun",
            "PMO cukup footprint tata kelola (bukan full-time)",
        ],
        "footnote": "Estimasi mandays mengasumsikan reuse maksimal + AI-agentic development. Build tradisional setara ~200–300 MD.",
    }
)

# 13 — Implementation Mandays by Role
add(
    {
        "kind": "table",
        "title": "Implementation Mandays by Role",
        "intro": "Estimasi effort (bukan biaya) untuk GentleWoman Storefront + integrasi Odoo. Kolom = PMO · IT BA · IT Developer · QA.",
        "headers": ["Phase", "PMO", "IT BA", "IT Dev", "QA"],
        "rows": [
            ["1. Discovery & Requirements (BRD/FSD)", "2", "6", "1", "1"],
            ["2. Solution & Technical Design (Blueprint/TSD)", "2", "3", "4", "1"],
            ["3. Odoo Backend API (extend custom_storefront_api)", "1", "2", "11", "3"],
            ["4. Storefront Build (Next.js, AI-accelerated)", "1", "2", "14", "4"],
            ["5. 3D PDP (three.js / R3F)", "1", "0", "5", "1"],
            ["6. AI Personal Shopper (ai-gateway glue)", "1", "1", "6", "2"],
            ["7. Integration & Security Hardening", "1", "1", "6", "3"],
            ["8. UAT, Bug-fix & Stabilization", "1", "3", "4", "5"],
            ["9. Deploy, Go-live & Hypercare", "2", "1", "3", "2"],
            ["TOTAL (mandays)", "12", "19", "54", "22"],
        ],
        "col_widths": [4.2, 1.0, 1.0, 1.0, 1.0],
        "footnote": "Total ~107 mandays. IT Developer mencakup backend Odoo + frontend Next.js + 3D + AI-gateway glue + DevOps (paralel ~2 developer). Re-baseline saat BRD freeze.",
    }
)

# 14 — Project Timeline (~10 weeks)
add(
    {
        "kind": "roadmap",
        "title": "Project Timeline (~10 Minggu)",
        "quarters": [
            (
                "Minggu 1–2",
                [
                    "Discovery & Requirements (BRD/FSD)",
                    "Solution & Technical Design (mulai)",
                    "Setup environment & akses",
                ],
            ),
            (
                "Minggu 3–4",
                [
                    "Technical Design selesai (Blueprint/TSD)",
                    "Odoo Backend API (extend storefront_api)",
                    "Storefront Build mulai (PLP/PDP)",
                ],
            ),
            (
                "Minggu 5–6",
                [
                    "Storefront Build (cart, checkout, i18n)",
                    "3D PDP",
                    "AI Personal Shopper (ai-gateway glue)",
                ],
            ),
            (
                "Minggu 7–8",
                [
                    "AI Shopper selesai",
                    "Integration & Security Hardening",
                    "UAT mulai",
                ],
            ),
            (
                "Minggu 9–10",
                [
                    "UAT & Bug-fix",
                    "Deploy, Go-live & Hypercare",
                    "Handover & dokumentasi",
                ],
            ),
        ],
    }
)

# 15 — Delivery Scope & Status
add(
    {
        "kind": "table",
        "title": "Delivery Scope & Status",
        "intro": "Status fitur saat ini (Phase-1 live pilot di tenant gentlewoman).",
        "headers": ["Status", "Fitur"],
        "rows": [
            [
                "Delivered",
                "Catalog/PLP/PDP · 3D PDP · AI Shopper (MVP) · Cart/Checkout/Wishlist · Store Locator + Click&Collect · Affiliate · Multilanguage ID/EN · Promo · Security & PDP consent",
            ],
            [
                "Pending",
                "CMS lanjutan · Share-to-social lengkap · AI Admin (auto-deskripsi/tagging) · Avatar / Virtual Try-On (Fase B/C)",
            ],
            [
                "Blocked",
                "Payment gateway Eraspace — menunggu dokumentasi API vendor (checkout siap di belakang PaymentProvider interface + feature flag)",
            ],
        ],
        "col_widths": [1.4, 7.6],
    }
)

# 16 — Risks & Mitigations
add(
    {
        "kind": "table",
        "title": "Risks & Mitigations",
        "headers": ["Risk", "Mitigation"],
        "rows": [
            ["Payment Eraspace tertunda (API vendor)", "Checkout sampai pembuatan order di belakang interface + feature flag; aktif begitu API tersedia"],
            ["Biaya AI membengkak", "Prompt caching + rate limit per tenant + fallback Ollama lokal"],
            ["Kebocoran data antar-tenant", "DB-per-tenant + HMAC + tenant allow-list + header X-Odoo-Database"],
            ["Scope creep menggeser mandays", "BRD freeze sebelum build · change request via approval engine · re-baseline"],
            ["Rate-limiter in-memory (single instance)", "Pindah ke Redis saat scale multi-instance"],
        ],
        "col_widths": [3.5, 5.5],
    }
)

# 17 — Document Control & Pengesahan
add(
    {
        "kind": "table",
        "title": "Document Control & Pengesahan",
        "intro": "Versioning & pengesahan dokumen presentasi.",
        "headers": ["Item", "Detail"],
        "rows": [
            ["Document", "GentleWoman Headless Commerce — Business Presentation"],
            ["Document ID / Version", "GW-PRES-001 · v1.0"],
            ["Status / Classification", "Final for Approval · Confidential — Internal"],
            ["Date", "Juni 2026"],
            ["Prepared by", "Product Owner — Value-Added Services (Erajaya)"],
            ["Reviewed by", "IT Business Analyst / Technical Lead — __________________"],
            ["Approved by", "Head of Value-Added Services / IT — __________________"],
        ],
        "col_widths": [2.6, 6.4],
        "footnote": "Riwayat revisi: v1.0 — rilis awal (Juni 2026).",
    }
)

# 18 — Closing
add(
    {
        "kind": "closing",
        "title": "Terima Kasih",
        "subtitle": "GentleWoman Headless Commerce — Storefront × Odoo · Diskusi & Q&A",
        "footer": "Product Owner — Value-Added Services  ·  Erajaya  ·  v1.0  ·  Juni 2026",
    }
)


def main():
    out_dir = Path(__file__).resolve().parent.parent / "docs" / "gentlewoman"
    out_dir.mkdir(parents=True, exist_ok=True)
    pptx_path = out_dir / "GentleWoman-Business-Presentation-v1.0.pptx"
    pdf_path = out_dir / "GentleWoman-Business-Presentation-v1.0.pdf"

    # Make build_pdf (which reads the module global) see our slides.
    bp.SLIDES = SLIDES

    print(f"Building PPTX -> {pptx_path}")
    bp.build_pptx(pptx_path, SLIDES, footer_text=FOOTER)
    print(f"  OK {pptx_path.stat().st_size:,} bytes  ({len(SLIDES)} slides)")

    print(f"Building PDF  -> {pdf_path}")
    bp.build_pdf(pdf_path, slides=SLIDES, footer_text=FOOTER, doc_title=DOC_TITLE)
    print(f"  OK {pdf_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
