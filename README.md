# MoniShield (v2) — dashboard log & keamanan

Dashboard log dan keamanan: FastAPI + DuckDB di server, Svelte di browser. Rancangan lengkap ada di `docs/`
(PRD, DRD, TRD, rencana); folder log lama di folder induk tetap menjadi sumber utama.

## Cara menjalankan

### 1. Prasyarat

| Perangkat | Versi | Untuk |
|---|---|---|
| Python | 3.12 atau lebih baru | server (FastAPI + DuckDB) |
| Node.js + npm | 20.19 atau lebih baru (diuji 22) | membangun tampilan (Svelte/Vite); tidak dibutuhkan saat server berjalan |
| Folder log | `YYYY-MM-DD/<namespace>/<layanan>/…` | data; bawaan: folder induk `v2/` (mis. `../2026-10-06/`) |

### 2. Siapkan konfigurasi

```sh
cd v2
cp .env.example .env && chmod 600 .env
```

Isi minimal di `.env`:

| Variabel | Isi |
|---|---|
| `S4_JWT_SECRET` | rahasia acak ≥ 32 karakter, mis. hasil `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `S4_ADMIN_PASSWORD` | sandi admin pertama (≥ 12 karakter); wajib diganti saat masuk pertama |
| `S4_COOKIE_SECURE` | `true` di server ber-HTTPS; **`false` hanya untuk mencoba di komputer sendiri** lewat `http://` |
| `S4_LOG_DIR` | folder log, bila bukan folder induk `v2/` |
| `MAXMIND_ACCOUNT_ID`, `MAXMIND_LICENSE_KEY` | opsional: lokasi IP di peta (GeoLite2, gratis; bisa juga diisi di layar **Konfigurasi**). Tanpa ini, atau dengan `S4_OFFLINE=true`, peta tetap jalan tanpa lokasi baru |

Pilihan lain (port, impor S3, aturan deteksi serangan, PostgreSQL untuk akun) dijelaskan di `.env.example`.

### 3. Jalankan

Cara singkat (memasang `.venv` bila belum ada, membangun tampilan bila sumbernya berubah, lalu menyalakan server):

```sh
./run.sh
```

Cara manual, langkah demi langkah:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .                    # tambah ".[s3]" untuk impor S3, ".[test,s3]" untuk menjalankan uji
(cd web && npm ci && npm run build)           # hasil di web/dist, dilayani server yang sama
.venv/bin/python -m monishield ingest            # opsional: ingest awal (server juga ingest saat mulai, S4_INGEST_ON_START)
.venv/bin/python -m monishield serve             # http://127.0.0.1:8000 (S4_BIND)
```

Buka `http://127.0.0.1:8000`, masuk sebagai `admin` dengan `S4_ADMIN_PASSWORD`, lalu ganti sandi.
Ingest pertama 11 folder ±10–40 detik; setelah itu hanya folder yang baru atau berubah yang diproses.

### 3b. Atau dengan Docker (server)

```sh
cp .env.example .env && chmod 600 .env        # isi DOCKER_LOG_DIR, POSTGRES_PASSWORD, S4_JWT_SECRET, S4_ADMIN_PASSWORD, S4_JOB_TOKEN
sudo chgrp 10001 .env && chmod 660 .env       # container (uid/gid 10001) boleh menulis .env dari layar Konfigurasi
docker compose build && docker compose up -d  # app + PostgreSQL, http://127.0.0.1:8000
docker compose run --rm ingest                # ingest sekali jalan (untuk cron harian)
docker compose --profile pgadmin up -d        # opsional: pgAdmin  http://127.0.0.1:5050 (akun, sesi, audit)
docker compose --profile dbgate up -d         # opsional: DbGate   http://127.0.0.1:5051 (data log DuckDB + PostgreSQL)
```

Rincian (keputusan DuckDB, cron, keamanan, alamat internet yang dihubungi, cadangan): `docs/06-docker.md`.

### 4. Pemakaian sehari-hari

**Folder log baru?** Salin foldernya (`YYYY-MM-DD/…`) ke folder log, lalu admin cukup menekan tombol **Sinkronkan data**
(ikon folder di kepala halaman). Lencana angka di tombol itu menunjukkan jumlah folder baru yang belum masuk; setelah
sinkronisasi dashboard pindah ke folder terbaru. Hanya file baru atau yang berubah yang diproses.

**Folder baru di S3 diambil sendiri**: **Ingest & impor** → *Sinkron otomatis dari S3* → isi folder induk, mis.
`s3://nama-bucket/k8s-logs` → **Simpan & aktifkan**. Pemeriksaan pertama berjalan beberapa detik kemudian, lalu tiap
jeda yang dipilih (bawaan 1 jam); folder tanggal yang baru diunduh dan di-ingest. Tombol **Sinkronkan data** di kepala
halaman juga memeriksa S3 dulu, lalu folder log lokal. (Alternatif tanpa layar: `S4_S3_WATCH` di `.env`.)

**Konfigurasi (semua kredensial di satu halaman)**: menu user → **Konfigurasi**. Berisi kunci akses AWS S3 + wilayah,
folder induk S3 otomatis, kunci MaxMind GeoLite2, notifikasi, dan pengecualian daftar blokir; tiap bagian punya
**Simpan** dan (untuk AWS/MaxMind) **Uji koneksi**. **Simpan menulis langsung ke file `.env`** (baris yang ada diganti,
komentar tetap) dan langsung berlaku tanpa mulai ulang; **Hapus dari .env** menonaktifkan barisnya (nilai bawaan).
Semua URL/alamat layanan luar dan batas yang dulu tertulis di kode juga ada di `.env` (bagian 10 `.env.example`:
`S4_URL_*`, `S4_TELEGRAM_API`, `S4_*_MAX_AGE_DAYS`, …). Server harus boleh menulis `.env`. Kredensial tidak pernah ditampilkan lagi
(Access Key ID hanya tersamar `AKIA…1234`). Yang tetap hanya lewat `.env` (dasar keamanan server: `S4_JWT_SECRET`,
`S4_JOB_TOKEN`, basis data akun, `S4_ADMIN_PASSWORD`, `S4_IMPORT_BUCKETS`) hanya ditampilkan statusnya.

**Notifikasi**: menu user → **Konfigurasi** → bagian *Notifikasi* → centang Telegram / Discord / Email, isi kredensialnya (token bot + chat ID,
URL webhook, atau server SMTP), **Simpan**, lalu **Kirim uji**. Dikirim saat: lonjakan (≥ 2× rata-rata 7 folder sebanding),
serangan kritis, ingest gagal, sinkron S3 bermasalah, folder log hari ini belum datang (jam bisa diatur), dan — bila
dicentang — ringkasan tiap folder baru. Pesan hanya berisi angka dan tautan, **tanpa alamat IP**; kredensial tidak pernah
ditampilkan lagi setelah disimpan.

**Pembanding**: Command Center membandingkan angka dengan **rata-rata 7 folder sebelumnya** yang lengkap (bisa diganti ke
"Folder sebelumnya"); bila belum ada 3 folder lengkap, otomatis memakai folder sebelumnya.

**Daftar blokir**: Keamanan → **Daftar blokir…** → format nginx (`deny`), ingress-nginx (`denylist-source-range`), atau
teks; rentang 1/7/30 folder; keparahan minimal → **Unduh** / **Salin**. IP privat, jaringan sendiri
(`S4_BLOCKLIST_EXCLUDE_ORG`, bawaan OMBUDSMAN), dan `S4_BLOCKLIST_EXCLUDE` tidak pernah masuk. Periksa dulu sebelum dipasang.

**Dokumentasi API (Swagger)**: menu user → **Dokumentasi API**, atau buka `/api/docs`. Masuk dengan akun yang sama
dengan halaman login (belum masuk → diarahkan ke login lalu kembali); "Try it out" memakai sesi itu dan tetap tunduk pada
peran. Skema mentah: `/api/openapi.json`.

**Unggah dari komputer**: **Ingest & impor** → **Unggah folder log** → **Pilih folder…** (folder `YYYY-MM-DD`, induknya,
atau isi satu tanggal + isi tanggalnya) → **Unggah**. Hanya `.log`/`.log.gz` yang dikirim (batas ukuran sama dengan
impor S3), file masuk ke kotak masuk lalu di-ingest. Di balik nginx, naikkan `client_max_body_size` (bawaan nginx 1 MB).

**Menghapus folder dari daftar**: admin → **Ingest & impor** → kartu **Folder log** → **Hapus**. Data folder hilang dari
dashboard; file hasil impor S3 (kotak masuk) bisa ikut dihapus. File di folder log utama tidak pernah dihapus: folder itu
ditandai *Diabaikan* agar sinkronisasi tidak memasukkannya lagi, dan bisa dikembalikan dengan **Pulihkan** + Sinkronkan.


| Perintah (`.venv/bin/python -m monishield …`) | Fungsi |
|---|---|
| `status` | konfigurasi efektif (tanpa rahasia), isi database, folder terakhir |
| `ingest [--folder 2026-10-06] [--force] [--offline]` | masukkan folder log baru/berubah; juga bisa dari layar **Ingest & impor** (admin) |
| `derive --all` | hitung ulang agregat tanpa membaca ulang log (mis. setelah memperbarui aturan deteksi) |
| `user list`, `user create` | kelola akun dari baris perintah |
| `refdata [--offline]` | perbarui pemilik & lokasi IP dan berkas peta |
| `import [--dry-run] s3://…/YYYY-MM-DD/` | impor folder log dari S3 (lihat bagian Impor dari S3) |
| `forget YYYY-MM-DD` | hapus data satu folder dari database |

Data ada di `data/` (`monishield.duckdb`, berkas peta) dan `auth.db` di `S4_STATE_DIR`: **cadangkan `auth.db`**
(akun, sesi, audit); `monishield.duckdb` bisa dibangun ulang dari folder log. Server memakai satu proses: jangan
menjalankan dua `serve` atau `ingest` bersamaan pada database yang sama (DuckDB mengunci berkasnya).

### 5. Mengembangkan tampilan

```sh
.venv/bin/python -m monishield serve             # terminal 1: API di :8000
cd web && npm run dev                         # terminal 2: Vite di :5173, permintaan /api diteruskan ke :8000
```

## Uji

```sh
.venv/bin/pip install -e ".[test,s3]"
.venv/bin/pytest -q                       # termasuk tests/test_import.py (S3 tiruan lokal, tanpa AWS)
```

Uji browser berdampingan dengan dashboard lama ada di `tools/uji_*.cjs` (Playwright; lihat kepala tiap berkas).

## Impor dari S3

Admin (layar **Ingest & impor**) atau sistem luar ber-token mesin mengirim tautan awalan, mis.
`s3://nama-bucket/k8s-logs/2026-09-26/`. Server memeriksa tautan terhadap daftar izin, mendaftar objek,
mengunduh file log ke kotak masuk (`S4_INBOX_DIR`, bawaan `data/inbox/`), lalu menjalankan ingest folder itu.
Tautan yang sama dikirim lagi tidak mengunduh ulang objek yang ukuran dan ETag-nya sama.

**Mengaktifkan** (di `.env` server, lalu mulai ulang):

```sh
pip install -e ".[s3]"                                        # boto3
S4_IMPORT_BUCKETS={"nama-bucket": ["k8s-logs/"]}              # daftar izin bucket -> awalan; {} = impor mati
S4_IMPORT_REGION=ap-southeast-3                               # Jakarta
AWS_ACCESS_KEY_ID=…                                           # kunci akses baca-saja
AWS_SECRET_ACCESS_KEY=…
```

Daftar izin adalah **satu-satunya** pembatas antara layar impor dan bucket lain yang bisa dibaca kunci itu;
ia hanya bisa diubah di konfigurasi server, tidak dari antarmuka. Batas bawaan: 500 objek, 1 GB per objek,
5 GB per impor, 30 menit (`S4_IMPORT_MAX_*`, `S4_IMPORT_TIMEOUT_MINUTES`).

**Sinkron otomatis tanpa tautan** (permintaan pemilik 2026-10-07): isi folder induknya di layar (lihat Pemakaian sehari-hari), atau di `.env` lalu mulai ulang server:

```sh
S4_S3_WATCH=s3://nama-bucket/k8s-logs/      # harus termasuk S4_IMPORT_BUCKETS; koma untuk lebih dari satu
S4_S3_WATCH_MINUTES=60                         # 0 = hanya tombol "Periksa S3 sekarang" / cron
S4_S3_WATCH_DAYS=30                            # hanya folder 30 hari terakhir (0 = seluruh riwayat)
S4_S3_WATCH_MAX_FOLDERS=3                      # maks. folder baru per pemeriksaan, terbaru dulu
```

Tiap pemeriksaan: daftar folder `YYYY-MM-DD` tepat di bawah awalan (ListObjectsV2 + Delimiter, isi folder tidak
didaftar) → folder yang belum ada di dashboard, folder log, kotak masuk, atau daftar *Diabaikan* diimpor + di-ingest
satu per satu (tercatat di Riwayat impor) → folder hasil sinkron yang masih baru (`S4_S3_WATCH_RECHECK_DAYS`) diperiksa
ulang dan hanya objek baru/berubah yang diunduh. Folder yang dihapus admin ditandai *Diabaikan* sehingga tidak diunduh
lagi (kembalikan dengan **Pulihkan**). Dari cron: `curl -X POST -H "Authorization: Bearer $S4_JOB_TOKEN"
-H "X-Requested-With: job" https://<server>/api/admin/import/sync`.

Coba dulu tanpa mengunduh apa pun (membuktikan susunan objek sama dengan folder log lokal):

```sh
python -m monishield import --dry-run s3://nama-bucket/k8s-logs/2026-09-26/
```

Dari sistem luar (otomatis, tanpa orang):

```sh
curl -H "Authorization: Bearer $S4_JOB_TOKEN" -H "X-Requested-With: job" -H "Content-Type: application/json" \
     -d '{"url": "s3://nama-bucket/k8s-logs/2026-09-26/"}' https://<server>/api/admin/import      # 202 + job_id
curl -H "Authorization: Bearer $S4_JOB_TOKEN" https://<server>/api/admin/import/<job_id>           # status
```

Kredensial tidak pernah dikirim ke browser, tidak muncul di respons API, log, basis data, maupun audit.
Admin bisa menempel kredensial sementara di layar impor (mis. saat kunci server sedang diganti); yang
ditempel hanya disimpan di memori proses dan hilang saat server dimulai ulang. Memutar kunci: ubah `.env`,
mulai ulang `app`.

**Saran keamanan.** Kunci yang dipakai sekarang baca-saja tetapi bisa melihat semua bucket di wilayah Jakarta.
Buat pengguna IAM khusus dashboard yang hanya bisa membaca awalan log, dan pakai kuncinya di server:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DaftarAwalanLog",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::nama-bucket",
      "Condition": { "StringLike": { "s3:prefix": ["k8s-logs/*"] } }
    },
    {
      "Sid": "BacaObjekLog",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::nama-bucket/k8s-logs/*"
    }
  ]
}
```

Dashboard hanya memakai dua operasi itu (ListObjectsV2 dan GetObject); tidak ada kode yang menulis,
menghapus, atau mendaftar bucket. Sebelum mengandalkan fitur ini, pastikan server bisa menjangkau S3:
`curl -sI https://s3.ap-southeast-3.amazonaws.com`.
