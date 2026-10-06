# SIMPeL4 Dashboard (v2)

Dashboard log SIMPeL4: FastAPI + DuckDB di server, Svelte di browser. Rancangan lengkap ada di `docs/`
(PRD, DRD, TRD, rencana); folder log lama di folder induk tetap menjadi sumber utama.

## Menjalankan

```sh
cp .env.example .env && chmod 600 .env   # isi rahasia: S4_JWT_SECRET, S4_ADMIN_PASSWORD, dll.
./run.sh                                  # memasang .venv bila belum ada, membangun tampilan, lalu `python -m simpel4 serve`
```

Perintah lain: `python -m simpel4 status`, `ingest`, `derive`, `forget`, `user`, `refdata`, `import` (lihat `--help`).

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
