# Katalog Fitur Platform Odoo — Erajaya Group

Katalog lengkap seluruh modul custom di `addons/`, dikelompokkan ke domain
fungsional, dengan pemisahan antara yang berlaku umum dan yang khusus satu
brand — ditambah satu bab administrasi platform beserta analisis kesenjangan.

| Berkas | Untuk siapa |
|---|---|
| `catalog.md` | Versi yang di-review di pull request. Masuk git. |
| `Katalog_Fitur_Platform_Odoo_Erajaya.pdf` | Versi kanonik untuk stakeholder. Tata letaknya persis seperti dirancang. |
| `Katalog_Fitur_Platform_Odoo_Erajaya.docx` | Agar dokumen bisa disunting. Word mengabaikan CSS kita, sehingga kotak catatan menjadi blockquote berlabel dan sampul menjadi halaman judul biasa. Isi dan urutannya sama. |
| `Matriks_Fitur_Platform_Odoo_Erajaya.xlsx` | Enam lembar untuk difilter dan dipivot. Lembar **Peta Brand** adalah alasan utama berkas ini ada. |

Bahasa: badan dokumen Bahasa Indonesia, lampiran per-modul Bahasa Inggris,
istilah antarmuka Odoo dipertahankan dalam Bahasa Inggris.

## Membangun ulang

```bash
./build.sh              # semuanya, lalu verifikasi
./build.sh --no-pdf     # lewati Chromium — loop cepat saat menyunting prosa
./publish.sh            # salin tiga deliverable ke share
python3 verify.py --published
```

Prasyarat, semuanya sudah ada di host ini: `python3` dengan `openpyxl`,
`python-docx`, `PyYAML`; `pandoc`, `pdfunite`, `pdfinfo`, `pdftotext`; Chromium
Playwright di cache npx.

## Cara kerjanya

```
addons/**/__manifest__.py    ─┐
addons/**/MODULE_KNOWLEDGE.md ┤
addons/**/models/*.py (AST)   ┼→ catalog.json ─┬→ render_md.py   → catalog.md
overrides/*.md                ┤                ├→ render_html.py → PDF, DOCX
taxonomy.py                   ┤                └→ build_xlsx.py  → XLSX
gaps.yaml                     ─┘
```

`catalog.json` adalah **sumber tunggal**. Tidak ada renderer yang menyentuh
`addons/`, sehingga PDF, Excel, dan Markdown tidak mungkin berbeda isi.

Angka di dalam prosa ditulis sebagai placeholder (`{{n.modules_total}}`,
`{{n.domain.<id>}}`, `{{n.group.ee_gap}}`) dan disubstitusi saat build.
Placeholder yang salah ketik **menggagalkan build**, bukan tercetak apa adanya.

### Berkas yang disunting manusia

| Berkas | Isi |
|---|---|
| `narrative/*.md` | Prosa Bahasa Indonesia, satu berkas per bab. Front matter `domain:` menghubungkan bab ke domainnya. |
| `taxonomy.py` | Klasifikasi seluruh modul: domain, cakupan, brand, label Bahasa Indonesia. |
| `gaps.yaml` | Register kesenjangan NOW/TARGET beserta rujukan berkasnya. |
| `overrides/<modul>.md` | Deskripsi tulisan tangan untuk modul tanpa `MODULE_KNOWLEDGE.md`. Memakai empat heading `##` yang sama. |
| `src/svg/D01..D03` | Diagram arsitektur. D04 dan D05 **dihasilkan** dari catalog.json. |

Sisanya dihasilkan otomatis dan tidak boleh disunting tangan.

## Aturan yang menjaga katalog ini tetap benar

**Modul baru menggagalkan build sampai diklasifikasikan.** `build_catalog_json.py`
menuntut `set(DOMAIN_BY_MODULE) == {modul di disk}`, dua arah. Tidak ada
kategori penampung — bucket serba-ada adalah cara katalog fitur membusuk tanpa
ketahuan.

**Klaim diperiksa terhadap kode.** 111 dari 129 dokumen pengetahuan modul adalah
keluaran generator yang belum diperiksa manusia. `--audit` membandingkan setiap
model dan field yang disebut dengan hasil pemindaian kode. Model yang tidak ada
di mana pun menurunkan modul ke `confidence: low` dan daftar modelnya dibuang
dari lampiran. Hasilnya di `catalog-audit.md`.

**Angka tidak diketik.** Tabel Module tiers di `docs/architecture.md` pernah
salah pada lima dari delapan barisnya (`ee_gap` tertulis 78 padahal 105).
Pemeriksaan #12 di `verify.py` membandingkan tabel itu dengan hasil pemindaian
dan gagal bila menyimpang lagi.

## Catatan yang menghemat waktu

- **Playwright tidak bisa di-`import 'playwright'` begitu saja.** Tidak ada
  `node_modules` di repo ini; Playwright hanya ada di cache npx yang nama
  direktorinya adalah hash. `playwright_entry.mjs` menelusuri cache tersebut dan
  menghormati `PLAYWRIGHT_ENTRY`.
- **`mmdc` (mermaid-cli) tidak terpasang** dan tidak ada jaminan jaringan.
  Diagram ditulis sebagai SVG langsung, lalu dirasterisasi ke PNG lewat
  Playwright untuk DOCX — Word tidak andal merender SVG.
- **Paksa `colorScheme: 'light'` pada context *dan* `emulateMedia`.** Menyetel
  salah satu saja membuat blok `prefers-color-scheme: dark` tetap aktif dan
  cetakan keluar terbalik.
- **Aturan `h1 { break-before: page }` juga mengenai judul sampul.** Tanpa
  pengecualian, halaman 1 hanya berisi eyebrow dan judulnya terlempar ke halaman
  2.
- **Jangan paksa 153 entri lampiran utuh satu halaman.** `break-inside: avoid`
  pada entri menghasilkan 173 halaman yang sebagian besar separuh kosong;
  membiarkannya terpotong menghasilkan 145 halaman yang padat.
- **Tabel sembilan kolom prosa tidak muat di A4 portrait.** Register kesenjangan
  dirender sebagai satu blok per butir; tabel lebar yang bisa difilter hidup di
  XLSX, tempat filter memang berguna.
- **File Browser melaporkan `unhealthy` secara keliru** — healthcheck bawaannya
  rusak, aplikasinya sendiri melayani HTTP 200.
