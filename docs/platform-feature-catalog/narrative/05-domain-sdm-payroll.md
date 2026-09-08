---
title: SDM & Payroll
domain: sdm-payroll
---

# 5. SDM & Payroll

{{n.domain.sdm-payroll}} modul, seluruhnya berlaku **umum** — tidak ada satu pun
yang terikat pada satu brand. Domain ini adalah contoh paling murni dari klaim
reuse platform: apa pun brandnya, aturan ketenagakerjaan Indonesia sama.

## 5.1 Payroll Indonesia

`custom_hr_payroll_id` adalah inti domain ini: **PPh 21 dengan skema TER** dan
perhitungan progresif tahunan, **BPJS Kesehatan dan Ketenagakerjaan**, PTKP, THR,
serta **SPT 1721 A1**. Perhitungan pajaknya berbagi registri tarif dengan mesin
pemotongan PPh di domain perpajakan, sehingga tarif tidak dipelihara di dua
tempat.

## 5.2 Kehadiran, cuti, dan waktu

**Absensi** (`custom_attendance`) menyediakan check-in dengan **geofence**, portal
kiosk untuk lokasi tanpa perangkat pribadi, alur persetujuan, dan lembur yang
mengalir langsung ke payroll sebagai komponen upah — bukan sebagai catatan
terpisah yang harus dimasukkan ulang.

**Cuti Indonesia** (`custom_hr_leave_id`) mengikuti UU Cipta Kerja, termasuk cuti
haid, kalender hari libur nasional, dan kebijakan carry-over saldo antar tahun.

**Perencanaan shift** (`custom_planning`) menutup penjadwalan sumber daya untuk
tim yang bekerja bergilir.

## 5.3 Biaya, rekrutmen, dan pengembangan

**Klaim biaya** (`custom_expenses`) memakai OCR berbantuan AI untuk membaca struk,
mendukung kartu korporat dan klaim kilometer, dan berjalan di atas mesin
persetujuan bersama.

**Rekrutmen** (`custom_recruitment_id`) menerima lamaran dari job board lewat
webhook, dengan retensi data pelamar yang sadar UU PDP — sebuah kewajiban yang
sering terlewat, karena berkas lamaran adalah data pribadi yang tidak boleh
disimpan tanpa batas.

Melengkapinya: **program referral** dengan buku besar imbalan, **penilaian
kinerja** dengan template dan umpan balik 360 derajat, serta **pembelajaran
daring** dengan sertifikat berbahasa Indonesia dan kohort peserta.

## 5.4 Fasilitas dan operasional kantor

Tiga modul menangani hal-hal yang bukan HR inti tetapi jatuh ke meja HR:
**armada kendaraan** dengan pengingat STNK dan KIR serta pencatatan BBM,
**katering** dengan tautan ke layanan pesan-antar dan potongan payroll yang
benar-benar terbukukan, dan **manajemen tamu** di lobi dengan notifikasi ke host.

## 5.5 Identitas

`custom_hr_sso_keycloak` menghubungkan login karyawan ke Keycloak dan
menyinkronkan data `hr.employee` dari klaim token serta HC API. Ia bekerja
berpasangan dengan `authenticate_keycloak` di domain Integrasi, yang menyediakan
alur OAuth2-nya.

## 5.6 Daftar modul

{{TABEL_MODUL}}

{{KHUSUS_BRAND}}
