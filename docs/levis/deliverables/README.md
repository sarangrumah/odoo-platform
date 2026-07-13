# Levis client deliverables

| File | Pages | Audience |
|---|---|---|
| `Levis_Functional_Document.pdf` | 42 | Sign-off fungsional: arsitektur, peran, swimlane per proses, dampak jurnal, katalog fitur, konfigurasi. |
| `Levis_Manual_Guide.pdf` | 48 | Pengguna akhir: panduan langkah-demi-langkah per peran, dengan tangkapan layar. |

Bahasa: Indonesia, dengan istilah antarmuka Odoo dipertahankan dalam Bahasa Inggris.

Screenshot diambil dari `prd_levis_begbal` pada 13 Juli 2026. DB itu tidak memiliki Purchase Order
maupun Receipt, sehingga layar Purchase/Receipt/Asset tampil sebagai form kosong.

## Regenerasi

Semua sumber ada di `src/`.

```bash
cd src
npm i playwright@1.61.1 @mermaid-js/mermaid-cli
npx playwright install --with-deps chromium
sudo apt-get install -y poppler-utils pngquant   # pdfunite, pdfinfo, kompresi PNG

# 1. Diagram (Mermaid -> SVG)
for f in dia/*.mmd; do
  npx mmdc -i "$f" -o "svg/$(basename "$f" .mmd).svg" \
    -c mmdc.json -p puppeteer.json -b transparent --width 2200
done

# 2. Screenshot (opsional -- hanya jika perlu tangkapan layar baru).
#    Perlu user Odoo dengan hak admin; lihat catatan di bawah.
node capture.mjs     # layar list & form
node capture2.mjs    # wizard (full page)
node capture3.mjs    # wizard (crop ke modal -- ini yang dipakai di manual)
pngquant --quality=65-92 --speed 1 --force --ext .png shots/*.png

# 3. PDF
node build-pdf.mjs fd.html     ../Levis_Functional_Document.pdf "Functional Document — Levi's / EBR Odoo 19"
node build-pdf.mjs manual.html ../Levis_Manual_Guide.pdf         "Manual Guide — Levi's / EBR Odoo 19"
```

### Catatan yang menghemat waktu

- **Login.** Form login Odoo dibungkus layout *website*, sehingga `button[type=submit]` justru cocok
  dengan tombol pencarian website. Pakai `button:has-text("Log in")`.
- **Wizard laporan** adalah modal (`target=new`). Menekan Escape sebelum screenshot akan menutupnya
  (halaman jadi kosong). Screenshot elemen `.modal-content` langsung — tangkapan satu halaman penuh
  isinya sebagian besar latar abu-abu dan tidak terbaca saat dicetak.
- **Mermaid mengabaikan `direction` di dalam subgraph** bila ada edge yang melintasi batas subgraph.
  Jangan mengandalkannya; beri tiap node dalam satu lapisan edge-nya sendiri ke lapisan berikutnya agar
  lapisan itu jatuh pada satu rank. Periksa rasio `viewBox` hasil render — di luar ~0.7–2.5 akan
  tidak terbaca di halaman A4.
- **Sampul** dicetak terpisah tanpa footer lalu digabung dengan `pdfunite`, supaya halaman sampul
  tidak bernomor.
- `capture*.mjs` memakai user `docbot@levis.local` yang **sudah dihapus** setelah capture selesai.
  Buat ulang user admin sementara bila perlu capture lagi.
