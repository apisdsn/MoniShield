# TRD — Kebutuhan teknis dashboard log SIMPEL4 (v2)

Keputusan teknis untuk migrasi. Dasar: [`00-inventaris.md`](00-inventaris.md) ("inv. §x"),
[`01-prd.md`](01-prd.md) (F/B/T/A/P-nn), [`02-drd.md`](02-drd.md) (U/D/Q-nn), ketiganya dibaca ulang dari
file. Dokumen ini tidak berisi kode implementasi; nama tabel, kolom, dan endpoint adalah kontrak.

Stack sudah ditetapkan di konteks: Python + FastAPI, DuckDB, Svelte + Vite, Chart.js, MapLibre GL JS.

**ASUMSI** teknis diberi nomor T-nn dan dirangkum di [§11](#11-asumsi-dan-pertanyaan-terbuka).

### Keputusan pemilik produk (diterima 2026-10-06, saat dokumen ini ditulis)

Empat pertanyaan PRD dijawab. Jawaban ini **mengalahkan** asumsi PRD/DRD yang bertentangan; dampaknya ke
dokumen lain didaftar di §10.

| PRD | Jawaban pemilik | Akibat teknis |
|---|---|---|
| P1, X10 | Ada login dengan dua peran, **admin** dan **user**. **Untuk sementara** hanya itu: user biasa melihat seluruh dashboard; admin juga bisa menambah user. Pembatasan per modul (permintaan awal P1) **ditunda**. | Autentikasi, sesi, dua peran: §8.2–§8.4, §2.6, §5.6 |
| P2 | "Hari" **tetap per folder**. Rencana: otomatisasi; ketika tautan folder di bucket dikirim, folder diunduh dan diolah otomatis. | A1 menjadi keputusan. Impor dari tautan: §3.8, §5.5 |
| X1 | Akun **lokal** di basis data aplikasi ini; bukan SSO. | T6 menjadi keputusan: §8.2 |
| X11 | Rincian perbaikan definisi **disetujui**: sesuai praktik yang baik. | T11 menjadi keputusan: §4.4 |
| DRD Q1 | Tampilan ponsel dikerjakan **serius**. | DRD §8 berlaku penuh, termasuk tabel lebar menjadi kartu baris |
| X9 | Tautan berbentuk awalan S3, mis. `s3://simpel4-backup/k8s-logs/2026-09-26/`. Kredensialnya **kunci akses tetap**, dibuat lewat situs AWS; kunci itu **hanya bisa membaca** (tidak bisa menulis atau menghapus), tetapi bisa melihat **semua bucket di wilayah Jakarta**. | Klien S3, kredensial di `.env`, impor bisa otomatis: §3.8. Karena kuncinya luas, pembatasan di sisi aplikasi wajib |
| P3 | Dashboard dibuka dari **banyak komputer**. | Diakses lewat jaringan, wajib HTTPS dan login; A3 gugur: §7, §8 |
| P4 | Definisi yang salah/janggal **diperbaiki** sesuai praktik yang baik. | Daftar perbaikan dan selisih yang diharapkan: §4.4, §9.3 |

Isi: [1 Arsitektur](#1-arsitektur-dan-alur-data) · [2 Skema](#2-skema-duckdb) · [3 Ingest](#3-ingest) ·
[4 Pakai ulang vs SQL](#4-yang-dipakai-ulang-dan-yang-diganti-sql) · [5 API](#5-kontrak-api) ·
[6 Struktur](#6-struktur-folder-cara-menjalankan-dependensi) · [7 Deploy](#7-deploy-dengan-docker-compose) ·
[8 Keamanan](#8-keamanan) · [9 Uji](#9-strategi-uji) · [10 Dampak ke dokumen lain](#10-dampak-ke-dokumen-lain) ·
[11 Asumsi](#11-asumsi-dan-pertanyaan-terbuka)

---

## 1. Arsitektur dan alur data

### 1.1 Gambaran

```
 folder log (baca-saja)                         satu proses "app"
 <tgl>/[ns/]<layanan>/*.log(.gz)   ┌──────────────────────────────────────────────┐
        │                          │  FastAPI (1 worker)                          │
        │  1. pindai + sidik jari  │   ├─ /api/...      baca tabel agregat        │
        ▼                          │   ├─ /api/admin/ingest   picu ingest         │
 ┌──────────────┐  2. parse        │   └─ berkas statis: aplikasi Svelte, peta    │
 │ proses parser│  (subproses,     │                                              │
 │ rules.py     │   per file)      │  Ingest (thread di proses yang sama)         │
 └──────┬───────┘                  │   3. muat CSV → tabel mentah   ┐ satu        │
        │ CSV sementara            │   4. turunkan agregat (SQL)    │ transaksi   │
        └─────────────────────────►│   5. catat status file         ┘ per folder  │
                                   │                                              │
 database IP (unduhan) ──────────► │   6. lengkapi pemilik & lokasi IP (offline)  │
 .cache: ip2asn, GeoLite2,         │                                              │
 Natural Earth, GeoNames           │        simpel4.duckdb  (satu file)           │
                                   └──────────────────────────────────────────────┘
                                                      ▲
                                    browser ──────────┘  hanya ke server ini
```

### 1.2 Keputusan

| # | Keputusan | Alasan |
|--:|---|---|
| K1 | **Satu proses memiliki file DuckDB**: proses API. Ingest berjalan **di dalam proses itu** (thread latar), bukan proses terpisah. | DuckDB hanya mengizinkan satu proses penulis, dan penulis mengunci file dari proses lain termasuk pembaca. Di dalam satu proses, pembaca dan satu penulis berjalan bersamaan dengan aman (MVCC). Ini menghapus seluruh masalah "bentrok" tanpa mekanisme tukar file. |
| K2 | **Parsing di subproses**, hasilnya CSV sementara; proses utama hanya memuat CSV dan menjalankan SQL. | Parsing adalah pekerjaan CPU Python murni; di thread ia akan menahan GIL dan memperlambat API. Subproses tidak membuka DuckDB, jadi K1 tetap berlaku. `read_csv` juga cara tercepat memasukkan ratusan ribu baris ke DuckDB tanpa pustaka tambahan. |
| K3 | **Dua lapis data**: tabel mentah (satu baris per baris log yang bermakna) dan tabel agregat per folder yang **dimaterialkan saat ingest**. API hanya membaca agregat. | Waktu respons tidak bergantung pada ukuran data mentah (target PRD §5.1 pada data setahun). Data mentah tetap ada untuk menurunkan ulang agregat tanpa parse ulang, untuk korelasi lintas folder, dan untuk analisis lintas folder (T02) kelak. |
| K4 | **Agregat disimpan tanpa dipotong**; top-N diterapkan saat query. | Menyelesaikan M3/B03/B04: KPI dihitung dari data lengkap, tabel bisa "tampilkan berikutnya", filter mencari seluruh data. Batas lama (inv. §5.2) menjadi `limit` bawaan. |
| K5 | **Aturan parse dan klasifikasi dipakai ulang dari sistem lama**, disalin apa adanya ke satu modul; hanya penjumlahan yang pindah ke SQL. | Kesetaraan angka (PRD §6.2) paling mudah dijamin bila regex dan fungsi keputusan tidak ditulis ulang. Rincian di §4. |
| K6 | **Satuan data = folder ekspor** (A1). Setiap baris mentah membawa `folder` dan cap waktu UTC aslinya. | Angka bisa dibandingkan langsung dengan acuan; tampilan per tanggal kalender (T01) tetap mungkin nanti karena waktu asli tersimpan. |
| K7 | **Satu transaksi per folder**: hapus baris lama folder/file yang berubah, muat yang baru, turunkan agregat, catat status. | Pembaca tidak pernah melihat folder setengah jadi; ingest yang terputus tidak meninggalkan sisa; mengulang ingest menghasilkan keadaan yang sama. |
| K8 | **Frontend dibangun menjadi berkas statis** dan dilayani oleh FastAPI yang sama. | Satu layanan, satu port, tanpa CORS; cukup untuk pemakaian internal. |
| K9 | **Teks yang sekarang menjadi data tetap berbahasa Indonesia sebagai pengenal** (kategori serangan, tanda akun, metrik bisnis, kelompok JWT). Terjemahan dilakukan frontend lewat kamus (U15). | Sama dengan sistem lama dan dengan kunci di `00-acuan.json`; API tidak perlu parameter bahasa. |
| K10 | **Kalimat temuan otomatis disusun di frontend** dari data, seperti sekarang. | Kalimatnya dua bahasa dan memuat markup; aturan (inv. §2.4, §2.5) tetap di satu tempat bersama tampilannya. |
| K11 | **Akun, sesi, dan catatan audit disimpan di PostgreSQL lewat ORM (SQLAlchemy)**, terpisah dari DuckDB. *(Diputuskan pemilik 2026-10-06: "untuk token gunakan jwt untuk database gunakan postgresql dan pakai orm".)* | DuckDB dirancang untuk analitik, bukan banyak tulis kecil; dan file DuckDB harus bisa dihapus lalu dibangun ulang dari log tanpa kehilangan akun. ORM membuat kode akun sama di PostgreSQL (server) dan SQLite (uji, jalan lokal tanpa server basis data; dipakai bila `S4_AUTH_DATABASE_URL` kosong). **ASUMSI T16**: keputusan itu berlaku untuk akun, sesi, audit, dan catatan impor saja; data log tetap di DuckDB, karena menggantinya berarti mengulang Tahap 3–9 (skema, ingest, agregat, kesetaraan, gerbang ukuran 4,75 GB/20 ms) dan bertentangan dengan stack di `migrate/00-konteks.md`. Perlu dikonfirmasi pemilik. |
| K12 | **Peran ditegakkan di API**, di satu tempat; menyembunyikan menu admin di frontend hanya kenyamanan. | Banyak komputer berarti API bisa dipanggil langsung; satu-satunya batas yang berarti ada di server. |
| K13 | **Impor dari bucket hanya menambah folder ke direktori "kotak masuk"** lalu memicu ingest biasa. | Satu jalur ingest untuk semua sumber; folder log asli tetap baca-saja. |

---

## 2. Skema DuckDB

Satu file: `simpel4.duckdb`. Konvensi:

- `folder` bertipe `DATE` (nama folder ekspor). Waktu disimpan sebagai `TIMESTAMP` **UTC**; WIB dihitung
  saat menurunkan agregat (`+ 7 jam`). Agregat per jam menyimpan `hour_wib`.
- Kunci tabel mentah adalah `(file_id, line_no)`; **tidak** dipasang sebagai `PRIMARY KEY` di DuckDB.
  Alasan: indeks kunci pada puluhan juta baris memperlambat muat massal dan memakan memori; keunikan sudah
  dijamin oleh pola hapus-lalu-muat per file (K7) dan diperiksa oleh uji (§9.4).
- Tabel agregat kecil; kuncinya dipasang sebagai `PRIMARY KEY`.
- Baris dimuat urut folder, sehingga penyaringan `folder = ?` dilayani statistik min/maks blok DuckDB.
- Teks tidak dipotong saat disimpan. Pemotongan lama (inv. §5.3) diterapkan saat menurunkan agregat, di
  tempat yang sama dengan sistem lama, karena memengaruhi pengelompokan.

### 2.1 Tabel kendali

**`ingest_file`** — satu baris per file log logis. PK `file_id`; unik `relpath`.

| Kolom | Tipe | Isi |
|---|---|---|
| `file_id` | INTEGER | nomor urut |
| `relpath` | VARCHAR | path relatif **tanpa** akhiran `.gz` (identitas logis, §3.2) |
| `source_ext` | VARCHAR | `.log` atau `.log.gz`: berkas yang benar-benar dibaca |
| `folder` | DATE | komponen path pertama |
| `ns` | VARCHAR | komponen tengah, atau `-` |
| `service` | VARCHAR | folder induk file |
| `pod` | VARCHAR | dari nama file (aturan lama, inv. §1.1) |
| `size_bytes` | BIGINT | ukuran berkas yang dibaca (sama dengan `D.files.size`) |
| `mtime_ns` | BIGINT | waktu ubah berkas |
| `sha256` | VARCHAR | sidik jari isi **setelah didekompresi** |
| `lines` | BIGINT | semua baris, termasuk yang tidak ter-parse |
| `err`, `warn` | INTEGER | penghitung lama per file (inv. §4.9) |
| `corrupt_lines` | INTEGER | baris `unsupported log format` (B05) |
| `status` | VARCHAR | `ok`, `kosong`, `rusak`, `gagal` |
| `rules_version` | INTEGER | versi aturan parse saat diproses |
| `ingested_at` | TIMESTAMP | |

**`file_counter`** — penghitung per file untuk baris yang tidak layak disimpan satu per satu.
PK `(file_id, kind, key)`.

| Kolom | Tipe | Isi |
|---|---|---|
| `file_id` | INTEGER | |
| `kind` | VARCHAR | `level` (inv. `extra`), `biz`, `mail` |
| `key` | VARCHAR | mis. `INFO`, `Hibernate SQL`, `Email Terkirim`, `Email Gagal`, jenis email notifikasi |
| `n` | BIGINT | |

Alasan: ±31 ribu baris `Hibernate:` per hari hanya perlu dihitung.

**`folder_state`** — PK `folder`: `derived_at`, `rules_version`, `range_start_utc`, `range_end_utc`,
`lines`, `files`, `files_empty`, `files_corrupt`. Sumber daftar folder dan label rentang waktu (B06).

**`ip_info`** — PK `ip`: `asn` INTEGER, `cc` VARCHAR, `org` VARCHAR, `is_private` BOOLEAN, `city`,
`region`, `country` VARCHAR, `lat`, `lon` DOUBLE, `geo_checked` BOOLEAN, `asn_db_date`, `geo_db_date` DATE.
Menggantikan `D.ipinfo`, `D.geo`, dan `.cache/geo.json`. Diisi untuk **semua** IP yang muncul, bukan hanya
yang tampil.

**`ingest_run`** — riwayat ingest: `run_id`, `started_at`, `finished_at`, `status`, `files_seen`,
`files_changed`, `message`.

### 2.2 Tabel mentah

Semua punya `file_id` INTEGER, `line_no` INTEGER, `folder` DATE (tidak diulang di bawah).

**`nginx_access`** — baris access ingress nginx yang cocok regex (inv. §3.1). ±130 ribu baris/hari.

| Kolom | Tipe | Isi |
|---|---|---|
| `ts_utc` | TIMESTAMP | presisi detik |
| `ip` | VARCHAR | IP klien |
| `method` | VARCHAR | |
| `path` | VARCHAR | path + query, mentah |
| `path_key` | VARCHAR | hasil `path_key()` |
| `status` | SMALLINT | |
| `bytes` | BIGINT | ukuran respons |
| `ua` | VARCHAR | User-Agent utuh |
| `request_time` | DOUBLE | detik |
| `upstream` | VARCHAR | tanpa awalan `ombudsman-ombudsman-`; `-` bila kosong |
| `request_id` | VARCHAR | NULL bila ekor baris tidak cocok |
| `pod_final` | VARCHAR | alamat pod yang menjawab; `-` bila tidak ada (aturan lama) |
| `up_addrs` | VARCHAR[] | daftar alamat percobaan; NULL bila ekor tidak berisi 4 bagian |
| `up_statuses` | VARCHAR[] | status tiap percobaan, sejajar `up_addrs` |
| `attack_cat` | VARCHAR | hasil `classify()`; NULL bila bersih |
| `is_uptime_kuma` | BOOLEAN | UA memuat `Uptime-Kuma` |

**`nginx_error`** — baris error log yang cocok regex (inv. §3.2); dipakai juga untuk error log frontend.

| Kolom | Tipe | Isi |
|---|---|---|
| `service` | VARCHAR | `nginx-ingress-controller` atau `om-fe-inhouse` |
| `ts_utc` | TIMESTAMP | |
| `level` | VARCHAR | `error`, `warn`, `crit`, … |
| `message` | VARCHAR | sampai `, client:` |
| `upstream_host` | VARCHAR | alamat pod; NULL bila bukan error upstream |
| `kind` | VARCHAR | pesan tanpa nomor errno, 100 karakter (aturan lama) |
| `request` | VARCHAR | `METODE path`, 120 karakter |

**`fe_access`** — access log frontend (inv. §3.3). ±86 ribu baris/hari.
Kolom: `ts_utc` TIMESTAMP, `ip` VARCHAR (entri pertama X-Forwarded-For), `method`, `path`, `path_key`
VARCHAR, `status` SMALLINT.

**`sl_event`** — event HTTP simpel-loop (JSON ber-`statusCode`, inv. §3.4). ±60 ribu baris/hari.

| Kolom | Tipe | Isi |
|---|---|---|
| `level` | VARCHAR | dari `[OM-<level>]` |
| `request_id` | VARCHAR | |
| `event` | VARCHAR | `http.request.completed` / `.failed` |
| `method`, `path`, `path_key` | VARCHAR | |
| `status` | SMALLINT | |
| `ip` | VARCHAR | NULL pada event gagal |
| `duration_ms` | DOUBLE | 0 bila tidak ada |
| `failed` | BOOLEAN | |
| `err_name`, `err_message` | VARCHAR | |

Tidak ada kolom waktu: log ini tidak bercap waktu (inv. §8 butir 4).

**`spring_line`** — setiap baris Spring Boot yang cocok regex utama (inv. §3.5). ±7 ribu baris/hari.

| Kolom | Tipe | Isi |
|---|---|---|
| `service` | VARCHAR | |
| `ts_utc` | TIMESTAMP | |
| `level` | VARCHAR | |
| `thread`, `logger` | VARCHAR | |
| `restart_app` | VARCHAR | dari `Started <App> in …` |
| `restart_seconds` | DOUBLE | |
| `jwt_expired_ms` | BIGINT | selisih milidetik |
| `refresh_expired` | BOOLEAN | |
| `pdf_template` | VARCHAR | diisi pada baris `Jasper template path` (template diingat per thread oleh parser) |
| `pdf_failed` | BOOLEAN | path `null` |
| `login_kind` | VARCHAR | `fail`, `lock`, `ok` |
| `login_account` | VARCHAR | teks asli di log |
| `login_ip` | VARCHAR | |

**`coredns_error`** — inv. §3.6. Kolom: `level`, `domain`, `rtype`, `message` VARCHAR.

**`log_message`** — satu baris per pesan ERROR/WARN/EXC yang masuk pengelompokan (setiap pemanggilan
`add_msg` di sistem lama). ±15 ribu baris/hari.
Kolom: `service`, `level` VARCHAR, `msg_key` VARCHAR (`LEVEL | pesan ternormalisasi`), `raw` VARCHAR (baris
asli 600 karakter, **hanya diisi pada kemunculan pertama kunci itu dalam file**; selain itu NULL).
Alasan: contoh baris hanya butuh yang pertama; menyimpan semuanya menggandakan ukuran tanpa guna.

Yang sengaja **tidak** disimpan: baris yang tidak cocok aturan mana pun (banner, stack trace, log pengendali
ingress, lanjutan multi-baris). Mereka hanya menambah `ingest_file.lines`, seperti di sistem lama.

### 2.3 Tabel agregat

Semua berkunci `folder` (+ kolom lain). Diisi ulang per folder pada langkah "turunkan" (§3.4).

| Tabel | Kunci | Kolom lain | Sumber |
|---|---|---|---|
| `agg_service` | folder, service | lines, err, warn, err_http, err_log, files, files_empty, files_corrupt, requests, n4xx, n5xx, ip_unique, users_ok | `ingest_file`, tabel mentah |
| `agg_hour` | folder, service, hour_wib | total, err | nginx/fe/spring; simpel-loop dari korelasi |
| `agg_status` | folder, service, status | n | nginx, fe, sl |
| `agg_endpoint` | folder, service, key | requests, n4xx, n5xx, dur_n, dur_avg, dur_max, p50, p95, p99 | nginx, fe, sl; coredns (`key` = domain) |
| `agg_endpoint_error` | folder, service, status, key | n | nginx/fe: semua 4xx/5xx; sl: hanya event gagal |
| `agg_ip` | folder, service, ip | requests, n4xx, ua_first_4xx | nginx, fe, sl |
| `agg_upstream` | folder, upstream | requests, n5xx | nginx |
| `agg_ua` | folder, ua90 | n | nginx |
| `agg_level` | folder, service, level | n | `file_counter` |
| `agg_message` | folder, service, msg_key | level, n, sample_raw | `log_message` |
| `agg_slow` | folder, seq | duration_ms, key, status | `sl_event` ≥ 1.000 ms |
| `agg_attack_url` | folder, category, method_path | hits, ip_count, top_ip, status_counts MAP(VARCHAR,INTEGER), sizes BIGINT[], upstreams VARCHAR[], ua_first, first_wib, last_wib | nginx |
| `agg_attack_ip` | folder, ip | hits, cats MAP, status_counts MAP, ua_top, first_wib, last_wib | nginx |
| `agg_attack_hour` | folder, hour_wib | n | nginx |
| `agg_login_ip` | folder, ip | fail, lock, ok, accounts VARCHAR[], first_wib, last_wib | `spring_line` |
| `agg_login_hour` | folder, hour_wib | fail, ok | `spring_line` |
| `agg_account` | folder, account | fail, lock, ok, fail_ips VARCHAR[], ok_ips VARCHAR[], flags VARCHAR[], first_wib, last_wib, notes VARCHAR[] | fungsi `accounts()` lama |
| `agg_incident` | folder, seq | start_wib, end_wib, n, upstreams MAP, statuses MAP | fungsi `incidents()` lama |
| `agg_c401` | folder, ip, key | n, peak_per_min, first_wib, last_wib | nginx status 401 |
| `agg_uk_hour` | folder, hour_wib | n, fail | nginx |
| `agg_uk_target` | folder, target | n | nginx |
| `agg_flow` | folder, ip, upstream, pod | n | nginx |
| `agg_pod` | folder, upstream, addr | attempts, n5xx | nginx `up_addrs` |
| `agg_retry` | folder, upstream, addr_first, status_first | n | nginx |
| `agg_corr` | folder | matched, total | sl ⋈ nginx |
| `agg_trace` | folder, ip, status, error, key | n, url, upstream, ua, first_wib, last_wib, max_ms | sl ⋈ nginx |
| `agg_biz` | folder, metric | n | sl + `file_counter` |
| `agg_mail` | folder, kind | n | `file_counter` |
| `agg_activity` | folder, key | n | sl |
| `agg_jwt` | folder, service, bucket | n | `spring_line` |
| `agg_report` | folder, template | ok, fail | `spring_line` |

View (bukan tabel, karena sudah kecil dan terfilter folder):
`v_upstream_error` (`nginx_error` dengan `upstream_host` terisi, layanan ingress), `v_restart`
(`spring_line` dengan `restart_app` terisi, digabung `ingest_file.pod`), `v_attack_cat` (jumlah `hits` per
kategori dari `agg_attack_url`), `v_dns` (`agg_endpoint` layanan coredns).

`agg_service` dan beberapa agregat kecil lain adalah satu-satunya yang dibaca tab Tren, jadi 365 folder
berarti beberapa ribu baris.

### 2.4 Pemetaan field inventaris → kolom

Field = keluaran `summarize()` sistem lama (inv. §1.3). "N" = batas lama, kini `limit` bawaan.

| Field lama | Di v2 | Catatan |
|---|---|---|
| `lines` | `agg_service.lines` = Σ `ingest_file.lines` | |
| `err`, `warn` | `agg_service.err/warn` = Σ `ingest_file.err/warn` | Penghitung per file dari parser; definisi lama kecuali perbaikan §4.4. `err` kini punya rincian `err_http` + `err_log` |
| `hour` | `agg_hour.total` | |
| `herr` | `agg_hour.err` | **diperbaiki**: nginx/FE kini memuat juga baris error log (§4.4 butir 2) |
| `status` | `agg_status` | |
| `paths` (N=20) | `agg_endpoint.requests`; coredns: `key` = domain | |
| `perr` (20) | `agg_endpoint_error` | |
| `pe` | `agg_endpoint.n4xx/n5xx` | |
| `ips` (15) | `agg_ip.requests` | |
| `ip4` (20) | `agg_ip.n4xx`, `ua_first_4xx` | UA dipotong 100 saat diturunkan |
| `up` (12), `up5` | `agg_upstream` | |
| `ua` (12) | `agg_ua` | kunci = 90 karakter pertama |
| `extra` | `agg_level` | **diperbaiki** untuk simpel-loop (§4.4 butir 4) |
| `dur` (15) | `agg_endpoint.dur_avg/dur_max` | tidak ditampilkan (inv. §8 butir 16); disimpan karena gratis |
| `ep` (150, min. 5) | `agg_endpoint` di mana `dur_n ≥ 5` | persentil dengan aturan indeks lama (§4.3) |
| `slow` (15) | `agg_slow` | |
| `msgs` (40) + `samples` | `agg_message` | contoh = `raw` pertama menurut (urutan file, `line_no`) |
| `atk` (300) | `agg_attack_url` | `sizes` = 5 terkecil; `ua_first` = UA kemunculan pertama |
| `atk_ip` (100) | `agg_attack_ip` | |
| `atk_h` | `agg_attack_hour` | |
| `atk_cat` | `v_attack_cat` | |
| `login` (100) | `agg_login_ip` di mana `fail > 0` atau `lock > 0` | |
| `login_h` | `agg_login_hour.fail` | |
| `login_okh` | `agg_login_hour.ok` | |
| `login_ok` | Σ `agg_login_hour.ok` | |
| `users_ok` | jumlah akun unik ber-`login_kind = 'ok'` di `spring_line` (disimpan di `agg_service` sebagai kolom tambahan appsmanager: `users_ok`) | |
| `acct` (150) | `agg_account` | |
| `incidents` | `agg_incident` | |
| `c401` (30) | `agg_c401` | |
| `uk`, `ukf` | `agg_uk_hour` | |
| `uk_t` (5) | `agg_uk_target` | |
| `pod` | `agg_pod` | |
| `retry` (30) | `agg_retry` | |
| `uperr` (200 terakhir) | `v_upstream_error` | |
| `corr` | `agg_corr` | |
| `trace` (300) | `agg_trace` | |
| `biz` | `agg_biz` | |
| `mail` | `agg_mail` | |
| `act` (20) | `agg_activity` | |
| `restart` | `v_restart` | |
| `jwt` | `agg_jwt` | termasuk `Refresh Token Kedaluwarsa` (B07) |
| `rep` | `agg_report` | |
| `flow` (3.000; 3 pod) | `agg_flow` | disimpan per pod; "3 pod teratas" saat query |
| `D.files` | `ingest_file` | |
| `D.ipinfo`, `D.geo` | `ip_info` | |
| `D.hosts`, `D.server` | konfigurasi (§6.3), dikirim lewat `/api/meta` | |
| `D.land` | berkas statis GeoJSON (§5.7) | bukan lagi string path SVG |
| `D.labels` | berkas statis `labels.json` | isi sama |

`err_http` (respons 5xx) dan `err_log` (baris log ber-level error) adalah rincian `err`; lihat §4.4.

### 2.5 Perkiraan ukuran

| Tabel | Baris/hari (folder penuh) | Baris/tahun |
|---|--:|--:|
| `nginx_access` | 130 ribu | 48 juta |
| `fe_access` | 86 ribu | 31 juta |
| `sl_event` | 60 ribu | 22 juta |
| `log_message` | 15 ribu | 5,5 juta |
| `spring_line` | 7 ribu | 2,6 juta |
| semua agregat | beberapa ribu | ±2 juta |

Anggaran PRD ≤ 10 GB/tahun (A8). **ASUMSI T1**: tercapai berkat kompresi kolom DuckDB (path, UA, dan IP
sangat berulang). Angka ini **belum diukur**; pengukurannya adalah pekerjaan pertama setelah ingest jalan
(§9.7). Bila meleset, kolom terboros (`ua`, `path`) dipindah ke tabel kamus; skema lain tidak berubah.

### 2.6 Akun (PostgreSQL lewat ORM, K11)

Model SQLAlchemy di `simpel4/auth.py`; tabel dibuat saat aplikasi mulai (`create_all`). Nama tabel diberi
awalan `app_` karena `user` dan `session` adalah kata kunci di PostgreSQL.

| Tabel | Kunci | Kolom |
|---|---|---|
| `app_user` | `user_id` | `username` (unik, huruf kecil), `display_name`, `role` (`admin` \| `user`), `password_hash`, `password_salt`, `hash_params`, `must_change_password` (0/1), `active` (0/1), `failed_logins`, `locked_until`, `created_at`, `created_by`, `last_login_at` |
| `app_session` | `sid` (acak, dimuat di JWT) | `user_id`, `created_at`, `last_seen_at`, `expires_at`, `ip`, `user_agent` |
| `audit_log` | `id` | `at`, `user_id`, `username`, `action`, `detail`, `ip` |
| `import_job` | `job_id` | `requested_by`, `bucket`, `prefix`, `folder`, `status`, `bytes`, `files`, `skipped`, `message`, `started_at`, `finished_at` |

Belum ada tabel hak akses per modul; bila kelak dibutuhkan, cukup menambah satu tabel `user_module`
(§8.3) tanpa mengubah tabel `app_user`.

Yang tidak disimpan di sini: kata sandi asli, token sesi (JWT) maupun rahasia penanda tangannya, dan kredensial AWS (§3.8).

`ponytail:` skema dibuat dengan `create_all`, tanpa alat migrasi; tambahkan Alembic saat pertama kali ada
perubahan kolom pada basis data yang sudah berisi akun.

---

## 3. Ingest

### 3.1 Urutan

1. **Pindai** folder log: semua `*.log`, dan `*.log.gz` hanya bila `.log` pasangannya tidak ada (aturan
   lama). Folder teratas harus berbentuk tanggal dan path minimal 3 komponen.
2. **Bandingkan** dengan `ingest_file` (§3.2) → daftar file baru, berubah, hilang, dan tidak berubah.
3. Untuk tiap folder yang punya perubahan:
   a. **Parse** file baru/berubah di subproses (paralel per file, maksimum 4) → CSV sementara per tabel.
   b. Dalam **satu transaksi**: hapus baris mentah milik file yang berubah/hilang; muat CSV; perbarui
      `ingest_file` dan `file_counter`; **turunkan** semua agregat folder itu; perbarui `folder_state`.
4. **Korelasi lintas folder** (§3.5) untuk folder lain yang terpengaruh.
5. **Lengkapi `ip_info`** untuk IP yang belum punya data (§3.6).
6. Hapus CSV sementara; catat `ingest_run`.

Hanya satu ingest berjalan pada satu waktu (kunci di dalam proses). Permintaan kedua mendapat jawaban
"sedang berjalan".

### 3.2 Mengenali file

Identitas logis = `relpath` **tanpa `.gz`**. Jadi `x.log` dan `x.log.gz` adalah file yang sama.

| Keadaan | Dikenali dari | Tindakan |
|---|---|---|
| Sudah diproses, tidak berubah | `size_bytes` dan `mtime_ns` sama, `rules_version` sama | Lewati, tanpa membaca isi |
| Disentuh tetapi isinya sama | ukuran/mtime beda, `sha256` sama | Perbarui `mtime_ns` saja |
| **Isinya bertambah** atau berubah | `sha256` beda | Hapus baris file itu, **parse ulang seluruh file**, turunkan ulang folder |
| Pasangan `.log`/`.log.gz` identik | `.log` muncul setelah `.gz` diproses (atau sebaliknya `.log` hilang dan `.gz` tersisa): `sha256` isi terdekompresi sama | Ganti `source_ext` dan `size_bytes` saja; tidak parse ulang |
| Pasangan ternyata **berbeda** | `sha256` beda | Perlakukan sebagai berubah; sumber mengikuti aturan lama (`.log` menang); catat peringatan di `ingest_run` |
| File hilang dari folder | ada di `ingest_file`, tidak ada di disk | Hapus barisnya, turunkan ulang folder |
| **Folder** hilang seluruhnya | tidak ada satu pun file folder itu | **Data dipertahankan** (ASUMSI T2) |
| Aturan parse berubah | `rules_version` di kode > yang tercatat | Parse ulang semua file |

Alasan-alasan:

- **Ukuran + mtime dulu, baru hash**: menjalankan ingest tanpa perubahan harus ≤ 5 detik (PRD §5.2);
  membaca 47 GB/tahun untuk hash tiap kali tidak mungkin. Hash hanya dihitung untuk file yang ukurannya
  atau mtime-nya berubah, dan untuk file baru.
- **Parse ulang seluruh file, bukan melanjutkan dari offset**: parser punya keadaan (template PDF per
  thread, lanjutan multi-baris, "contoh pertama"), dan file terbesar ±60 MB selesai dalam beberapa detik.
  Melanjutkan dari offset menghemat sedikit dan membuka kelas bug yang sulit diuji. Batasnya: bila satu
  file kelak mencapai gigabyte dan ditulis terus-menerus, ini perlu ditinjau.
- **Hash isi terdekompresi**: satu-satunya cara membuktikan pasangan `.log`/`.log.gz` identik (PRD P5),
  dan sekaligus menjawabnya dengan data: perbedaan tercatat sebagai peringatan.
- **T2 (folder hilang → data dipertahankan)**: log mentah ±47 GB/tahun kemungkinan besar akan dipindahkan
  dari server sebelum setahun; dashboard tidak boleh ikut kehilangan sejarah. Sistem lama berperilaku
  sebaliknya (folder hilang = hilang dari dashboard). Penghapusan disediakan sebagai perintah eksplisit.

### 3.3 Aman diulang

- Semua tulis untuk satu folder ada di satu transaksi (K7). Proses mati di tengah = transaksi batal.
- Tidak ada `INSERT` tanpa `DELETE` pasangannya pada kunci yang sama (file untuk tabel mentah, folder untuk
  agregat). Menjalankan ingest dua kali menghasilkan isi tabel yang sama.
- CSV sementara ditulis ke direktori sekali pakai di volume data dan dihapus di akhir, juga saat gagal.
- Satu file gagal di-parse (galat tak terduga): `status = 'gagal'` + pesan; file lain di folder itu tetap
  masuk (PRD §5.2). Baris `unsupported log format` bukan galat: dihitung sebagai baris dan menandai file
  `rusak` (A6, B05).

### 3.4 Menurunkan agregat

Satu berkas SQL per tabel agregat, masing-masing berbentuk "hapus baris folder ini, sisipkan hasil SELECT
atas tabel mentah folder ini". Urutan tetap; dua agregat memakai fungsi Python lama atas hasil query kecil:
`agg_account` (`accounts()`) dan `agg_incident` (`incidents()`).

Perubahan definisi agregat tidak butuh parse ulang: cukup turunkan ulang semua folder dari tabel mentah
(perintah `derive --all`).

### 3.5 Korelasi nginx ↔ simpel-loop

Sistem lama memakai satu kamus request id **untuk semua folder** (inv. §4.4, §8 butir 11); kemunculan
terakhir menang. v2 meniru: `sl_event` digabung dengan `nginx_access` **tanpa** batas folder; bila satu
request id muncul lebih dari sekali, yang dipakai adalah yang terakhir menurut (`relpath`, `line_no`).

Akibat untuk ingest bertahap: folder baru bisa membuat event di folder lama menjadi "cocok". Jadi setelah
memuat folder F, agregat korelasi (`agg_corr`, `agg_trace`, `agg_hour` simpel-loop) diturunkan untuk F
**dan** untuk folder lain yang punya event simpel-loop ber-request-id sama dengan nginx di F.

Diukur pada data sekarang (11 folder, 308.157 request id): **0 kecocokan lintas folder dan 0 request id
ganda**. Jadi dalam praktik langkah ini tidak mengerjakan apa-apa, tetapi tanpa itu kesetaraan tidak
terjamin. Konsekuensi: kriteria PRD "menambah folder ke-12 tidak mengubah angka folder 1–11" berlaku
kecuali untuk tiga agregat korelasi ini (lihat §10).

### 3.6 Pemilik dan lokasi IP

**Diputuskan pemilik (2026-10-06): lokasi IP memakai MaxMind GeoLite2**, menggantikan DB-IP City Lite.
Pemilik jaringan (ASN) tetap dari ip2asn (**ASUMSI T15**: permintaannya hanya soal lokasi).

| Hal | Keputusan |
|---|---|
| Berkas | `GeoLite2-City-CSV` (zip ±49 MB): blok jaringan IPv4 (CIDR) + tabel lokasi. Varian CSV dipilih agar cukup pustaka standar; tidak ada pustaka pembaca `.mmdb` |
| Unduhan | `https://download.maxmind.com/geoip/databases/GeoLite2-City-CSV/download?suffix=zip` dengan `MAXMIND_ACCOUNT_ID` dan `MAXMIND_LICENSE_KEY` dari lingkungan (`.env`). Kredensial sudah diuji diterima MaxMind (2026-10-06) |
| Privasi | Tidak berubah: yang diunduh berkas utuh; pencocokan di server sendiri; tidak ada IP yang dikirim |
| Pencocokan | Blok CIDR diubah menjadi rentang awal–akhir terurut, lalu dicocokkan dengan sapuan yang sama seperti `geo_scan()` lama. Nama kota/provinsi diambil dalam bahasa Inggris (`en`), seperti DB-IP; negara tetap kode ISO |
| Pembaruan | Diunduh ulang bila berkas lebih tua dari 7 hari. Syarat lisensi GeoLite2: tidak memakai basis data yang lebih tua dari 30 hari setelah rilis baru, jadi berkas lama **dihapus** saat yang baru berhasil diunduh |
| Tanpa kunci atau unduhan gagal | Ingest tetap selesai; lokasi kosong untuk IP baru, dengan keterangan (PRD §5.5). **Tidak** jatuh ke DB-IP diam-diam |
| Atribusi | "Produk ini memuat data GeoLite2 buatan MaxMind, tersedia dari https://www.maxmind.com" di setiap peta dan di catatan tabel alur |
| Kesetaraan | Lokasi **tidak lagi** dibandingkan dengan sistem lama (sumbernya berbeda). E3 tetap berlaku untuk pemilik jaringan. Jumlah lokasi/negara di Peta IP masuk daftar selisih yang diharapkan |
| Kredensial | Hanya di `.env`; tidak masuk repo, image, log, maupun respons API |

Butir di bawah ini berlaku seperti semula kecuali kata "DB-IP" dibaca "GeoLite2":

- Sumber, URL, dan umur cache sama dengan sistem lama (inv. §6, §5.5). Unduhan hanya mengambil file utuh;
  tidak ada IP yang dikirim (PRD §5.4).
- Setelah tiap ingest: IP di tabel mentah yang belum ada di `ip_info` dicocokkan dengan fungsi lama
  (`ip_owner`, `geo_scan`). Database 86 MB hanya dibaca bila ada IP baru, seperti sekarang.
- Bila database belum ada dan unduhan gagal: ingest tetap selesai; `ip_info` kosong untuk IP itu; dicoba
  lagi pada ingest berikutnya (PRD §5.5).
- **ASUMSI T3**: hasil untuk satu IP tidak diperbarui ketika database baru diunduh (sama dengan
  `geo.json` lama yang tidak pernah kedaluwarsa). `asn_db_date`/`geo_db_date` dicatat supaya pembaruan
  massal bisa ditambahkan kelak.
- Data peta (daratan, batas, label) dibuat sekali menjadi berkas statis di volume data (§5.7).

### 3.7 Kinerja yang dituju

Parser lama memproses ±55 ribu baris/detik (774 ribu baris dalam 14 detik, termasuk peringkasan). Folder
terbesar (359 ribu baris): parse ±7 detik satu inti, lebih cepat bila paralel; muat CSV dan turunkan agregat
diperkirakan beberapa detik. Target PRD ≤ 60 detik punya kelonggaran besar; tetap diukur (§9.7).

### 3.8 Impor otomatis dari tautan bucket (P2, X9)

Pemilik menerima tautan berbentuk **awalan S3**, mis. `s3://simpel4-backup/k8s-logs/2026-09-26/`, dan
kredensial AWS hanya bisa diperoleh lewat situs AWS. Dashboard harus mengunduh isi awalan itu dan mengolahnya.

**Alur**

1. Admin (lewat layar "Ingest & impor") atau sistem luar ber-**token mesin** mengirim tautan ke
   `POST /api/admin/import` (§5.5).
2. Server memeriksa tautan, **mendaftar objek** di awalan itu, memilih objek yang akan diambil, mengunduhnya
   ke direktori sementara, lalu memindahkan folder `YYYY-MM-DD` secara atomik ke **kotak masuk**
   (`S4_INBOX_DIR`).
3. Ingest biasa (§3.1) dijalankan. Pemindai membaca dua akar: folder log dan kotak masuk. Bila folder
   bertanggal sama ada di keduanya, folder log yang menang dan peringatan dicatat.
4. Status dicatat di `import_job` (bucket, awalan, jumlah objek diambil/dilewati, byte) dan bisa ditanyakan
   lewat API.

**Aturan tautan dan objek**

- Bentuk wajib: `s3://<bucket>/<awalan>/<YYYY-MM-DD>/`. Komponen terakhir harus tanggal yang sah; itulah
  nama folder. Bentuk lain ditolak.
- `<bucket>` harus ada di **daftar izin** (`import_buckets`) dan `<awalan>` harus diawali salah satu
  awalan yang diizinkan untuk bucket itu. Bawaan konfigurasi kosong = fitur mati. Nilai yang diharapkan:
  bucket `simpel4-backup`, awalan `k8s-logs/`.
- Kunci objek, setelah awalan dibuang, harus cocok pola `[ns/]<layanan>/<nama>.log` atau `.log.gz` (pola
  yang sama dengan pemindai, §3.1). Objek lain (mis. `.DS_Store`) dilewati dan dihitung di `skipped`.
  Kunci berisi `..`, garis miring ganda, atau karakter kendali ditolak.
- **Hemat unduhan**: bila `x.log` dan `x.log.gz` sama-sama ada, hanya `.log` yang diambil (aturan lama:
  `.gz` hanya dibaca bila `.log` tidak ada). Objek yang ukuran dan ETag-nya sama dengan unduhan sebelumnya
  tidak diunduh lagi, sehingga mengirim tautan yang sama dua kali murah dan aman.
- Batas: jumlah objek, ukuran per objek, ukuran total (bawaan 500 objek / 1 GB / 5 GB), dan batas waktu.
  Melewati batas = impor gagal tanpa menyentuh kotak masuk.
- Server hanya menghubungi titik akhir S3 resmi untuk wilayah yang dikonfigurasi. Tidak ada URL bebas dari
  pengguna yang diambil, jadi tidak ada celah "server mengambil alamat sembarang".
- Satu impor pada satu waktu; berbagi kunci dengan ingest.

**Kredensial AWS** (diputuskan pemilik, X9)

Kredensialnya **kunci akses tetap** yang dibuat lewat situs AWS. Diberikan ke dashboard lewat variabel
lingkungan standar AWS di `.env` server (tidak masuk image maupun repo), sehingga impor bisa berjalan
**otomatis** tanpa orang. Wilayah bucket: Jakarta (`ap-southeast-3`), bisa diubah lewat `import_region`.

Sebagai cadangan, admin tetap bisa menempel kredensial lain di layar impor (mis. saat kunci di server
sedang diganti); yang ditempel hanya disimpan di memori proses dan hilang saat server dimulai ulang. Urutan
pencarian: yang ditempel admin, lalu variabel lingkungan. Bila tidak ada keduanya, impor menjawab dengan
pesan yang menjelaskan cara memberikannya.

**Kunci itu baca-saja tetapi luas**: menurut pemilik ia tidak bisa menulis atau menghapus, namun bisa
melihat semua bucket di wilayah Jakarta. Akibatnya:

- **Daftar izin bucket dan awalan di aplikasi adalah satu-satunya pembatas** antara layar impor dan bucket
  lain. Ia tidak boleh bisa dimatikan atau dilonggarkan dari antarmuka; hanya dari konfigurasi server.
  Dashboard tidak punya fitur "jelajahi bucket"; ia hanya menerima tautan lengkap yang lolos daftar izin.
- Dashboard hanya memakai dua operasi baca: mendaftar objek dan mengambil objek. Tidak ada kode yang
  menulis, menghapus, atau mendaftar bucket.
- Bila server atau `.env` bocor, tidak ada yang bisa dirusak atau dihapus di AWS, tetapi **isi semua
  bucket** yang bisa dijangkau kunci itu bisa dibaca, bukan hanya log. **Saran** (bukan syarat untuk mulai): buat pengguna IAM khusus dashboard dengan hak baca-saja pada
  `simpel4-backup` awalan `k8s-logs/` saja, dan pakai kunci itu di server. Contoh kebijakannya disertakan
  di README pada tahap pengerjaan.
- Kunci diputar (diganti) cukup dengan mengubah `.env` dan memulai ulang `app`.

**ASUMSI T14**: susunan objek di bawah awalan sama dengan folder log lokal
(`[ns/]<layanan>/log_<layanan>_<pod>_<tanggal>.log[.gz]`). Dibuktikan pada pemakaian pertama dengan
**mode coba** (`simpel4 import --dry-run s3://…`), yang hanya mendaftar objek dan mencetak mana yang akan
diambil atau dilewati, tanpa mengunduh.

Kredensial tidak pernah dikirim ke browser, tidak muncul di respons API, dan tidak ditulis ke log.
`/api/meta` hanya melaporkan "kredensial tersedia: ya/tidak, sumber, kedaluwarsa".

Fitur ini dijadwalkan **setelah** kesetaraan terbukti (PRD R9); antarmuka API-nya ditetapkan sekarang agar
skema dan hak akses tidak berubah lagi.

---

## 4. Yang dipakai ulang dan yang diganti SQL

`build_dashboard.py` tidak boleh diubah dan tidak akan ikut ke dalam image. Jadi bagian yang dipakai ulang
**disalin apa adanya** ke satu modul (`rules.py`) dengan catatan asal baris, dan sebuah uji membandingkan
keluaran modul itu dengan modul lama selama file lama masih ada (§9.2).

### 4.1 Disalin apa adanya

| Dari `build_dashboard.py` | Guna |
|---|---|
| Regex `NGINX`, `FE`, `JAVA`, `NGX_TAIL`, `NGX_ERR`, `LOGIN_FAIL`, `LOGIN_LOCK`, `LOGIN_OK`, pola simpel-loop dan coredns, `MON` | mencocokkan baris |
| `ATTACKS`, `SCANNER_UA`, `path_attack()`, `classify()` | klasifikasi serangan |
| `norm()`, `path_key()` | normalisasi pesan dan path |
| `BIZ_EP`, `jwt_bucket()` | metrik bisnis, kelompok umur JWT |
| `accounts()`, `incidents()`, `dt()` | analisis akun, insiden 5xx |
| `load_ip2asn()`, `ip_owner()`, `fetch()`, `ip_int()`, `geo_scan()` | pemilik dan lokasi IP offline |
| `map_labels()`, `kab_name()`, `PROV` | label wilayah |
| `HOSTS`, `SERVER_IP`, `SERVER_FALLBACK` | menjadi **nilai bawaan konfigurasi** (B11) |
| Aturan pilih file dan nama pod di `build()` | pemindaian |
| Isi `demo()` | menjadi uji unit |

### 4.2 Ditulis ulang dengan perilaku sama

| Bagian lama | Di v2 | Yang berubah |
|---|---|---|
| `parse()` | parser yang **mengeluarkan baris** (ke CSV) alih-alih menambah penghitung. Cabang, urutan pemeriksaan, dan penghitung `err`/`warn`/`lines` per file tetap. | Bentuk keluaran saja. Diuji baris demi baris dan terhadap penghitung parser lama (§9.3) |
| `wib()` | Waktu disimpan UTC presisi detik; WIB dan pemotongan ke menit/jam di SQL | Detik tidak lagi dibuang saat simpan |
| `geolocate()` | Memakai `geo_scan()` lama; cache pindah dari `geo.json` ke `ip_info` | Tempat cache |
| `land_path()` | Diganti berkas GeoJSON untuk MapLibre (DRD §7.2) | Bentuk keluaran |

### 4.3 Diganti SQL

| Bagian lama | Pengganti |
|---|---|
| Semua `Counter` di `parse()` dan `add_attack()` | `GROUP BY` atas tabel mentah → tabel agregat |
| `summarize()` (urut + potong top-N) | `ORDER BY … LIMIT` saat query; batas lama = bawaan |
| `pct()` persentil | Durasi diurutkan per endpoint, diambil elemen ke-`min(n−1, ⌊q·n⌋)` (indeks dari 0), **bukan** fungsi kuantil bawaan DuckDB, supaya angkanya sama |
| `correlate()` | `JOIN sl_event ⋈ nginx_access` pada request id (§3.5) |
| `shown_ips()` | Tidak perlu: `ip_info` berisi semua IP |
| Perhitungan `err`/`warn` per file (`D.files`) | Dikeluarkan parser per file (bukan selisih penghitung) |

Titik rawan kesetaraan yang harus dijaga di SQL:

- **"Yang pertama"**: contoh baris pesan, UA pertama per URL serangan, UA pertama per IP ber-4xx, URL
  pertama per jejak. Semuanya = minimum menurut (`relpath`, `line_no`), yaitu urutan baca sistem lama.
- **"Yang terbanyak"** (IP teratas per URL serangan, UA terbanyak per IP): bila seri, sistem lama memilih
  yang pertama muncul. v2 memakai aturan yang sama (seri → kemunculan pertama).
- **Pemotongan teks sebelum mengelompokkan** (UA 90, path serangan 200 setelah decode, `path_key` 120).
- **Presisi menit** pada analisis akun, insiden, dan puncak 401 per menit.
- **Pengecualian**: status 101 tidak masuk durasi; `ips` simpel-loop hanya dari event ber-`ipAddress`.

### 4.4 Perbaikan definisi (keputusan P4)

Pemilik meminta definisi yang salah atau janggal (inv. §8 butir 6–14) diperbaiki. Rincian tiap perbaikan
di bawah **sudah disetujui pemilik** (X11), dipilih agar angka utama tetap bisa dibandingkan dengan acuan dan
setiap selisih bisa dijelaskan. Semuanya masuk daftar **selisih yang diharapkan** di uji kesetaraan (§9.3).

| # | Inv. §8 | Lama | v2 | Angka yang berubah |
|--:|---|---|---|---|
| 1 | 6 | KPI dihitung dari daftar terpotong (error koneksi pod, retry, IP sumber unik, IP login gagal, serangan kritis, total request dan IP tujuan di Peta IP, chart jenis error koneksi) | Dihitung dari data lengkap (K4) | KPI itu, pada folder yang daftarnya melebihi batas (mis. error koneksi pod 09-30: 200 → 1.200) |
| 2 | 7 | `err` nginx/FE = 5xx + baris error log, tetapi chart per jam (`herr`) hanya 5xx | `err` tetap jumlah keduanya, kini dengan rincian `err_http` dan `err_log`; **chart per jam memuat keduanya** sehingga jumlah per jam = KPI | `herr` nginx dan FE; KPI Error **tidak** berubah |
| 3 | 8 | `crit` = error di ingress, warning di frontend | `error`, `crit`, `alert`, `emerg` = error di **keduanya**; level lain = warning | `err`/`warn` frontend bila ada baris `crit` (pada data sekarang: 0 baris, jadi tidak ada selisih) |
| 4 | 9 | Donat level simpel-loop memakai tag aplikasi: event gagal 4xx terhitung `ERROR` padahal KPI menghitungnya warning | Donat memakai **tingkat efektif**, sama dengan aturan KPI: event gagal 5xx → `ERROR`, event gagal lainnya → `WARN`; baris lain memakai tagnya | `extra` simpel-loop (mis. 09-29: ERROR 9.614 → 0, WARN 0 → 9.614) |
| 5 | 10 | Baris `EXC` tampil di tabel pesan tetapi tidak menambah Error | **Tetap tidak dihitung**: baris itu rincian exception dari baris ERROR di atasnya; menghitungnya berarti menghitung ganda. Diberi keterangan di tabel (DRD U8) | tidak ada |
| 6 | 11 | Korelasi lintas folder | **Dipertahankan** (§3.5): request di batas folder memang satu kejadian | tidak ada |
| 7 | 12 | Analisis akun dan insiden terputus di batas folder | **Tetap per folder**, konsisten dengan P2. Menengok ke folder sebelumnya adalah T02 dan tetap ditunda | tidak ada |
| 8 | 13 | Label "Pod dengan retry 502" | "Pod dengan retry" | teks |
| 9 | 14 | KPI "Request lambat ≥ 5 dtk" hanya menjumlah jejak berstatus 2xx | Menjumlah semua jejak lambat yang **tidak gagal** (termasuk 3xx) | KPI itu, bila ada jejak lambat 3xx |
| 10 | 15 | "Refresh token kedaluwarsa" dihitung tetapi tidak tampil | Ditampilkan (B07) | tampilan |

Yang **tidak** disentuh walau bisa diperdebatkan, karena bukan kesalahan: aturan indeks persentil, definisi
"File kosong" (0 byte), dan baris file rusak yang tetap dihitung sebagai baris (A6).

Angka inti acuan (baris, request, 4xx, 5xx, error, warning, IP unik, alur IP) **tidak** terpengaruh oleh
perbaikan mana pun di atas, kecuali butir 3 bila kelak muncul baris `crit` di frontend.

### 4.5 Dibuang

Penanaman JSON ke HTML, `snapshot()` dan `watch()` (A7), `lru_cache` pada `wib()`, `.cache/geo.json`,
dan path SVG daratan.

### 4.6 Rencana: deteksi serangan dengan OWASP CRS dan penamaan CAPEC

Permintaan pemilik (2026-10-06). Dikerjakan di Tahap 21, **setelah** kesetaraan dengan aturan lama
terbukti, karena mengganti aturan mengubah semua angka tab Keamanan.

| Hal | Keputusan | Alasan |
|---|---|---|
| Cara | **Di skrip**: pola CRS dicocokkan ke URL dan User-Agent di log nginx, saat ingest | Satu-satunya cara yang ada dalam kendali proyek dashboard. Cara **di ingress** (ModSecurity/Coraza mode deteksi) lebih akurat karena memeriksa body, header, dan cookie, tetapi mengubah konfigurasi klaster; diusulkan ke pengelola klaster, bukan dikerjakan di sini |
| Sumber aturan | Satu rilis CRS yang versinya dikunci; diolah sekali oleh alat menjadi berkas JSON yang ikut repo | Tidak ada unduhan saat jalan; perubahan aturan terjadi lewat perubahan versi yang terlihat |
| Berkas CRS yang dipakai | 913 pemindai, 930 LFI, 931 RFI, 932 RCE, 933 PHP, 934 generik, 941 XSS, 942 SQLi, 944 Java; hanya aturan yang sasarannya URI, argumen, atau User-Agent | Sisanya memeriksa bagian request yang tidak ada di log |
| Kategori | Dari tag CAPEC yang sudah dibawa tiap aturan CRS; nama Indonesia dan Inggris dari kamus kecil | Penamaan baku; tidak mengarang kategori sendiri |
| Keparahan | Dari tingkat keparahan aturan CRS (kritis/galat/peringatan/pemberitahuan), dipetakan ke tiga tingkat tag tampilan | Menggantikan tabel keparahan tulis-tangan |
| Tingkat paranoia | 1 (**ASUMSI**, pertanyaan S1) | Paling sedikit salah-tuduh; bisa dinaikkan lewat konfigurasi |
| Mesin regex | Pustaka standar Python. Aturan yang polanya tidak didukung dicatat dan dilewati | Tanpa dependensi baru; yang dilewati terlihat di laporan |
| Penyimpanan | Kolom baru di `nginx_access`: `crs_rules` (daftar ID), `capec`, `crs_severity`, `crs_score`. `attack_cat` lama tetap | Uji kesetaraan lama tetap bisa dijalankan; perbandingan lama vs baru bisa dihitung |
| Tanpa parse ulang | Klasifikasi baru dihitung dari `path` dan `ua` yang sudah tersimpan utuh, per pasangan unik | Mengganti versi CRS tidak butuh membaca log lagi |
| Lisensi | CRS berlisensi Apache 2.0: berkas lisensi dan pemberitahuan disertakan; halaman Keamanan menyebut CRS dan versinya | Kepatuhan |
| Kesetaraan | Angka serangan di tampilan **sengaja berbeda** dari sistem lama setelah tahap ini; dilaporkan per folder (lama vs baru) | Daftar selisih yang diharapkan bertambah satu kelompok: semua angka serangan |

Keterbatasan yang tidak berubah: body POST, header lain, dan cookie tidak ada di log. Bila kelak ingress
menjalankan CRS sendiri, log auditnya menjadi sumber deteksi yang lebih baik dan dashboard perlu parser
tambahan untuk itu.

---

## 5. Kontrak API

### 5.1 Aturan umum

- Awalan `/api`. Hanya `GET`, kecuali pemicu ingest.
- Waktu dalam respons: teks WIB `YYYY-MM-DD HH:MM` (jam: `YYYY-MM-DD HH`), sama dengan format data lama,
  sehingga pemformat tampilan lama (inv. §2.0) dipakai tanpa perubahan.
- Setiap IP dalam respons disertai pemiliknya bila ada: objek `{"ip", "asn", "cc", "org"}`; `asn` null dan
  `cc: "-"` untuk IP privat; hanya `{"ip"}` bila tidak diketahui.
- Respons tab berisi **KPI + seri chart + halaman pertama tiap tabel** (jumlah baris = batas lama) dan
  `total` tiap tabel. Baris berikutnya, filter, dan urut lewat endpoint tabel (§5.4). Ini menjaga satu tab
  ≤ 500 KB (PRD §5.1).
- Galat: `{"error": {"code": "…", "message": "…"}}` dengan status 400 (parameter salah), 401 (belum
  masuk / sesi habis), 403 (bukan admin), 404 (folder / layanan / tabel tidak ada), 409
  (ingest sedang berjalan), 429 (terlalu banyak percobaan masuk), 503 (belum ada data).
- Semua endpoint selain `/api/health` dan `/api/auth/login` butuh sesi. Endpoint data terbuka untuk kedua
  peran; `/api/admin/*` hanya admin (§8.3).
- Cache: respons data membawa `ETag` = waktu ingest terakhir folder itu.

### 5.2 Kerangka

| Endpoint | Guna | Halaman DRD |
|---|---|---|
| `GET /api/health` | Hidup (tanpa data, tanpa sesi) | — |
| `GET /api/meta` | Daftar folder, konfigurasi tampilan, status ingest | Kerangka (§2), pemilih folder (§6.1) |
| `GET /api/folders/{folder}` | Layanan + lencana, file, angka folder sebelumnya untuk perbandingan. | Sidebar, Overview, Pod |

Contoh `GET /api/meta`:

```json
{
  "version": "2.0.0",
  "folders": [
    {"folder": "2026-10-06", "range_start": "2026-10-05 09:00", "range_end": "2026-10-06 00:59",
     "lines": 191898, "services": 7, "files": 18, "files_empty": 1, "files_corrupt": 4},
    {"folder": "2026-10-05", "range_start": "2026-10-04 00:00", "range_end": "2026-10-05 00:59",
     "lines": 18611, "services": 7, "files": 16, "files_empty": 1, "files_corrupt": 9}
  ],
  "hosts": {"om-be-simpel-loop-3000": "https://api-simpel4.ombudsman.go.id"},
  "server": {"ip": "103.170.104.228", "city": "Jakarta", "region": "Jakarta", "cc": "ID",
             "lat": -6.17494, "lon": 106.822},
  "dns_upstream": "10.88.1.100",
  "ip_data": {"owner": true, "location": true},
  "ingest": {"running": false, "last_finished": "2026-10-06 17:51", "last_status": "ok"}
}
```

Contoh `GET /api/folders/2026-10-06` (dipersingkat):

```json
{
  "folder": "2026-10-06", "prev_folder": "2026-10-05",
  "attack_ip_count": 14,
  "services": [
    {"service": "nginx-ingress-controller", "lines": 125097, "err": 125, "warn": 136, "files": 3,
     "requests": 124822, "n4xx": 4533, "n5xx": 51, "prev": {"lines": 17751, "err": 2, "warn": 25}},
    {"service": "om-be-appsmanager", "lines": 24544, "err": 2419, "warn": 71, "files": 3,
     "requests": 0, "n4xx": 0, "n5xx": 0, "prev": {"lines": 3, "err": 0, "warn": 0}}
  ],
  "files": [
    {"service": "nginx-ingress-controller", "pod": "nginx-ingress-controller-5v8j4", "ns": "ingress-nginx",
     "lines": 111301, "err": 110, "warn": 120, "size_bytes": 61938892, "status": "ok"}
  ]
}
```

Aturan "sebanding" dan teks ▲/▼ (inv. §2.0) dihitung frontend dari `prev`, seperti sekarang.

### 5.3 Satu endpoint per halaman

| Endpoint | Parameter | Halaman DRD | Isi |
|---|---|---|---|
| `GET /api/folders/{folder}/overview` | — | §3.1 Overview | periode, error per jam per layanan, 25 pesan teratas lintas layanan. (KPI dan tabel layanan/file dari `/api/folders/{folder}`; bagian "Traffic HTTP" dari endpoint layanan nginx) |
| `GET /api/folders/{folder}/map` | `module` (opsional) | §3.2 Peta IP; peta di §3.10 | daftar modul, 6 KPI, titik lokasi, angka luar negeri / tanpa lokasi, halaman pertama alur |
| `GET /api/trends` | `last` = 14 \| 30 \| 90 \| `all` (bawaan 30) | §3.3 Tren | per folder × layanan: baris, error, warning; nginx total/4xx/5xx; serangan; password salah; reset; 5 metrik bisnis |
| `GET /api/folders/{folder}/security` | — | §3.4 Keamanan | 8 KPI, seri 6 chart, bahan "Temuan utama", halaman pertama 5 tabel |
| `GET /api/folders/{folder}/rootcause` | — | §3.5 Akar Masalah | bahan ringkasan, seri 4 chart, halaman pertama 3 tabel, refresh token kedaluwarsa |
| `GET /api/folders/{folder}/availability` | — | §3.6 Ketersediaan | 7 KPI, seri 3 chart, halaman pertama 4 tabel |
| `GET /api/folders/{folder}/pods` | — | §3.7 Pod | KPI, seri 2 chart, halaman pertama 2 tabel (kesehatan pod dari `/api/folders/{folder}`) |
| `GET /api/folders/{folder}/business` | — | §3.8 Bisnis | 11 KPI + nilai folder sebelumnya, seri 5 chart, 2 tabel |
| `GET /api/folders/{folder}/tracing` | — | §3.9 Pelacakan | `corr`, KPI, seri 2 chart, halaman pertama jejak |
| `GET /api/folders/{folder}/services/{service}` | — | §3.10 Layanan; §3.1 bagian traffic | KPI, per jam, status, upstream, level, 10/20 teratas tiap daftar, kinerja endpoint, pesan |

Bila log yang dibutuhkan halaman tidak ada, respons tetap 200 dengan `"available": false` dan
`"reason"` (`no_nginx`, `no_correlation`, `no_simpel_loop`, `empty`), supaya frontend menampilkan keadaan
kosong yang tepat (DRD §6.6) dan bisa membedakan "0" dari "tidak ada log" (U16).

Contoh `GET /api/folders/2026-10-06/security` (dipersingkat):

```json
{
  "available": true,
  "kpi": {"attack_requests": 88, "attack_ips": 14, "critical_hits": 5, "attack_urls_2xx": 62,
          "login_fail_ips": 9, "accounts_ok_after_fail": 1, "accounts_ok_other_ip": 0, "resets": 4},
  "by_category": [["Probe PHP / CGI", 35], ["Probe file sensitif", 28], ["Scan CMS / WordPress", 15]],
  "by_hour": [["2026-10-05 12", 1], ["2026-10-05 21", 30]],
  "top_ips": [{"ip": "45.148.10.238", "asn": 48090, "cc": "NL", "org": "DMZHOST", "hits": 47,
               "max_severity": 2}],
  "by_owner": [["DMZHOST", 47], ["GOOGLE-CLOUD-PLATFORM", 30]],
  "login_by_hour": [["2026-10-05 12", 2], ["2026-10-05 13", 10]],
  "login_top_ips": [{"ip": "39.194.1.60", "asn": 23693, "cc": "ID", "org": "TELKOMSEL-ASN-ID", "fail": 6}],
  "findings": {
    "log4shell": {"hits": 5, "ips": ["34.19.127.176", "34.19.127.195"],
                  "upstreams": ["cattle-system-rancher-80", "om-fe-inhouse-3000"]},
    "by_critical_category": [],
    "rancher_probe_hits": 25,
    "cloud_owners": ["GOOGLE-CLOUD-PLATFORM", "OVH"],
    "ombudsman_login_ips": ["103.160.147.100"],
    "multi_account_ips": [],
    "accounts_other_ip": []
  },
  "tables": {
    "attack-urls": {"total": 71, "rows": [
      {"category": "Log4Shell / RCE", "method_path": "GET /", "hits": 2, "ip_count": 2,
       "top_ip": {"ip": "34.19.127.176", "asn": 396982, "cc": "US", "org": "GOOGLE-CLOUD-PLATFORM"},
       "status_counts": {"200": 2}, "sizes": [6599, 10046],
       "upstreams": ["cattle-system-rancher-80", "om-fe-inhouse-3000"],
       "ua": "${${4b2w:g:-j}${i6a3:-n}…", "first": "2026-10-05 21:30", "last": "2026-10-05 21:30"}]},
    "attack-ips": {"total": 14, "rows": []},
    "accounts": {"total": 10, "rows": []},
    "login-ips": {"total": 9, "rows": []},
    "ip-4xx": {"total": 216, "rows": []}
  }
}
```

Contoh `GET /api/folders/2026-10-06/map` (dipersingkat):

```json
{
  "available": true, "module": null,
  "modules": ["cattle-system-rancher", "om-be-appsmanager", "om-be-simpel-loop", "om-fe-inhouse"],
  "kpi": {"source_ips": 516, "locations": 222, "countries": 12, "modules": 9, "dest_pods": 15,
          "requests": 124822},
  "abroad_requests": 2030, "unlocated_requests": 0,
  "points": [
    {"lat": -6.2114, "lon": 106.8446, "city": "Jakarta", "region": "Jakarta", "cc": "ID",
     "ips": 211, "requests": 18855, "modules": {"om-be-simpel-loop": 15102, "om-fe-inhouse": 3753}}
  ],
  "tables": {"flows": {"total": 1242, "rows": [
    {"src": {"ip": "103.160.147.100", "asn": 141576, "cc": "ID", "org": "IDNIC-OMBUDSMAN-AS-ID …"},
     "location": {"city": "Jakarta", "region": "Jakarta", "cc": "ID"},
     "module": "om-be-simpel-loop", "requests": 13565,
     "pods": [["10.42.233.181:3000", 6783], ["10.42.233.147:3000", 6782]]}]}}
}
```

Contoh `GET /api/trends?last=30` (dipersingkat):

```json
{
  "folders": ["2026-10-05", "2026-10-06"],
  "services": ["nginx-ingress-controller", "om-be-appsmanager"],
  "lines": {"nginx-ingress-controller": [17751, 125097], "om-be-appsmanager": [3, 24544]},
  "err":   {"nginx-ingress-controller": [2, 125],        "om-be-appsmanager": [0, 2419]},
  "warn":  {"nginx-ingress-controller": [25, 136],       "om-be-appsmanager": [0, 71]},
  "http": {"total": [17313, 124822], "n4xx": [544, 4533], "n5xx": [0, 51]},
  "security": {"attack_requests": [30, 88], "login_fail": [0, 19], "resets": [0, 4]},
  "business": {"Laporan Dibuat": [0, 7], "Registrasi Laporan": [0, 1], "File Diunggah": [0, 27],
               "Email Terkirim": [0, 1], "OTP Diminta": [0, 7]},
  "file_status": {"om-be-appsmanager": ["rusak", "ok"]}
}
```

Layanan yang tidak ada di suatu folder bernilai `null` pada posisi itu ("Tidak Ada" di tabel kelengkapan).

### 5.4 Endpoint tabel

`GET /api/folders/{folder}/tables/{table}` — satu kontrak untuk semua tabel yang bisa dilanjutkan,
difilter, dan diurut (DRD §4.3).

| Parameter | Nilai | Bawaan |
|---|---|---|
| `service` | nama layanan; wajib untuk tabel per layanan | — |
| `module` | modul tujuan; hanya `flows` | semua |
| `q` | teks filter, maks. 200 karakter; substring tanpa beda huruf besar/kecil pada kolom teks tabel itu | kosong |
| `sort` | salah satu kolom yang diizinkan untuk tabel itu | urutan lama |
| `dir` | `asc` \| `desc` | `desc` |
| `limit` | 1–500 | batas lama tabel itu |
| `offset` | ≥ 0 | 0 |

Respons: `{"table": "…", "total": N, "matched": M, "limit": L, "offset": O, "rows": […]}`; bentuk tiap
baris sama dengan yang ada di respons halaman.

| `table` | Halaman | Per layanan | Batas bawaan | Sumber |
|---|---|:-:|--:|---|
| `endpoints` | Layanan | ya | 20 | `agg_endpoint` |
| `endpoint-errors` | Layanan | ya | 20 | `agg_endpoint_error` |
| `endpoint-perf` | Layanan | ya | 25 | `agg_endpoint` (`dur_n ≥ 5`) |
| `endpoint-error-rate` | Layanan | ya | 20 | `agg_endpoint` (≥ 20 request) |
| `slow` | Layanan | ya | 15 | `agg_slow` |
| `ips` | Layanan | ya | 15 | `agg_ip` |
| `user-agents` | Layanan | ya | 12 | `agg_ua` |
| `messages` | Layanan, Overview | ya | 40 | `agg_message` |
| `flows` | Peta IP, Layanan | — | 3.000 → **100** | `agg_flow` |
| `attack-urls` | Keamanan | — | 300 | `agg_attack_url` |
| `attack-ips` | Keamanan | — | 100 | `agg_attack_ip` |
| `accounts` | Keamanan | — | 150 | `agg_account` |
| `login-ips` | Keamanan | — | 100 | `agg_login_ip` |
| `ip-4xx` | Keamanan | — | 20 | `agg_ip` |
| `c401` | Akar Masalah | — | 30 | `agg_c401` |
| `pdf-templates` | Akar Masalah, Bisnis | — | semua | `agg_report` |
| `dns` | Akar Masalah | — | 20 | `v_dns` |
| `upstreams` | Ketersediaan | — | 12 | `agg_upstream` |
| `incidents` | Ketersediaan | — | semua | `agg_incident` |
| `upstream-errors` | Ketersediaan | — | 200 | `v_upstream_error` |
| `uptime-targets` | Ketersediaan | — | 5 | `agg_uk_target` |
| `backend-pods` | Pod | — | semua | `agg_pod` + `agg_retry` |
| `restarts` | Pod | — | semua | `v_restart` |
| `activity` | Bisnis | — | 20 | `agg_activity` |
| `trace` | Pelacakan | — | 300 | `agg_trace` |

Satu penyimpangan dari batas lama: `flows` tampil 100 baris pertama (bukan 3.000) karena kini bisa
dilanjutkan dan difilter; 3.000 baris × sel IP adalah beban render terbesar di halaman lama. KPI dan titik
peta tetap dihitung dari semua alur.

Contoh `GET /api/folders/2026-10-06/tables/c401?limit=2`:

```json
{"table": "c401", "total": 555, "matched": 555, "limit": 2, "offset": 0, "rows": [
  {"client": {"ip": "36.75.23.204", "asn": 7713, "cc": "ID", "org": "TELKOMNET-AS-AP PT Telekomunikasi Indonesia"},
   "endpoint": "GET /tx-laporan/count", "n": 412, "peak_per_min": 24,
   "first": "2026-10-05 17:02", "last": "2026-10-05 23:58"},
  {"client": {"ip": "103.142.111.209", "asn": 38758, "cc": "ID", "org": "HYPERNET-AS-ID PT. HIPERNET INDODATA"},
   "endpoint": "GET /v-monitoring", "n": 180, "peak_per_min": 12,
   "first": "2026-10-05 18:10", "last": "2026-10-05 22:41"}
]}
```

(Angka di contoh §5.2–§5.4 ilustratif untuk bentuk respons; hanya angka yang juga ada di
`00-acuan.json` yang nyata.)

### 5.5 Admin

| Endpoint | Guna |
|---|---|
| `POST /api/admin/ingest` | Memulai ingest di proses API. Badan opsional `{"folder": "YYYY-MM-DD", "force": false}`. Jawaban 202 + `run_id`; 409 bila sedang berjalan |
| `GET /api/admin/ingest/status` | Status ingest berjalan/terakhir: fase, folder, file selesai/total, peringatan |
| `POST /api/admin/derive` | Turunkan ulang agregat dari tabel mentah (semua atau satu folder) |
| `POST /api/admin/forget` | Hapus data satu folder (pengganti perilaku lama "folder hilang") |

| `POST /api/admin/import` | Impor dari awalan S3 (§3.8). Badan `{"url": "s3://simpel4-backup/k8s-logs/2026-09-26/", "dry_run": false}`. Jawaban 202 + `job_id`; `dry_run` hanya mendaftar objek |
| `POST /api/admin/import/credentials` | **Hanya admin** (bukan token mesin). Menyimpan kredensial AWS sementara di memori: `access_key_id`, `secret_access_key`, `session_token`. Jawaban tidak memuat nilainya |
| `DELETE /api/admin/import/credentials` | Menghapus kredensial dari memori |
| `GET /api/admin/import/{job_id}` | Status impor |

Hanya untuk peran **admin**, atau untuk pemanggil mesin dengan token (§8.2): tugas `ingest` di compose dan
sistem luar yang mengirim tautan bucket.

### 5.6 Autentikasi dan pengelolaan user (P1)

| Endpoint | Siapa | Guna |
|---|---|---|
| `POST /api/auth/login` | publik | Badan `{"username", "password"}` → membuat sesi (cookie). 401 dengan pesan yang sama untuk "user tidak ada" dan "sandi salah"; 429 saat dibatasi |
| `POST /api/auth/logout` | sesi | Menghapus sesi |
| `GET /api/me` | sesi | User, peran, `must_change_password` |
| `POST /api/me/password` | sesi | Ganti sandi sendiri (butuh sandi lama); sesi lain user itu dicabut |
| `GET /api/admin/users` | admin | Daftar user |
| `POST /api/admin/users` | admin | Buat user: `username`, `display_name`, `role` (`admin` \| `user`), sandi awal (wajib diganti saat masuk pertama) |
| `PATCH /api/admin/users/{id}` | admin | Ubah nama, peran, aktif/nonaktif |
| `POST /api/admin/users/{id}/reset-password` | admin | Sandi sementara baru; semua sesi user dicabut |
| `DELETE /api/admin/users/{id}` | admin | Hapus user (admin terakhir tidak bisa dihapus/diturunkan) |
| `GET /api/admin/audit` | admin | Catatan audit, terbaru dulu, berhalaman |

Contoh `GET /api/me`:

```json
{"username": "rina", "display_name": "Rina", "role": "user", "must_change_password": false}
```

Contoh `POST /api/admin/users`:

```json
{"username": "budi", "display_name": "Budi", "role": "user", "password": "<sandi awal>"}
```

### 5.7 Berkas statis

| Path | Isi | Dibuat |
|---|---|---|
| `/` dan `/assets/*` | Aplikasi Svelte hasil build, termasuk Chart.js, MapLibre, huruf Outfit dan JetBrains Mono | saat build image |
| `/map/land.geojson` | Daratan Natural Earth 50m | saat ingest pertama, dari cache unduhan |
| `/map/borders-country.geojson` | Batas negara Natural Earth 50m | sama |
| `/map/borders-province-id.geojson` | Batas provinsi Indonesia, Natural Earth 10m | sama |
| `/map/labels.json` | Label negara / provinsi / kabupaten-kota (isi `D.labels`) | sama |
| `/fonts/{fontstack}/{range}.pbf` | Glyph label peta untuk MapLibre, rentang Latin | ikut repo (§6.4) |

Bila berkas `/map/*` belum ada (unduhan gagal), `/api/meta` melaporkannya dan frontend menampilkan keadaan
kosong peta (DRD §6.6).

---

## 6. Struktur folder, cara menjalankan, dependensi

### 6.1 Struktur

```
v2/
├─ README.md
├─ run.sh                    jalankan lokal: satu perintah
├─ pyproject.toml            dependensi Python
├─ config.example.toml       contoh konfigurasi (semua opsional)
├─ simpel4/                  paket Python
│  ├─ config.py              baca konfigurasi + variabel lingkungan
│  ├─ rules.py               salinan aturan lama (§4.1)
│  ├─ parse.py               parser per layanan → baris CSV (§4.2)
│  ├─ ingest.py              pindai, sidik jari, transaksi per folder (§3)
│  ├─ schema.sql             definisi tabel (§2)
│  ├─ derive/                satu .sql per tabel agregat (+ accounts, incidents)
│  ├─ refdata.py             unduhan + pemilik/lokasi IP + berkas peta
│  ├─ db.py                  satu koneksi DuckDB untuk seluruh proses
│  ├─ auth.py                sandi, sesi JWT, peran, audit (ORM, §8)
│  ├─ importer.py            impor dari awalan S3 (§3.8)
│  ├─ api/
│  │  ├─ app.py              FastAPI, berkas statis, galat, header keamanan
│  │  ├─ common.py           validasi parameter, sel IP, endpoint tabel
│  │  └─ overview.py map.py trends.py security.py rootcause.py availability.py
│  │     pods.py business.py tracing.py service.py              ← satu modul per halaman
│  │     admin.py users.py session.py                           ← ingest/impor, user, masuk/keluar
│  └─ cli.py                 serve | ingest | derive | forget | status | user (buat admin pertama)
├─ web/                      Svelte + Vite
│  ├─ package.json  vite.config.js  index.html
│  ├─ public/fonts/          glyph .pbf untuk label peta
│  └─ src/
│     ├─ App.svelte  api.js  state.js (folder, tab, modul ↔ URL)  format.js (waktu, durasi, angka)
│     ├─ theme.css           token DRD §5
│     ├─ i18n/  id.json  en.json
│     ├─ lib/                Kpi, ChartCard, DataTable, IpCell, SeverityTag, Alert, Note, MapView, …
│     └─ pages/              Overview, IpMap, Trends, Security, RootCause, Availability, Pods,
│                            Business, Tracing, Service      ← satu berkas per halaman
│                            Login, ChangePassword, AdminUsers, AdminIngest
├─ tests/
│  ├─ fixtures/lines/        baris log asli per format (dari inv. §3)
│  ├─ test_rules.py  test_parse.py  test_ingest.py  test_api.py  test_auth.py  test_import.py
│  └─ test_equivalence.py    terhadap sistem lama (§9.3)
├─ tools/acuan_lama.py       (sudah ada) angka acuan dari sistem lama
├─ docs/
├─ Dockerfile  docker-compose.yml          (dikerjakan di langkah 7)
└─ data/                     simpel4.duckdb, map/, inbox/, tmp/ (auth.db hanya bila tanpa PostgreSQL)     ← tidak masuk repo
```

Satu modul backend dan satu berkas frontend per halaman memenuhi PRD §5.6 (mengubah satu tab tidak
menyentuh tab lain). Bagian yang dipakai bersama hanya `common.py` dan `web/src/lib/`.

### 6.2 Menjalankan lokal

Prasyarat: Python ≥ 3.11 dan Node.js ≥ 20 (Node hanya untuk membangun frontend).

`./v2/run.sh` melakukan, berurutan dan dilewati bila sudah beres: membuat lingkungan Python dan memasang
dependensi; membangun frontend bila belum ada atau sumbernya berubah; menjalankan server di
`127.0.0.1:8000`; server meng-ingest folder yang belum masuk; membuka browser. Pada jalan pertama skrip
meminta nama dan sandi admin pertama (sekali saja).

Keesokan harinya, perintah yang sama memperbarui (PRD §5.5). Bila server sudah berjalan,
`./v2/run.sh ingest` hanya memicu ingest lewat API (K1).

Mode pengembangan: server Vite dengan proxy `/api` ke FastAPI; tidak dipakai di luar pengembangan.

### 6.3 Konfigurasi

Semua punya nilai bawaan = perilaku sistem lama. **Satu tempat untuk semua konfigurasi dan rahasia: `.env`**
(keputusan pemilik 2026-10-06). Urutan prioritas: variabel lingkungan > `v2/.env` > `config.toml` (opsional)
> nilai bawaan. Setiap kunci di bawah bisa ditulis di `.env` sebagai `S4_<NAMA>` (huruf besar); daftar dan
kamus (`hosts`, `server_fallback`, `import_buckets`) ditulis sebagai JSON satu baris. Rahasia hanya boleh
di `.env`/lingkungan, tidak di `config.toml`, dan tidak pernah dicetak. `.env.example` (ikut repo, tanpa
rahasia) memuat semua kunci beserta nilai bawaannya; `.env` tidak masuk git maupun image. Kunci `S4_*`
yang tidak dikenal di `.env` menggagalkan start, supaya salah ketik tidak diam-diam diabaikan.

| Kunci | Bawaan | Guna |
|---|---|---|
| `S4_LOG_DIR` | folder induk `v2/` | folder log (dibaca saja) |
| `S4_DATA_DIR` | `v2/data` | DuckDB, berkas peta, CSV sementara |
| `S4_CACHE_DIR` | `<log dir>/.cache` | unduhan; bawaan lokal memakai cache lama agar tidak mengunduh ulang 100 MB |
| `S4_BIND` | `127.0.0.1:8000` | alamat dengar |
| `S4_INGEST_ON_START` | `true` | ingest saat server mulai |
| `S4_STATE_DIR` | `v2/data` | `auth.db` SQLite, hanya bila `S4_AUTH_DATABASE_URL` kosong |
| `S4_AUTH_DATABASE_URL` | kosong | **Rahasia.** URL PostgreSQL akun: `postgresql+psycopg://user:sandi@host:5432/db` |
| `S4_JWT_SECRET` | — (wajib) | **Rahasia.** Penanda tangan token sesi, minimal 32 karakter acak; server menolak mulai bila kosong atau pendek |
| `S4_INBOX_DIR` | `v2/data/inbox` | folder hasil impor bucket (§3.8) |
| `S4_ADMIN_USER`, `S4_ADMIN_PASSWORD` | kosong | membuat admin pertama **hanya bila belum ada user**; sandi wajib diganti saat masuk pertama |
| `MAXMIND_ACCOUNT_ID`, `MAXMIND_LICENSE_KEY` | kosong | unduhan GeoLite2 untuk lokasi IP (§3.6); tanpa keduanya lokasi kosong |
| `S4_JOB_TOKEN` | kosong | token untuk pemanggil mesin: tugas `ingest` dan pengirim tautan bucket (§8.2) |
| `S4_COOKIE_SECURE` | `true` | cookie hanya lewat HTTPS; `false` hanya untuk jalan lokal tanpa TLS |
| `import_buckets` | kosong (impor mati) | daftar izin: bucket → awalan yang boleh, mis. `simpel4-backup` → `k8s-logs/` |
| `import_region` | `ap-southeast-3` | wilayah bucket (Jakarta) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | kosong | kredensial baca-saja untuk impor; nama standar AWS |
| `import_max_objects`, `import_max_object_mb`, `import_max_total_mb` | 500, 1024, 5120 | batas impor |
| `session_idle_minutes`, `session_max_hours` | 60, 12 | umur sesi |
| `server_ip`, `server_fallback` | nilai lama | titik tujuan peta |
| `hosts` | 6 entri lama | upstream → base URL |
| `dns_upstream` | `10.88.1.100` | teks Akar Masalah |
| `upstream_prefix` | `ombudsman-ombudsman-` | awalan upstream yang dibuang |

### 6.4 Dependensi

Prinsip: sesedikit mungkin; pustaka standar dulu.

**Python (jalan)**

| Paket | Guna |
|---|---|
| `duckdb` | penyimpanan dan query |
| `fastapi` | API dan penyajian berkas statis |
| `uvicorn` | server ASGI |

| `sqlalchemy` | ORM untuk akun, sesi, audit (K11) |
| `psycopg[binary]` | penggerak PostgreSQL |
| `pyjwt` | membuat dan memeriksa token sesi (JWT HS256) |

Hash sandi tetap `hashlib.scrypt` dari pustaka standar; token mesin dibandingkan dengan `hmac`.

**Python (opsional, hanya untuk impor S3)**

| Paket | Guna |
|---|---|
| `boto3` | mendaftar dan mengunduh objek S3 dengan kredensial AWS (termasuk token sesi, halaman daftar, percobaan ulang) |

Dipasang sebagai tambahan opsional (`simpel4[s3]`) dan hanya diimpor saat fitur dipakai; tanpa paket ini
dashboard berjalan penuh dan impor menjawab "tidak tersedia". Alasan tidak menulis sendiri: menandatangani
permintaan AWS dengan tangan adalah kode keamanan yang mudah salah di kasus tepi, sedangkan ini satu-satunya
tempat dashboard memegang kredensial pihak lain.

Sengaja tidak dipakai: pandas/pyarrow (CSV dari pustaka standar cukup), ORM (SQL ditulis langsung),
penjadwal (pemicu dari luar), pustaka HTTP (unduhan memakai `urllib`, seperti sekarang), pustaka geo (label
dan lokasi sudah ditangani fungsi lama).

**Python (uji)**: `pytest` (menjalankan uji), `httpx` (dibutuhkan klien uji FastAPI).

**Frontend (jalan)**

| Paket | Guna |
|---|---|
| `svelte` | komponen tampilan |
| `chart.js` | chart (sama dengan sekarang, versi 4) |
| `maplibre-gl` | peta |
| `@fontsource/outfit`, `@fontsource/jetbrains-mono` | huruf dibundel, tanpa Google Fonts (B09) |

**Frontend (bangun)**: `vite`, `@sveltejs/vite-plugin-svelte`.

Sengaja tidak dipakai: SvelteKit dan pustaka router (tiga parameter URL ditangani `state.js`), pustaka i18n
(dua berkas JSON dan satu fungsi), pustaka komponen UI, pustaka state, pembungkus Chart.js.

**Aset yang ikut repo**: glyph `.pbf` untuk label peta (dua rentang Latin, dua ketebalan, ±200 KB).
MapLibre butuh glyph dalam format ini dan biasanya mengambilnya dari server pihak ketiga; menyimpannya di
repo adalah cara memenuhi "tanpa domain luar". **ASUMSI T4**: memakai Noto Sans (lisensi OFL) dari kumpulan
glyph siap pakai; huruf label peta jadi berbeda dari Outfit di antarmuka.

---

## 7. Deploy dengan Docker Compose

Berkas `Dockerfile` dan `docker-compose.yml` ditulis di langkah 7; yang diputuskan di sini:

### 7.1 Pembagian layanan

| Layanan | Peran | Membuka DuckDB? |
|---|---|:-:|
| `app` | Satu-satunya layanan yang berjalan terus: API + frontend statis + ingest di dalam proses. **Uvicorn 1 worker.** | **ya, satu-satunya** |
| `ingest` | Tugas sekali jalan (profil `job`): memanggil `POST /api/admin/ingest` di `app` dengan `S4_JOB_TOKEN`, menunggu selesai, keluar dengan kode sukses/gagal. Tidak memasang volume apa pun. | tidak |
| `proxy` | Terminasi **HTTPS** di depan `app`. Wajib ada karena dashboard dibuka dari banyak komputer (P3) dan cookie sesi hanya dikirim lewat HTTPS. Bisa proxy yang sudah ada di server, atau layanan di compose ini (ASUMSI T5). | tidak |
| `postgres` | PostgreSQL untuk akun, sesi, audit (K11). Hanya terjangkau dari `app` di jaringan compose, tanpa port ke luar; sandi dari `.env`. | tidak |

DuckDB tetap tertanam di `app`; satu-satunya layanan basis data adalah `postgres` untuk akun. Tidak ada layanan frontend terpisah (K8).
**ASUMSI T5**: langkah 7 menyertakan layanan `proxy` di compose dengan sertifikat yang disediakan pemilik
server; bila server sudah punya proxy, layanan itu dilewati dan `app` cukup didaftarkan di proxy tersebut.

### 7.2 Berbagi file DuckDB tanpa bentrok

Tidak dibagi: hanya `app` yang membukanya (K1). `ingest` hanya pemicu lewat HTTP. Aturan yang menjaganya:

- `app` berjalan dengan **satu worker**; lebih dari satu berarti lebih dari satu proses penulis. Ini
  ditulis sebagai konstanta, bukan konfigurasi.
- Perintah baris (`simpel4 ingest|derive|forget`) selalu mencoba API dulu; membuka DuckDB sendiri hanya
  bila server tidak berjalan, dan gagal dengan pesan jelas bila file terkunci.
- Pembaca tidak pernah terblokir: ingest menulis dalam transaksi; permintaan API selama ingest melihat
  keadaan sebelum transaksi selesai.
- Batas yang diterima: API tidak bisa diskalakan ke banyak proses. Untuk beberapa pengguna internal dan
  query atas agregat kecil ini bukan masalah.

### 7.3 Volume dan pemasangan

| Pemasangan | Jenis | Mode | Isi |
|---|---|---|---|
| folder log di host → `/logs` | bind | **baca-saja** | ekspor log; mode baca-saja juga menjamin aturan "jangan ubah folder log" |
| `s4-data` → `/data` | volume bernama | baca-tulis | `simpel4.duckdb`, berkas peta, CSV sementara |
| `s4-cache` → `/cache` | volume bernama | baca-tulis | unduhan ip2asn, GeoLite2, Natural Earth, GeoNames (±70 MB) |
| `s4-pgdata` → data PostgreSQL | volume bernama | baca-tulis | akun, sesi, audit, catatan impor. **Tidak bisa dibangun ulang**; wajib dicadangkan (`pg_dump`) |
| `s4-inbox` → `/inbox` | volume bernama | baca-tulis | folder log hasil impor bucket (§3.8) |

Empat volume dipisah menurut sifatnya: `s4-data` bisa dibangun ulang dari log, `s4-cache` bisa diunduh
ulang, `s4-state` tidak tergantikan, `s4-inbox` adalah log mentah yang hanya ada di sini (dan di bucket). Path folder log di host diberikan lewat variabel `.env`.

### 7.4 Lain-lain

- **Image**: dua tahap; tahap Node membangun `web/`, tahap Python hanya membawa paket, hasil build, dan
  glyph. Berjalan sebagai pengguna bukan root.
- **Port**: `app` tidak membuka port ke luar; hanya `proxy` yang membuka 443. Bila memakai proxy server
  yang sudah ada, port `app` dipetakan ke `127.0.0.1` host saja.
- `app` mempercayai header `X-Forwarded-For`/`-Proto` **hanya** dari proxy itu (untuk catatan audit dan
  pembatasan percobaan masuk).
- **Pemeriksaan kesehatan**: `GET /api/health`.
- **Ingest harian**: dua jalur. (a) Folder log yang dipasang: cron di host menjalankan
  `docker compose run --rm ingest` setelah ekspor log tiba (ASUMSI T7; jam ekspor belum diketahui).
  (b) Bucket: pengirim tautan memanggil `POST /api/admin/import` (§3.8), yang berakhir dengan ingest. `S4_INGEST_ON_START` juga menangkap folder yang terlewat saat
  layanan dimulai ulang.
- **Jaringan keluar**: untuk mengunduh database IP dan data peta (`iptoasn.com`, `download.maxmind.com`
  dan penyimpanan unduhannya, `raw.githubusercontent.com`, `download.geonames.org`), dan ke S3
  wilayah bucket (`s3.ap-southeast-3.amazonaws.com` dan `simpel4-backup.s3.ap-southeast-3.amazonaws.com`). Bila server
  tidak punya akses keluar, volume `s4-cache` diisi manual; ingest tetap berjalan tanpa lokasi/pemilik.
- **Cadangan**: `s4-state` wajib (akun dan audit). `s4-data` bisa dibangun ulang dari log selama log
  masih ada; karena T2 membuatnya satu-satunya salinan setelah log lama dipindahkan, ia juga perlu ikut
  jadwal cadangan server (salin file saat `app` berhenti, atau lewat perintah ekspor).
- **Sumber daya**: batas memori DuckDB dan jumlah thread ditetapkan lewat konfigurasi; nilai awal 1 GB.

---

## 8. Keamanan

### 8.1 Validasi parameter

| Parameter | Aturan |
|---|---|
| `folder` | harus `YYYY-MM-DD` yang sah **dan** ada di `folder_state`; selain itu 404 |
| `service` | harus ada di folder itu (dicocokkan dengan data, bukan pola) |
| `table` | daftar tetap di §5.4 |
| `sort` | daftar kolom tetap per tabel; nilai dipetakan ke nama kolom oleh kode, tidak pernah disisipkan dari masukan |
| `dir` | `asc` \| `desc` |
| `limit`, `offset` | bilangan bulat dalam rentang; `limit` maks. 500 |
| `module` | harus salah satu modul di folder itu |
| `q` | maks. 200 karakter; selalu sebagai **parameter terikat**; karakter pola (`%`, `_`) di-escape |
| `last` | `14` \| `30` \| `90` \| `all` |
| `username` | 3–32 karakter `[a-z0-9._-]`; disimpan huruf kecil |
| `password` | 12–128 karakter; ditolak bila sama dengan username |
| `role` | `admin` \| `user` |
| `url` (impor) | harus `s3://<bucket>/<awalan>/<YYYY-MM-DD>/`; bucket dan awalan dari daftar izin (§3.8) |
| kredensial AWS | panjang dan pola karakter kunci akses diperiksa; nilainya tidak pernah dipantulkan dalam galat |

Aturan umum:

- Semua nilai masuk ke SQL sebagai parameter terikat. Tidak ada SQL yang dirangkai dari teks masukan.
- Tidak ada parameter yang menjadi path berkas. Berkas statis hanya dari dua direktori tetap.
- Isi log adalah **data tak tepercaya** (URL serangan memuat `<script>`, `${jndi:…}`). Frontend
  menampilkannya sebagai teks; Svelte meng-escape secara bawaan dan `{@html}` **tidak dipakai** untuk apa
  pun yang berasal dari log. Kalimat temuan yang butuh huruf tebal disusun dari komponen, bukan dari HTML
  dalam string (di sistem lama HTML dirangkai sebagai string).
- Header: `Content-Security-Policy` dengan `default-src 'self'` (ditambah `worker-src blob:` dan
  `img-src 'self' data: blob:` yang dibutuhkan MapLibre), `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, `frame-ancestors 'none'`. CSP sekaligus **menegakkan** aturan privasi:
  browser menolak permintaan ke domain luar walau ada kode yang mencobanya.
- Tanpa CORS (asal yang sama).
- Ukuran respons dan `limit` dibatasi; query berjalan dengan batas waktu.

### 8.2 Login dan sesi (keputusan P1, P3)

Dashboard dibuka dari banyak komputer dan memuat email akun, IP klien, URL lengkap, dan contoh baris log
(inv. §8 butir 19). Maka: **semua akses lewat HTTPS dan butuh login.**

| Hal | Keputusan | Alasan |
|---|---|---|
| Akun | Dibuat oleh admin. Tidak ada pendaftaran sendiri dan tidak ada "lupa sandi" lewat email; admin memberi sandi sementara. | Pengguna sedikit dan dikenal; tanpa ketergantungan email |
| Admin pertama | Dari `S4_ADMIN_USER`/`S4_ADMIN_PASSWORD` saat belum ada user, atau perintah `simpel4 user`. Wajib ganti sandi saat masuk pertama. | Tidak ada sandi bawaan di kode |
| Sandi | Minimal 12 karakter, tanpa aturan komposisi. Disimpan sebagai hash **scrypt** bergaram per user; parameter disimpan agar bisa dinaikkan. Perbandingan waktu-konstan. | Rekomendasi umum (panjang lebih berarti daripada komposisi); scrypt ada di pustaka standar |
| Sesi | **JWT** (HS256, ditandatangani `S4_JWT_SECRET`) berisi `sub` (id user), `sid` (id sesi), `iat`, `exp`; dikirim hanya lewat **cookie** `HttpOnly`, `Secure`, `SameSite=Strict`, tidak diterima dari header `Authorization`. Setelah tanda tangan, penerbit, dan masa berlaku lolos, baris sesi `sid` **tetap diperiksa di basis data**. Habis setelah 60 menit tanpa aktivitas atau 12 jam total. Keluar, ganti sandi, reset, dan nonaktif mencabut sesi seketika. Peran tidak dimuat di token. | Diminta pemilik (JWT). JWT murni tidak bisa dicabut sebelum kedaluwarsa; pemeriksaan `sid` mempertahankan pencabutan seketika. Hanya algoritma HS256 yang diterima (`alg: none` dan algoritma lain ditolak). Token tidak bisa dibaca skrip halaman |
| CSRF | `SameSite=Strict` + setiap permintaan yang mengubah data wajib membawa header khusus dan `Origin` yang cocok. | API dan halaman satu asal; tidak perlu token terpisah |
| Percobaan masuk | Setelah 5 kali gagal: akun dikunci 15 menit; juga dibatasi per IP. Pesan galat tidak membedakan "user tidak ada" dari "sandi salah". Hash tetap dihitung untuk user yang tidak ada. | Menahan tebak sandi dan pencacahan user |
| Pemanggil mesin | Tugas `ingest` dan pengirim tautan bucket memakai `S4_JOB_TOKEN` di header; token hanya berlaku untuk `POST /api/admin/ingest`, `POST /api/admin/import`, dan status keduanya. | Mesin tidak punya sesi; cakupan token sesempit mungkin |
| Audit | Dicatat: masuk berhasil/gagal, keluar, ganti/reset sandi, buat/ubah/hapus user, perubahan peran, ingest, impor, `forget`. Tidak dicatat: sandi, token, isi halaman yang dibuka. | Jejak untuk tindakan yang mengubah akses atau data |
| Tanpa sesi | API menjawab 401; frontend pindah ke halaman masuk dan kembali ke alamat semula setelah berhasil. | |

**Diputuskan pemilik (X1)**: login dikelola aplikasi ini dengan akun lokal di basis data akun (K11); tidak ada SSO.

Di luar cakupan: autentikasi dua faktor, riwayat sandi, kedaluwarsa sandi berkala.

### 8.3 Peran (keputusan P1, X10)

Untuk sementara hanya dua peran, tanpa pembatasan per modul:

| Peran | Bisa |
|---|---|
| **user** | Melihat **seluruh** dashboard: semua tab analisis dan semua halaman layanan, semua folder. Mengganti sandinya sendiri |
| **admin** | Semua yang bisa user, ditambah: menambah, mengubah, menonaktifkan, dan menghapus user; mereset sandi; memicu ingest, impor, `derive`, `forget`; melihat catatan audit |

| Endpoint | Siapa |
|---|---|
| `/api/health`, `/api/auth/login` | publik |
| Semua endpoint data (§5.2–§5.4), `/api/me`, `/api/auth/logout`, `/api/me/password` | user dan admin |
| `/api/admin/*` | admin; token mesin hanya untuk ingest dan impor (§8.2) |

Aturan:

- Pemeriksaan ada di satu tempat (dependensi FastAPI yang dipasang per router), bukan di tiap fungsi.
  Router tanpa deklarasi peran **ditolak saat aplikasi mulai** (aman secara bawaan).
- User biasa memanggil endpoint admin → 403; frontend menampilkan "Anda tidak punya akses ke halaman ini".
- Perubahan peran atau penonaktifan berlaku pada permintaan berikutnya (dibaca dari basis data akun per
  permintaan; tanpa cache).
- Admin terakhir tidak bisa dihapus, dinonaktifkan, atau diturunkan menjadi user.

**Pembatasan per modul ditunda**, bukan dibuang. Bila kelak diminta, penambahannya terlokalisasi: satu
tabel `user_module`, satu pemeriksaan tambahan di dependensi yang sama, daftar centang di layar Kelola
user, dan sidebar yang menyaring. Endpoint data sudah satu-per-halaman (§5.3), jadi tidak perlu dipecah.
Karena itu tidak ada pekerjaan sekarang yang harus dibongkar nanti.

### 8.4 Layar baru yang dibutuhkan (masukan untuk DRD)

DRD ditulis sebelum P1 dijawab dan belum memuat layar ini. Kebutuhan minimumnya:

| Layar | Isi |
|---|---|
| Masuk | Nama user, sandi, tombol; pesan galat umum; pemilih bahasa dan tema tetap ada |
| Ganti sandi | Wajib saat masuk pertama / setelah reset; juga dari menu user |
| Menu user (di header) | Nama, peran, "Ganti sandi", "Keluar"; untuk admin: "Kelola user", "Ingest & impor" |
| Kelola user (admin) | Tabel user (nama, peran, aktif, terakhir masuk); tambah user (nama, peran, sandi awal); ubah peran; reset sandi; nonaktifkan; hapus |
| Ingest & impor (admin) | Status ingest terakhir dan yang berjalan, peringatan, tombol "Ingest sekarang"; kolom tautan bucket + status impor; catatan audit |
| Tidak punya akses | Hanya untuk user biasa yang membuka alamat layar admin (403) |
| Sesi habis | Kembali ke layar Masuk dengan keterangan, lalu ke alamat semula |

Sidebar sama untuk semua user; butir admin ("Kelola user", "Ingest & impor") hanya ada di menu user admin.

### 8.5 Lain-lain

- Kontainer: pengguna bukan root; folder log baca-saja.
- Kredensial hanya lewat variabel lingkungan / `.env` yang tidak masuk repo.
- Unduhan database: HTTPS, ditulis ke berkas sementara lalu diganti nama (seperti sekarang); isinya
  diperlakukan sebagai data (di-parse, tidak dieksekusi).
- Dependensi dikunci versinya (`pyproject` dengan batas versi, `package-lock.json`).
- Log aplikasi tidak menulis isi baris log pengguna.

---

## 9. Strategi uji

### 9.1 Uji unit parser dengan baris asli

- Sumber: baris asli di inv. §3 dan §4.1, disimpan per format di `tests/fixtures/lines/` (nama akun
  disamarkan seperti di inventaris). Minimal satu baris per pola di inv. §3, termasuk: access nginx
  normal / dengan retry / tanpa upstream / Uptime-Kuma; error nginx dengan dan tanpa upstream; access dan
  error frontend; event simpel-loop sukses dan gagal; tiap baris teks simpel-loop yang bermakna; delapan
  pola Spring; baris exception; baris `Hibernate:`; coredns; baris `unsupported log format`; baris yang
  harus diabaikan.
- Untuk tiap baris: baris keluaran yang diharapkan (tabel dan nilai kolom) dan perubahan penghitung
  (`lines`, `err`, `warn`, `file_counter`).
- Isi `demo()` lama (lokasi IP, `kab_name`, alur dengan retry) dipindahkan menjadi uji.

### 9.2 Uji aturan terhadap modul lama

Selama `build_dashboard.py` ada di folder induk: untuk kumpulan masukan nyata (path, UA, pesan yang diambil
dari log), `rules.py` dan modul lama harus memberi hasil identik untuk `classify`, `path_key`, `norm`,
`jwt_bucket`, `accounts`, `incidents`, `ip_owner`, `geo_scan`. Uji ini dilewati (bukan gagal) bila modul
lama tidak ada, mis. di dalam image.

### 9.3 Uji kesetaraan

Menjawab PRD §6.2. Dijalankan terhadap folder log nyata; butuh sistem lama.

| Tingkat | Yang dibandingkan | Syarat |
|---|---|---|
| E1 Angka acuan | Setiap angka di `00-acuan.json` (dibuat ulang oleh `tools/acuan_lama.py` tepat sebelum uji) vs query pada tabel agregat, per folder × layanan | sama persis |
| E2 Isi daftar | Setiap daftar di `D` yang diekstrak dari `dashboard.html` (`paths`, `perr`, `ips`, `msgs`, `atk`, `atk_ip`, `login`, `acct`, `ep`, `c401`, `incidents`, `pod`, `retry`, `uperr`, `trace`, `flow`, `rep`, …) vs respons API dengan `limit` = batas lama | baris dan nilai sama; urutan boleh beda hanya di antara baris bernilai sama; persentil sama sampai pembulatan tampilan |
| E3 Data IP | `D.ipinfo` (pemilik jaringan) vs `ip_info` untuk IP yang sama, dengan berkas ip2asn yang sama | sama. Lokasi tidak dibandingkan: sumbernya kini GeoLite2 (§3.6); diuji terhadap berkas GeoLite2 itu sendiri |
| E4 Selisih yang diharapkan | Perbaikan §4.4: untuk tiap butir, nilai lama, nilai baru, dan nilai yang seharusnya (dari `00-acuan.json` untuk butir 1; dihitung dari data mentah sistem lama untuk butir 2, 4, 9) | nilai baru = nilai seharusnya; daftar selisih **tertutup** (butir 1, 2, 3, 4, 9 di §4.4), selisih lain = gagal |

Hasil E1–E4 ditulis ke laporan kesetaraan (langkah 8). E1 dijalankan sejak tahap ingest selesai, sebelum
ada tampilan (PRD R2, R9).

### 9.4 Uji ingest

Dengan folder log buatan kecil dari berkas contoh:

- Ingest dua kali → isi semua tabel identik (dibandingkan lewat jumlah baris dan checksum per tabel).
- File bertambah isinya → hanya folder itu yang berubah; hasil sama dengan ingest bersih.
- `.log.gz` saja → lalu `.log` identik muncul → tidak ada parse ulang, tidak ada baris ganda.
- Pasangan `.log`/`.log.gz` berbeda → peringatan tercatat; `.log` yang dipakai.
- File dihapus → barisnya hilang, agregat folder diturunkan ulang.
- File rusak → `status = rusak`, baris dihitung, file lain tetap masuk.
- Proses dihentikan di tengah transaksi → ingest berikutnya menghasilkan keadaan bersih.
- `(file_id, line_no)` unik di tiap tabel mentah.
- Folder tanpa namespace (A9) dan folder layanan tak dikenal (A10, dengan peringatan).

### 9.5 Uji API

- Tiap endpoint: bentuk respons, `available: false` pada folder tanpa log terkait, galat 400/404.
- Validasi: nilai di luar daftar, `q` berisi tanda kutip / `%` / skrip, `limit` di luar rentang, folder
  yang tidak ada, upaya penyisipan SQL pada tiap parameter.
- Ukuran respons tiap halaman ≤ 500 KB pada folder terbesar.
- Header keamanan ada di semua respons.

### 9.6 Uji login, peran, dan impor

- Sandi: hash tidak sama untuk sandi sama; verifikasi benar/salah; sandi pendek ditolak.
- Sesi: tanpa cookie → 401; sesi habis → 401; keluar/reset/nonaktif mencabut sesi; cookie membawa
  `HttpOnly`, `Secure`, `SameSite=Strict`.
- Penguncian setelah 5 gagal; pesan galat sama untuk user ada/tidak ada.
- **Matriks peran**: untuk setiap endpoint × {tanpa sesi, user, admin, token mesin} → status yang
  diharapkan (401 / 200 / 403). Matriks dibuat dari tabel §8.3, sehingga endpoint baru tanpa baris di
  matriks menggagalkan uji.
- Permintaan yang mengubah data tanpa header/`Origin` yang benar ditolak.
- Admin terakhir tidak bisa dihapus, dinonaktifkan, atau diturunkan.
- Token mesin hanya diterima di endpoint ingest/impor.
- Impor, terhadap **S3 tiruan lokal** (server kecil di dalam uji, tanpa AWS sungguhan): tautan bukan
  `s3://`, bucket di luar daftar izin, awalan di luar yang diizinkan, komponen terakhir bukan tanggal, kunci
  berisi `..`, objek di luar pola, melebihi batas jumlah/ukuran, tanpa kredensial, kredensial ditolak S3 →
  semuanya gagal dengan pesan jelas tanpa menulis ke kotak masuk. Awalan sah → folder muncul dan
  ter-ingest; pasangan `.log`/`.log.gz` → hanya `.log` diunduh; tautan sama dua kali → 0 objek diunduh
  ulang; `dry_run` → tidak ada berkas tertulis.
- Kredensial: tidak muncul di respons, log, basis data akun, maupun audit; token mesin tidak bisa memanggil
  endpoint kredensial; kredensial sementara hilang setelah server dimulai ulang.
- Uji terhadap bucket sungguhan **tidak** bisa otomatis; dilakukan manual sekali dengan mode coba (T14).

### 9.7 Uji kinerja dan ukuran

- **Data setahun buatan**: baris mentah folder `2026-09-29` digandakan ke 365 tanggal folder dengan query
  (tanpa parse ulang), lalu agregat diturunkan. Diukur: ukuran file (target ≤ 10 GB), waktu respons tiap
  endpoint halaman (target PRD §5.1), waktu ingest satu folder lagi di atas data itu (≤ 60 detik), waktu
  ingest tanpa perubahan (≤ 5 detik).
- Dilakukan **segera setelah ingest dan skema jadi**, sebelum frontend (PRD R4). Ini juga yang memastikan
  atau membatalkan ASUMSI T1.
- Biaya login: hash scrypt diukur dan parameternya dipilih agar satu verifikasi ±100 ms di server.

### 9.8 Uji frontend dan privasi

- Kelengkapan kamus: setiap kunci di `id.json` ada di `en.json` dan sebaliknya (skrip kecil, tanpa
  kerangka uji).
- Hasil build tidak memuat URL ke domain luar selain tautan atribusi (pemeriksaan teks atas `dist/`).
- Pemeriksaan manual berdaftar periksa untuk tiap halaman × {ID, EN} × {gelap, terang} × {lebar, sempit}
  terhadap inv. §2 dan DRD §3 (PRD §6.1), dengan jaringan dimatikan.
- **ASUMSI T8**: tidak ada uji peramban otomatis (Playwright dsb.) di migrasi ini; daftar periksa manual
  cukup untuk 10 halaman dan menghemat satu dependensi berat. Ditambahkan bila tampilan sering berubah.

---

## 10. Dampak ke dokumen lain

Hal yang diputuskan di sini dan mengubah atau mempertajam dokumen sebelumnya.
**Status: sudah diterapkan** ke PRD dan DRD pada Tahap 1 rencana (2026-10-06); layar di §8.4 kini
dirancang di DRD §3.11 dan §6.9.

| Dokumen | Butir | Perubahan |
|---|---|---|
| PRD A1, P2, T01 | "hari" | **Diputuskan**: per folder. T01 (per tanggal kalender) tidak lagi direncanakan |
| PRD A2, P4, T05 | definisi ditiru | **Diputuskan**: diperbaiki. Rinciannya §4.4; T05 sebagian besar dikerjakan sekarang |
| PRD A3, P3, §5.4 butir 4, §7 | "hanya dibuka di komputer yang menjalankannya"; "menjalankan di server di luar cakupan" | **Gugur**: berjalan di server, diakses banyak komputer lewat HTTPS dengan login |
| PRD A5, P1, T03, §7 | pengguna diasumsikan; login ditunda dan di luar cakupan | **Diputuskan**: login dengan dua peran masuk cakupan (§8.2–§8.4); hak akses per modul ditunda |
| PRD A7, T04 | tanpa ingest otomatis | Ditambah jalur impor dari tautan bucket (§3.8), dijadwalkan setelah kesetaraan terbukti |
| PRD §4 | daftar fitur | Fitur baru: login, kelola user, audit, impor bucket; ditunda: hak akses per modul |
| PRD §5.5 | "satu perintah" | Tetap untuk lokal (`run.sh`, sekali membuat admin); di server: `docker compose up -d` |
| PRD §6.2 | selisih yang diharapkan hanya inv. §8 butir 6 | Daftar tertutup kini butir 1, 2, 3, 4, 9 di §4.4 |
| PRD §6.3 | "menambah folder ke-12 tidak mengubah angka folder 1–11" | Berlaku kecuali agregat korelasi (§3.5) |
| PRD T09 | retensi | Folder log yang hilang tidak menghapus data (T2); penghapusan eksplisit lewat `forget` |
| PRD R7 | risiko data pribadi | Ditangani login + hak akses + audit; risiko baru: pengelolaan sandi dan fitur impor (SSRF) |
| DRD D7, Q2 | tanpa login | **Gugur**: perlu layar di §8.4 (belum dirancang di DRD) |
| DRD Q1 | keseriusan tampilan ponsel | **Diputuskan**: serius; DRD §8 berlaku penuh |
| DRD §1.1, §2 | kerangka | Sidebar tetap menampilkan semua tab; header mendapat menu user (admin: + "Kelola user", "Ingest & impor") |
| DRD §6.6–§6.7 | keadaan kosong/gagal | Ditambah "tidak punya akses" dan "sesi habis" |
| DRD U8 | keterangan `(i)` | Wajib untuk Error (rincian 5xx + log), baris `EXC`, dan level simpel-loop (§4.4) |
| DRD §4.3, tabel alur | batas awal 3.000 | Tampilan awal 100 baris, sisanya "tampilkan berikutnya" |
| DRD §6.5 | memuat per kartu | Satu permintaan per halaman; kartu tampil bersamaan. "Gagal per kartu" menjadi "gagal per halaman" + "gagal per tabel lanjutan" |
| DRD §7.2–§7.3 | sumber peta | Lima berkas statis di §5.7; huruf label Noto Sans (T4) |

---

## 11. Asumsi dan pertanyaan terbuka

### 11.1 ASUMSI teknis

| # | ASUMSI | Bila salah |
|--:|---|---|
| T1 | Data mentah setahun muat dalam ≤ 10 GB berkat kompresi DuckDB | Pindahkan `ua`/`path` ke tabel kamus, atau simpan mentah hanya N bulan terakhir (agregat tetap) |
| T2 | Folder log yang hilang dari disk **tidak** menghapus datanya dari dashboard | Jalankan `forget` otomatis saat folder hilang (perilaku lama) |
| T3 | Pemilik/lokasi satu IP tidak diperbarui saat database baru diunduh | Tambah perintah pembaruan massal |
| T4 | Glyph label peta = Noto Sans yang disimpan di repo | Buat glyph dari Outfit (butuh alat pembuat sekali jalan) |
| T5 | Compose menyertakan layanan proxy HTTPS; sertifikat disediakan pemilik server | Pakai proxy yang sudah ada; `app` hanya di loopback |
| T7 | Ingest harian dipicu cron host | Penjadwal di dalam `app` (satu konfigurasi jam) |
| T8 | Tanpa uji peramban otomatis | Tambah Playwright |
| T9 | Mewarisi PRD yang belum dijawab: tanpa CDN (A4), file rusak tetap dihitung (A6), folder tanpa namespace dan layanan tak dikenal didukung (A9, A10) | Lihat PRD §9 |
| T14 | Susunan objek di bawah awalan = susunan folder log lokal | Tambah pemetaan nama di `importer.py`; diketahui dari mode coba |
| T15 | Hanya **lokasi** yang pindah ke GeoLite2; pemilik jaringan (ASN, organisasi) tetap ip2asn | Ganti juga ke `GeoLite2-ASN-CSV` (kredensial yang sama); uji E3 pemilik gugur |

### 11.2 Pertanyaan untuk pemilik produk

Sudah dijawab: PRD P1, P2, P3, P4; X1 (akun lokal); X11 (perbaikan definisi); DRD Q1 (ponsel serius);
X9 (awalan S3, kunci tetap, wilayah Jakarta); X10 (untuk sementara hanya admin dan user, tanpa
pembatasan per modul). Yang tersisa, diurutkan menurut pengaruhnya ke langkah 5–7:

| # | Pertanyaan | Asumsi sementara |
|--:|---|---|
| X9 | **Impor S3** (jenis kunci, wilayah, dan sifat baca-saja sudah dijawab): siapa yang akan mengirim tautan, admin lewat layar atau sistem lain lewat API? Bisakah kelak dibuat pengguna IAM khusus yang hanya membaca `simpel4-backup/k8s-logs/`? | Keduanya didukung; kunci yang ada dipakai dulu |
| X2 | **Server** (pemilik belum tahu; ditanyakan ke pengelola server): sudah ada reverse proxy/HTTPS dan nama domain? Ada akses keluar ke S3 Jakarta dan ke lima alamat unduhan database IP? Berapa disk dan memori? Semuanya **diperiksa dengan perintah saat deploy** (langkah 7), bukan diandaikan | Proxy ikut di compose (T5); ada akses keluar; ≥ 20 GB, ≥ 2 GB |
| X3 | **Folder log di server**: tetap ada ekspor ke folder yang dipasang, atau semua lewat bucket? Jam berapa data tiba; berapa lama disimpan? | Keduanya didukung |
| X4 | **Folder log yang hilang**: data dashboard dipertahankan (T2) atau ikut hilang seperti sistem lama? | Dipertahankan |
| X5 | `.log` dan `.log.gz`: v2 mencatat peringatan bila isinya berbeda. Mana yang benar bila berbeda? (= PRD P5) | `.log` |
| X6 | Tabel alur IP tampil 100 baris pertama, bukan 3.000: setuju? | Ya |
| X7 | Huruf label peta berbeda dari huruf antarmuka (T4): bisa diterima? | Ya |
| X8 | Cadangan volume `s4-state` (wajib) dan `s4-data`: ikut jadwal cadangan server? | Ya |

Pertanyaan DRD Q3, Q6, Q7 masih terbuka; skema dan API di atas tidak bergantung pada jawabannya.

**Permintaan baru pemilik (2026-10-06, saat Tahap 12)**: modul **Command Center** (peta, overview, dan semua info
di satu layar, **realtime**) karena data kelak dialirkan lewat **Kafka**. Ini mengubah K1/A7 (ingest harian, tanpa
pembaruan otomatis); usulan dan asumsinya di §12. Pertanyaan yang menentukan:

| # | Pertanyaan | Asumsi sementara |
|--:|---|---|
| R1 | **Isi aliran Kafka**: baris log mentah per layanan (format sama dengan file sekarang) atau event yang sudah terstruktur? Siapa produsennya (Fluent Bit/Vector/aplikasi)? Nama topik? | Baris log mentah, satu topik per layanan, dikirim pengumpul log klaster |
| R2 | **Seberapa realtime**: angka di layar boleh terlambat berapa (detik/menit)? | ≤ 10 detik |
| R3 | **Hubungan dengan folder harian**: folder log harian (dan impor S3) tetap jadi sumber kebenaran, aliran Kafka hanya untuk "hari ini"? | Ya: aliran mengisi jendela berjalan; folder harian tetap di-ingest dan menggantikan data aliran untuk tanggal itu |
| R4 | **Akses Kafka**: alamat broker, autentikasi (SASL/TLS), bisa dijangkau dari server dashboard? | Belum diketahui; diperiksa saat deploy (seperti X2) |
| R5 | **Command Center menggantikan Overview** atau halaman baru di samping 10 halaman yang ada? Untuk siapa (layar dinding/NOC atau pengguna biasa)? | Halaman baru, paling atas di sidebar; Overview tetap |
| R6 | **Gaya tampilan** mengikuti gambar referensi untuk **seluruh** dashboard atau hanya Command Center? | Seluruh dashboard (token dan komponen bersama), susunan isi tiap halaman tetap |

---

## 12. Usulan: Command Center dan aliran realtime (Kafka) — BELUM DISETUJUI

Ditulis saat Tahap 12 atas permintaan pemilik; semua butir di bawah **ASUMSI** sampai R1–R6 (§11.2) dijawab.

- **Tetap satu proses pemilik DuckDB (K1).** Konsumen Kafka berjalan sebagai utas di proses server yang sama (seperti
  ingest dalam proses, Tahap 10), menulis per kelompok kecil (mis. tiap 2 detik atau 5.000 pesan) ke tabel
  `rt_*` berjendela waktu, memakai parser yang sama (`parse.py`) agar definisi angka tidak bercabang.
- **Ke browser lewat Server-Sent Events** (`GET /api/stream`, satu arah, cookie sesi yang sama, lolos CSP `'self'`,
  tersambung ulang otomatis). WebSocket tidak perlu karena browser tidak mengirim apa-apa.
- **Command Center** = satu halaman yang memakai komponen bersama: KPI berjalan, peta, "yang perlu perhatian"
  (temuan otomatis yang sudah ada: serangan, login gagal, 5xx, error koneksi pod), dan aliran kejadian terbaru;
  penanda "streaming · kejadian terakhir N detik lalu" dan status Live/terputus.
- **Folder harian tetap sumber kebenaran (R3)**: ingest folder menggantikan data aliran untuk tanggal itu, jadi uji
  kesetaraan E1–E4 tetap berlaku.
- Dependensi baru opsional `simpel4[kafka]` (`confluent-kafka`), hanya diimpor bila `S4_KAFKA_BROKERS` diisi;
  tanpa itu dashboard berjalan seperti sekarang dan Command Center memakai data folder terbaru.

