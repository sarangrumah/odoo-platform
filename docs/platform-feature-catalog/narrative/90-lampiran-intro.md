---
title: Lampiran — Rincian Teknis per Modul
---

# Lampiran — Rincian Teknis per Modul

Bagian ini ditulis dalam **Bahasa Inggris**, ditujukan untuk tim pengembang dan
arsitek. Isinya adalah satu entri untuk setiap dari {{n.modules_total}} modul,
diurutkan menurut domain fungsional yang sama dengan badan dokumen.

Cara membaca entri:

- **Path, Version, Depends** diambil langsung dari `__manifest__.py`.
- **Scope** memakai tiga tingkat yang dijelaskan di Bab 2.
- **Maturity / confidence** — kematangan diturunkan dari kode; keyakinan
  menyatakan seberapa dipercaya deskripsi di bawahnya, bukan kualitas modulnya.
- **Models / routes / tests** dihitung dengan analisis statis. Modul yang
  seluruhnya berupa controller sah bernilai nol model.
- Sebuah **catatan** muncul di atas deskripsi bila dokumen pengetahuan modul
  belum diperiksa manusia, atau bila ia ditulis terhadap versi manifest yang
  lebih lama. Perlakukan entri semacam itu sebagai indeks, bukan spesifikasi.

Prosa di setiap entri berasal dari tiga sumber, dengan urutan prioritas:
override yang ditulis tangan untuk katalog ini, lalu `MODULE_KNOWLEDGE.md` di
dalam modul, lalu ringkasan otomatis dari manifest. Setiap klaim sudah melewati
gerbang audit yang membandingkannya dengan kode; model yang disebut tetapi tidak
ditemukan di mana pun menyebabkan daftar model entri itu dibuang dan
keyakinannya diturunkan.

{{LAMPIRAN}}
