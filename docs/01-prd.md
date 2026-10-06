# PRD — Migrasi dashboard log SIMPEL4 (v2)

Dokumen kebutuhan produk untuk memindahkan dashboard log SIMPEL4 dari satu file HTML hasil build ke
aplikasi kecil (ingest sekali per hari, data diambil per tab). Ditulis untuk pembaca yang belum melihat
kodenya. Rincian sistem lama ada di [`00-inventaris.md`](00-inventaris.md); nomor seperti "inv. §2.4"
merujuk ke sana. Keputusan teknis (skema, endpoint, struktur kode) sengaja tidak dibuat di sini; itu bagian TRD.

Yang ditandai **ASUMSI** adalah keputusan yang saya ambil tanpa konfirmasi pemilik produk, dipilih yang
paling aman dan paling mudah dibatalkan. Semua asumsi dirangkum di [§9](#9-daftar-asumsi) dan pertanyaan
untuk pemilik produk di [§10](#10-pertanyaan-terbuka-untuk-pemilik-produk).

> **Revisi 2026-10-06 (Tahap 1 rencana).** Pemilik produk sudah menjawab sebagian pertanyaan. Dokumen ini
> diselaraskan dengan jawaban itu dan dengan [`03-trd.md`](03-trd.md). Butir yang berubah ditandai
> **[Diputuskan]**, **[Gugur]**, atau **[Baru]**.

| Keputusan pemilik | Isi |
|---|---|
| "Hari" | Tetap **per folder ekspor** (P2). |
| Akses | Dashboard dibuka dari **banyak komputer** (P3), lewat HTTPS, **wajib login**. |
| Peran | Untuk sementara dua peran: **admin** dan **user**. User melihat seluruh dashboard; admin juga menambah dan mengelola user. Pembatasan per modul **ditunda** (P1). |
| Akun | **Lokal** di basis data aplikasi; bukan SSO. |
| Definisi yang janggal | **Diperbaiki** sesuai praktik yang baik (P4); rinciannya di TRD §4.4. |
| Impor otomatis | Dari awalan S3, mis. `s3://simpel4-backup/k8s-logs/2026-09-26/`, dengan kunci akses tetap yang baca-saja, wilayah Jakarta. |
| Tampilan ponsel | Dikerjakan **serius**. |

Istilah:

| Istilah | Arti |
|---|---|
| Folder log | Satu folder bernama tanggal (mis. `2026-10-06`) berisi ekspor log semua layanan. Isinya log hari **sebelumnya** dalam WIB (inv. §8 butir 1). |
| Layanan | Sumber log: ingress nginx, om-fe-inhouse, om-be-simpel-loop, om-be-appsmanager, om-be-referensi, om-be-report, coredns. |
| Ingest | Proses membaca file log dan menyimpannya dalam bentuk yang siap ditampilkan. |
| Sistem lama | `build_dashboard.py` + `dashboard_template.html` → `dashboard.html`. |
| Angka acuan | Angka dari sistem lama untuk tiap folder, di `00-acuan.json` (inv. §7). |

---

## 1. Latar belakang dan masalah

Tim SIMPEL4 (Ombudsman RI) menerima ekspor log harian dari klaster dan membacanya lewat satu file
`dashboard.html`. Dashboard itu berguna: dalam satu tempat terlihat kesehatan layanan, indikasi serangan,
aktivitas pelaporan, dan asal pengguna. Cara pembuatannya yang tidak akan bertahan.

### 1.1 Masalah yang mau diselesaikan

| # | Masalah | Bukti dari sistem lama |
|--:|---|---|
| M1 | **Semua log di-parse ulang setiap build.** Waktu build tumbuh seiring jumlah folder. | 11 folder (774 ribu baris) = 14 detik. Pada volume hari penuh (±360 ribu baris/hari) setahun = ±131 juta baris, kira-kira 40 menit per build. |
| M2 | **Semua data semua hari dimuat sekaligus ke browser.** | `dashboard.html` 2,3 MB untuk 11 folder; satu folder penuh menambah ±200 KB. Setahun berarti puluhan MB dalam satu halaman. |
| M3 | **Detail dibuang saat build.** Agar file tidak membengkak, hampir semua daftar dipotong (top 15–300). Beberapa KPI lalu dihitung dari daftar yang sudah terpotong sehingga **angkanya salah**. | "Error koneksi ke pod" tampil 200, sebenarnya 1.200 (folder 09-30). Daftar klien 401 dipotong 30 dari 653. Filter teks hanya mencari di baris yang tersisa. (inv. §5.2, §8 butir 6) |
| M4 | **Kode tampilan satu file 1.900 baris.** Sembilan tab, tujuh jenis halaman layanan, dua bahasa, dan peta bercampur; mengubah satu tab berisiko merusak yang lain. | inv. §2 |
| M5 | **Tidak bisa melihat lintas hari selain di tab Tren.** Analisis akun, insiden, dan pelacakan terputus di batas folder. | inv. §8 butir 12 |
| M6 | **Tidak sepenuhnya mandiri dan tidak terkendali aksesnya.** Butuh CDN untuk chart dan font; file HTML memuat email akun dan IP klien dan bisa disalin ke mana saja. | inv. §8 butir 18–19 |

### 1.2 Yang sengaja tidak disentuh

- **Cara log diekspor dari klaster** dan struktur foldernya. v2 membaca folder yang sama apa adanya.
- **Format log aplikasi.** Simpel-loop dan coredns tetap tanpa cap waktu (inv. §8 butir 4); menambahkannya
  adalah pekerjaan tim aplikasi, bukan migrasi ini.
- **Aturan deteksi.** Signature serangan, aturan analisis akun, pengelompokan insiden, normalisasi pesan,
  dan pemetaan endpoint → metrik bisnis dipindahkan apa adanya (inv. §4). Deteksi tetap berbasis pola
  sederhana, bukan pengganti WAF. **[Diputuskan]** Pengecualian: definisi metrik yang salah atau janggal
  diperbaiki; daftarnya tertutup, di TRD §4.4. Aturan deteksi serangan diganti OWASP CRS pada tahap
  terakhir (B15), setelah kesetaraan dengan aturan lama terbukti.
- **Isi dan susunan tab analisis.** Tidak ada tab analisis baru dan tidak ada yang dihapus. (Layar masuk
  dan layar admin adalah tambahan di luar tab analisis.)
- **Sistem lama dan folder log.** Tetap ada dan tetap bisa dijalankan, sebagai pembanding.
- **Peringatan real-time, notifikasi, dan integrasi** ke sistem lain.

---

## 2. Tujuan

1. Isi dashboard sama dengan yang lama untuk folder yang sama, dan itu bisa dibuktikan dengan angka;
   yang berbeda hanya perbaikan yang terdaftar.
2. Menambah satu folder log baru tidak mengulang pekerjaan untuk folder lama.
3. Membuka dashboard tetap cepat ketika data sudah setahun.
4. Satu tab bisa diubah tanpa menyentuh tab lain.
5. Privasi tidak mundur: IP pengguna tetap tidak pernah dikirim ke pihak ketiga.
6. **[Baru]** Bisa dibuka dari banyak komputer dengan aman: hanya orang yang punya akun yang melihat data.
7. **[Baru]** Folder log baru bisa masuk tanpa menyalin berkas dengan tangan (impor dari S3).

Bukan tujuan: menambah analisis baru, mengganti alat pemantauan (Uptime-Kuma, Rancher), atau menjadi SIEM.

---

## 3. Pengguna dan kebutuhannya

Sistem lama tidak mencatat siapa penggunanya. Tiga peran di bawah **disimpulkan dari isi tab**, jadi
tabel peran pekerjaan ini berstatus **ASUMSI**. Yang sudah diputuskan pemilik adalah peran akses, di bawah tabel.

| Peran (ASUMSI) | Pertanyaan yang ingin dijawab | Tab yang dipakai | Yang paling penting bagi mereka |
|---|---|---|---|
| **Operasional / DevOps** — menjaga layanan tetap hidup | Ada gangguan kemarin? Layanan dan pod mana? Apa penyebabnya? Endpoint mana yang lambat? Log hari ini lengkap? | Overview, Ketersediaan, Pod, Akar Masalah, Pelacakan Request, halaman layanan, Tren | Angka error dan 5xx yang benar; bisa menelusuri dari gejala ke baris log asli; tahu kalau data tidak lengkap |
| **Keamanan** — memantau percobaan serangan dan penyalahgunaan akun | Siapa yang memindai kita dan dari jaringan mana? Ada serangan yang "berhasil" (2xx)? Ada akun yang kemungkinan dibobol? | Keamanan, Peta IP, halaman ingress nginx | Daftar lengkap (bukan hanya top-N) yang bisa dicari; pemilik jaringan dan lokasi IP; tidak ada IP yang bocor ke luar |
| **Pemilik produk / manajemen layanan** — memantau pemakaian SIMPEL4 | Berapa laporan dibuat? OTP dan email berjalan? Pengguna datang dari mana? Naik atau turun dibanding kemarin? | Bisnis, Tren, Peta IP, Overview | Angka ringkas dengan perbandingan; tampilan yang bisa dibaca tanpa paham log; bahasa Indonesia |
| **Pengembang aplikasi** (sekunder) — memperbaiki bug yang terlihat di log | Error apa yang paling sering di layanan saya? Request mana yang gagal dan dari siapa? | Halaman layanan, Pelacakan Request, Akar Masalah | Pesan error terkelompok dengan contoh baris asli; URL lengkap |
| **Perawat dashboard** (sekunder) — yang menjalankan dan mengubah dashboard ini | Bagaimana memasukkan folder baru? Bagaimana menambah satu kartu? | — | Satu perintah untuk menjalankan; ingest yang aman diulang; kode per tab |

**[Diputuskan]** Peran **akses** (berbeda dari peran pekerjaan di atas) hanya dua untuk sementara:

| Peran akses | Bisa |
|---|---|
| **user** | Melihat seluruh dashboard (semua tab, semua layanan, semua folder); mengganti sandinya sendiri |
| **admin** | Semua itu, ditambah: menambah, mengubah, menonaktifkan, menghapus user; mereset sandi; memicu ingest dan impor; melihat catatan audit |

Siapa pun dari lima peran pekerjaan di atas bisa diberi salah satu peran akses. Membatasi user ke halaman
tertentu ditunda (T03).

Kebutuhan bersama, terlihat dari desain lama dan dipertahankan: dua bahasa (ID/EN), dua tema, semua waktu
dalam WIB, bisa dibaca di layar kecil, dan tautan langsung ke tab tertentu.

---

## 4. Fitur dan prioritas

- **P0 — wajib setara**: harus ada saat v2 dinyatakan menggantikan yang lama.
- **P1 — perbaikan**: dimungkinkan oleh arsitektur baru; dikerjakan bila tidak mengganggu P0.
- **P2 — ditunda**: dicatat agar tidak hilang, tidak dikerjakan di migrasi ini.

### 4.1 P0 — wajib setara dengan sistem lama

| ID | Fitur | Acuan |
|---|---|---|
| F01 | **Ingest** tujuh layanan dengan aturan parse yang sama, termasuk baris yang diabaikan dan file `.log.gz` yang hanya dibaca bila `.log` tidak ada | inv. §1.1, §3 |
| F02 | **Kerangka**: sidebar dua grup (Analisis, Layanan) dengan lencana, pemilih folder (bawaan folder terbaru), judul dan subjudul, tautan langsung ke tab | inv. §2.0 |
| F03 | **Dua bahasa** ID/EN untuk seluruh teks antarmuka, termasuk kalimat temuan otomatis, format angka, tanggal, dan nama negara; pilihan diingat | inv. §2.0 |
| F04 | **Dua tema** gelap/terang, termasuk warna chart dan peta; pilihan diingat | inv. §2.0 |
| F05 | **Tab Overview** lengkap, termasuk bagian "Traffic HTTP seluruh sistem" | inv. §2.1 |
| F06 | **Tab Peta IP**: filter modul, 6 KPI, peta dengan titik lokasi, busur ke server, label wilayah bertingkat, preset Indonesia/Dunia, zoom dan geser, legenda, tabel alur, catatan atribusi | inv. §2.2 |
| F07 | **Tab Tren** lintas folder: 6 chart, tabel perubahan, tabel kelengkapan data | inv. §2.3 |
| F08 | **Tab Keamanan**: 8 KPI, "Temuan utama" (9 aturan), 6 chart, 5 tabel, tag keparahan | inv. §2.4 |
| F09 | **Tab Akar Masalah**: ringkasan (5 aturan), 4 chart, 3 tabel | inv. §2.5 |
| F10 | **Tab Ketersediaan**: 7 KPI, 3 chart, 4 tabel | inv. §2.6 |
| F11 | **Tab Pod**: 5 KPI, 2 chart, 3 tabel | inv. §2.7 |
| F12 | **Tab Bisnis**: 11 KPI dengan perbandingan, 5 chart, 2 tabel | inv. §2.8 |
| F13 | **Tab Pelacakan Request**: 6 KPI, 2 chart, tabel jejak | inv. §2.9 |
| F14 | **Halaman layanan** untuk tiap layanan: KPI, peta modul, dan 19 kartu sesuai jenis layanan | inv. §2.10 |
| F15 | **Logika turunan** dengan hasil yang sama: klasifikasi serangan, analisis akun, insiden 5xx, korelasi request id, alur IP → pod, retry, persentil endpoint, 401 berulang, metrik bisnis, JWT, PDF report, restart | inv. §4 |
| F16 | **Pemilik dan lokasi IP secara offline** dari database yang diunduh; tag "Jaringan Ombudsman"; "Jaringan Internal" untuk IP privat | inv. §4.6 |
| F17 | **Perbandingan dengan folder sebelumnya** (▲/▼, "tidak lengkap, tidak dibandingkan") dengan aturan kesebandingan yang sama | inv. §2.0 |
| F18 | **Filter teks** pada tabel yang sekarang punya filter | inv. §2.0 |
| F19 | **Pesan error terkelompok** dengan contoh baris log asli (waktu UTC) | inv. §2.10, §4.7 |
| F20 | **Keadaan kosong** yang menjelaskan sebabnya (tanpa nginx, tanpa korelasi, file kosong) | inv. §2 |
| F21 | **Tampilan layar kecil**: navigasi pindah ke atas, tabel bisa digulir | inv. §2.0 |
| F22 | **Atribusi** sumber lokasi IP dan GeoNames tetap tampil. **[Diputuskan]** Sumber lokasi diganti dari DB-IP ke **MaxMind GeoLite2** (tetap dicocokkan di server sendiri), jadi atribusinya menjadi MaxMind | inv. §6; TRD §3.6 |
| F23 | **Format tampilan** angka, waktu WIB, durasi, dan rentang waktu sama | inv. §2.0 |

**[Baru] P0 dari keputusan pemilik** (tidak ada di sistem lama; wajib ada saat serah terima):

| ID | Fitur | Rincian |
|---|---|---|
| N01 | **Login**: nama user + sandi; sesi berakhir sendiri setelah tidak aktif; keluar | TRD §8.2 |
| N02 | **Dua peran**, admin dan user, ditegakkan di server | TRD §8.3 |
| N03 | **Kelola user** oleh admin: tambah, ubah peran, reset sandi, nonaktifkan, hapus. Tanpa pendaftaran sendiri; sandi awal wajib diganti | TRD §5.6, §8.4 |
| N04 | **Catatan audit**: masuk, perubahan user, ingest, impor | TRD §8.2 |
| N05 | **Akses dari banyak komputer** lewat HTTPS | TRD §7 |
| N06 | **Tampilan ponsel yang serius**: navigasi laci, tabel lebar menjadi kartu baris, target sentuh memadai | DRD §8 |

Semua ambang yang terlihat pengguna dipertahankan: lambat ≥ 1 detik dan ≥ 5 detik, error rate minimal 20
request, kinerja minimal 5 request, jeda insiden 5 menit, jendela login 60 menit, multi-akun ≥ 3
(inv. §5.4).

### 4.2 P1 — perbaikan yang dimungkinkan arsitektur baru

| ID | Perbaikan | Masalah | Catatan |
|---|---|---|---|
| B01 | **Ingest bertahap**: folder yang sudah masuk dan tidak berubah dilewati; folder yang berubah diganti seluruhnya | M1 | Inti migrasi; diperlakukan seperti P0 |
| B02 | **Data diambil per tab dan per folder**, bukan sekaligus | M2 | Inti migrasi; diperlakukan seperti P0 |
| B03 | **KPI dihitung dari data lengkap**, bukan dari daftar terpotong | M3 | **[Diputuskan]** (P4). Selisih terhadap sistem lama dicatat sebagai "selisih yang diharapkan" (§6.2) |
| B04 | **Tabel tidak lagi terpotong diam-diam**: tampilan awal tetap top-N seperti sekarang, tetapi sisanya bisa dibuka, dan filter teks mencari di seluruh data | M3 | Batas tampilan awal = batas lama (inv. §5.2) |
| B05 | **File rusak ditandai** di tab Pod, Overview, dan tabel Kelengkapan Data, terpisah dari "kosong" | inv. §8 butir 3 | Jumlah baris tetap dihitung seperti lama agar angka setara |
| B06 | **Label folder yang jujur**: tampilkan rentang waktu log sebenarnya di samping nama folder | inv. §8 butir 1–2 | Tidak mengubah pengelompokan (lihat A1) |
| B07 | **"Refresh token kedaluwarsa" ditampilkan** di Akar Masalah | inv. §8 butir 15 | Sudah dihitung, tinggal ditampilkan |
| B08 | **Atribusi di setiap tempat lokasi tampil**, termasuk peta di halaman layanan | inv. §8 butir 17 | |
| B09 | **Tanpa ketergantungan CDN**: chart, font, dan peta berjalan tanpa internet | M6 | **ASUMSI A4** |
| B10 | **Label "Pod dengan retry 502"** diperbaiki menjadi sesuai isinya | inv. §8 butir 13 | Hanya teks |
| B11 | **Nilai tulis-mati jadi konfigurasi**: IP server, daftar host, DNS upstream | inv. §8 butir 20 | Nilai bawaan = nilai sekarang |
| B12 | **Kode tampilan terpisah per tab** | M4 | Tidak terlihat pengguna; syarat perawatan |
| B13 | **[Baru] Definisi janggal diperbaiki**: chart error per jam nginx/frontend memuat juga baris error log; `crit` = error di kedua layanan; donat level simpel-loop memakai tingkat efektif; "lambat ≥ 5 dtk" memuat 3xx | inv. §8 butir 7–9, 14 | **[Diputuskan]** (P4). Daftar tertutup di TRD §4.4; angka inti tidak berubah |
| B14 | **[Baru] Impor folder log dari S3**: admin atau sistem mengirim tautan `s3://simpel4-backup/k8s-logs/<tanggal>/`; dashboard mengunduh lalu meng-ingest | tujuan 7 | **[Diputuskan]**. Dikerjakan setelah kesetaraan terbukti. Hanya bucket dan awalan di daftar izin (TRD §3.8) |
| B15 | **[Baru] Deteksi serangan dengan OWASP CRS, kategori bernama CAPEC**: menggantikan tujuh pola tulis-tangan sistem lama; tiap temuan menyebut ID aturan | inv. §5.1 (deteksi sederhana) | **[Diputuskan]** permintaan pemilik. Dikerjakan paling akhir, setelah kesetaraan terbukti, karena mengubah semua angka tab Keamanan. Cara: mencocokkan pola CRS ke URL dan User-Agent di log; pemeriksaan body/header/cookie butuh CRS di ingress (di luar proyek ini) |

### 4.3 P2 — ditunda

| ID | Hal | Mengapa ditunda |
|---|---|---|
| T01 | ~~Tampilan per tanggal kalender WIB~~ | **[Gugur]** Diputuskan per folder (P2); tidak direncanakan |
| T02 | Analisis akun, insiden, dan pelacakan **lintas folder** | Sama: mengubah angka |
| T03 | **Pembatasan per modul**: membatasi user ke halaman tertentu. Juga SSO dan autentikasi dua faktor | **[Diputuskan]** Login dua peran sudah masuk cakupan (N01–N04); pembatasan per modul ditunda atas keputusan pemilik; penambahannya terlokalisasi (TRD §8.3) |
| T04 | Memantau folder dan ingest otomatis saat berkas muncul (pengganti `--watch`) | Kebutuhan otomatisasi dijawab impor S3 (B14) dan ingest terjadwal; pemantau berkas tidak perlu |
| T05 | Sisa definisi yang **tidak** diubah: baris `EXC` tetap tidak menambah Error (mencegah hitung ganda) | **[Diputuskan]** Sebagian besar T05 lama dikerjakan sekarang (B13); butir ini sengaja dibiarkan (TRD §4.4 butir 5) |
| T06 | Ekspor tabel (CSV), menyimpan tautan dengan filter | Belum diminta |
| T07 | Lokasi dan pemilik untuk IPv6 | Sistem lama juga tidak punya |
| T08 | Cap waktu untuk simpel-loop dan coredns | Butuh perubahan di aplikasi sumber |
| T09 | Retensi otomatis (hapus data lebih tua dari N bulan) | Belum perlu sebelum data setahun. Catatan (TRD §3.2): folder log yang hilang dari disk **tidak** menghapus datanya dari dashboard; penghapusan hanya lewat perintah admin |

---

## 5. Kebutuhan non-fungsional

Angka diukur di laptop pengembang yang sama dengan pengukuran acuan (build lama 14,2 detik untuk 11
folder), dengan data setahun disimulasikan dari folder terbesar (`2026-09-29`: 359 ribu baris, 131 MB).

### 5.1 Kecepatan tampilan

| Ukuran | Target |
|---|---|
| Membuka dashboard sampai Overview folder terbaru terbaca | ≤ 2 detik |
| Pindah tab atau ganti folder sampai isi tampil | ≤ 1 detik (persentil 95) |
| Tab Tren dengan data 365 folder | ≤ 2 detik |
| Mengetik di filter tabel sampai hasil berubah | ≤ 0,5 detik |
| Data yang diunduh untuk membuka satu tab | ≤ 500 KB, **tidak bertambah** dengan jumlah folder (kecuali Tren) |

### 5.2 Ingest

| Ukuran | Target |
|---|---|
| Ingest satu folder sebesar `2026-09-29` | ≤ 60 detik |
| Menjalankan ingest ketika tidak ada folder baru | ≤ 5 detik |
| Ingest ulang folder yang sama | Hasil identik, tidak menggandakan data |
| Satu file rusak | Dicatat dan dilewati; file lain tetap masuk; ingest tidak berhenti |
| Ingest awal semua folder yang ada (11) | ≤ 3 menit |

### 5.3 Ukuran data

| Ukuran | Target |
|---|---|
| Volume yang direncanakan | 365 folder × ±360 ribu baris = ±131 juta baris/tahun; log mentah ±47 GB/tahun |
| Penyimpanan dashboard untuk setahun | ≤ 10 GB (**ASUMSI A8**; angka pastinya bergantung keputusan TRD tentang seberapa rinci data disimpan) |
| Database lokasi dan pemilik IP | ±100 MB, seperti sekarang |
| Kecepatan tampilan §5.1 | Tetap terpenuhi pada data setahun |

Log mentah tidak dipindahkan atau dihapus oleh v2.

### 5.4 Privasi

1. **IP pengguna tidak pernah dikirim ke layanan pihak ketiga**, baik saat ingest maupun saat dashboard
   dibuka. Lokasi dan pemilik dicocokkan dari database yang diunduh (inv. §6).
2. Unduhan database itu hanya mengambil file utuh; tidak ada IP yang disertakan dalam permintaan.
3. Browser pembuka dashboard tidak memanggil domain luar (ASUMSI A4). Ini termasuk peta: tidak boleh
   bergantung pada layanan peta daring.
4. **[Diputuskan]** Dashboard memuat data pribadi (email akun, IP klien, contoh baris log). Ia dibuka dari
   banyak komputer, jadi **semua akses lewat HTTPS dan butuh login**; tanpa sesi tidak ada data yang keluar.
   Sandi disimpan sebagai hash; tindakan admin dicatat.
5. Lokasi tetap diperlakukan sebagai perkiraan tingkat kota dan pemilik sebagai pemilik jaringan, bukan
   identitas orang; teks penjelasnya dipertahankan.
6. **[Baru]** Kredensial AWS untuk impor hanya ada di konfigurasi server; tidak pernah dikirim ke browser,
   tidak ditulis ke log atau basis data. Dashboard hanya membaca dari bucket dan awalan yang diizinkan.

### 5.5 Cara menjalankan

- **Lokal: satu perintah** dari folder proyek untuk: menyiapkan kebutuhan, meng-ingest folder yang belum
  masuk, lalu membuka dashboard di browser lokal. Pada jalan pertama perintah itu meminta nama dan sandi
  admin pertama.
- **[Diputuskan] Server: satu perintah** `docker compose up -d` (langkah 7); ingest harian lewat tugas
  terjadwal atau impor S3.
- Menjalankan perintah yang sama keesokan harinya, setelah folder baru disalin, cukup untuk memperbarui.
- Jalan lokal: tanpa layanan yang harus dipasang terpisah (akun memakai berkas SQLite). **Server**: akun disimpan
  di PostgreSQL, yang ikut dijalankan oleh `docker compose` yang sama (keputusan pemilik 2026-10-06; TRD K11).
- Tanpa internet tetap berjalan, asalkan database lokasi/pemilik IP sudah pernah diunduh; bila belum,
  dashboard tetap tampil tanpa lokasi dan pemilik, dengan keterangan.
- Petunjuk menjalankan muat dalam satu halaman README.

### 5.6 Perawatan

- Menambah atau mengubah satu kartu hanya menyentuh kode tab itu dan data yang dibutuhkannya.
- Aturan parse dan logika turunan punya uji otomatis terhadap contoh baris asli (inv. §3).
- Uji kesetaraan (§6.2) bisa dijalankan ulang dengan satu perintah setiap ada folder baru.

---

## 6. Kriteria sukses

### 6.1 Kelengkapan

- Setiap baris tabel di inv. §2.1–§2.10 (KPI, chart, tabel, catatan, filter, keadaan kosong) ada di v2,
  diperiksa satu per satu. Target: **100 %**, tanpa pengecualian yang tidak tertulis.
- Setiap teks antarmuka punya versi ID dan EN; tidak ada teks Indonesia yang tertinggal saat EN dipilih.
- Kedua tema terbaca di semua tab, termasuk chart dan peta.

### 6.2 Kesetaraan angka dengan sistem lama

Dibandingkan per folder dan per layanan terhadap `00-acuan.json`, yang dihasilkan ulang dari sistem lama
pada isi folder yang sama.

| Kelompok | Angka | Syarat |
|---|---|---|
| Inti | baris, request, 4xx, 5xx, error, warning, IP unik, alur IP | **sama persis** untuk semua 11 folder × semua layanan |
| Per fitur | request serangan dan per kategori, URL serangan, IP penyerang, IP ber-4xx, klien 401, total 5xx per upstream, insiden, pod backend, retry, error koneksi pod, Uptime-Kuma, event simpel-loop, jumlah korelasi, request lambat, metrik bisnis, email notifikasi, aktivitas, restart, kelompok JWT, PDF sukses/gagal, login gagal/reset/sukses, akun dianalisis | **sama persis** |
| Isi daftar | Untuk tiap tabel top-N: N baris pertama v2 = baris sistem lama (kunci dan nilai) | sama; urutan boleh berbeda hanya di antara baris bernilai sama |
| Persentil | P50, P95, P99, maksimum per endpoint | sama sampai pembulatan tampilan |
| Lokasi dan pemilik IP | negara, kota, ASN untuk IP yang sama | sama bila memakai file database yang sama |

**[Diputuskan] Selisih yang diharapkan** (akibat B03 dan B13) dicatat di laporan kesetaraan dengan nilai
lama, nilai baru, dan alasannya. Daftarnya tertutup: butir 1, 2, 3, 4, dan 9 di TRD §4.4. Selisih di luar
daftar itu = kegagalan. Angka inti (baris pertama tabel di atas) tidak termasuk daftar selisih.

### 6.3 Kinerja dan operasi

- Semua target §5.1–§5.3 terpenuhi dan terukur, pada data 11 folder nyata dan pada simulasi 365 folder.
- Menambah folder ke-12 tidak mengubah angka folder 1–11 (kecuali angka korelasi request id, yang seperti
  di sistem lama bisa berubah bila request yang sama muncul di dua folder; TRD §3.5) dan selesai dalam
  batas §5.2.
- Dashboard terbuka dan berfungsi penuh dengan jaringan dimatikan.
- Pemeriksaan lalu lintas jaringan saat ingest dan saat dashboard dipakai: tidak ada IP dari log yang keluar.
- Orang yang belum pernah melihat proyek ini bisa menjalankannya dari README dalam ≤ 10 menit.
- **[Baru]** Tanpa sesi, setiap alamat data menjawab "belum masuk"; user biasa tidak bisa memanggil fungsi
  admin; enam kali sandi salah mengunci percobaan; admin terakhir tidak bisa dihapus.
- **[Baru]** Di ponsel sungguhan (lebar 360–390 px): masuk, ganti folder, membuka tiap halaman, dan membaca
  tiap tabel bisa dilakukan tanpa menggulir halaman ke samping.
- **[Baru]** Impor S3: tautan ke bucket atau awalan di luar daftar izin ditolak sebelum AWS dihubungi;
  mengirim tautan yang sama dua kali tidak menggandakan data.

### 6.4 Serah terima

v2 dinyatakan menggantikan sistem lama bila §6.1–§6.3 terpenuhi dan pemilik produk menyetujui daftar
selisih yang diharapkan. Sistem lama tidak dihapus.

---

## 7. Di luar cakupan

- Mengubah ekspor log, format log aplikasi, atau konfigurasi klaster.
- Analisis atau tab baru; perubahan aturan deteksi serangan.
- Peringatan, notifikasi, laporan terjadwal.
- **[Diputuskan]** Pembatasan per modul, SSO, autentikasi dua faktor, pendaftaran sendiri, dan "lupa
  sandi" lewat email (T03). Login dua peran dan audit **masuk** cakupan.
- Menjalankan di klaster Kubernetes. Deploy di satu server lewat Docker Compose **masuk** cakupan (langkah 7).
- Folder `recovery-file/` dan `recovery-file.zip` (bukan bagian dashboard; inv. §8 butir 22).
- Memperbaiki masalah yang ditemukan dashboard (401 berulang, template PDF hilang, DNS timeout).

---

## 8. Risiko

| # | Risiko | Dampak | Penanganan |
|--:|---|---|---|
| R1 | ~~Arti "hari" diubah di tengah jalan~~ | — | **[Gugur]** Diputuskan per folder (P2) |
| R2 | **Kesetaraan tidak tercapai karena perilaku tersembunyi** sistem lama (pemotongan teks, urutan saat nilai sama, korelasi lintas folder, pembulatan) | Migrasi tidak bisa dibuktikan | Inventaris §4–§5 sebagai spesifikasi; uji per aturan dengan baris asli; bandingkan sejak tahap pertama, bukan di akhir |
| R3 | **Angka acuan basi** karena folder log bertambah | Perbandingan salah | Acuan selalu dibuat ulang tepat sebelum membandingkan |
| R4 | **Data tumbuh lebih cepat dari perkiraan** (volume naik, atau disimpan terlalu rinci) | Target ukuran dan kecepatan meleset | Uji dengan simulasi setahun sebelum kode tampilan ditulis; T09 sebagai cadangan |
| R5 | **Peta**: pustaka peta baru biasanya memakai layanan peta daring | Melanggar §5.4 butir 3, atau peta kosong tanpa internet | Syarat "tanpa layanan peta daring" masuk TRD; pakai data daratan dan label yang sama dengan sekarang |
| R6 | **Lisensi dan atribusi** data IP tidak dipenuhi | Risiko hukum kecil, mudah dicegah | B08; cek lisensi ip2asn (P6) |
| R7 | **Data pribadi lebih mudah diakses** begitu dashboard menjadi layanan yang dibuka banyak komputer | Kebocoran email akun dan IP | **[Diputuskan]** HTTPS + login + dua peran + audit (N01–N05); port aplikasi tidak dibuka langsung ke jaringan |
| R8 | **File log rusak atau format berubah** tanpa pemberitahuan (sudah terjadi: 3 dari 11 folder praktis kosong) | Hari terlihat "sepi" padahal datanya hilang | B05, B06; tabel Kelengkapan Data dipertahankan |
| R9 | **Cakupan melebar**: perbaikan P1 dan P2 dikerjakan sebelum P0 terbukti setara | Migrasi molor, sulit dibandingkan | Urutan: P0 + B01–B03 → uji kesetaraan → sisa P1 |
| R10 | **Dua sistem berjalan bersamaan terlalu lama** | Kebingungan angka mana yang benar | Kriteria serah terima §6.4 yang jelas |
| R11 | **[Baru] Akun dan sandi dikelola sendiri** | Sandi lemah, akun bekas pegawai tetap aktif, admin tunggal lupa sandi | Sandi minimal 12 karakter dan wajib diganti saat masuk pertama; nonaktifkan user; perintah server untuk membuat admin baru; catatan audit |
| R12 | **[Baru] Kunci AWS untuk impor luas**: baca-saja, tetapi bisa melihat semua bucket di wilayah Jakarta | Bila server bocor, isi bucket lain ikut terbaca | Daftar izin bucket dan awalan di aplikasi, tidak bisa diubah dari layar; saran: kunci khusus yang hanya membaca `simpel4-backup/k8s-logs/` |
| R13 | **[Baru] Server belum diketahui keadaannya** (proxy/HTTPS, akses keluar, disk, memori) | Deploy tertunda; impor S3 atau unduhan database IP gagal | Diperiksa dengan perintah saat deploy; tanpa akses keluar dashboard tetap jalan dari folder log yang dipasang |

---

## 9. Daftar asumsi

Semua bisa dibatalkan tanpa membuang pekerjaan besar; kolom terakhir menjelaskan biayanya.

| # | ASUMSI | Alasan memilih ini | Bila ternyata salah |
|--:|---|---|---|
| A1 | **[Diputuskan]** "Hari" = **folder ekspor**, seperti sekarang. Waktu asli tiap baris tetap disimpan dan rentangnya ditampilkan (B06). | Keputusan pemilik (P2) | — |
| A2 | **[Diputuskan, berubah]** Definisi metrik yang salah atau janggal **diperbaiki** (B03, B13); selebihnya ditiru persis. Daftar perbaikan tertutup di TRD §4.4. | Keputusan pemilik (P4) | — |
| A3 | **[Gugur]** ~~Hanya lokal, tanpa login.~~ Diganti: dibuka dari banyak komputer lewat HTTPS dengan login dua peran, akun lokal. | Keputusan pemilik (P1, P3) | — |
| A4 | Dashboard **harus berfungsi tanpa internet** dan tidak memanggil domain luar dari browser. | Sejalan dengan aturan privasi; menghapus ketergantungan yang sekarang tidak disengaja | Mengizinkan CDN kembali hanya melonggarkan syarat |
| A5 | Peran **pekerjaan** pengguna = tabel di §3 (masih asumsi). Peran **akses** sudah diputuskan: admin dan user. | Disimpulkan dari isi tab | Prioritas P1 disusun ulang; P0 tidak berubah |
| A6 | File rusak **tetap dihitung barisnya** seperti lama, dan ditandai (B05). | Menjaga kesetaraan "Total baris log" | Mengecualikannya mengubah angka baris di 5 folder |
| A7 | Mode `--watch` **tidak dibawa**; diganti ingest bertahap yang dipicu manual, terjadwal, atau oleh impor S3 (B14). | Tujuan migrasi menyebut "sekali per hari"; pemilik merencanakan otomatisasi lewat bucket | T04 |
| A8 | Data disimpan **setahun**, anggaran ≤ 10 GB. | Permintaan menyebut "ukuran data setahun" | Anggaran dan T09 disesuaikan |
| A9 | Folder **tanpa namespace** (09-26, 09-27) tetap didukung. | Ada di angka acuan | Bisa dibuang kapan saja |
| A10 | Folder layanan tak dikenal tetap diperlakukan seperti sekarang (parser Spring Boot), **dengan peringatan** saat ingest. | Setara dengan lama tanpa menyembunyikan masalah | Ubah menjadi ditolak |
| A11 | `.log` dan `.log.gz` dianggap identik; aturan pilih file sama seperti lama. | Setara | Aturan diganti setelah P5 dijawab |

---

## 10. Pertanyaan terbuka untuk pemilik produk

Diurutkan menurut besarnya pengaruh. **P1–P4 sudah dijawab** (2026-10-06). Pertanyaan baru yang muncul
setelah TRD ada di TRD §11.2 (server, folder log di server, cadangan).

| # | Pertanyaan | Asumsi sementara | Mengapa penting |
|--:|---|---|---|
| P1 | ~~Siapa saja pengguna dashboard ini?~~ | **Terjawab**: login dua peran (admin, user); admin menambah user; pembatasan per modul ditunda | — |
| P2 | ~~"Hari" per folder atau per tanggal kalender?~~ | **Terjawab**: per folder; folder baru akan datang lewat impor S3 | — |
| P3 | ~~Dibuka di satu komputer atau banyak?~~ | **Terjawab**: banyak komputer; login dengan akun lokal | — |
| P4 | ~~KPI yang salah dan definisi janggal: tiru atau perbaiki?~~ | **Terjawab**: perbaiki sesuai praktik yang baik (TRD §4.4) | — |
| P5 | Apakah `.log` dan `.log.gz` selalu identik, dan mana yang akan terus tersedia? | A11 | Aturan ingest |
| P6 | Lisensi ip2asn: kode menyebut "public domain", belum dicek ke sumbernya. Atribusi lokasi kini MaxMind GeoLite2 dan tampil di setiap peta (sudah diputuskan). | B08 | Kepatuhan lisensi |
| P7 | Berapa lama data perlu disimpan, dan berapa ruang disk yang tersedia? | A8 | Anggaran ukuran |
| P8 | File rusak (`unsupported log format`): cukup ditandai, atau perlu dilaporkan ke tim yang mengekspor log? Apakah penyebabnya diketahui? | A6 | 3 dari 11 folder praktis tanpa data |
| P9 | Bisakah simpel-loop dan coredns diberi cap waktu di sumbernya? | tidak (T08) | Sekarang chart per jam simpel-loop hanya mencakup 4–70 % event |
| P10 | IP server, daftar host, dan DNS upstream: cukup konfigurasi dengan nilai sekarang? Siapa yang memperbaruinya bila berubah? | B11 | Titik tujuan peta dan URL lengkap |
| P11 | Perlukah ingest otomatis saat folder baru muncul? | tidak (A7) | T04 |
| P12 | Folder tanpa namespace dan layanan tak dikenal: masih mungkin muncul? | A9, A10 | Aturan ingest |
| P13 | Setelah v2 diterima, sistem lama disimpan berapa lama? | tidak dihapus | Serah terima |
