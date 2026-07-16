# Functional Specification Document (FSD)
## GentleWoman — Headless Commerce Storefront × Odoo 19

**Erajaya — Value-Added Services**
*Functional behaviour, user stories & acceptance criteria*

---

### Document Control / Kendali Dokumen

| Item | Detail |
|---|---|
| Document Title | Functional Specification Document — GentleWoman Headless Commerce |
| Document ID | GW-FSD-001 |
| Version | 1.0 |
| Status | Final for Approval |
| Classification | Confidential — Internal |
| Date | Juni 2026 |
| Author / Owner | Product Owner — Value-Added Services (Erajaya) |
| Audience | Product, QA, Business Analyst, Engineering |
| Related Documents | Blueprint (GW-BP-001), TSD (GW-TSD-001), Business Presentation (GW-PRES-001) |

### Revision History / Riwayat Revisi

| Version | Date | Author | Description |
|---|---|---|---|
| 1.0 | Juni 2026 | Product Owner — VAS | Initial release / Rilis awal |

### Approval / Lembar Pengesahan

| Role | Name | Signature | Date |
|---|---|---|---|
| Prepared by — Product Owner, Value-Added Services | ______________________ | ______________ | __________ |
| Reviewed by — IT Business Analyst / Technical Lead | ______________________ | ______________ | __________ |
| Approved by — Head of Value-Added Services / IT | ______________________ | ______________ | __________ |

> **Catatan bahasa / Language note.** Bilingual: Bahasa Indonesia + English technical terms.

---

# 1. Pendahuluan / Introduction

**ID.** Dokumen ini mendefinisikan perilaku fungsional storefront GentleWoman (frontend
Next.js) di atas Odoo 19 (backend). Setiap fitur diuraikan dengan deskripsi, user story,
perilaku, kriteria penerimaan, serta pembagian tanggung jawab Storefront vs Odoo.

**EN.** This document defines the functional behaviour of the GentleWoman storefront
(Next.js frontend) over Odoo 19 (backend). Each feature is described with its narrative,
user story, behaviour, acceptance criteria, and Storefront-vs-Odoo responsibility split.

## 1.1 Ruang Lingkup / Scope
Fitur Fase-1 (live pilot) tenant `gentlewoman`. Di luar ruang lingkup: lihat §6.

# 2. Aktor & Peran / Actors & Roles

| Actor | Deskripsi |
|---|---|
| Visitor / Pengunjung | Anonim; melihat katalog, PDP, store locator, AI shopper |
| Customer / Pelanggan | Akun terdaftar (`res.partner` + portal user); cart, order, wishlist, address |
| Guest / Tamu | Checkout tanpa registrasi (access-only token, consent wajib) |
| Affiliate / Afiliasi | Pemilik link; melihat klik, konversi, earnings |
| Admin / Merchandiser | Staf Odoo back-office; kelola produk, harga, promo, stok, konten, order |

# 3. Kebutuhan Fungsional / Functional Requirements

## F1 — Katalog & Product Detail (PLP/PDP)

**Deskripsi.** Pengunjung menelusuri katalog (PLP) dengan filter & sort, lalu membuka
detail produk (PDP) berisi galeri, varian/ukuran, harga, material, dan ketersediaan.

**User story.** *Sebagai pengunjung, saya ingin memfilter & melihat detail produk agar
dapat memilih item yang sesuai.*

**Perilaku.**
- PLP: filter kategori, tag (multi), range harga (`price_min/max` atas `list_price`),
  search nama, sort (price_asc/desc, name, newest), pagination (default 24, max 60),
  slider range memakai `price_bounds`.
- PDP: galeri + zoom, varian (ukuran) dengan status stok per varian, harga (pricelist),
  `compare_at` + diskon %, material (`custom_material_composition`), ref/SKU
  (`default_code`), badge "New" otomatis (window 30 hari).

**Kriteria penerimaan.**
- Filter/sort/pagination konsisten; produk non-aktif tidak tampil.
- Harga & stok sesuai data Odoo saat itu; gambar tampil via proxy.

**Tanggung jawab.** Storefront: UI PLP/PDP, slider, galeri, 2D/3D. Odoo:
serialize produk (harga, stok, tags, material, is_new), facet tags, price_bounds.

## F1a — 3D Product Viewer

**Deskripsi.** PDP menyediakan tampilan 3D interaktif produk.

**User story.** *Sebagai pengunjung, saya ingin memutar produk dalam 3D agar memahami
bentuk/jatuhnya bahan.*

**Perilaku.** Gambar produk dipetakan ke mesh kain; drag-rotate; toggle 2D⇄3D; lazy-load;
fallback galeri 2D; CSP-safe (tanpa fetch eksternal).

**Kriteria penerimaan.** Viewer dapat dibuka/ditutup; rotasi halus; fallback bekerja;
tidak ada pelanggaran CSP.

**Tanggung jawab.** Storefront: rendering 3D (three.js/R3F), aset HDRI. Odoo: menyediakan
gambar produk.

## F2 — Cart, Wishlist & Checkout

**Deskripsi.** Pelanggan/tamu menambah item ke cart/wishlist dan menyelesaikan order.

**User story.** *Sebagai pelanggan, saya ingin menyimpan item ke wishlist, menambah ke
cart, dan checkout dengan alamat & pengiriman yang benar.*

**Perilaku.**
- Cart = draft `sale.order`; tambah/ubah/hapus line; pricelist & pajak native.
- Wishlist: satu baris per `(partner, product_tmpl)`; move-to-cart & move-all (hanya
  item in-stock).
- Checkout: jalur guest & member; alamat kirim/tagih (saved address untuk member, inline
  untuk tamu); pilih kurir **atau** pickup toko (XOR); konfirmasi order; inisiasi
  pembayaran.

**Kriteria penerimaan.**
- Cart akurat (qty, harga, ongkir); wishlist idempoten; checkout menghasilkan order
  terkonfirmasi dengan `partner_shipping_id`/`partner_invoice_id` benar.
- Tamu wajib `consent_data`; ownership alamat tervalidasi (anti-IDOR).

**Tanggung jawab.** Storefront: UI cart/drawer/checkout, selektor alamat/kurir/pickup.
Odoo: `_cart_add`, rating kurir, `action_confirm`, validasi consent & ownership.

## F3 — Multilanguage (ID/EN)

**Deskripsi.** Seluruh pengalaman tersedia dalam Bahasa Indonesia dan Inggris.

**User story.** *Sebagai pengunjung, saya ingin beralih bahasa dan melihat konten katalog
dalam bahasa tersebut.*

**Perilaku.** URL-prefixed `/id`·`/en`; field translatable Odoo via `?lang=`; UI string via
dictionary; OG tag terlokalisasi. Mata uang IDR.

**Kriteria penerimaan.** Pergantian bahasa mengubah konten katalog & UI; OG tag sesuai URL.

**Tanggung jawab.** Storefront: routing locale, dictionary. Odoo: translasi field.

## F4 — Promo & Strike-through Price

**Deskripsi.** Harga diskon ditampilkan dengan harga coret & badge diskon.

**Perilaku.** `price` dari pricelist aktif; `compare_at` = `list_price` saat diskon;
`discount_pct` dihitung. Mata uang pricelist = IDR.

**Kriteria penerimaan.** Produk diskon menampilkan harga coret + % benar; non-diskon tidak.

**Tanggung jawab.** Storefront: tampilan. Odoo: resolusi pricelist & perhitungan.

## F5 — Segmentasi Produk (Kategori & Tags)

**Deskripsi.** Produk tersegmentasi via kategori & tag (style, occasion, color, age_range,
material) untuk filter & rekomendasi.

**Kriteria penerimaan.** Facet tag & kategori memfilter PLP dengan benar.

**Tanggung jawab.** Storefront: UI facet. Odoo: `product.tag`, `product.public.category`.

## F6 — Affiliate Program

**Deskripsi.** Afiliasi membagikan link; konversi diatribusikan & menghasilkan komisi.

**User story.** *Sebagai afiliasi, saya ingin melihat klik, konversi, dan earnings saya.*

**Perilaku.** Link `?aff=CODE` → cookie (consent-gated) → atribusi ke `sale.order` →
konversi & komisi (pending sampai window retur tutup) → dashboard self-serve.

**Kriteria penerimaan.** Klik tercatat; order terkonfirmasi membawa `custom_affiliate_id`;
dashboard menampilkan status (pending/approved/reversed/paid).

**Tanggung jawab.** Storefront: capture & dashboard. Odoo: `custom_affiliate*`, atribusi,
cron lifecycle.

## F7 — New Drops (Badge "New")

**Deskripsi.** Produk baru ditandai badge "New" otomatis.

**Perilaku.** `custom_drop_date` (atau `create_date`) dalam window (default 30 hari) →
`is_new=true`.

**Kriteria penerimaan.** Badge muncul untuk produk dalam window; hilang setelahnya.

**Tanggung jawab.** Storefront: badge. Odoo: field & komputasi.

## F8 — Social & Share, Newsletter

**Deskripsi.** Tautan sosial di footer + tombol share di PDP + pendaftaran newsletter.

**Perilaku.** Footer Instagram/TikTok/Facebook/WhatsApp (`NEXT_PUBLIC_SOCIAL_*`); PDP
"Share" via Web Share API + fallback clipboard; newsletter `POST /newsletter` (idempoten,
validasi email).

**Kriteria penerimaan.** Share berfungsi (atau fallback); subscriber tersimpan.

**Tanggung jawab.** Storefront: UI share/footer. Odoo: `custom.storefront.subscriber`.

## F9 — Editorial Content (CMS di Odoo)

**Deskripsi.** Konten non-katalog (hero copy, editorial, lookbook, announcement) dikelola
di Odoo.

**Perilaku.** `custom.storefront.content` per `code` (translatable); `GET /content?lang=`
mengembalikan `{code: block}`; hero tetap 3D `HeroCanvas` (CMS hanya copy).

**Kriteria penerimaan.** Edit di Odoo (Storefront ▸ Site Content) tampil di storefront
setelah re-fetch; gambar tampil untuk anonim (ACL `base.group_public`).

**Tanggung jawab.** Storefront: rendering. Odoo: model & editor back-office.

## F10 — Store Locator

**Deskripsi.** Pengunjung menemukan toko terdekat dengan alamat & jam buka.

**Perilaku.** Toko = `stock.warehouse` published (geo lat/long, jam buka, gambar); endpoint
`/stores`; "toko terdekat" via geolokasi browser.

**Kriteria penerimaan.** Hanya toko published tampil; jarak/terdekat akurat.

**Tanggung jawab.** Storefront: peta/daftar. Odoo: field & serialisasi warehouse.

## F11 — In-Store Stock & Click & Collect

**Deskripsi.** Pengunjung melihat stok per toko dan memilih ambil di toko.

**Perilaku.** Stok per warehouse (`location`-scoped) via `/products/<id>/availability`;
checkout toggle Dikirim/Ambil-di-toko; pickup men-set `warehouse_id`+`custom_is_pickup`
dan menghapus line kurir (pickup XOR kirim).

**Kriteria penerimaan.** Stok per toko akurat; mode pickup tanpa ongkir & tanpa alamat.

**Tanggung jawab.** Storefront: toggle & daftar toko. Odoo: availability & pickup logic.

## F12 — AI Personal Shopper

**Deskripsi.** Asisten belanja/stylist berbasis chat yang menjawab dari katalog nyata.

**User story.** *Sebagai pengunjung, saya ingin meminta rekomendasi outfit/produk dan
mendapat saran yang relevan dari katalog.*

**Perilaku.** `EXTRACT` intent → `CLARIFY` bila terlalu umum → `RETRIEVE` dari katalog Odoo
→ `SYNTHESIZE` balasan → `GUARD` (kartu produk hanya item nyata) → `ESCALATE` (komplain/
retur → WhatsApp). Greeting hanya pesan pertama; history maks 8 turn; rate-limit 12/min.

**Kriteria penerimaan.** Tidak ada produk/harga halusinasi (selalu dari Odoo); eskalasi
muncul untuk kata kunci komplain; rate-limit berlaku.

**Tanggung jawab.** Storefront: widget chat. ai-gateway: orchestration. Odoo: katalog.

## F13 — Consent & Privasi (UU PDP)

**Deskripsi.** Persetujuan data ditangkap & dihormati.

**Perilaku.** Register/guest wajib `consent_data`; `consent_marketing` opsional; cookie
banner default privacy-preserving; profil AI shopper consent-gated.

**Kriteria penerimaan.** Tanpa `consent_data`, registrasi/guest ditolak; consent &
tanggal tersimpan.

**Tanggung jawab.** Storefront: form/banner. Odoo: field consent di `res.partner`.

# 4. Aturan Bisnis / Business Rules

- BR-1: Cart selalu draft `sale.order`; checkout = `action_confirm`.
- BR-2: Pengiriman **XOR** pickup (tidak keduanya).
- BR-3: Filter harga & sort memakai `list_price` (harga katalog), konsisten satu sama lain.
- BR-4: Mata uang pricelist = mata uang company (IDR) untuk mencegah konversi FX.
- BR-5: Body request partner/address id tidak pernah dipercaya — selalu di-scope dari JWT &
  divalidasi kepemilikan (anti-IDOR).
- BR-6: AI shopper tidak boleh menampilkan produk/harga di luar katalog Odoo.
- BR-7: `consent_data` wajib untuk registrasi & guest checkout.
- BR-8: Seed per-tenant (store, promo, drop date, stock) via script, bukan module data.

# 5. Alur UX / UX Flows (ringkas)

- **Browse → PDP → Cart → Checkout → Pay** (member/guest).
- **Wishlist → Move-to-cart → Checkout.**
- **AI Shopper → rekomendasi → klik kartu produk → PDP → Cart.**
- **Store Locator → pilih toko → Click & Collect di checkout.**
- **Affiliate link → browse → checkout → konversi → dashboard.**

# 6. Di Luar Ruang Lingkup / Out of Scope (Fase 2–3)

- CMS lanjutan (mis. Payload) — saat ini editorial via Odoo content model.
- Share-to-social lengkap (OG kaya, kampanye).
- AI untuk Admin: auto-deskripsi & auto-tagging produk (draft → review → publish).
- Mix-and-match lanjutan: Avatar/Mannequin (Fase B), Virtual Try-On realistis (Fase C).
- Integrasi payment **Eraspace** — BLOCKED menunggu dokumentasi API vendor.

# 7. Ringkasan Kriteria Penerimaan / Acceptance Summary

- Seluruh journey Fase-1 (F1–F13) lulus end-to-end di tenant `gentlewoman`.
- Aturan bisnis BR-1…BR-8 terpenuhi.
- Keamanan & privasi (consent, IDOR, CSP, rate-limit) tervalidasi.
- Isolasi tenant terkonfirmasi.

# Appendix — Feature Status Matrix

| ID | Feature | Status |
|---|---|---|
| F1 / F1a | Katalog & PDP / 3D Viewer | ✓ Delivered |
| F2 | Cart, Wishlist & Checkout | ✓ Delivered |
| F3 | Multilanguage ID/EN | ✓ Delivered |
| F4 | Promo & Strike-through | ✓ Delivered |
| F5 | Segmentasi (kategori & tags) | ✓ Delivered |
| F6 | Affiliate Program | ✓ Delivered |
| F7 | New Drops badge | ✓ Delivered |
| F8 | Social/Share + Newsletter | ◷ Partial (share + newsletter ada; kampanye sosial lanjutan pending) |
| F9 | Editorial Content (Odoo CMS) | ✓ Delivered |
| F10 | Store Locator | ✓ Delivered |
| F11 | In-Store Stock & Click&Collect | ✓ Delivered |
| F12 | AI Personal Shopper (MVP) | ✓ Delivered |
| F13 | Consent & Privasi (UU PDP) | ✓ Delivered |
| — | AI Admin (auto-desc/tag) | ◷ Pending (Fase 2) |
| — | Avatar / Virtual Try-On | ◷ Pending (Fase 3) |
| — | Payment Eraspace | ⛔ Blocked (API vendor) |

---

*GW-FSD-001 · v1.0 · Confidential — Internal · Erajaya Value-Added Services · Juni 2026*
