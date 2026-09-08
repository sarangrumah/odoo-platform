---
title: Kepatuhan Data (UU PDP) & Audit
domain: kepatuhan-data-pdp
---

# 12. Kepatuhan Data (UU PDP) & Audit

{{n.domain.kepatuhan-data-pdp}} modul mengimplementasikan kewajiban **UU 27/2022
tentang Pelindungan Data Pribadi**. Domain ini kecil dalam jumlah tetapi
menyentuh hampir seluruh platform: puluhan modul lain mewarisi mixin audit dan
klasifikasinya.

## 12.1 Rantai lapisan

Empat lapisan dibangun berurutan, dan urutannya menentukan:

**Klasifikasi** (`custom_pdp_core`) menyediakan taksonomi: field mana pada model
mana yang merupakan data pribadi, dan pada tingkat sensitivitas apa. Tanpa ini,
tiga lapisan di atasnya tidak punya sesuatu untuk dijaga.

**Audit** (`custom_pdp_audit`) adalah log **append-only berantai-hash**. Setiap
baris menyimpan hash baris sebelumnya, sehingga penghapusan atau penyuntingan di
tengah rantai terdeteksi. Perlindungannya tidak berhenti di tingkat aplikasi:
sebuah trigger PostgreSQL menolak UPDATE dan DELETE pada tabel itu, dan sebuah
cron malam menelusuri rantai serta memberi alert bila ada mata rantai putus.
Modul mana pun dapat ikut dengan mewarisi mixin-nya.

**Consent** (`custom_pdp_consent`) mencatat pemberian dan penarikan persetujuan
per tujuan pemrosesan. Inilah yang dibaca gerbang PDP di kanal pemasaran.

**DSAR** (`custom_pdp_dsar`) menangani permintaan subjek data — akses, koreksi,
penghapusan — sebagai alur kerja dengan tenggat, bukan permintaan email yang
hilang di kotak masuk.

## 12.2 Masking dan retensi

**Masking PII** (`custom_pdp_masking`) menyamarkan data pribadi lewat hook pada
pembacaan ORM, sehingga pengguna tanpa hak melihat data tersamar di layar yang
sama — bukan layar terpisah yang harus dibangun dua kali.

**Retensi** (`custom_pdp_retention`) menjalankan kebijakan penyimpanan dan
otomasi siklus hidup. Ini yang membuat data pelamar kerja tidak tersimpan tanpa
batas, sebuah kewajiban yang paling sering terlewat dalam praktik.

## 12.3 Jangkauan sesungguhnya

Nilai domain ini tidak terletak pada enam modulnya, melainkan pada seberapa jauh
ia menjangkau. Tag `audit-trail` muncul pada 78 manifest dan tag `pdp` pada 37
dari {{n.modules_total}} modul. Artinya jejak audit dan kesadaran data pribadi
bukan fitur yang dinyalakan di satu tempat, melainkan properti yang diwarisi
sebagian besar platform.

> Catatan kematangan: lima dari enam modul PDP dinilai *Beta* karena tidak
> membawa suite pengujian sendiri. Perilaku append-only-nya ditegakkan di tingkat
> basis data lewat trigger, yang berlaku terlepas dari ada tidaknya pengujian di
> tingkat aplikasi.

## 12.4 Daftar modul

{{TABEL_MODUL}}

{{KHUSUS_BRAND}}
