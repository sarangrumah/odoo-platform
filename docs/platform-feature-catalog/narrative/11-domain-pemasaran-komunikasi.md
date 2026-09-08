---
title: Pemasaran & Komunikasi
domain: pemasaran-komunikasi
---

# 11. Pemasaran & Komunikasi

{{n.domain.pemasaran-komunikasi}} modul, seluruhnya berlaku umum. Ciri khas
domain ini: **setiap kanal keluar melewati gerbang persetujuan UU PDP**. Ini
bukan tambahan opsional — mengirim pesan pemasaran ke seseorang yang menarik
persetujuannya adalah pelanggaran, dan platform ini menutup jalurnya di tingkat
kode, bukan prosedur.

## 11.1 WhatsApp

`custom_whatsapp` adalah adapter Meta WhatsApp Cloud API dengan manajemen
template dan **antrean keluar bergerbang PDP**. Ia terintegrasi ke penjualan,
akuntansi, dan helpdesk, sehingga konfirmasi pesanan, pengingat tagihan, dan
pembaruan tiket berjalan lewat kanal yang benar-benar dibaca pelanggan di
Indonesia.

## 11.2 Kanal lain

**SMS Indonesia** (`custom_sms_id`) menyediakan adapter Zenziva untuk penyedia
lokal dan Twilio untuk global. **Email marketing**
(`custom_email_marketing`) menambahkan galeri template, uji A/B, dan mekanisme
berhenti berlangganan yang patuh. **Marketing automation** menjalankan kampanye
multi-langkah, rangkaian drip, dan segmentasi audiens.

**Live chat** (`custom_livechat`) menambahkan eskalasi ke helpdesk, jawaban siap
pakai, skrip chatbot, routing berdasarkan keahlian, dan saran balasan dari AI.
**VoIP** (`custom_voip`) menyediakan click-to-call dan pencatatan panggilan
dengan beberapa adapter SIP/PBX.

## 11.3 Event, survei, dan komunitas

**Manajemen event** (`custom_events`) mengirim tiket lewat WhatsApp dengan kode
QR, menangani check-in QR di lokasi, sponsor, track sesi, survei pasca-acara, dan
daftar tunggu. **Survei** (`custom_survey`) menangani pulse karyawan, NPS
pelanggan, sertifikasi, dan survei yang terhubung ke penilaian kinerja.

**Reservasi janji temu** (`custom_appointments`) menyediakan pemesanan publik
dengan ketersediaan sumber daya. **Forum** (`custom_forum`) menambahkan moderasi
AI, gamifikasi, dan penyamaran identitas penulis sesuai PDP. **Media sosial**
(`custom_social`) mengelola akun dan penjadwalan unggahan.

**Program afiliasi** (`custom_affiliate`) melacak tautan, menangkap klik,
mengatribusikan pesanan, dan menghitung komisi beserta pembayarannya.

## 11.4 Catatan kematangan

Sebagian besar modul di domain ini dinilai *Beta* karena tidak membawa suite
pengujian, bukan karena tidak berfungsi. Empat yang dinilai *Produksi* —
WhatsApp, email marketing, live chat, dan survei — adalah yang paling banyak
dipakai dan karenanya paling banyak diuji.

## 11.5 Daftar modul

{{TABEL_MODUL}}

{{KHUSUS_BRAND}}
