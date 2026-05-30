# Implementation Brief — Headless Fashion Commerce + AI Personal Shopper

> **Untuk:** Claude Code @ Odoo Platform VPS
> **Inisiatif:** Erajaya (Product Owner: Ade Maryadi) — storefront fashion headless di atas Odoo Platform.
> **Payment:** Eraspace Payment API (dokumen API menyusul — lihat §10).
> **Status:** Draft v2 untuk implementasi bertahap.
> **Brand:** _TBD_ (placeholder dokumen: "the Store").
> **Konvensi modul/field kustom:** prefix **`custom_`** (modul: `custom_*`, field: `custom_*`, model baru: `custom.*`). **Jangan** gunakan prefix lain.

---

## 0. ⚠️ WAJIB DULU — Inventory Existing (jangan skip)

> **Aturan keras:** JANGAN membuat model, field, modul, tabel, atau script baru sebelum memetakan apa yang SUDAH ADA. Pekerjaan baru tidak boleh menabrak infrastruktur eksisting.

Sebelum menulis kode apa pun, Claude Code **harus** menjalankan & melaporkan hasil dari:

```bash
# Struktur & script yang sudah ada
ls -la addons/ ; ls -la addons/custom_* 2>/dev/null
ls -la scripts/ ; crontab -l
cat docker-compose.yml ; cat .env   # (redact secrets sebelum lapor)
```

```sql
-- Modul Odoo terpasang
SELECT name, state, latest_version FROM ir_module_module WHERE state='installed' ORDER BY name;
-- Custom field yang sudah ada di product & partner
SELECT model, name, field_description, ttype FROM ir_model_fields
 WHERE model IN ('product.template','product.product','res.partner','stock.warehouse','sale.order')
   AND state='manual';
-- Cek model bawaan yang relevan apakah tersedia di CE19 ini
SELECT model FROM ir_model WHERE model IN ('product.tag','product.public.category','loyalty.program','loyalty.card');
-- Gudang / lokasi yang sudah ada (untuk store locator & click&collect)
SELECT id, name, code FROM stock_warehouse;
```

**Lapor balik ke Ade:** "Yang sudah ada untuk X: ... ; yang belum ada: ..." sebelum mulai. Khusus untuk:
- Apakah `product.tag` & `product.public.category` tersedia (jangan bikin taksonomi tag baru kalau bawaan ada).
- Apakah `default_code` (Internal Reference) sudah dipakai → **itu = "kode referensi", jangan bikin field baru.**
- Apakah sudah ada API layer / CMS / Qdrant / Redis yang berjalan.
- Apakah sudah ada modul/field ber-prefix `custom_` yang konflik.

---

## 1. Arsitektur (recap keputusan)

```
Next.js storefront (Web + PWA)
        │
   BFF / API orchestration layer  (FastAPI sidecar · Redis cache · Qdrant)
        │
 ┌──────────────┬──────────────┬─────────────────┬────────────────────┐
 Odoo CE 19      Headless CMS    Eraspace Payment   AI services
 (system of      (Payload v3)    API (eksternal)    (shopper, search,
  record:        konten non-     — DOKUMEN API       try-on/3D — eksternal
  produk, stok,   produk, toko,    MENYUSUL           API)
  order, customer editorial)
```

**Content contract (kunci):**
- **Odoo = source of truth** produk, varian, harga, **stok per lokasi**, customer, order, promo, loyalty, atribusi affiliate.
- **CMS (Payload v3) = konten non-produk:** halaman, homepage blocks/banner, koleksi & lookbook editorial (referensi produk via `product_id`), **data toko** (alamat, jam, foto, geo), blog, size guide, FAQ, nav, SEO meta.
- **Next.js compose keduanya** lewat BFF. Produk di-cache (Redis), di-index untuk search (Qdrant).
- **Payment = Eraspace API** (bukan payment provider Odoo) — **lihat §10, masih BLOCKED menunggu dokumen API.**

---

## 2. Feature Catalog

Tiap fitur diberi: **Odoo-side** (model/field/modul, prefix `custom_`), **CMS-side**, **Frontend/BFF-side**. Prinsip: pakai mekanisme bawaan Odoo dulu, custom hanya jika perlu.

### F1 — Product Detail & Media
- **Zoom per gambar + galeri multi-image:** murni frontend (lightbox/zoom). Sumber gambar: `product.template.image_1920` + `product.image` (extra media). Layani via image CDN/resizer.
- **Availability size:** = stok per **variant**. Pakai `product.attribute` "Size" + `product.product` (variant) + `stock.quant`. UI: ukuran sold-out di-grey. **Jangan** bikin field "size availability" — itu turunan stok varian.
- **Komposisi bahan:** field baru `custom_material_composition` (Html/Text, **translatable**) di `product.template`. Alternatif: `product.attribute` "Material" bila ingin filterable.
- **Kode referensi:** **pakai `default_code` bawaan** (Internal Reference). Konfirmasi di §0.
- **Product tag:** pakai `product.tag` bawaan bila ada (lihat §0). Tag ini juga jadi sumber pencarian AI (§3).

### F2 — Cart, Wishlist, Checkout, Registrasi & Guest
- **Cart:** `sale.order` state draft. Putuskan storage: SO draft di Odoo (persisten, login) + Redis untuk guest/anonymous, merge saat login.
- **Wishlist:** model baru `custom.wishlist` (partner_id, product_id, variant_id, created) — Odoo CE tidak punya wishlist headless yang clean.
- **Checkout:** guest & registered. Guest → buat `res.partner` minimal + flag `custom_is_guest`. Registered → akun penuh.
- **Registrasi:** SSO/OAuth/passwordless atau email. **Password & data sensitif diinput user sendiri** (jangan auto-fill kredensial).

### F3 — Multilanguage (ID / EN)
- **Odoo:** translatable fields aktif untuk `name`, `description_sale`, `custom_material_composition`, kategori. Default lang = ID, sekunder = EN.
- **CMS:** Payload localization (id, en).
- **Frontend:** `next-intl` / i18n routing (`/id`, `/en`). Currency: IDR (Rp).

### F4 — Promo (Harga Coret / Special Price)
- **Odoo:** `pricelist` untuk harga normal + harga promo. Harga coret = `list_price` vs harga pricelist aktif. Badge "−30%"/"Special Price" dihitung dari selisih.
- **Loyalty/coupon/gift card:** pakai `loyalty.*` bawaan bila tersedia (§0) untuk member-price (Club) & voucher.

### F5 — Product Segmentation (Type / Style / Age range / dll)
- **Category by type:** `product.public.category` (hierarki e-commerce).
- **Style / occasion / color / age-range:** taksonomi terstruktur. Rekomendasi: `product.tag` dengan grup tag (mis. grup `style`, `occasion`, `color`, `age_range`) **atau** custom `custom.fashion.attribute` (m2m) bila butuh metadata per-tag. **Konsisten dengan tag yang dibaca AI (§3).** Definisikan taksonomi sekali, dipakai filter UI + AI.

### F6 — Affiliate, Careers, Cookie Consent, Perlindungan Data (UU PDP)

**Affiliate program — prinsip inti:** **setiap link penjualan yang dibagikan affiliator SELALU menyematkan identifier affiliator** (kode/ID unik). Apa pun yang dibagikan — homepage, halaman produk, koleksi, lookbook — membawa identifier itu, sehingga **setiap transaksi yang berasal dari link tersebut teratribusi ke affiliator** yang bersangkutan.

Odoo CE tidak punya modul affiliate → custom module **`custom_affiliate`**.

**Cara kerja (alur):**
1. **Pendaftaran affiliator** → dapat `affiliate_code` unik (mis. `RAYA123`).
2. **Generate link** → affiliator membuat link untuk URL apa pun (produk/koleksi/home). Identifier disisipkan sebagai param (`?aff=RAYA123`) atau path pendek (`/a/RAYA123` → redirect ke target). Opsional short-link + parameter UTM.
3. **Klik & capture** → visitor klik → identifier dibaca dari URL → disimpan di **first-party cookie** `aff_ref` (**consent-gated**) selama **attribution window** (mis. 30 hari), model **last-click** (atau first-click — keputusan §8). Tulis 1 record `custom.affiliate.click`.
4. **Konversi** → saat order confirm, cookie dibaca → resolve affiliator → set `custom_affiliate_id` di `sale.order` → buat `custom.affiliate.conversion` + hitung komisi.
5. **Hold & reversal** → komisi `pending` sampai window retur lewat; `reversed` bila order diretur/cancel; lalu `approved` (siap dibayar).
6. **Payout** → settlement periodik per affiliator.

**Data model (`custom_affiliate`):**
| Model | Field utama | Fungsi |
|---|---|---|
| `custom.affiliate` | partner_id, **affiliate_code (unik)**, status, commission_rate / tier, payout_method | master affiliator |
| `custom.affiliate.link` | affiliate_id, target_url / product_id / category_id, slug / short_code, utm_* | link terlacak (identifier tersemat) |
| `custom.affiliate.click` | affiliate_id, link_id, ts, ip_hash, ua_hash, referrer, landing_url | analitik klik & atribusi |
| `custom.affiliate.conversion` | affiliate_id, sale_order_id, order_value, commission_rate, commission_amount, status (pending/approved/reversed/paid) | atribusi & komisi per order |
| `custom.affiliate.payout` | affiliate_id, period, total_amount, status, paid_date, method | batch pembayaran |
| `sale.order` (extend) | `custom_affiliate_id` (m2o → custom.affiliate) | jejak atribusi di order |

**Attribution & anti-fraud:**
- Komisi dihitung dari nilai order **setelah** retur/refund (bukan nilai kotor).
- **Block self-referral** (affiliator beli lewat link sendiri).
- De-dup klik (rate-limit per identifier+session); tentukan last-click vs first-click (default last-click).
- Identifier yang tidak dikenal/non-aktif → diabaikan tanpa error.

**Share-to-social (lihat F8):** dashboard affiliator meng-generate share-link + preview card (OG meta) per produk **dengan identifier tersemat**; "post to social" = share pre-filled berisi tracked link. Setiap share otomatis membawa identifier affiliator.

**Privacy:** cookie atribusi gated oleh cookie consent (di bawah). Hash IP/UA; jangan simpan PII visitor mentah di click log.

**Lainnya di F6:**
- **Careers / Partnership / Supplier:** halaman + form di **CMS** (bukan Odoo). Submission → simpan di CMS / email notifikasi (bukan auto-action).
- **Cookie consent:** banner (config di CMS), default paling privacy-preserving. Simpan preferensi; cookie affiliate hanya aktif setelah consent.
- **UU PDP pada register:** consent eksplisit (checkbox tidak pre-checked) untuk marketing & data processing. Simpan `custom_consent_marketing`, `custom_consent_data`, `custom_consent_date` di `res.partner`. Sediakan hak akses/hapus data (berlaku juga untuk data AI — §3/§5).

### F7 — Weekly Trend / New Drops
- **Odoo:** field `custom_drop_date` / `custom_is_new` di product, atau tag `new`. "New" otomatis = `create_date`/`custom_drop_date` dalam N hari.
- **Frontend:** section "Baru Tiba" + halaman drop mingguan. **CMS** atur editorial drop (banner, cerita koleksi).

### F8 — Social Media & Sharing
- **Brand social links:** Instagram, TikTok, Facebook, **WhatsApp** (peran LINE di pasar TH = WA di ID) — config di CMS footer.
- **Share button:** Web Share API + fallback (WA, IG story, copy-link, FB) di product & lookbook.
- **Post-to-social untuk affiliate:** generate share-link ber-identifier affiliator (F6) + preview card (OG meta per produk). Klik dari share → atribusi otomatis.

### F9 — CMS v3 (Payload)
- **Payload CMS v3** (native Next.js, TypeScript, Postgres). Collections: `pages`, `homepageBlocks`, `collections` (referensi `product_id` Odoo), `stores`, `blog`, `sizeGuides`, `navigation`, `banners`, `seoMeta`. Localized (id/en).
- BFF menggabungkan data CMS + produk Odoo per halaman.

### F10 — Store Locator
- **Stores di CMS** (alamat, jam buka per-hari, foto, **lat/lng**, `odoo_warehouse_id`).
- **Frontend:** peta + list + **"toko terdekat dari saya"** via browser Geolocation API → hitung jarak (Haversine) → sort. Privacy: minta izin lokasi, jangan kirim koordinat ke URL.

### F11 — In-Store Stock & Click & Collect
- **Inti kemenangan kompetitif.**
- **Odoo:** stok per toko = `stock.quant` per `stock.warehouse`/`stock.location`. Map `store(CMS).odoo_warehouse_id`.
- **BFF endpoint:** `GET /stock?variant_id&store_id` → qty available real-time (cache pendek di Redis).
- **Click & Collect:** SO dengan `warehouse_id` = toko terpilih, tipe delivery = pickup. UI: "Tersedia di [toko terdekat] · Reserve / Ambil di toko".

---

## 3. AI Personal Shopper / Fashion Stylist (komponen baru, purpose-built)

> Dibangun **terpisah & spesifik untuk use-case fashion shopper**. Pola arsitektur (RAG + Claude API + embeddings) standar, tapi knowledge, persona, dan guardrail disesuaikan untuk retail fashion.

### 3.1 Persona & UX
- **Floating animated character** (maskot) — widget melayang kanan-bawah, animasi ringan (Lottie/Rive), klik → buka panel chat.
- **Nama karakter:** _TBD_ (keputusan Ade).
- **Sapaan default "Kak"** (mis. "Halo Kak! Lagi cari apa hari ini?"). Tone friendly, helpful, ringkas.
- **Aturan greeting:** sapa **hanya di pesan pertama**. Bila sudah ada history percakapan → langsung jawab, **jangan re-greeting tiap balasan**. Deteksi first-turn via session state (Redis).

### 3.2 Arsitektur
```
Visitor ─► Chat widget ─► BFF /ai/shopper ─► Agent (Claude API)
                                              ├─ Tool: search_products (Qdrant + filter Odoo)
                                              ├─ Tool: check_stock (Odoo live)
                                              ├─ Tool: get_visitor_profile (consent-gated)
                                              ├─ Tool: get_purchase_history (consent-gated)
                                              └─ KB: Trend KB (refreshed) + product tags
```
- **Model routing:** Claude Haiku untuk intent/percakapan ringan, Sonnet untuk reasoning outfit/styling kompleks. Prompt caching agresif (system prompt + taksonomi tag sebagai cached block).
- **Indexing produk:** embed nama+deskripsi+tag+atribut per produk (Voyage multimodal) → **Qdrant**, key = `product_id`. Re-index saat produk berubah (webhook/cron dari Odoo).

### 3.3 Sumber pengetahuan
1. **Katalog Odoo** (produk, varian, harga live, stok live) — **grounding utama.**
2. **Product tags / taksonomi** (F5) — AI membaca tag untuk pencarian (`style`, `occasion`, `color`, `age_range`, `material`).
3. **Trend KB** — pengetahuan tren fashion terkini. **Catatan jujur:** Odoo tidak menyimpan ini → butuh KB terpisah yang **di-refresh berkala** (kurasi manual / scheduled research). Opsi web-search fallback **hanya** untuk topik tren (whitelist), **dilarang** untuk harga/stok (wajib dari Odoo).
4. **Profil visitor** (umur, warna favorit, ukuran, budget) — dikumpulkan dalam percakapan, **consent-gated**, disimpan di session/`res.partner` (lihat §3.5).
5. **History pembelian** (untuk personalisasi style) — consent-gated.

### 3.4 Kapabilitas & contoh alur
- Pencarian natural-language: _"Carikan outfit kerja under Rp 1jt warna earth-tone"_ →
  parse intent → `occasion=work`, `budget<=1.000.000`, `color in {earth-tone}` →
  `search_products` (Qdrant + filter harga/tag) → **compose outfit** (top+bottom+shoes/acc, total ≤ budget) →
  `check_stock` → tampilkan **kartu produk asli** (link ke PDP) + alasan styling.
- Mix & match / "complete the look" (lihat §5).
- Tanya tren: jawab dari Trend KB.

### 3.5 Data visitor & UU PDP
- Kumpulkan hanya yang relevan (umur range, warna, ukuran, budget). **Consent eksplisit** sebelum simpan/personalisasi.
- Retensi terbatas, hak hapus. Jangan simpan data sensitif tak perlu. (Foto untuk try-on → §5, aturan lebih ketat.)

### 3.6 Guardrails (kritikal)
- **Hanya rekomendasikan produk nyata** yang ada di Odoo + **in-stock** + harga **live**. **Dilarang mengarang SKU/harga/stok.** Setiap rekomendasi wajib ber-`product_id`.
- Bila tidak ada produk cocok → katakan jujur + tawarkan alternatif terdekat, jangan memaksa.
- Jangan over-cautious menolak hal yang sebenarnya bisa dijawab; jangan re-greeting. Iterasi prompt: tulis → tes → identifikasi failure → tambah few-shot → tes ulang.
- Eskalasi ke CS manusia (atau WhatsApp) bila: minta CS, sentimen negatif, intent komplain/retur, 3 turn gagal beruntun.

### 3.7 Sketsa system prompt (ringkas — untuk diiterasi)
```
Kamu adalah [Nama], personal shopper untuk [Brand]. Sapa pelanggan dengan "Kak".
ATURAN:
- Sapa HANYA jika belum ada history. Jika sudah ada, langsung jawab tanpa salam ulang.
- HANYA rekomendasikan produk dari hasil tool search_products. Jangan mengarang produk,
  harga, atau stok. Selalu sertakan link produk.
- Hormati budget & filter pelanggan (warna, occasion, ukuran).
- Untuk pertanyaan tren, gunakan Trend KB. Untuk harga/stok, WAJIB dari tool (Odoo).
- Ringkas, hangat, jujur. Jika tak ada yang cocok, katakan & tawarkan alternatif.
- Eskalasi ke CS bila diminta / komplain / 3x gagal.
[+ few-shot examples occasion/budget/color]
```

---

## 4. AI untuk Admin (back-office)
- **Generate deskripsi produk** (ID + EN) dari atribut + foto. Draft → **review admin sebelum publish** (jangan auto-publish).
- **Auto product tagging** — saran tag (`style`, `occasion`, `color`, `material`, `age_range`) dari gambar+atribut, admin approve. Tag konsisten dgn taksonomi F5/§3.3.
- **Translation** ID↔EN field produk.
- **Output filter & human-in-the-loop:** semua output AI admin = draft, bukan langsung live.

---

## 5. Outfit Mix-and-Match + Mannequin / Model
> **Penilaian jujur — fitur paling ambisius & berisiko. Dibagi bertahap, jangan langsung yang tersulit.**

- **Fase A (feasible, mulai dari sini): 2D "Complete the Look" / outfit builder.** Susun item top→toe (top, bottom, shoes, bag, accessory) sebagai komposisi flat-lay / grid, dengan saran dari AI shopper (§3). Tanpa render tubuh. ROI tinggi, risiko rendah.
- **Fase B (medium): mannequin/avatar bergaya, opsi mirip visitor** (pilih skin-tone, body-type kategori) — render outfit di figur ilustratif/avatar, **bukan** foto realistis. Lebih aman dari sisi ekspektasi & privasi.
- **Fase C (sulit, opsional): Virtual Try-On realistis "model seperti kamu"** via API eksternal (mis. FASHN/Segmind). **Caveat:** motif rumit (plaid/garis halus/logo) sering gagal, resolusi & latensi terbatas, **biaya per-generate**, dan **upload foto = data pribadi sensitif → consent + retensi ketat (UU PDP).** Posisikan sebagai "preview gaya", bukan prediksi fit. **Tunda sampai Fase A/B terbukti dipakai.**
- **3D/AR view (terpisah):** hanya untuk barang **kaku** (tas, sepatu, jewelry, parfum) via Tripo/Meshy (ekspor GLB/USDZ + AR). **Bukan** untuk kain yang jatuh.

---

## 6. Penambahan Data Model Odoo (ringkas)

| Tujuan | Model | Field/Mekanisme | Catatan |
|---|---|---|---|
| Kode referensi | `product.template/product` | `default_code` (bawaan) | Jangan bikin baru |
| Komposisi bahan | `product.template` | `custom_material_composition` (Html, translatable) | atau attribute "Material" |
| Size availability | `product.product` + `stock.quant` | varian + stok | turunan, bukan field |
| Tags fashion | `product.tag` (bawaan) | grup: style/occasion/color/age_range | taksonomi tunggal utk UI+AI |
| Kategori | `product.public.category` | hierarki | bawaan |
| New/drop | `product.template` | `custom_drop_date`, `custom_is_new` | atau tag `new` |
| Promo | `pricelist` + `loyalty.*` | bawaan | badge dari selisih harga |
| Wishlist | `custom.wishlist` (baru) | partner, product, variant | CE tak punya |
| Guest flag | `res.partner` | `custom_is_guest` | checkout guest |
| Consent UU PDP | `res.partner` | `custom_consent_marketing/data/date` | hak akses & hapus |
| Affiliate | `custom.affiliate*` (baru) | affiliate/link/click/conversion/payout | identifier tersemat di link |
| Atribusi order | `sale.order` | `custom_affiliate_id` (m2o) | jejak atribusi |
| Store ↔ stok | `stock.warehouse` ↔ CMS `stores` | `odoo_warehouse_id` di CMS | konten toko di CMS |
| AI embeddings | (eksternal Qdrant) | key `product_id` | re-index on change |

---

## 7. Roadmap Bertahap (dengan flag risiko)

**Fase 1 — Fondasi commerce + quick win (risiko rendah, ROI tinggi)**
- F1–F5, F7, F9 (CMS), F10 (store locator + GPS), **F11 (in-store stock + click&collect)**.
- AI Personal Shopper §3 (Fase A: search + outfit suggestion teks).
- Mix-and-match §5 **Fase A** (2D complete-the-look).
- Checkout **non-payment** dulu (siapkan SO), payment menyusul (§10).

**Fase 2 — Diferensiasi**
- F6 lengkap (affiliate + share-to-social), F8 lengkap, AI Admin §4.
- Mix-and-match §5 **Fase B** (avatar/mannequin).
- 3D/AR untuk aksesori (§5).

**Fase 3 — Ambisius / R&D**
- VTON realistis §5 **Fase C** (gated, UU PDP, kelola ekspektasi).

---

## 8. Open Decisions (butuh jawaban Ade)
1. **Brand & nama karakter AI** (untuk persona & copy).
2. **Single-tenant** (satu brand) atau **multi-tenant** (banyak brand di bawah Erajaya)? → menentukan desain Payload & isolasi data.
3. Jumlah **toko** & **SKU** + apakah Odoo sudah terisi stok multi-lokasi (untuk F11).
4. **Affiliate:** model atribusi **last-click vs first-click**, panjang **attribution window**, skema komisi (flat vs per-kategori vs tier), dan window reversal retur.
5. **CMS final:** Payload v3 (rekomendasi) — konfirmasi.
6. **Eraspace payment:** kapan dokumen API tersedia? (§10 BLOCKED).
7. Budget operasional AI (token Claude + VTON/3D per-generate) — menentukan model routing & gating.

---

## 9. Instruksi Operasional untuk Claude Code
1. **Inventory existing dulu (§0).** Lapor "yang sudah ada vs belum" sebelum membuat apa pun.
2. **Interface-first:** definisikan Odoo models/fields + TypeScript interfaces (BFF/CMS) sebelum logic.
3. **Namespace `custom_`** untuk semua kustomisasi Odoo (modul `custom_*`, field `custom_*`, model `custom.*`). **Tidak ada prefix lain.**
4. **Feature flags** untuk fitur belum siap (mis. `ENABLE_VTON=false`, `ENABLE_AFFILIATE=false`, `ENABLE_PAYMENT=false`). Endpoint belum siap → HTTP 501.
5. **No trial-and-error:** kalau tak bisa mereproduksi env → minta diagnostik (`cat`, query) dulu, validasi hipotesis dgn tes definitif, baru tulis satu fix terverifikasi.
6. **Jangan tindakan destruktif/permission** (hapus permanen, ubah sharing/akses, transaksi finansial) tanpa konfirmasi Ade.
7. **Grounding AI:** rekomendasi AI WAJIB dari data Odoo live (product_id + stok + harga). Dilarang mengarang.

---

## 10. ⛔ BLOCKED — Eraspace Payment API
Checkout-payment **tidak bisa difinalkan** sampai dokumen API Eraspace diterima. Saat tersedia, klarifikasi: metode bayar (QRIS/VA/kartu/e-wallet), model integrasi (redirect/embedded/server-to-server), **verifikasi signature webhook**, **idempotency** (anti double-charge), refund/void, settlement/rekonsiliasi, sandbox env. Sampai itu: bangun checkout s/d pembuatan SO + abstraksi `PaymentProvider` interface dengan implementasi Eraspace sebagai stub (flag `ENABLE_PAYMENT=false`).
