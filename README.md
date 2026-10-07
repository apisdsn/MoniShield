# MoniShield (v2) — dashboard log SIMPeL4

Dashboard log SIMPeL4: FastAPI + DuckDB di server, Svelte di browser. Rancangan lengkap ada di `docs/`
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
| `MAXMIND_ACCOUNT_ID`, `MAXMIND_LICENSE_KEY` | opsional: lokasi IP di peta (GeoLite2, gratis). Tanpa ini, atau dengan `S4_OFFLINE=true`, peta tetap jalan tanpa lokasi baru |

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
.venv/bin/python -m simpel4 ingest            # opsional: ingest awal (server juga ingest saat mulai, S4_INGEST_ON_START)
.venv/bin/python -m simpel4 serve             # http://127.0.0.1:8000 (S4_BIND)
```

Buka `http://127.0.0.1:8000`, masuk sebagai `admin` dengan `S4_ADMIN_PASSWORD`, lalu ganti sandi.
Ingest pertama 11 folder ±10–40 detik; setelah itu hanya folder yang baru atau berubah yang diproses.

### 4. Pemakaian sehari-hari

**Folder log baru?** Salin foldernya (`YYYY-MM-DD/…`) ke folder log, lalu admin cukup menekan tombol **Sinkronkan data**
(ikon folder di kepala halaman). Lencana angka di tombol itu menunjukkan jumlah folder baru yang belum masuk; setelah
sinkronisasi dashboard pindah ke folder terbaru. Hanya file baru atau yang berubah yang diproses.

**Menghapus folder dari daftar**: admin → **Ingest & impor** → kartu **Folder log** → **Hapus**. Data folder hilang dari
dashboard; file hasil impor S3 (kotak masuk) bisa ikut dihapus. File di folder log utama tidak pernah dihapus: folder itu
ditandai *Diabaikan* agar sinkronisasi tidak memasukkannya lagi, dan bisa dikembalikan dengan **Pulihkan** + Sinkronkan.


| Perintah (`.venv/bin/python -m simpel4 …`) | Fungsi |
|---|---|
| `status` | konfigurasi efektif (tanpa rahasia), isi database, folder terakhir |
| `ingest [--folder 2026-10-06] [--force] [--offline]` | masukkan folder log baru/berubah; juga bisa dari layar **Ingest & impor** (admin) |
| `derive --all` | hitung ulang agregat tanpa membaca ulang log (mis. setelah memperbarui aturan deteksi) |
| `user list`, `user create` | kelola akun dari baris perintah |
| `refdata [--offline]` | perbarui pemilik & lokasi IP dan berkas peta |
| `import [--dry-run] s3://…/YYYY-MM-DD/` | impor folder log dari S3 (lihat bagian Impor dari S3) |
| `forget YYYY-MM-DD` | hapus data satu folder dari database |

Data ada di `data/` (`simpel4.duckdb`, berkas peta) dan `auth.db` di `S4_STATE_DIR`: **cadangkan `auth.db`**
(akun, sesi, audit); `simpel4.duckdb` bisa dibangun ulang dari folder log. Server memakai satu proses: jangan
menjalankan dua `serve` atau `ingest` bersamaan pada database yang sama (DuckDB mengunci berkasnya).

### 5. Mengembangkan tampilan

```sh
.venv/bin/python -m simpel4 serve             # terminal 1: API di :8000
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
`s3://simpel4-backup/k8s-logs/2026-09-26/`. Server memeriksa tautan terhadap daftar izin, mendaftar objek,
mengunduh file log ke kotak masuk (`S4_INBOX_DIR`, bawaan `data/inbox/`), lalu menjalankan ingest folder itu.
Tautan yang sama dikirim lagi tidak mengunduh ulang objek yang ukuran dan ETag-nya sama.

**Mengaktifkan** (di `.env` server, lalu mulai ulang):

```sh
pip install -e ".[s3]"                                        # boto3
S4_IMPORT_BUCKETS={"simpel4-backup": ["k8s-logs/"]}           # daftar izin bucket -> awalan; {} = impor mati
S4_IMPORT_REGION=ap-southeast-3                               # Jakarta
AWS_ACCESS_KEY_ID=…                                           # kunci akses baca-saja
AWS_SECRET_ACCESS_KEY=…
```

Daftar izin adalah **satu-satunya** pembatas antara layar impor dan bucket lain yang bisa dibaca kunci itu;
ia hanya bisa diubah di konfigurasi server, tidak dari antarmuka. Batas bawaan: 500 objek, 1 GB per objek,
5 GB per impor, 30 menit (`S4_IMPORT_MAX_*`, `S4_IMPORT_TIMEOUT_MINUTES`).

Coba dulu tanpa mengunduh apa pun (membuktikan susunan objek sama dengan folder log lokal):

```sh
python -m simpel4 import --dry-run s3://simpel4-backup/k8s-logs/2026-09-26/
```

Dari sistem luar (otomatis, tanpa orang):

```sh
curl -H "Authorization: Bearer $S4_JOB_TOKEN" -H "X-Requested-With: job" -H "Content-Type: application/json" \
     -d '{"url": "s3://simpel4-backup/k8s-logs/2026-09-26/"}' https://<server>/api/admin/import      # 202 + job_id
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
      "Resource": "arn:aws:s3:::simpel4-backup",
      "Condition": { "StringLike": { "s3:prefix": ["k8s-logs/*"] } }
    },
    {
      "Sid": "BacaObjekLog",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::simpel4-backup/k8s-logs/*"
    }
  ]
}
```

Dashboard hanya memakai dua operasi itu (ListObjectsV2 dan GetObject); tidak ada kode yang menulis,
menghapus, atau mendaftar bucket. Sebelum mengandalkan fitur ini, pastikan server bisa menjangkau S3:
`curl -sI https://s3.ap-southeast-3.amazonaws.com`.
