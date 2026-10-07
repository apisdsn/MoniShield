# Changelog

Format mengikuti [Keep a Changelog](https://keepachangelog.com/id/1.1.0/); versi mengikuti [SemVer](https://semver.org/lang/id/).
Mulai repo ini, setiap commit memakai [Conventional Commits](https://www.conventionalcommits.org/id/v1.0.0/)
(lihat `CONTRIBUTING.md`), sehingga bagian *Unreleased* bisa disusun dari riwayat commit.

## [Unreleased]

### Changed
- Repo berdiri sendiri: isi folder `v2/` repo `apisdsn/dashboard-logging` dipindah ke `apisdsn/MoniShield` beserta
  riwayat commit-nya. Folder log bawaan kini `logs/` di folder proyek (dulu folder induk `v2/`).
- Branch: `dev` (pengembangan) → `stg` (uji/staging) → `prd` (produksi); aturan di `CONTRIBUTING.md`.

## [2.0.0] — 2026-10-07

Pengganti dashboard HTML statis lama (`build_dashboard.py` → `dashboard.html`): FastAPI + DuckDB di server, Svelte di
browser, akun berperan (admin/user), dua bahasa (ID/EN), tema terang/gelap, bisa dipakai di ponsel. Angka utamanya diuji
setara dengan sistem lama. Rancangan: `docs/` (PRD, DRD, TRD, rencana `04-rencana.md`).

### Tambahan atas permintaan pemilik

Dirangkum dari catatan rencana (`docs/04-rencana.md`, tahap 12a–25 dan baris penyimpangan 25 (a)–(s)).

**Akun, keamanan, dan basis data**
- Sesi login memakai **JWT**; akun, sesi, audit, dan riwayat impor di **PostgreSQL lewat ORM (SQLAlchemy)**
  (SQLite hanya untuk uji/lokal).
- Deteksi serangan berbasis **OWASP Core Rule Set (CRS)** + kategori **CAPEC**, tingkat paranoia bisa diatur;
  aturan lama tetap tersedia untuk pembanding.
- **Swagger / OpenAPI** di `/api/docs` dilindungi login yang sama dengan dashboard.

**Tampilan**
- Gaya visual mengikuti gambar referensi pemilik (token warna kedua tema, ikon, kartu, chip, tabel).
- Nama aplikasi **MoniShield**; logo perisai yang sama di halaman login, navigasi, Swagger, dan ikon tab; semua sebutan
  "SIMPeL4" di tampilan dan konfigurasi dihapus (nama paket `simpel4` → `monishield`, basis data `monishield.duckdb`).
- Halaman login dengan perisai besar sebagai latar; tombol "tampilkan sandi" dihapus.
- **Navigasi kiri bisa diciutkan** menjadi lajur ikon.
- **Pemilih tanggal** baru (kalender) yang lebih jelas.
- Semua teks dari server ikut diterjemahkan saat mode **English**.
- **Command Center** (peta selebar layar + ringkasan): perubahan vs folder sebelumnya, grafik per jam, butir perhatian
  baru, pembanding **rata-rata 7 folder sebelumnya** (bisa diganti ke "folder sebelumnya").
- **Profil IP** + unduh daftar IP (CSV), keterangan aturan CRS, **pencarian global** (Ctrl+K), kelengkapan data dan
  **heatmap jam × tanggal** di Tren, **ringkasan harian PDF** (1 halaman A4).
- **Animasi alur di peta**: partikel bergerak dari lokasi asal menuju IP tujuan (server), riak saat tiba, garis
  bergradasi menunjukkan arah; tombol jeda; menghormati pengaturan "kurangi gerak".

**Data masuk**
- Tombol **Sinkronkan data** di kepala halaman: mendeteksi folder log baru, memeriksa S3 dulu, lalu ingest.
- **Impor dari S3** dengan daftar izin bucket; `.log.gz` diekstrak otomatis.
- **Sinkron S3 otomatis**: cukup isi folder induk (mis. `s3://simpel4-backup/k8s-logs`), folder tanggal baru diunduh
  dan di-ingest sendiri berkala.
- **Unggah folder log dari browser**.
- **Kelola folder log**: hapus folder dari dashboard dan pulihkan lagi.
- Peringatan khusus bila file dari S3 berisi pesan galat alat ekspor, bukan log.
- **Log dari Kafka** (Rancher cluster logging → Kafka): pesan ditulis ulang menjadi folder yang sama dengan log S3 lalu
  di-ingest berkala (hasil diuji identik dengan S3); kartu status + **"Cek pesan di topic"**; **peta realtime** dengan
  lencana LANGSUNG (hanya koordinat lokasi yang dikirim ke browser, bukan alamat IP).

**Notifikasi dan pengaturan**
- **Notifikasi Telegram / Discord / email** (lonjakan, serangan kritis, ingest gagal, sinkron S3 bermasalah, folder log
  belum datang, ringkasan harian); pesan tanpa alamat IP.
- **Daftar blokir siap pakai** (nginx `deny`, ingress-nginx, teks) dengan pengecualian jaringan sendiri.
- Halaman **Konfigurasi** (admin): AWS S3, folder S3 otomatis, Kafka, MaxMind, notifikasi, daftar blokir, dan status
  kunci yang hanya lewat `.env` — dengan tombol **Uji koneksi**.
- **Semua konfigurasi di `.env`**: halaman Konfigurasi menulis langsung ke file `.env` (langsung berlaku tanpa mulai
  ulang); semua URL sumber unduhan, API Telegram, dan batas yang dulu tertulis di kode kini variabel `.env`.

**Deploy**
- **Docker Compose**: app + PostgreSQL, profil opsional pgAdmin (akun/audit) dan **DbGate** (data log DuckDB lewat
  salinan baca), `kafka` (broker Apache Kafka untuk log Rancher), `https` (Caddy + **sertifikat Let's Encrypt otomatis**),
  `proxy` (sertifikat sendiri).
- Panduan **deploy ke VPS baru sampai bisa dibuka lewat domain**: `docs/07-deploy-vps.md`.
- Dokumen arsitektur, mekanisme, cara pakai, dan alur data (artifact terpisah).

### Diketahui / belum
- Belum diuji di ponsel sungguhan (hanya emulasi 390/360 px).
- Kafka belum diuji terhadap cluster Rancher asli; sertifikat Let's Encrypt baru diuji dengan sertifikat lokal Caddy.
- Kredensial yang diisi lewat layar tersimpan di `.env` tanpa enkripsi tambahan (lindungi izin file dan server).
