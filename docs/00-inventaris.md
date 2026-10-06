# Inventaris sistem lama — dashboard log SIMPEL4

Daftar periksa "tidak ada yang hilang" untuk migrasi. Sumber: `build_dashboard.py` (583 baris) dan
`dashboard_template.html` (1.913 baris), dibaca sampai habis, ditambah satu kali build pada 2026-10-06
terhadap 11 folder log (2026-09-26 … 2026-10-06).

Dokumen ini hanya mencatat apa yang ada sekarang. Tidak ada usulan desain; hal yang perlu diputuskan
dikumpulkan di [§9 Pertanyaan terbuka](#9-pertanyaan-terbuka).

Notasi: `S.<field>` = `D.days[<folder>][<layanan>].<field>`, yaitu keluaran `summarize()` yang ditanam ke
HTML. `s['x']` = statistik mentah di Python sebelum diringkas. Indeks `r[i]` = posisi kolom dalam baris array.

Isi: [1 Gambaran](#1-gambaran-sistem-lama) · [2 Tab](#2-tab-dan-halaman-layanan) · [3 Format log](#3-format-log-yang-di-parse) ·
[4 Logika turunan](#4-logika-turunan) · [5 Batas](#5-batas-dan-penyederhanaan-yang-disengaja) ·
[6 Sumber luar](#6-sumber-data-luar-lisensi-atribusi) · [7 Angka acuan](#7-angka-acuan) ·
[8 Temuan](#8-temuan-perilaku-yang-tidak-jelas-dari-tampilan) · [9 Pertanyaan](#9-pertanyaan-terbuka)

---

## 1. Gambaran sistem lama

### 1.1 Alur build

1. `build()` mencari `*/**/*.log`, ditambah `*.log.gz` **hanya bila** `.log` pasangannya tidak ada.
2. Dari path relatif: `tanggal` = folder teratas (harus cocok `\d{4}-\d\d-\d\d`, minimal 3 komponen path),
   `layanan` = folder induk file, `ns` = komponen di antaranya (atau `-`), `pod` = nama file tanpa awalan
   `log_<layanan>_` dan akhiran `_YYYY-…`.
3. Tiap baris diberikan ke `parse(layanan, baris, s)`; `s` = satu kantong statistik per (tanggal, layanan),
   gabungan semua pod. File dibaca dengan `errors='replace'`.
4. `correlate()` menggabungkan event simpel-loop dengan request nginx (lihat §4.4).
5. `summarize()` memotong tiap statistik menjadi top-N (§5) → `D.days`.
6. Pemilik IP (`ipinfo`), lokasi (`geo`), daratan (`land`), label wilayah (`labels`) dihitung offline (§4.6, §6).
7. JSON menggantikan `/*DATA*/ null` di template (harus tepat satu kali; `</` di-escape) → `dashboard.html`.

Mode baris perintah: tanpa argumen = build sekali; `--watch` = polling 5 detik atas ukuran+mtime semua
`*.log*` dan template, lalu build ulang **seluruh** hari; `--selftest` = `demo()` (uji `geo_scan`,
`kab_name`, dan alur IP dengan retry).

### 1.2 Bentuk data yang ditanam (`D`)

| Kunci | Isi | Ukuran sekarang |
|---|---|--:|
| `days` | `{folder: {layanan: ringkasan}}`, 45 field per layanan (§1.3) | 1.081 KB |
| `land` | satu string path SVG daratan dunia | 755 KB |
| `ipinfo` | `{ip: {asn, cc, org}}` untuk IP yang tampil | 148 KB (1.734 IP) |
| `geo` | `{ip: [kota, provinsi, negara, lat, lon]}` untuk IP alur + server | 106 KB (1.676 IP) |
| `files` | `[{date, ns, svc, pod, size, lines, err, warn}]` | 28 KB (195 file) |
| `labels` | `{c: negara, p: provinsi, k: kab/kota}` | 27 KB (177 / 38 / 514) |
| `hosts` | upstream → base URL produksi (konstanta `HOSTS`) | 6 entri |
| `server` | `[ip, kota, provinsi, negara, lat, lon]` titik tujuan peta | 1 |

`dashboard.html` = 2.267.447 byte. Field terbesar di `days`: `flow` 437 KB, `trace` 195 KB, `msgs` 86 KB,
`ep` 73 KB, `uperr` 72 KB, `atk` 47 KB.

### 1.3 Field ringkasan per layanan

| Field | Bentuk | Diisi oleh |
|---|---|---|
| `lines`, `err`, `warn` | angka | semua |
| `hour` | `[[jam WIB 'YYYY-MM-DD HH', n]]` | nginx, FE, Spring; simpel-loop hanya lewat korelasi |
| `herr` | `{jam: n}` | nginx & FE (5xx), Spring (ERROR), simpel-loop (event gagal yang terkorelasi) |
| `status` | `[[kode, n]]` | nginx, FE, simpel-loop |
| `paths` | top 20 `[kunci, n]` | nginx/FE/simpel-loop: `METODE path_key`; coredns: domain |
| `perr` | top 20 `['<status> <kunci>', n]` | nginx, FE (4xx/5xx), simpel-loop (hanya event gagal) |
| `ips` | top 15 `[ip, n]` | nginx, FE, simpel-loop |
| `up`, `ua` | top 12 | nginx |
| `extra` | `[[level/jenis, n]]` | simpel-loop (`OM-<level>`), Spring (level + `Hibernate SQL`) |
| `dur` | top 15 rata-rata `{k,n,avg,max}` | nginx, simpel-loop — **tidak dipakai template** |
| `ep` | top 150 `[kunci, request, 4xx, 5xx, p50, p95, p99, maks]` (detik) | nginx, simpel-loop |
| `slow` | top 15 `[ms, kunci, status]` | simpel-loop |
| `msgs` | top 40 `['LEVEL \| pesan ternormalisasi', n, baris asli]` | semua |
| `atk`, `atk_ip`, `atk_h`, `atk_cat`, `ip4` | §4.1 | nginx |
| `login`, `login_h`, `acct`, `login_ok`, `users_ok`, `login_okh` | §4.2 | Spring (praktis appsmanager) |
| `incidents`, `up5` | §4.3 | nginx |
| `corr`, `trace` | §4.4 | simpel-loop |
| `flow`, `pod`, `retry`, `uperr` | §4.5 | nginx |
| `c401` | top 30 `[ip, kunci, n, puncak/menit, pertama, terakhir]` | nginx |
| `uk`, `ukf`, `uk_t` | Uptime-Kuma per jam, gagal per jam, top 5 target | nginx |
| `biz`, `mail`, `act` | §4.8 | simpel-loop |
| `restart`, `jwt`, `rep` | §4.9 | Spring |

---

## 2. Tab dan halaman layanan

### 2.0 Kerangka yang berlaku di semua tab

- **Sidebar**: logo "S4 SIMPEL4 Log"; grup *Analisis* (9 tab, urutan tetap: Overview, Peta IP, Tren, Keamanan,
  Akar Masalah, Ketersediaan, Pod, Bisnis, Pelacakan Request); grup *Layanan* = layanan yang ada di folder
  terpilih, urut sesuai urutan file. Lencana: tab Keamanan `N IP` (`atk_ip.length`), tiap layanan = `S.err`.
  Footer "Semua waktu dalam WIB (UTC+7)". Di layar ≤ 900 px sidebar menjadi bar atas yang bisa digulir.
- **Header**: judul tab; subjudul `Folder log <tgl> · N layanan · Semua waktu dalam WIB (UTC+7)`;
  pemilih folder (bawaan = folder terbaru); tombol bahasa ID/EN; tombol tema ☀/☾.
- **Status yang diingat**: tab di `location.hash`; bahasa dan tema di `localStorage` (`lang`, `theme`; bawaan
  `id` dan `dark`). Pilihan modul peta, tampilan peta, dan kotak zoom hanya di memori.
- **Dua bahasa**: kamus `EN` (±240 entri, kunci = teks Indonesia huruf kecil, cocok persis), 10 `RULES` regex
  untuk teks berisi angka/tanggal, `L(id, en)` untuk kalimat panjang; `translateDom()` menyapu semua text node
  setelah render; sebagian kunci kamus adalah teks yang datang dari Python (tanda akun, metrik bisnis,
  kelompok umur JWT, kategori serangan). Label dan legenda chart lewat `tr()`. Nama negara lewat `Intl.DisplayNames`.
- **Dua tema**: variabel CSS di `:root` dan `:root[data-theme="light"]`; warna chart dibaca dari variabel saat
  render, jadi ganti tema = render ulang.
- **Format**: angka `toLocaleString` (`id-ID` / `en-US`); waktu `28 Sep 2026 06.03 WIB` (EN memakai `:`), jam
  `28 Sep 06.00`; durasi `850 ms` / `2,35 dtk` / `1 mnt 52 dtk`; rentang waktu digabung bila tanggalnya sama.
  Teks antarmuka di-*Capitalize Each Word* lewat CSS; data (URL, IP, pesan, UA) tidak.
- **Komponen**: KPI (label, nilai, warna, baris delta); kartu chart tinggi 280 px; tabel dengan header lekat,
  tinggi maksimum 440–600 px, kolom angka rata kanan; kolom pertama tabel sederhana diberi batang proporsi bila
  kolom kedua berjudul "Jumlah"; kode status diwarnai (2xx hijau, 4xx kuning, 5xx merah); tag keparahan.
- **Keterangan pemilik IP** (`ipTag`): di bawah setiap IP yang punya `ipinfo` tampil `AS<asn> · <cc> · <org>`,
  plus tag "Jaringan Ombudsman" bila `org` memuat `OMBUDSMAN`. Tooltip chart IP juga menampilkan `org`.
- **Filter teks**: input di judul kartu menyembunyikan baris tabel yang tidak memuat teks (substring, tanpa
  beda huruf besar/kecil, di sisi browser atas baris yang sudah dipotong top-N).
- **Chart**: Chart.js 4.4.1; garis = area bergradien; batang bersudut bulat; donat dengan persentase dan label
  irisan terbesar di tengah; batang horizontal top-N memotong label di 48 karakter (teks lengkap di tooltip).
- **Delta vs folder sebelumnya** (`dlt`): hanya layanan yang *sebanding* (baris log folder sebelumnya ≥ 50 %
  folder ini, dan folder ini tidak kosong). Keluaran: `▲/▼ N% Vs <tgl>` (merah bila memburuk),
  `≈ Sama Dengan <tgl>` bila |perubahan| < 0,5 %, `Baru (<tgl>: 0)`, atau
  `Log <tgl> Tidak Lengkap, Tidak Dibandingkan`.

### 2.1 Overview (per folder)

| Elemen | Isi | Sumber |
|---|---|---|
| Teks | Periode log: jam pertama – jam terakhir | min/maks `S.hour` semua layanan |
| KPI | Total baris log (+delta, naik = baik) | Σ `S.lines` |
| KPI | Error (+delta) | Σ `S.err` |
| KPI | Warning / 4xx app (+delta) | Σ `S.warn` |
| KPI | HTTP request, Rate 4xx (1 desimal), Rate 5xx (2 desimal) — hanya bila nginx punya baris | `nginx.status` |
| KPI | Layanan, File log, File kosong (ukuran 0 byte) | `D.days`, `D.files` |
| Chart | Error per jam per layanan (batang bertumpuk, lebar) — hanya layanan yang punya `herr` | `S.herr` |
| Chart | Error & warning per layanan; Baris log per layanan (batang horizontal) | `S.err`, `S.warn`, `S.lines` |
| Tabel | Ringkasan layanan: Layanan, Baris, Error, Warn, Pod (= jumlah file) | `S.*`, `D.files` |
| Tabel | File log: Layanan / pod, Baris, Ukuran (MB) | `D.files` |
| Tabel | Top pesan error lintas layanan (25 teratas, lebar, dengan batang) | gabungan `S.msgs` semua layanan |
| Bagian | "Traffic HTTP seluruh sistem" + catatan sumber, lalu **semua kartu halaman layanan nginx** kecuali peta dan kartu pesan (§2.10) | `nginx.*` |

### 2.2 Peta IP (per folder)

| Elemen | Isi | Sumber |
|---|---|---|
| Filter | Pemilih modul: "Semua Modul" + tiap upstream tanpa akhiran port | `nginx.flow[*][1]` |
| KPI | IP Asal Unik; Lokasi Asal (pasangan lat,lon unik); Negara Asal; Modul Tujuan; IP Tujuan Unik (Pod); Total Request | `nginx.flow`, `D.geo` |
| Peta | Daratan; busur melengkung dari tiap lokasi ke server (tebal 1–4 menurut request); titik per lokasi (IP digabung per lat,lon) dengan tooltip `kota, provinsi, negara · N IP asal · N request → modul (n)`; 6 lokasi terbesar diberi label; titik server "Server SIMPEL4 + IP" | `D.land`, `nginx.flow`, `D.geo`, `D.server` |
| Peta | Label wilayah: negara selalu (peringkat > 2 disembunyikan saat lebar tampilan > 100°); provinsi saat ≤ 100°; kabupaten/kota saat ≤ 6° | `D.labels` |
| Interaksi | Preset Indonesia `[94,-8,48,20]` / Dunia `[-168,-80,336,140]`; tombol +/−; roda mouse (zoom ke arah kursor); seret untuk menggeser; lebar 1°–360°, rasio 2,4 | — |
| Legenda | Lokasi IP asal; Server tujuan; `N request dari luar Indonesia · M request dari IP internal / tanpa lokasi (tidak digambar)` | `D.geo` |
| Tabel | Alur IP Asal → IP Tujuan: IP Asal (+pemilik), Lokasi, Modul Tujuan, IP Tujuan (Pod) maks. 3 dengan ×jumlah, Request; berfilter | `nginx.flow` |
| Catatan | Lokasi = perkiraan tingkat kota; **atribusi DB-IP dan GeoNames**; IP tujuan = IP pod sehingga digambar di lokasi server; "Maksimal 3.000 alur teratas per hari" | — |
| Kosong | "Peta butuh log ingress nginx; folder ini tidak memilikinya." Kartu peta juga hilang bila `D.land` kosong. | — |

Lokasi di tabel: tempat dari `geo`; "Jaringan Internal" bila `ipinfo.cc == '-'`; selain itu "Tidak diketahui".

### 2.3 Tren (semua folder, tidak bergantung pemilih folder)

| Elemen | Isi | Sumber |
|---|---|---|
| Catatan | Data tiap hari tidak selalu lengkap | — |
| Chart | Error per hari per layanan; Warning per hari per layanan; Baris log per hari per layanan (bertumpuk) | `S.err`, `S.warn`, `S.lines` |
| Chart | Request HTTP per hari (ingress nginx): Total, 4xx, 5xx | `nginx.status` |
| Chart | Keamanan per hari: Request Serangan, Password Salah, Reset Password | Σ `nginx.atk_cat`; Σ `appsmanager.login[*][1]` dan `[2]` |
| Chart | Aktivitas bisnis per hari: Laporan Dibuat, Registrasi Laporan, File Diunggah, Email Terkirim, OTP Diminta | `simpel-loop.biz` |
| Tabel | Error per layanan & perubahan vs hari sebelumnya (▲/▼ % bila error kemarin > 0 dan baris kemarin ≥ 50 % hari ini) | `S.err`, `S.lines` |
| Tabel | Kelengkapan data: jumlah baris; "Kosong" bila 0; "Tidak Ada" bila layanannya tidak ada di folder | `S.lines` |

### 2.4 Keamanan (per folder)

| Elemen | Isi | Sumber |
|---|---|---|
| KPI | Request indikasi serangan | Σ `nginx.atk_cat` |
| KPI | IP sumber unik | `nginx.atk_ip.length` |
| KPI | Serangan kritis (SQLi/XSS/LFI/RCE) | Σ hit baris `nginx.atk` berkeparahan 3 |
| KPI | Endpoint serangan dgn respons 2xx | jumlah baris `atk` keparahan ≥ 2 yang statusnya memuat 2xx |
| KPI | IP dengan login gagal | `appsmanager.login.length` |
| KPI | Akun sukses setelah ≥3 gagal; Sukses dari IP berbeda | `appsmanager.acct[*][6]` |
| KPI | Reset password (3× gagal) | Σ `login[*][2]` |
| Peringatan | "Temuan utama": hingga 9 kalimat otomatis (di bawah) | `atk`, `atk_ip`, `login`, `acct`, `ipinfo` |
| Chart | Request per kategori serangan (warna menurut keparahan); Timeline indikasi serangan per jam | `atk_cat`, `atk_h` |
| Chart | Top 10 IP sumber serangan; Sumber serangan per pemilik jaringan (ASN), 10 teratas | `atk_ip`, `ipinfo.org` |
| Chart | Password salah per jam; Top 10 IP dengan password salah | `login_h`, `login` |
| Tabel | Endpoint dengan indikasi serangan: Kategori, URL lengkap (base URL upstream + path ter-decode, + UA), Hit, IP (IP teratas `+N` lainnya, pemilik), Status (`kode×n`, tanda "2xx – verifikasi"), Ukuran respons (maks. 5 nilai), Target upstream, Waktu; urut keparahan lalu hit; berfilter | `atk`, `D.hosts` |
| Tabel | IP sumber serangan: IP, Hit, Kategori (+jumlah), Status, User-Agent terbanyak, Waktu; berfilter | `atk_ip` |
| Tabel | Analisis akun: Akun, Gagal, Reset, Sukses, IP Gagal, IP Sukses, Tanda (+hingga 3 kejadian), Waktu; berfilter | `acct` |
| Tabel | Login gagal / brute force: IP (+tag "Multi-akun" bila ≥ 3 akun berbeda), Password salah, Reset, Login sukses, Akun dicoba, Waktu; berfilter | `login` |
| Tabel | IP dengan respons 4xx terbanyak (nginx): IP, Jumlah 4xx, User-Agent | `ip4` |
| Catatan | Tanpa nginx: "deteksi serangan per URL tidak tersedia". Kaki halaman: deteksi berbasis signature, body POST tidak diperiksa, 2xx biasanya fallback SPA | — |

Keparahan: 3 = Log4Shell / RCE, SQL Injection, Path Traversal / LFI, XSS; 2 = Probe file sensitif,
Scan CMS / WordPress, Probe PHP / CGI; 1 = UA tool/scanner otomatis.

Aturan "Temuan utama":

1. Ada kategori Log4Shell / RCE → jumlah, IP, upstream, saran log4j-core ≥ 2.17.
2. Untuk masing-masing SQL Injection, XSS, Path Traversal / LFI → jumlah, IP, status.
3. Ada baris keparahan ≥ 2 yang upstream-nya memuat `rancher` → "Panel Rancher dapat dijangkau dari internet".
4. Ada endpoint serangan berrespons 2xx → minta verifikasi ukuran respons.
5. Pemilik IP penyerang (keparahan ≥ 2) cocok `CLOUD|OCEAN|AMAZON|AWS|AZURE|MICROSOFT|HETZNER|OVH|LINODE|VULTR|ALIBABA|TENCENT|HOSTING|DATACENTER`.
6. IP login gagal milik jaringan Ombudsman → kemungkinan NAT kantor.
7. IP mencoba ≥ 3 akun berbeda (bagian sebelum `@`) → indikasi credential stuffing.
8. Akun bertanda "Sukses Dari IP Berbeda" → verifikasi ke pemilik akun.
9. Ada reset password otomatis → jumlahnya.

Di tabel Analisis akun, tanda "Sukses Dari IP Berbeda" berubah menjadi "… (ISP Sama)" bila semua IP sukses
punya ASN yang sama dengan salah satu IP gagal.

### 2.5 Akar Masalah (per folder)

| Elemen | Isi | Sumber |
|---|---|---|
| Peringatan | "Ringkasan akar masalah", hingga 5 butir: 401 berulang (klien teratas, puncak/menit); token JWT kedaluwarsa (total + % > 1 jam); PDF report gagal karena template null; DNS timeout (teks menyebut upstream DNS `10.88.1.100`, ditulis mati); error koneksi nginx → pod (jenis terbanyak). Kosong → "Tidak ada pola akar masalah…" | `nginx.c401`, `*.jwt`, `report.rep`, `coredns.paths`, `nginx.uperr` |
| Chart | Klien dengan 401 berulang (IP + endpoint), 10 teratas | `c401` |
| Chart | Umur token JWT saat ditolak: 5 kelompok umur, bertumpuk per layanan (appsmanager, referensi, report) | `jwt` |
| Chart | Pembuatan PDF report per template (sukses vs gagal), 12 teratas | `rep` |
| Chart | Error koneksi nginx → pod per jenis | `uperr[*][1]` |
| Tabel | Klien dengan 401 berulang: IP, Endpoint, Jumlah 401, Puncak / menit, Waktu; berfilter | `c401` |
| Tabel | Status pembuatan PDF report per template: Template, Sukses, Gagal (template null) | `rep` |
| Tabel | DNS timeout per domain: Domain, Jumlah, Dampak | `coredns.paths` |

Dampak DNS: `backup|s3.` → "Backup ke S3 bisa gagal"; `pg-|postgres|.local` → "Koneksi database / layanan
internal"; `rancher|longhorn` → "Cek update Rancher / Longhorn"; lainnya → "Resolusi domain eksternal".

### 2.6 Ketersediaan (per folder; butuh nginx)

| Elemen | Isi | Sumber |
|---|---|---|
| KPI | Ketersediaan (non-5xx), 3 desimal | (Σ `status` − Σ `up5`) / Σ `status` |
| KPI | Total respons 5xx; Insiden 5xx | Σ `up5`; `incidents.length` |
| KPI | Retry ke pod lain; Error koneksi ke pod | Σ `retry[*][3]`; `uperr.length` |
| KPI | Cek Uptime-Kuma; Cek uptime gagal | Σ `uk`; Σ `ukf` |
| Chart | Respons 5xx per jam (lebar); Respons 5xx per upstream; Health check Uptime-Kuma per jam (berhasil/gagal) | `herr`, `up5`, `uk`, `ukf` |
| Tabel | Ketersediaan per upstream: Upstream, Request, 5xx, Ketersediaan | `up`, `up5` |
| Tabel | Daftar insiden 5xx: Mulai – selesai, Durasi (menit, selisih + 1), Jumlah 5xx, Upstream ×n, Status ×n | `incidents` |
| Tabel | Error koneksi nginx → pod: Waktu, Jenis, Pod (IP), Request; berfilter | `uperr` |
| Tabel | Target health check Uptime-Kuma: Target (`METODE path → upstream`), Jumlah cek | `uk_t` |
| Kosong | "Analisis ketersediaan memakai log ingress nginx…" | — |

### 2.7 Pod (per folder)

| Elemen | Isi | Sumber |
|---|---|---|
| KPI | Pod (file log); Pod tanpa log (0 baris) | `D.files` |
| KPI | Pod backend terlihat di nginx; Pod dengan retry 502 | `nginx.pod.length`; kombinasi upstream+pod unik di `nginx.retry` |
| KPI | Restart / start aplikasi | Σ `S.restart` semua layanan |
| Catatan | Nama pod dari nama file; nginx hanya mencatat IP pod, pemetaan IP → nama pod tidak ada | — |
| Chart | Error per pod (15 file teratas); Sebaran request per pod (IP) dari nginx (15 teratas) | `D.files[*].err`, `nginx.pod` |
| Tabel | Kesehatan per pod: Layanan / pod, Baris, Error, Warning, Ukuran, Status (Ada Log / Tanpa Log); berfilter | `D.files` |
| Tabel | Sebaran traffic per pod backend: Upstream, Pod (IP), Request, Porsi dalam upstream, 5xx, Retry (pod ini gagal) | `nginx.pod`, `nginx.retry` |
| Tabel | Restart / start aplikasi (Spring Boot): Waktu, Pod, Aplikasi, Lama startup | `S.restart` |

### 2.8 Bisnis (per folder)

| Elemen | Isi | Sumber |
|---|---|---|
| KPI (+delta, naik = baik) | Laporan Dibuat, Registrasi Laporan, OTP Diminta, OTP Terverifikasi, File Diunggah, Email Terkirim | `simpel-loop.biz` |
| KPI | Upload Ditolak = terlalu besar + tipe file | `biz` |
| KPI | PDF Report Dibuat, PDF Report Gagal | Σ `report.rep[*][1]`, `[2]` |
| KPI | Login Sukses, Pengguna Unik Login | `appsmanager.login_ok`, `users_ok` |
| Catatan | Dihitung dari event 2xx; hanya pod yang lognya ada | — |
| Chart | Ringkasan aktivitas layanan publik (semua kunci `biz`) | `biz` |
| Chart | Email notifikasi per jenis; Top aktivitas proses laporan (12 teratas) | `mail`, `act` |
| Chart | Login sukses per jam; PDF report per template (12 teratas menurut total) | `login_okh`, `rep` |
| Tabel | Aktivitas proses laporan (Endpoint, Jumlah); PDF report per template (Template, Sukses, Gagal) | `act`, `rep` |

"OTP Gagal", "Lampiran Ditambahkan", dan "Email Gagal" hanya muncul di chart ringkasan, tidak sebagai KPI.

### 2.9 Pelacakan Request (per folder; butuh simpel-loop yang terkorelasi)

| Elemen | Isi | Sumber |
|---|---|---|
| KPI | RequestId Simpel-Loop; Cocok dengan nginx; Tingkat kecocokan | `corr = [cocok, total]` |
| KPI | Request gagal terlacak; IP unik (gagal) | baris `trace` berstatus 4xx/5xx |
| KPI | Request lambat ≥ 5 dtk | Σ baris `trace` berstatus 2xx |
| Catatan | Penjelasan `requestId` + persentase event yang tidak cocok | `corr` |
| Chart | Top 10 IP dengan request gagal; Request gagal per jenis error (`status + error`) | `trace` |
| Tabel | Jejak request gagal / lambat: IP, Status, Error, URL lengkap (dipotong 200 karakter, UA di bawahnya), Jumlah, Durasi maks, Waktu; berfilter | `trace`, `D.hosts` |
| Kosong | "Pelacakan butuh log om-be-simpel-loop dan ingress nginx pada rentang waktu yang sama…" | — |

### 2.10 Halaman layanan (per layanan × folder)

Satu fungsi untuk semua layanan; kartu yang datanya kosong tidak dirender. Urutan:

| # | Elemen | Sumber | nginx | FE | simpel-loop | Spring ×3 | coredns |
|--:|---|---|:-:|:-:|:-:|:-:|:-:|
| – | KPI: Baris log, Error, Warning | `lines`, `err`, `warn` | ✓ | ✓ | ✓ | ✓ | ✓ |
| – | KPI: HTTP request, Rate 4xx, Rate 5xx | `status` | ✓ | ✓ | ✓ | | |
| – | KPI: 4 entri pertama distribusi level | `extra` | | | ✓ | ✓ | |
| 1 | Peta + tabel alur untuk modul ini (nginx: semua alur) | `nginx.flow` | ✓ | ✓ | ✓ | ✓ | |
| 2 | Chart Aktivitas per jam: Total & Error (simpel-loop: judul ditambah "dari X % request yang terlacak di nginx") | `hour`, `herr`, `corr` | ✓ | ✓ | ✓* | ✓ | |
| 3 | Chart Status code HTTP (sumbu logaritmik) | `status` | ✓ | ✓ | ✓ | | |
| 4 | Chart donat Traffic per upstream service | `up` | ✓ | | | | |
| 5 | Chart donat Distribusi level / jenis log | `extra` | | | ✓ | ✓ | |
| 6 | Chart Top 10 endpoint (coredns: Top 10 domain gagal resolve) | `paths` | ✓ | ✓ | ✓ | | ✓ |
| 7 | Chart Top 10 endpoint dengan status 4xx/5xx | `perr` | ✓ | ✓ | ✓ | | |
| 8 | Chart Top 10 IP klien | `ips` | ✓ | ✓ | ✓ | | |
| 9 | Chart Top 10 pesan error / warning | `msgs` | ✓ | ✓ | ✓ | ✓ | ✓ |
| 10 | Tabel Top endpoint (coredns: Domain gagal resolve) | `paths` | ✓ | ✓ | ✓ | | ✓ |
| 11 | Tabel Endpoint dengan status 4xx/5xx | `perr` | ✓ | ✓ | ✓ | | |
| 12 | Chart Waktu respons P95 – 10 endpoint paling lambat | `ep` | ✓ | | ✓ | | |
| 13 | Chart Error rate tertinggi (min. 20 request), 10 teratas | `ep` | ✓ | | ✓ | | |
| 14 | Tabel Kinerja endpoint (25 teratas menurut P95): Endpoint, Request, P50, P95, P99, Maks, Error Rate; P95 ≥ 1 dtk kuning, P99 ≥ 5 dtk merah | `ep` | ✓ | | ✓ | | |
| 15 | Tabel Endpoint dengan error rate tertinggi (20 teratas): Endpoint, Request, 4xx, 5xx, Error Rate | `ep` | ✓ | | ✓ | | |
| 16 | Tabel Request lambat (≥ 1 detik) | `slow` | | | ✓ | | |
| 17 | Tabel Top IP klien (+pemilik) | `ips` | ✓ | ✓ | ✓ | | |
| 18 | Tabel Top User-Agent | `ua` | ✓ | | | | |
| 19 | Tabel Pesan error / warning (dikelompokkan): Level, Pesan (klik → baris log asli, waktu UTC), Jumlah; berfilter | `msgs` | ✓ | ✓ | ✓ | ✓ | ✓ |

\* hanya bila ada korelasi dengan nginx. Bila `lines == 0`, KPI diganti teks "Tidak ada log untuk layanan
ini di tanggal ini (file kosong)."

---

## 3. Format log yang di-parse

Layanan ditentukan dari **nama folder induk**; folder yang tidak dikenal jatuh ke parser Spring Boot.
Semua cap waktu log adalah UTC; `wib()` menambah 7 jam dan memotong ke menit. Contoh di bawah adalah baris
asli; hanya nama akun pada contoh login yang disamarkan.

### 3.1 Ingress nginx — access log (`nginx-ingress-controller`)

```
(\S+) - \S+ \[(\d+)/(\w+)/(\d+):(\d+:\d+):\d+ [^\]]+\] "(\S+) (\S+)[^"]*" (\d{3}) (\d+) "[^"]*" "([^"]*)" \d+ ([\d.]+) \[([^\]]*)\]
```

Field: IP klien, hari, bulan, tahun, `HH:MM`, metode, path+query, status, ukuran respons, User-Agent,
`request_time` (detik), nama upstream. Awalan `ombudsman-ombudsman-` dibuang dari upstream; kosong → `-`.
Referer, panjang request, dan detik tidak diambil.

Ekor baris, dicari terpisah: `\] \[[^\]]*\] (.+) ([0-9a-f]{32})$` → blok
`upstream_addr panjang waktu status` (tiap bagian bisa berisi daftar `a, b` bila ada retry) dan request id.

```
103.160.147.100 - - [27/Sep/2026:17:02:58 +0000] "GET / HTTP/1.1" 200 6599 "-" "Uptime-Kuma/2.0.2" 355 0.001 [ombudsman-ombudsman-om-fe-inhouse-3000] [] 10.42.233.139:3000 6599 0.004 200 bbc49c2ed69b931599dd60d93314128c
```

Tanpa upstream (ditolak di ingress): `… 503 592 "-" "Mozilla/5.0 …" 313 0.000 [ombudsman-minio-web] [] - - - - ed48a8f22c074106a1eea58e5c038af9`.

Yang dihitung dari tiap baris: `hour`, `status`, `ips`, `up`, `ua` (90 karakter), `paths`, `dur` (kecuali
status 101), 4xx/5xx per endpoint, `err`+`herr`+`perr` untuk 5xx, `perr` untuk 4xx, `ip4`, `c401`,
Uptime-Kuma (UA memuat `Uptime-Kuma`; gagal = status bukan 2xx/3xx), serangan (§4.1), insiden (§4.3),
alur/pod/retry (§4.5), dan tabel request id (§4.4).

### 3.2 Ingress nginx — error log

```
\d{4}/\d\d/\d\d \d\d:\d\d:\d\d \[(\w+)\] \d+#\d+: \*\d+ (.*?)(?:, client:|$)
```

Field: level, pesan sampai `, client:`. `error` dan `crit` → `err`; level lain → `warn`. Masuk `msgs`
(dinormalisasi). Bila baris memuat `upstream: "http(s)://<host>`, dicatat ke `uperr`: waktu WIB, pesan tanpa
nomor errno (`(104: ` → `(`) dipotong 100 karakter, alamat pod, `METODE path` dari `request: "…"` dipotong 120.

```
2026/09/27 18:45:30 [error] 41#41: *90237038 recv() failed (104: Connection reset by peer) while reading response header from upstream, client: 103.170.104.160, server: _, request: "GET / HTTP/1.1", upstream: "http://10.42.245.132:8080/", host: "*.ombudsman.go.id"
```

Tidak di-parse (hanya menambah `lines`): log pengendali ingress (`I1005 … status.go`, `W… controller.go`),
garis pemisah, dan baris tanpa nomor koneksi `*N`.

### 3.3 Frontend (`om-fe-inhouse`) — access log nginx

```
\S+ - \S+ \[(\d+)/(\w+)/(\d+):(\d+:\d+):\d+ [^\]]+\] "(\S+) (\S+)[^"]*" (\d{3}) \d+ "[^"]*" "[^"]*" "([^",]*)
```

Field: hari, bulan, tahun, `HH:MM`, metode, path, status, **IP = entri pertama `X-Forwarded-For`** (kolom
bertanda kutip ketiga). IP di awal baris (IP node) diabaikan. Tidak ada waktu respons.

```
10.88.1.102 - - [25/Sep/2026:16:46:08 +0000] "GET /js/chunk-vendors.60f38547.js HTTP/1.1" 200 1110667 "https://simpel4.ombudsman.go.id/lapor-ombudsman" "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Mobile Safari/537.36" "114.4.82.221, 10.88.1.100"
```

Error log memakai regex §3.2: hanya `error` → `err`, level lain → `warn`; masuk `msgs`.

```
2026/10/05 07:31:51 [error] 22#22: *26370 open() "/app/apple-touch-icon-precomposed.png" failed (2: No such file or directory), client: 10.42.233.128, server: localhost, request: "GET /apple-touch-icon-precomposed.png HTTP/1.1", host: "simpel4.ombudsman.go.id"
```

### 3.4 Simpel-loop (`om-be-simpel-loop`, Node.js)

Baris harus cocok `\[OM-(\w+)\] (.*)`; selain itu dianggap lanjutan multi-baris dan diabaikan.
**Tidak ada cap waktu di baris log ini.** Level masuk `extra`.

Event HTTP = isi berupa JSON yang punya `statusCode`:

```
[OM-INFO] {"requestId":"cbd8b650fbf2ff78ef03826371defaad","event":"http.request.completed","method":"GET","path":"/tx-file-upload","statusCode":200,"ipAddress":"103.138.53.20","durationMs":59}
[OM-ERROR] {"event":"http.request.failed","requestId":"69dda3958192b7ac11f28e3e2dc2f10c","method":"GET","path":"/tx-laporan/count","statusCode":401,"durationMs":1,"error":{"name":"UnauthorizedError","message":"Unauthorized"}}
```

Field: `requestId`, `event`, `method`, `path`, `statusCode`, `ipAddress` (tidak ada pada event gagal),
`durationMs`, `error.name`, `error.message`. Dihitung: `status`, `paths`, `ips`, `dur` (detik), `slow`
(≥ 1.000 ms), 4xx/5xx per endpoint, daftar event untuk korelasi, metrik bisnis (§4.8). Event
`http.request.failed` → `perr`, `msgs` (`<status> <name>: <message>`, level `ERROR` bila 5xx selain itu
`WARN`), dan `err` (5xx) atau `warn` (lainnya).

Baris teks:

| Pola | Efek |
|---|---|
| diawali `Email sent successfully` | `biz['Email Terkirim']` |
| `Notification email sent successfully (\w+)` | `mail[<jenis>]` |
| level `ERROR` dan memuat `mail` | `biz['Email Gagal']` |
| level `ERROR` / `WARN` | `err` / `warn` + `msgs` |

```
[OM-INFO] Notification email sent successfully sendNotificationMailToKepalaKeasistenanRiksa {
[OM-PERFORMANCE] GET /v-monitoring { totalMs: 95 }
```

### 3.5 Spring Boot (`om-be-appsmanager`, `om-be-referensi`, `om-be-report`)

```
(\d{4}-\d\d-\d\d \d\d:\d\d):\d\d\.\d+ +(\w+) \d+ --- \[([^\]]+)\] (\S+) *: (.*)
```

Field: waktu (menit), level, thread, logger, pesan. Dihitung: `hour`, `extra[level]`, `err`+`herr` (ERROR),
`warn` (WARN), `msgs` untuk ERROR/WARN dengan kunci `<kelas logger terakhir>: <pesan>`.

| Pola pada pesan | Efek | Contoh asli |
|---|---|---|
| `Started (\w+) in ([\d.]+) seconds` | `restart` (waktu, pod, aplikasi, detik) | `2026-09-25 16:04:28.984  INFO 1 --- [           main] i.c.appsmanager.AppsmanagerApplication   : Started AppsmanagerApplication in 17.163 seconds (JVM running for 19.336)` |
| `JWT token is expired: .* a difference of (\d+) milliseconds` | `jwt[<kelompok umur>]` | `2026-09-25 16:23:24.776 ERROR 1 --- [nio-3000-exec-6] id.com.appsmanager.config.jwt.JwtUtils   : JWT token is expired: JWT expired at 2026-09-25T23:22:35Z. Current time: 2026-09-25T23:23:24Z, a difference of 49775 milliseconds.  Allowed clock skew: 0 milliseconds.` |
| memuat `Refresh token expired` | `jwt['Refresh Token Kedaluwarsa']` | `2026-09-27 23:31:53.899  WARN 1 --- [nio-3000-exec-5] i.c.a.controller.UserController          : SECURITY ALERT: Refresh token expired from IP: 125.164.203.65. Error: JWT expired at 2026-09-27T02:59:54Z. …` |
| `(\S+) pdf path` | ingat template per thread | `2026-09-27 19:14:19.466  INFO 1 --- [nio-3000-exec-3] i.c.jasper.service.JasperReportService   : cover_map_kuning pdf path : /tmp/cover_map_kuning7643129013998660935.pdf` |
| diawali `Jasper template path : ` | `rep[template][sukses \| gagal]`; gagal bila berakhir `: null` | `… JasperReportService   : Jasper template path : /jasper/cover_map_kuning.jrxml` dan `… : Jasper template path : null` |
| `Invalid password for user/email: '([^']*)' from IP: ([\d.]+)` | login gagal | `2026-09-27 23:39:32.545  WARN 1 --- [nio-3000-exec-6] i.c.a.controller.UserController          : SECURITY EVENT: Invalid password for user/email: '<akun>@ombudsman.go.id' from IP: 39.194.3.114 (Attempt 1/3)` |
| `due to 3 failed login attempts for user/email: '([^']*)' from IP: ([\d.]+)` | reset password | `… SECURITY ALERT: Password reset and notification email sent due to 3 failed login attempts for user/email: '<akun>@ombudsman.go.id' from IP: 36.83.211.41` |
| `User '([^']*)' successfully logged in from IP: ([\d.]+)` | login sukses | `2026-09-25 16:55:52.965  INFO 1 --- [nio-3000-exec-4] i.c.a.controller.UserController          : SECURITY EVENT: User '<akun>' successfully logged in from IP: 103.247.21.209` |

Baris yang tidak cocok regex utama:

- cocok `[\w.$]+(Exception|Error)\b` di awal → `msgs` dengan level `EXC` (tidak menambah `err`):
  `org.springframework.security.web.firewall.RequestRejectedException: The request was rejected because the URL contained a potentially malicious String "//"`
- diawali `Hibernate:` → `extra['Hibernate SQL']`
- lainnya (banner, stack trace) diabaikan.

Kelompok umur JWT: `< 5 Menit`, `5–60 Menit`, `1–24 Jam`, `1–7 Hari`, `> 7 Hari`.

### 3.6 CoreDNS (`coredns`)

```
\[(\w+)\] plugin/errors: \d+ (\S+) (\w+): (.*)
```

Field: level, domain, tipe record, pesan. Setiap baris yang cocok: `err`, `paths[domain]`, `msgs`
(`<domain> <tipe>: <pesan>` dengan semua `ip:port` diganti `X`). **Tidak ada cap waktu.**

```
[ERROR] plugin/errors: 2 backup-simpel4-volume.s3.ap-southeast-3.amazonaws.com. AAAA: read udp 10.42.191.189:58401->10.88.1.100:53: i/o timeout
```

### 3.7 Baris yang bukan log

File yang gagal diekspor berisi satu baris raksasa
`failed to get parse function: unsupported log format: "\x00\x00…"` (bisa 30 MB). Baris ini hanya menambah
`lines`. Lihat §8.

---

## 4. Logika turunan

### 4.1 Klasifikasi serangan (nginx)

Path di-*URL-decode* dua kali (`unquote_plus` ×2), lalu dicocokkan berurutan; **cocok pertama yang dipakai**
(semua tanpa beda huruf besar/kecil):

| # | Kategori | Pola |
|--:|---|---|
| 1 | SQL Injection | `union\s+(all\s+)?select\|select\s.{1,60}\sfrom\|information_schema\|sleep\(\d\|benchmark\(\|waitfor\s+delay\|'\s*or\s*'?\d\|\bor\s+1=1\|;\s*drop\s` |
| 2 | XSS | `<script\|javascript:\|on(error\|load)\s*=\|alert\(\|<svg\|<iframe` |
| 3 | Path Traversal / LFI | `\.\./\|\.\.\\\|/etc/(passwd\|shadow\|hosts)\|win\.ini\|/proc/self` |
| 4 | Log4Shell / RCE | `\$\{jndi:\|\$\{.*\}\|;\s*(cat\|wget\|curl\|id\|uname\|sh)\b\|\|\s*(cat\|id\|sh)\b\|/bin/(ba)?sh\|cmd\.exe\|base64_decode\|eval\(\|system\(` |
| 5 | Probe file sensitif | `/\.(env\|git\|svn\|aws\|ssh\|htaccess\|htpasswd\|ds_store\|npmrc\|docker)\|/config\.(json\|php\|ya?ml)\|\.(sql\|bak\|old\|swp)$\|/id_rsa\|/actuator\|/server-status\|/_profiler\|/debug/` |
| 6 | Scan CMS / WordPress | `wp-(admin\|content\|includes\|login\|json)\|wordpress\|xmlrpc\|joomla\|drupal\|phpmyadmin\|/pma/` |
| 7 | Probe PHP / CGI | `\.(php\d?\|asp\|aspx\|jsp\|cgi)\b\|cgi-bin` |

Bila path bersih: User-Agent (setelah decode) memuat `${` → Log4Shell / RCE; lalu UA cocok
`sqlmap|nikto|nmap|masscan|zgrab|nuclei|gobuster|dirbuster|dirb|wpscan|acunetix|nessus|openvas|-scanner|python-requests|go-http-client|curl/|wget|libwww|httpx|fuzz`
→ "UA tool/scanner otomatis". Pola `;id` sengaja tidak diterapkan ke UA (UA Instagram memuat `; id;`).

Contoh yang terklasifikasi "Probe file sensitif":
`34.19.127.176 - - [05/Oct/2026:14:30:46 +0000] "GET /.git HTTP/1.1" 200 5642 "-" "Mozilla/5.0 …" 289 0.001 [cattle-system-rancher-80] [] 10.42.233.150:80 5642 0.000 200 6fca94688c3a10d03c80b31af70877af`

Agregasi:

- `atk`: kunci = kategori + `METODE path` (decode sekali, 200 karakter). Baris:
  `[kategori, 'METODE path', hit, jumlah IP, IP teratas, 'kode×n …', 5 ukuran respons terkecil, daftar upstream, UA pertama (100), pertama, terakhir]`; urut hit, 300 teratas.
- `atk_ip`: per IP `[ip, hit, {kategori: n}, 'kode×n …', UA terbanyak, pertama, terakhir]`; 100 teratas.
- `atk_h`: per jam WIB. `atk_cat`: per kategori (tidak dipotong).
- `ip4`: 20 IP dengan 4xx terbanyak + UA pertamanya.

### 4.2 Login dan analisis akun (Spring; datanya hanya ada di appsmanager)

- `login`: per IP `[ip, gagal, reset, sukses, akun yang dicoba (hanya dari gagal/reset), pertama, terakhir]`;
  hanya IP yang punya gagal atau reset; urut reset lalu gagal; 100 teratas.
- `login_h`: password salah per jam. `login_okh`: sukses per jam. `login_ok`: jumlah sukses.
  `users_ok`: jumlah akun unik yang sukses.
- Nama akun untuk analisis = bagian sebelum `@`, huruf kecil.

`accounts()` — per akun yang punya ≥ 1 password salah:

1. Untuk tiap login sukses, ambil password salah dalam **60 menit sebelumnya** (presisi menit).
2. Bila ≥ 3 → tanda "Sukses Setelah ≥3 Gagal". Bila IP sukses tidak termasuk IP gagal itu → tanda
   "Sukses Dari IP Berbeda" + catatan `<waktu> sukses dari <ip>` (maks. 3).
3. Password salah dari ≥ 2 IP → tanda "Dicoba Dari ≥2 IP".

Baris: `[akun, gagal, reset, sukses, IP gagal, IP sukses, tanda, pertama, terakhir, catatan]`; urut
"IP berbeda" dulu, lalu jumlah tanda, lalu gagal; 150 teratas. Pembeda "ISP sama" dihitung di browser dari ASN.

### 4.3 Insiden 5xx (nginx)

Tiap respons 5xx dicatat per (menit WIB, upstream, status). Menit-menit ber-5xx digabung menjadi satu
insiden bila jedanya ≤ 5 menit, **lintas upstream**. Baris: `[mulai, selesai, jumlah, {upstream: n}, {status: n}]`.
`up5` = total 5xx per upstream.

### 4.4 Korelasi request id nginx ↔ simpel-loop

- Setiap baris access nginx yang ekornya cocok mengisi `REQ[request id] = (waktu WIB, ip, metode, path, status, upstream, UA 120)`.
  `REQ` adalah satu kamus **global untuk semua folder** (308.157 id pada build acuan).
- Untuk tiap event simpel-loop: bila `requestId` ada di `REQ` → dihitung cocok, menambah `hour[jam]`
  simpel-loop (dan `herr` bila gagal). Inilah satu-satunya sumber waktu simpel-loop.
- Masuk `trace` bila event gagal **atau** `durationMs ≥ 5000`. Kunci = (IP, status, error atau
  `Lambat X dtk`, endpoint). Baris: `[ip, status, error, endpoint, jumlah, URL lengkap ter-decode (300), upstream, UA, pertama, terakhir, durasi maks ms]`; urut jumlah, 300 teratas.
- `corr = [cocok, total event]`.

### 4.5 Alur IP asal → pod, sebaran pod, retry (nginx)

Blok ekor dipecah menjadi 4 bagian (`alamat panjang waktu status`), masing-masing daftar dipisah koma.

- `flow[(IP klien, upstream)][pod]`: pod = **alamat terakhir** (yang menjawab); `-` bila ekor tidak cocok
  atau tidak ada upstream. Baris: `[ip, upstream, total, 3 pod teratas [alamat, n]]`; 3.000 teratas per folder.
- `pod[(upstream, alamat)]`: jumlah per percobaan (termasuk yang gagal); `pod5` = percobaan berstatus 5xx.
  Baris: `[upstream, alamat, request, 5xx]`, tidak dipotong.
- `retry[(upstream, alamat pertama, status pertama)]`: dihitung bila ada lebih dari satu alamat; 30 teratas.
- Di browser, "modul" = upstream tanpa akhiran `-<port>`.

### 4.6 Pemilik dan lokasi IP (offline)

**Pemilik (`ipinfo`)** — hanya untuk IP yang tampil (`shown_ips`: top IP, sumber serangan, login, 4xx, jejak,
401, alur, analisis akun):

- IP privat/loopback → `{asn: null, cc: '-', org: 'Jaringan Internal (IP Privat)'}`.
- IPv4 publik → pencarian biner pada rentang `ip2asn-v4.tsv` (baris ASN 0 dilewati) → `{asn, cc, org}`.
- IPv6 atau di luar rentang → tidak ada entri.

**Lokasi (`geo`)** — hanya untuk IP di `flow` + IP server:

- Hanya IPv4 global. Hasil per IP disimpan di `.cache/geo.json` (termasuk "tidak ditemukan"); database 86 MB
  hanya dibaca bila ada IP baru, dengan satu sapuan atas daftar IP terurut (`geo_scan`).
- Kolom DB-IP: awal, akhir, benua, negara, provinsi, kota, lat, lon → `[kota, provinsi, negara, lat, lon]`.
- Titik tujuan = `SERVER_IP = '103.170.104.228'` (hasil resolve `api-simpel4.ombudsman.go.id`, ditulis
  mati); bila tidak ada di database dipakai `['Jakarta', 'Jakarta', 'ID', -6.2, 106.82]`.

**Daratan (`land`)**: Natural Earth 50m; ring yang titik awalnya di selatan −60° dibuang; koordinat 2 desimal;
titik beruntun yang sama digabung; ring ≤ 3 titik dibuang; x = bujur, y = −lintang.

**Label (`labels`)**: negara `[nama ID, nama EN, bujur, lintang, peringkat]` dari Natural Earth 110m;
provinsi dari GeoNames `ADM1` yang kodenya ada di tabel `PROV` (38 provinsi, nama Indonesia ditulis mati);
kabupaten/kota dari `ADM2`, dinormalkan `kab_name()` (`… Regency` → `Kab. …`, `… City` → `Kota …`).

### 4.7 Normalisasi pesan dan path

`norm(pesan)`, berurutan, lalu dipotong 220 karakter:

1. `'…@…'` → `'<email>'`
2. `YYYY-MM-DDTHH:MM:SSZ` → `<ts>`
3. heksadesimal ≥ 16 karakter → `<id>`
4. angka (termasuk desimal) → `#`

Kunci `msgs` = `LEVEL | pesan ternormalisasi`; contoh yang disimpan = baris asli **pertama**, 600 karakter.

`path_key(path)`: buang query; `/[0-9a-f-]{16,}` → `/:id`; `/<angka>` → `/:n`; potong 120 karakter.

### 4.8 Metrik bisnis (simpel-loop)

Hanya respons 2xx, kunci = `METODE path_key`:

| Endpoint | Metrik |
|---|---|
| `POST /tx-laporan` | Laporan Dibuat |
| `POST /tx-laporan/registrasi` | Registrasi Laporan |
| `POST /tx-laporan/request-otp` | OTP Diminta |
| `POST /tx-laporan/verify-otp` | OTP Terverifikasi |
| `POST /tx-file-upload`, `POST /files` | File Diunggah |
| `POST /tx-lampiran` | Lampiran Ditambahkan |

Tambahan: `verify-otp` non-2xx → OTP Gagal; `error.name == MulterError` → Upload Ditolak (Terlalu Besar);
`UnsupportedMediaTypeError` → Upload Ditolak (Tipe File); Email Terkirim / Email Gagal dari baris teks (§3.4).
`act` = POST/PATCH/PUT/DELETE 2xx yang bukan endpoint di atas (20 teratas). `mail` = email notifikasi per jenis.

### 4.9 Lain-lain

- **Persentil endpoint** (`ep`): durasi diurutkan, indeks `min(n−1, int(q·n))`; hanya endpoint ≥ 5 durasi.
  Kolom "Request" = jumlah request endpoint itu (termasuk status 101 yang tidak punya durasi).
- **401 berulang** (`c401`): per (IP, endpoint): jumlah, puncak per menit, pertama, terakhir.
- **Base URL** (`HOSTS`): 6 upstream → host produksi; upstream lain tampil "[Host tidak tercatat]", `-` tampil
  "[Ditolak di ingress, host tidak tercatat]".
- **`D.files`**: `err`/`warn` per file = selisih penghitung layanan sebelum dan sesudah file itu.

---

## 5. Batas dan penyederhanaan yang disengaja

### 5.1 Komentar `ponytail:` (3)

| Lokasi | Isi |
|---|---|
| `build_dashboard.py:33` | Signature regex sederhana, bisa false positive/negative; pakai WAF untuk deteksi serius |
| `build_dashboard.py:319` | 3.000 alur teratas per hari; naikkan bila IP unik per hari sudah ribuan |
| `build_dashboard.py:547` | `--watch` polling tiap 5 detik; ganti ke watchdog bila folder sangat besar |

### 5.2 Top-N di Python

| Field | Batas | Tercapai pada data sekarang? |
|---|--:|---|
| `paths`, `perr` | 20 | ya (nginx 825 endpoint unik pada folder 10-06) |
| `ips` | 15 | ya (723 IP unik pada 09-29) |
| `up`, `ua` | 12 | `ua` ya |
| `dur` | 15, min. 5 durasi | ya (tidak dipakai) |
| `slow` | 15 | ya (553 pada 09-29) |
| `msgs` | 40 | ya (appsmanager 43 pada 09-29) |
| `atk` / `atk_ip` | 300 / 100 | tidak (maks. 77 / 14) |
| `ip4` | 20 | ya (233 pada 09-29) |
| `login` / `acct` | 100 / 150 | tidak |
| `ep` | 150, min. 5 durasi | ya |
| `c401` | 30 | ya (653 pada 09-29) |
| `uk_t` | 5 | — |
| `retry` | 30 kunci | — |
| `uperr` | 200 **terakhir** | ya (1.200 pada 09-30) |
| `trace` | 300 | ya (09-29) |
| `act` | 20 | ya |
| `flow` | 3.000, 3 pod per alur | tidak (maks. 1.762) |
| catatan akun | 3 | — |

### 5.3 Pemotongan teks

UA 90 (`ua`), 100 (serangan, `ip4`), 120 (korelasi); path serangan 200; `path_key` 120; pesan 220; contoh
baris 600; jenis error koneksi 100; request error koneksi 120; URL jejak 300 (200 di tabel).

### 5.4 Ambang dan batas di browser

- Chart top 10; pesan lintas layanan 25; tabel kinerja 25; error rate 20 (tabel) / 10 (chart), min. 20 request;
  error per pod dan request per pod 15; PDF/aktivitas 12; label lokasi peta 6.
- Lambat ≥ 1 dtk (tabel), ≥ 5 dtk (jejak); P95 ≥ 1 dtk kuning; P99 ≥ 5 dtk merah.
- Sebanding bila baris kemarin ≥ 50 %; perubahan < 0,5 % = "sama".
- Multi-akun ≥ 3 akun; jendela login 60 menit, ≥ 3 gagal; jeda insiden 5 menit.
- Tingkat detail label peta: lebar > 100° / > 6° / ≤ 6°.

### 5.5 Penyederhanaan lain

- Semua waktu dipotong ke menit; agregasi per jam.
- `.log.gz` dilewati bila `.log` ada (dianggap identik).
- Lanjutan multi-baris (stack trace, objek) diabaikan.
- Body request tidak ada di log, jadi serangan lewat POST tidak terdeteksi.
- Lokasi hanya IPv4; pemilik hanya IPv4.
- Umur cache: ip2asn 7 hari; DB-IP 30 hari (coba bulan ini lalu bulan lalu); daratan, negara, GeoNames
  3.650 hari; `geo.json` tidak pernah kedaluwarsa. Gagal unduh → pakai file lama bila ada.
- `lru_cache` pada `wib()` dan `path_attack()` (200.000 entri).
- Watcher menelan semua exception build agar tidak mati karena satu file rusak.

---

## 6. Sumber data luar, lisensi, atribusi

Dipakai saat build (diunduh ke `.cache/`, dicocokkan offline; IP pengguna tidak dikirim keluar):

| Data | URL | Berkas cache | Lisensi menurut kode | Kewajiban | Dipakai untuk |
|---|---|---|---|---|---|
| ip2asn v4 | `https://iptoasn.com/data/ip2asn-v4.tsv.gz` | `ip2asn-v4.tsv.gz` (7,0 MB) | "public domain" | tidak ada | pemilik IP |
| DB-IP City Lite | `https://download.db-ip.com/free/dbip-city-lite-YYYY-MM.csv.gz` | `dbip-city-lite.csv.gz` (85,8 MB) | CC BY 4.0 | **atribusi "IP Geolocation by DB-IP"** dengan tautan ke db-ip.com | lokasi IP |
| Natural Earth 50m land | `raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson` | `ne_50m_land.geojson` (1,6 MB) | public domain | tidak ada | daratan peta |
| Natural Earth 110m countries | `…/geojson/ne_110m_admin_0_countries.geojson` | `ne_110m_countries.geojson` (0,8 MB) | public domain | tidak ada | label negara |
| GeoNames ID | `https://download.geonames.org/export/dump/ID.zip` | `geonames-ID.zip` (10,4 MB) | CC BY 4.0 | **atribusi GeoNames** | label provinsi & kab/kota |

Atribusi sekarang hanya ditulis di catatan bawah tab **Peta IP** (tautan DB-IP dan GeoNames).

Dimuat browser saat dashboard dibuka (bukan data log, tetapi tetap panggilan ke pihak ketiga):

| Sumber | Lisensi | Catatan |
|---|---|---|
| Chart.js 4.4.1 dari `cdnjs.cloudflare.com` | MIT | tanpa internet chart tidak tampil |
| Font Outfit dari `fonts.googleapis.com` | SIL OFL 1.1 | tanpa internet jatuh ke font sistem |

---

## 7. Angka acuan

Dihasilkan `python3 v2/tools/acuan_lama.py` (membungkus build lama; `dashboard.html` ikut ditulis ulang) →
`v2/docs/00-acuan.json`. Kondisi: 2026-10-06 17:51, Python 3.13.1, build 14,2 detik, 195 file log,
`--selftest` lulus. Angka diambil dari statistik **mentah**, sebelum top-N.

**Angka ini hanya berlaku untuk isi folder log saat itu.** Folder log bertambah tiap hari; jalankan ulang
skrip sebelum uji kesetaraan.

Definisi kolom: *Baris* = semua baris file termasuk yang tidak ter-parse; *Request* = Σ `status`;
*Error* / *Warning* = `err` / `warn` (§3); *IP unik* = jumlah kunci `ips`; *Alur IP* = pasangan
(IP asal, upstream) unik.

| Folder | File (0 baris) | Layanan | Baris | Request | 4xx | 5xx | Error | Warning | IP unik | Alur IP |
|---|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| 2026-09-26 | 19 (0) | om-fe-inhouse | 515 | 405 | 0 | 0 | 0 | 0 | 5 | 0 |
|  |  | om-be-simpel-loop | 75 | 54 | 1 | 0 | 0 | 0 | 3 | 0 |
|  |  | om-be-appsmanager | 206 | 0 | 0 | 0 | 5 | 4 | 0 | 0 |
|  |  | om-be-referensi | 286 | 0 | 0 | 0 | 1 | 4 | 0 | 0 |
|  |  | om-be-report | 121 | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| | | **total** | **1.203** | | | | **6** | **11** | | |
| 2026-09-27 | 19 (0) | om-fe-inhouse | 18.254 | 18.229 | 371 | 0 | 25 | 0 | 384 | 0 |
|  |  | om-be-simpel-loop | 3.620 | 2.988 | 552 | 0 | 0 | 552 | 162 | 0 |
|  |  | om-be-appsmanager | 2.001 | 0 | 0 | 0 | 190 | 17 | 0 | 0 |
|  |  | om-be-referensi | 1.301 | 0 | 0 | 0 | 46 | 0 | 0 | 0 |
|  |  | om-be-report | 193 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| | | **total** | **25.369** | | | | **262** | **569** | | |
| 2026-09-28 | 24 (16) | nginx-ingress-controller | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-fe-inhouse | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-simpel-loop | 9.014 | 7.642 | 1.273 | 0 | 0 | 1.273 | 156 | 0 |
|  |  | om-be-appsmanager | 1.949 | 0 | 0 | 0 | 117 | 12 | 0 | 0 |
|  |  | om-be-referensi | 781 | 0 | 0 | 0 | 41 | 0 | 0 | 0 |
|  |  | om-be-report | 708 | 0 | 0 | 0 | 7 | 0 | 0 | 0 |
|  |  | coredns | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| | | **total** | **12.452** | | | | **165** | **1.285** | | |
| 2026-09-29 | 25 (1) | nginx-ingress-controller | 132.402 | 132.203 | 4.635 | 59 | 94 | 164 | 723 | 1.762 |
|  |  | om-fe-inhouse | 86.089 | 86.064 | 26 | 0 | 25 | 0 | 662 | 0 |
|  |  | om-be-simpel-loop | 69.133 | 60.665 | 9.599 | 0 | 0 | 9.614 | 440 | 0 |
|  |  | om-be-appsmanager | 37.373 | 0 | 0 | 0 | 3.266 | 349 | 0 | 0 |
|  |  | om-be-referensi | 25.283 | 0 | 0 | 0 | 609 | 1 | 0 | 0 |
|  |  | om-be-report | 8.612 | 0 | 0 | 0 | 47 | 0 | 0 | 0 |
|  |  | coredns | 117 | 0 | 0 | 0 | 117 | 0 | 0 | 0 |
| | | **total** | **359.009** | | | | **4.158** | **10.128** | | |
| 2026-09-30 | 10 (1) | nginx-ingress-controller | 26.192 | 24.506 | 1.639 | 490 | 1.690 | 17 | 288 | 677 |
|  |  | om-be-appsmanager | 19.150 | 0 | 0 | 0 | 852 | 32 | 0 | 0 |
|  |  | om-be-referensi | 20.131 | 0 | 0 | 0 | 516 | 0 | 0 | 0 |
|  |  | coredns | 51 | 0 | 0 | 0 | 51 | 0 | 0 | 0 |
| | | **total** | **65.524** | | | | **3.109** | **49** | | |
| 2026-10-01 | 16 (12) | nginx-ingress-controller | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-fe-inhouse | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-simpel-loop | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-appsmanager | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-referensi | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | coredns | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| | | **total** | **4** | | | | **0** | **0** | | |
| 2026-10-02 | 16 (12) | nginx-ingress-controller | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-fe-inhouse | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-simpel-loop | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-appsmanager | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-referensi | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | coredns | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| | | **total** | **4** | | | | **0** | **0** | | |
| 2026-10-03 | 16 (1) | nginx-ingress-controller | 9.586 | 9.314 | 244 | 17 | 18 | 15 | 125 | 245 |
|  |  | om-fe-inhouse | 16.713 | 16.711 | 6 | 0 | 2 | 0 | 268 | 0 |
|  |  | om-be-simpel-loop | 42.994 | 37.244 | 5.084 | 0 | 0 | 5.081 | 501 | 0 |
|  |  | om-be-appsmanager | 19.821 | 0 | 0 | 0 | 1.820 | 91 | 0 | 0 |
|  |  | om-be-referensi | 7.598 | 0 | 0 | 0 | 100 | 1 | 0 | 0 |
|  |  | om-be-report | 3.327 | 0 | 0 | 0 | 9 | 7 | 0 | 0 |
|  |  | coredns | 142 | 0 | 0 | 0 | 142 | 0 | 0 | 0 |
| | | **total** | **100.181** | | | | **2.091** | **5.195** | | |
| 2026-10-04 | 16 (7) | nginx-ingress-controller | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-fe-inhouse | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-simpel-loop | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-appsmanager | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-referensi | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-report | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | coredns | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| | | **total** | **9** | | | | **0** | **0** | | |
| 2026-10-05 | 16 (1) | nginx-ingress-controller | 17.751 | 17.313 | 544 | 0 | 2 | 25 | 147 | 384 |
|  |  | om-fe-inhouse | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-simpel-loop | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-appsmanager | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-referensi | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-report | 545 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
|  |  | coredns | 305 | 0 | 0 | 0 | 305 | 0 | 0 | 0 |
| | | **total** | **18.611** | | | | **309** | **25** | | |
| 2026-10-06 | 18 (1) | nginx-ingress-controller | 125.097 | 124.822 | 4.533 | 51 | 125 | 136 | 516 | 1.242 |
|  |  | om-fe-inhouse | 26.682 | 26.640 | 49 | 0 | 42 | 0 | 286 | 0 |
|  |  | om-be-simpel-loop | 6.398 | 5.981 | 648 | 0 | 0 | 649 | 87 | 0 |
|  |  | om-be-appsmanager | 24.544 | 0 | 0 | 0 | 2.419 | 71 | 0 | 0 |
|  |  | om-be-referensi | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-report | 8.979 | 0 | 0 | 0 | 33 | 0 | 0 | 0 |
|  |  | coredns | 195 | 0 | 0 | 0 | 191 | 0 | 0 | 0 |
| | | **total** | **191.898** | | | | **2.810** | **856** | | |

### 7.1 Angka per fitur

**Ingress nginx**

| Folder | IP asal (alur) | Request serangan | URL serangan | IP penyerang | IP ber-4xx | Klien 401 (IP+endpoint) | Insiden 5xx | Pod backend | Retry | Error koneksi pod | Cek Uptime-Kuma (gagal) | Endpoint ≥5 durasi |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 2026-09-29 | 723 | 155 | 77 | 12 | 233 | 653 | 7 | 21 | 30 | 35 | 699 (0) | 309 |
| 2026-09-30 | 288 | 32 | 19 | 9 | 142 | 151 | 10 | 22 | 825 | 1.200 | 270 (27) | 256 |
| 2026-10-03 | 125 | 10 | 10 | 4 | 50 | 70 | 1 | 14 | 0 | 1 | 364 (0) | 194 |
| 2026-10-05 | 147 | 30 | 15 | 3 | 58 | 139 | 0 | 14 | 1 | 2 | 669 (0) | 200 |
| 2026-10-06 | 516 | 88 | 71 | 14 | 216 | 555 | 1 | 14 | 71 | 74 | 859 (2) | 313 |

**Simpel-loop**

| Folder | Event HTTP | Cocok nginx | Baris jejak | Lambat ≥1 dtk | Laporan Dibuat | Registrasi Laporan | OTP Diminta | OTP Terverifikasi | File Diunggah | Lampiran Ditambahkan | Email Terkirim | Upload ditolak | Email notifikasi | Aktivitas |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 2026-09-26 | 54 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| 2026-09-27 | 2.988 | 0 | 0 | 1 | 1 | 5 | 1 | 1 | 13 | 0 | 6 | 0 | 9 | 29 |
| 2026-09-28 | 7.642 | 0 | 0 | 27 | 6 | 1 | 18 | 7 | 56 | 17 | 9 | 0 | 9 | 336 |
| 2026-09-29 | 60.665 | 22.638 | 300 | 553 | 12 | 108 | 35 | 12 | 314 | 116 | 55 | 18 | 74 | 1.571 |
| 2026-10-03 | 37.244 | 1.580 | 53 | 235 | 10 | 36 | 12 | 10 | 233 | 58 | 25 | 0 | 37 | 1.126 |
| 2026-10-06 | 5.981 | 4.161 | 111 | 27 | 7 | 1 | 7 | 10 | 27 | 2 | 1 | 0 | 2 | 99 |

**Appsmanager**

| Folder | IP login | Password salah | Reset | Login sukses | Akun dianalisis | Restart | JWT < 5 Menit | JWT 5–60 Menit | JWT 1–24 Jam | JWT 1–7 Hari | JWT > 7 Hari | Refresh Token Kedaluwarsa |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 2026-09-26 | 2 | 0 | 0 | 2 | 0 | 4 | 1 | 0 | 0 | 0 | 0 | 0 |
| 2026-09-27 | 21 | 0 | 0 | 23 | 0 | 0 | 85 | 20 | 38 | 15 | 2 | 17 |
| 2026-09-28 | 6 | 1 | 0 | 6 | 1 | 0 | 59 | 17 | 11 | 8 | 4 | 11 |
| 2026-09-29 | 117 | 86 | 24 | 389 | 39 | 0 | 2.057 | 559 | 283 | 226 | 40 | 237 |
| 2026-09-30 | 57 | 14 | 1 | 110 | 9 | 0 | 505 | 158 | 124 | 14 | 5 | 16 |
| 2026-10-03 | 115 | 19 | 0 | 142 | 14 | 0 | 1.108 | 265 | 288 | 57 | 15 | 68 |
| 2026-10-06 | 52 | 19 | 4 | 135 | 10 | 0 | 1.621 | 319 | 263 | 44 | 8 | 48 |

**Report**

| Folder | PDF sukses | PDF gagal | JWT report | Restart |
|---|--:|--:|--:|--:|
| 2026-09-26 | 0 | 0 | 0 | 3 |
| 2026-09-27 | 28 | 0 | 1 | 0 |
| 2026-09-28 | 92 | 1 | 6 | 0 |
| 2026-09-29 | 813 | 32 | 14 | 0 |
| 2026-10-03 | 519 | 2 | 7 | 0 |
| 2026-10-05 | 91 | 0 | 2 | 0 |
| 2026-10-06 | 1.182 | 15 | 15 | 0 |

**Referensi**

| Folder | JWT kedaluwarsa | Restart |
|---|--:|--:|
| 2026-09-26 | 1 | 4 |
| 2026-09-27 | 46 | 0 |
| 2026-09-28 | 41 | 0 |
| 2026-09-29 | 608 | 0 |
| 2026-09-30 | 516 | 0 |
| 2026-10-03 | 99 | 0 |

Angka lain (distribusi level, kategori serangan, semua kunci bisnis dan JWT, jam terisi, endpoint unik,
pesan unik) ada di `00-acuan.json`.

---

## 8. Temuan: perilaku yang tidak jelas dari tampilan

Hal-hal ini memengaruhi arti "setara". Dicatat apa adanya.

**Data**

1. **Nama folder bukan tanggal log.** Folder `2026-09-29` berisi log 28 Sep 00.00–23.59 WIB; folder
   `2026-10-06` berisi 5 Okt. Semua tab "per hari" sebenarnya "per folder ekspor", dan jam di chart
   bertanggal H−1.
2. **Rentang waktu tiap layanan dalam satu folder berbeda.** Contoh folder `2026-10-06`: nginx 5 Okt
   09–24 WIB, appsmanager 11–24, report 00–23, FE 13–23.
3. **File rusak.** 52 dari 195 file berisi 0 baris; folder 10-01, 10-02, 10-04 hanya berisi baris
   `failed to get parse function: unsupported log format` (total 4–9 baris per folder), begitu pula sebagian
   layanan di 10-05 dan 10-06. Baris itu ikut terhitung di "Total baris log".
4. **Simpel-loop dan coredns tidak punya cap waktu.** Chart per jam simpel-loop hanya mencakup event yang
   terkorelasi (37 % pada 09-29, 4 % pada 10-03, 70 % pada 10-06; 0 % bila folder tanpa nginx). Coredns tidak
   punya chart waktu sama sekali.
5. **Struktur folder dua macam**: `2026-09-26` dan `-27` tanpa namespace; sisanya dengan namespace.
   `D.files[*].ns` dihitung tetapi tidak pernah ditampilkan.

**Penghitungan**

6. **KPI yang dihitung dari daftar terpotong.** "Error koneksi ke pod" = panjang `uperr` (maks. 200; nilai
   sebenarnya 1.200 pada 09-30). Hal yang sama berlaku untuk "Retry ke pod lain" (30 kunci), "IP sumber unik"
   (100), "IP dengan login gagal" (100), "Serangan kritis" (300 baris), "Total request" dan "IP tujuan unik"
   di Peta IP (3.000 alur, 3 pod per alur), serta chart jenis error koneksi.
7. **`err` nginx mencampur dua hal**: respons 5xx dan baris error log; `herr` (chart per jam) hanya 5xx.
8. **Level `crit`** dihitung error di ingress nginx tetapi warning di frontend.
9. **Simpel-loop**: event gagal 4xx ditulis aplikasi dengan `[OM-ERROR]`, jadi donat level menampilkan ERROR
   9.614 sementara KPI Error = 0 dan Warning = 9.614 (09-29).
10. **Baris `EXC`** (exception Spring tanpa cap waktu) masuk tabel pesan tetapi tidak menambah KPI Error.
11. **Korelasi lintas folder.** `REQ` global, jadi event simpel-loop bisa cocok dengan request nginx dari
    folder lain, dan jamnya masuk ke folder tempat event itu berada.
12. **Analisis akun dan insiden dihitung per folder**; rangkaian yang melewati batas folder terputus.
13. **Label "Pod dengan retry 502"** menghitung retry dengan status awal apa pun.
14. **"Request lambat ≥ 5 dtk"** hanya menjumlah baris jejak berstatus 2xx; yang 3xx tidak masuk KPI mana pun.

**Dihitung tetapi tidak tampil**

15. `jwt['Refresh Token Kedaluwarsa']` (mis. 237 pada 09-29) tidak ada di chart maupun ringkasan.
16. `S.dur` (rata-rata dan maksimum per endpoint) tidak dipakai template.

**Lain-lain**

17. **Atribusi DB-IP hanya ada di tab Peta IP**, padahal peta dan kolom lokasi juga tampil di halaman
    layanan.
18. **"Self-contained" tidak sepenuhnya**: butuh Chart.js dari CDN dan font Google.
19. **Data pribadi tertanam di HTML**: alamat email/nama akun (tabel login dan analisis akun), IP klien, dan
    hingga 40 contoh baris log asli per layanan.
20. **Nilai yang ditulis mati**: `SERVER_IP`, `SERVER_FALLBACK`, `HOSTS` (6 host), `PROV` (38 provinsi),
    `BIZ_EP`, upstream DNS `10.88.1.100` dalam teks Akar Masalah, awalan `ombudsman-ombudsman-`.
21. **`--watch` membangun ulang semua folder** setiap ada perubahan (14 detik sekarang).
22. Folder `recovery-file/` dan `recovery-file.zip` tidak disentuh `build_dashboard.py` (bukan folder
    bertanggal).

---

## 9. Pertanyaan terbuka

Tidak bisa disimpulkan dari kode; perlu jawaban sebelum PRD/DRD.

1. **"Hari" itu apa?** Folder ekspor (seperti sekarang) atau tanggal kalender WIB tiap baris? Jawabannya
   menentukan apakah angka §7 bisa dibandingkan langsung.
2. **Setara sampai tingkat mana?** Apakah perilaku di §8 butir 6–14 harus ditiru persis (agar angka sama)
   atau boleh diperbaiki, dengan selisihnya dicatat?
3. **Top-N mana yang dipertahankan sebagai batas tampilan**, dan mana yang hanya ada demi ukuran file HTML?
4. **File rusak** (`unsupported log format`): dihitung sebagai baris seperti sekarang, atau ditandai rusak?
5. **`.log` vs `.log.gz`**: apakah memang selalu identik, dan mana yang akan tersedia ke depan?
6. **Simpel-loop dan coredns tanpa cap waktu**: apakah format log di sumbernya bisa ditambah waktu, atau
   tetap bergantung pada korelasi nginx?
7. **Lisensi ip2asn**: kode menyebut "public domain"; perlu dicek ke halaman iptoasn.com apakah ada syarat
   lain. Apakah atribusi DB-IP perlu tampil di setiap halaman yang memuat lokasi?
8. **Dashboard harus bisa dibuka tanpa internet?** (Chart.js dan font sekarang dari CDN.)
9. **Siapa yang boleh membuka dashboard?** Isinya memuat email akun dan IP klien.
10. **Nilai tulis-mati** (IP server, host, DNS upstream): tetap konstanta atau jadi konfigurasi?
11. **Mode `--watch`** masih dibutuhkan, atau cukup "parse sekali per hari"?
12. **Folder tanpa namespace** (09-26, 09-27) masih harus didukung?
13. **Layanan baru**: sekarang folder tak dikenal diam-diam diperlakukan sebagai Spring Boot. Itu disengaja?
