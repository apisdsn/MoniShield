# 06 — Menjalankan MoniShield dengan Docker

Langkah 7 (`migrate/07-docker-compose.md`), mengikuti TRD §7. Berkas: `Dockerfile`, `docker-compose.yml`,
`.dockerignore`, `.env.example`, `deploy/Caddyfile`, `deploy/pgadmin/servers.json`, `tools/uji_docker.cjs`.

## 1. Layanan

| Layanan | Selalu? | Untuk | Alasan ada |
|---|---|---|---|
| `app` | ya | API + tampilan (hasil build Svelte) + **ingest di dalam proses** | inti; satu-satunya pembuka DuckDB (§3) |
| `postgres` | ya | akun, sesi, audit, riwayat impor S3 | TRD K11: data akun tidak boleh hilang saat `s4-data` dibangun ulang, dan perlu `pg_dump` |
| `ingest` | profil `job`, sekali jalan | memicu ingest di `app` lewat HTTP, menunggu, lalu keluar | titik masuk untuk cron (§4); tanpa volume, tidak membuka DuckDB sendiri |
| `proxy` | profil `proxy`, opsional | HTTPS (Caddy) | hanya bila server belum punya reverse proxy (TRD §7.1 ASUMSI T5); dashboard wajib HTTPS + login |
| `pgadmin` | profil `pgadmin`, opsional | melihat PostgreSQL | permintaan pemilik 2026-10-07 |
| `dbgate` | profil `dbgate`, opsional | melihat **data log** (DuckDB) dan PostgreSQL | permintaan pemilik 2026-10-07: pgAdmin tidak bisa membuka DuckDB |

Tanpa `--profile`, `docker compose up -d` hanya menyalakan `app` dan `postgres`.

## 2. Menjalankan

Prasyarat: Docker Engine 26+ dengan Compose 2.30+ (diuji Engine 29.8, Compose 5.6). Versi itu dibutuhkan untuk
`volume.subpath` di layanan `dbgate`.

```sh
cd v2
cp .env.example .env && chmod 600 .env       # isi: lihat tabel di bawah; .env tidak ikut git maupun image
docker compose build                         # ±1–3 menit pertama kali
docker compose up -d                         # app + postgres; tunggu "healthy":
docker compose ps
```

| Variabel `.env` | Wajib | Isi |
|---|---|---|
| `DOCKER_LOG_DIR` | ya | folder log di **host**, mis. `/srv/log` (dipasang hanya-baca ke `/logs`) |
| `POSTGRES_PASSWORD` | ya | acak, tidak perlu diingat |
| `S4_JWT_SECRET` | ya | acak ≥ 32 karakter |
| `S4_ADMIN_PASSWORD` | ya | sandi admin pertama; wajib diganti saat masuk pertama |
| `S4_JOB_TOKEN` | ya untuk cron | token mesin yang dipakai layanan `ingest` |
| `S4_COOKIE_SECURE` | — | `true` (bawaan) di balik HTTPS; `false` hanya untuk mencoba lewat `http://127.0.0.1:8000` |
| `MAXMIND_ACCOUNT_ID`, `MAXMIND_LICENSE_KEY` | — | lokasi IP di peta (GeoLite2, gratis) |
| `PGADMIN_EMAIL`, `PGADMIN_PASSWORD` | bila pgAdmin | login pgAdmin (email hanya nama login; `.local` diterima) |
| `DBGATE_LOGIN`, `DBGATE_PASSWORD` | bila DbGate | login DbGate; sandi ≥ 12 karakter, tanpa itu DbGate menolak mulai |

Lalu buka `http://127.0.0.1:8000` (atau domain proxy), masuk sebagai `admin` dengan `S4_ADMIN_PASSWORD`, ganti sandi.
Server meng-ingest semua folder saat mulai (`S4_INGEST_ON_START`, bawaan `true`); dashboard sudah bisa dibuka selama itu.

**Server tanpa internet:** isi volume cache dari salinan `.cache` yang sudah ada (±190 MB), sebelum `up`:

```sh
docker compose create                        # membuat volume tanpa menyalakan apa pun
docker run --rm -v "$PWD/../.cache":/src:ro -v monishield_s4-cache:/cache --entrypoint sh monishield:2.0.0 -c 'cp -r /src/. /cache/'
```

**Dari komputer lain:** semua port terikat ke `127.0.0.1` host. Untuk dashboard pakai reverse proxy server (atau
`--profile proxy`). Untuk pgAdmin/DbGate pakai tunnel SSH, mis. `ssh -L 5051:127.0.0.1:5051 server`.

## 3. DuckDB hanya satu pembuka — keputusan

DuckDB mengizinkan **satu proses** membuka file untuk menulis, dan selama itu proses lain tidak bisa membukanya, termasuk
hanya-baca. Pilihan yang dipakai (TRD §7.2, K1): **ingest berjalan di dalam proses `app`**, di thread terpisah, dengan
koneksi DuckDB yang sama. Pembacaan dashboard memakai kursor sendiri dan tetap melihat data lama yang utuh sampai transaksi
ingest per folder di-commit (MVCC DuckDB).

- Layanan `ingest` **tidak** memasang volume data. Ia memanggil `POST /api/admin/ingest` di `app` dengan
  `S4_JOB_TOKEN`, menunggu sampai selesai, lalu keluar dengan kode 0 (berhasil) atau ≠ 0 (gagal / server berhenti).
- Ditolak: "app hanya-baca + ingest menulis file baru lalu ditukar". Cara itu menyalin ±100 MB tiap ingest dan butuh
  `app` membuka ulang koneksi. Lagi pula DuckDB tidak bisa dibuka hanya-baca saat proses lain sedang menulis file yang sama.
- **Penampil luar (DbGate)** juga tidak boleh membuka file milik `app`. Karena itu `app` menulis **salinan baca**
  `/data/snapshot/monishield.duckdb` (`S4_DUCKDB_SNAPSHOT=true`, bawaan di compose) saat mulai bila belum ada dan setiap
  kali ingest selesai. Salinan ditulis ke `.tmp` lalu diganti atomik (`os.replace`); DbGate yang sedang terhubung tetap
  membaca versi lama sampai disambung ulang. Formatnya `STORAGE_VERSION 'v1.2.0'` agar terbaca DuckDB 1.2.1 di DbGate
  6.6.4. Biaya: ±4 detik dan ±50 % ukuran database. Set `S4_DUCKDB_SNAPSHOT=false` bila DbGate tidak dipakai.

Diuji di container (§8): 73 permintaan data dashboard selama ingest paksa 51 detik, semuanya 200 (median 54 ms, maks 610 ms).

## 4. Ingest harian

Server sudah meng-ingest saat mulai. Admin juga bisa menekan **Sinkronkan data** di dashboard. Untuk jadwal tetap, pakai
cron di host:

```cron
# setiap hari 06.15 WIB (server ber-zona Asia/Jakarta); keluaran ke log host
15 6 * * *  cd /srv/monishield/v2 && docker compose run --rm ingest >> /var/log/monishield-ingest.log 2>&1
```

| Keadaan | Yang terjadi |
|---|---|
| Tidak ada folder baru | selesai < 1 detik ("0 file berubah"); hanya file baru/berubah yang di-parse |
| Dijalankan dua kali bersamaan (cron + tombol, atau dua cron) | yang kedua menunggu ingest yang sedang berjalan lalu melaporkan hasilnya ("ingest sudah berjalan di server; menunggu selesai"); tidak ada parse ganda |
| Terputus di tengah (container dimatikan, `kill -9`, listrik) | tiap folder di-commit dalam satu transaksi: folder yang sudah selesai tetap ada, folder yang sedang diproses kembali ke isi sebelumnya. Ingest berikutnya menandai run yang terputus sebagai `gagal` ("terputus: …"), menghapus CSV sementaranya, dan memproses ulang folder yang belum selesai |
| `app` mati / tidak sehat | `ingest` keluar dengan kode ≠ 0 ("server berhenti menjawab saat ingest berjalan"); cron mencatatnya di log |
| Unduhan database acuan gagal | ingest tetap `ok` dengan peringatan "refdata gagal …"; lokasi/pemilik IP memakai berkas lama di cache, atau dikosongkan bila belum pernah ada |

### Folder log tanpa menyalin ke server

- **Sinkron otomatis dari S3**: isi `S4_IMPORT_BUCKETS` dan kunci AWS di `.env`, lalu di layar Ingest & impor isi folder induk
  (mis. `s3://nama-bucket/k8s-logs`) → Simpan & aktifkan (tersimpan di PostgreSQL, tabel `app_setting`). Alternatif: `S4_S3_WATCH` di `.env`.
  `app` memeriksa bucket tiap `S4_S3_WATCH_MINUTES` menit, mengunduh folder tanggal baru ke volume `s4-inbox`, lalu
  meng-ingest-nya. Pemeriksaan pertama 1 menit setelah container mulai. Cron dengan token mesin juga bisa memicunya:
  `curl -X POST -H "Authorization: Bearer $S4_JOB_TOKEN" -H "X-Requested-With: job" http://127.0.0.1:8000/api/admin/import/sync`.
- **Unggah dari browser**: layar Ingest & impor → Unggah folder log. File masuk ke `s4-inbox` lalu di-ingest. Reverse proxy
  di depan `app` harus mengizinkan badan permintaan sebesar file log terbesar (nginx: `client_max_body_size 1024m;`;
  Caddy dari profil `proxy` tidak membatasi).

### Dokumentasi API

Swagger UI di `https://<server>/api/docs` (skema: `/api/openapi.json`), hanya setelah masuk dengan akun dashboard yang
sama. Aset Swagger UI disalin ke image saat build (`web/dist/swagger/`, dari `swagger-ui-dist`); tidak ada CDN.

## 5. Melihat isi database

| Alat | Alamat | Melihat | Catatan |
|---|---|---|---|
| pgAdmin 9.8 | `http://127.0.0.1:5050` | PostgreSQL: `app_user`, `app_session`, `audit_log`, `import_job` | `docker compose --profile pgadmin up -d`. Server "MoniShield" sudah terdaftar (`deploy/pgadmin/servers.json`); sandi basis data = `POSTGRES_PASSWORD` |
| DbGate 6.6.4 | `http://127.0.0.1:5051` | **data log** (DuckDB, salinan baca) + PostgreSQL | `docker compose --profile dbgate up -d`. Kedua koneksi terdaftar dan ditandai read-only |

**Data log tidak ada di PostgreSQL.** Tabel seperti `nginx_access`, `spring_line`, `agg_*`, dan `folder_state` ada di
DuckDB, jadi lihat lewat DbGate. pgAdmin hanya untuk akun dan audit. Bila DbGate menampilkan data lama setelah ingest,
klik kanan koneksi DuckDB lalu pilih *Refresh* / sambung ulang.

DbGate tidak bisa memasang salinan sebagai mount `:ro`: plugin DuckDB-nya selalu membuka berkas dalam mode tulis dan
mengabaikan `READONLY_`. Karena itu yang dipasang hanya **folder** `snapshot/` (`volume.subpath`), baca-tulis. File
DuckDB milik `app` tidak terlihat dari container DbGate. Apa pun yang tertulis hanya mengenai salinan, dan sisa WAL
salinan lama dibuang sebelum salinan baru dipasang.

## 6. Keamanan

- Proses `app` berjalan sebagai pengguna `monishield` (uid 10001), dengan `read_only: true`, `cap_drop: ALL`, dan
  `no-new-privileges`. Hanya volume data dan `/tmp` (tmpfs) yang bisa ditulis.
- Port hanya `127.0.0.1:8000` (dashboard); pgAdmin/DbGate `127.0.0.1:5050/5051` dan hanya bila profilnya dinyalakan.
  PostgreSQL tidak punya port ke host. `proxy` membuka 443.
- Tidak ada rahasia di image maupun `docker-compose.yml`: semua dari `.env`, dan `.env` dikecualikan oleh
  `.dockerignore` dan `.gitignore`. CA proxy untuk build masuk sebagai *build secret*, tidak tersimpan di lapisan image.
- Log (berisi IP dan email pengguna) **tidak pernah** disalin ke image. `.dockerignore` menolak `*.log`, `*.log.gz`, `data/`,
  dan folder tanggal. Log dipasang hanya-baca dari host ke `/logs`.
- Lokasi dan pemilik IP dicocokkan **offline** dari database yang diunduh ke `s4-cache`. Tidak ada IP pengguna yang
  dikirim ke layanan luar.
- Pemeriksaan kesehatan `GET /api/health` tiap 30 detik; `restart: unless-stopped` untuk `app`, `postgres`, `proxy`,
  `pgadmin`, dan `dbgate`.
- pgAdmin: `SERVER_MODE`, tanpa cek versi ke internet. DbGate: menolak mulai tanpa login dan sandi ≥ 12 karakter, karena
  tanpa `LOGIN` DbGate terbuka untuk siapa saja.

## 7. Akses internet (firewall keluar)

Hanya `app`, dan hanya saat ingest (refdata), dengan masa simpan di cache. `S4_OFFLINE=true` mematikan semua unduhan.

| Host | Berkas | Bila gagal |
|---|---|---|
| `iptoasn.com` | `ip2asn-v4.tsv.gz` (pemilik IP) | pemilik IP dari berkas lama / kosong |
| `download.maxmind.com` | GeoLite2-City CSV (butuh akun gratis) | jatuh ke `download.db-ip.com` |
| `download.db-ip.com` | `dbip-city-lite-YYYY-MM.csv.gz` (lokasi IP) | lokasi IP dari berkas lama / kosong |
| `raw.githubusercontent.com` | Natural Earth: daratan, batas negara, provinsi, nama negara | peta memakai berkas lama |
| `download.geonames.org` | `ID.zip` (nama wilayah Indonesia) | label wilayah memakai berkas lama |
| endpoint S3 (bila impor S3 dipakai) | folder log `s3://…` | impor gagal dengan pesan; data lain tidak terpengaruh |

Notifikasi (bila diaktifkan di layar Notifikasi): `api.telegram.org`, `discord.com`, dan/atau server SMTP kantor. Isi pesan
hanya angka ringkasan + tautan dashboard, tanpa alamat IP pengguna.

Saat build saja: `registry-1.docker.io` / `production.cloudflare.docker.com` (image dasar), `registry.npmjs.org`, dan
`pypi.org` + `files.pythonhosted.org`.

## 8. Cadangan dan pembaruan

| Volume | Isi | Cadangkan? |
|---|---|---|
| `s4-pgdata` | akun, sesi, audit | **wajib**: `docker compose exec postgres pg_dump -U monishield monishield > akun.sql` |
| `s4-inbox` | folder log hasil impor S3 | ya (log mentah) |
| `s4-data` | `monishield.duckdb`, salinan baca, berkas peta | tidak wajib: bisa dibangun ulang dari log |
| `s4-cache` | database acuan ±190 MB | tidak: bisa diunduh ulang |
| `s4-pgadmin`, `s4-dbgate` | setelan penampil | tidak |

Pembaruan aplikasi: `git pull && docker compose build && docker compose up -d`. Skema DuckDB diterapkan ulang saat mulai
(aman diulang).

### Ganti nama 2026-10-07 (simpel4 → monishield)

Pengguna dan basis data PostgreSQL di compose kini `monishield` (dulu `simpel4`), berkas DuckDB `monishield.duckdb`
(dulu `simpel4.duckdb`; dipindah otomatis saat server mulai, tanpa ingest ulang), penerbit JWT `monishield` (sesi lama
berakhir, cukup masuk lagi). Volume `s4-pgdata` yang dibuat versi sebelumnya masih berisi pengguna `simpel4`: karena
belum dipasang di server, cukup buat ulang dengan `docker compose down -v` (akun di volume itu ikut terhapus).

## 9. Hasil verifikasi (2026-10-07, mesin pengembang, Docker 29.8.2, Compose 5.6.0)

| # | Langkah | Hasil |
|---|---|---|
| 1 | `docker compose build` | berhasil, 41 detik (lapisan dependensi dari cache); image `monishield:2.0.0` **413 MB di disk / 105 MB terkompresi**; tanpa Node/`node_modules` |
| 2 | `docker compose run --rm ingest` (11 folder, 195 file) | `ok; 195 file dilihat, 195 file berubah … 11 folder berubah; 73.44 detik` (job menunggu ingest saat-mulai yang sedang berjalan); ingest paksa ulang 50.75 detik; tanpa perubahan 0.03 detik |
| 3 | `docker compose up -d` | `app` *healthy* dalam ±11 detik |
| 4 | browser (`tools/uji_docker.cjs`) | 8/8 LULUS: masuk + wajib ganti sandi, Ringkasan (KPI), layanan `nginx-ingress-controller`, Command Center (peta MapLibre), 11 folder, tanpa galat JS; pgAdmin masuk + server terdaftar; DbGate masuk + tabel `nginx_access` terbaca dari salinan |
| 5 | `down` lalu `up -d` | data utuh tanpa ingest ulang (`last_run ok 195`, ingest saat mulai "0 file berubah"); akun admin dengan sandi yang sudah diganti dan 4 baris audit tetap ada |
| — | dashboard selama ingest | 73 permintaan `/api/folders/…` selama ingest paksa 51 detik: 73 OK, 0 gagal |
| — | `kill -9` di tengah ingest | job keluar ≠ 0; setelah `up`, data utuh; sisa `tmp/run-6` (194 MB CSV) dan baris run `berjalan` dibersihkan oleh ingest berikutnya |
| — | ingest saat DbGate membuka salinan | `snapshot_error: None`; salinan diganti, DbGate membaca versi baru setelah sambung ulang |

Masalah yang ditemukan dan diperbaiki saat verifikasi:

- `${PGADMIN_EMAIL:?}` membuat `docker compose up` gagal walau profil pgAdmin tidak dipakai. Sekarang memakai `:-`;
  pgAdmin menolak sendiri bila kosong, dan DbGate memakai pemeriksaan di `entrypoint`.
- pgAdmin menolak email `@….local` → `ALLOW_SPECIAL_EMAIL_DOMAINS`.
- pgAdmin mendengarkan `[::]` dan gagal di jaringan docker tanpa IPv6 → `PGADMIN_LISTEN_ADDRESS=0.0.0.0`.
- DbGate gagal membuka salinan di mount `:ro` → mount folder `snapshot/` baca-tulis (§5).
- `kill -9` meninggalkan CSV sementara dan run `berjalan` → dibersihkan di awal ingest berikutnya.

## 10. Perubahan kode aplikasi di langkah ini

| Berkas | Perubahan | Alasan |
|---|---|---|
| `config.py` | `S4_API_URL` | `ingest` di container memanggil `app` lewat HTTP, tidak membuka DuckDB |
| `config.py`, `db.py`, `api/admin.py`, `api/app.py` | `S4_DUCKDB_SNAPSHOT` + `db.snapshot()` | salinan baca untuk DbGate (§3) |
| `ingest.py` | `_cleanup_killed()` di awal ingest | sisa run yang dimatikan paksa (§4) |
| `cli.py` | `ingest` dengan `S4_API_URL` → lewat API, menunggu, kode keluar | layanan `ingest` / cron |

Uji: `tests/test_ingest.py::test_salinan_baca_untuk_dbgate`,
`::test_dimatikan_paksa_dibersihkan_pada_ingest_berikutnya`, dan `tests/test_api.py::test_salinan_duckdb_untuk_dbgate`.
