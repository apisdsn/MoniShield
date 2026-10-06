# Rencana implementasi — dashboard log SIMPEL4 (v2)

Rencana bertahap untuk membangun v2 sesuai [`03-trd.md`](03-trd.md) (teknis), [`02-drd.md`](02-drd.md)
(tampilan), [`01-prd.md`](01-prd.md) (kebutuhan), dan [`00-inventaris.md`](00-inventaris.md) (acuan).
Bila dokumen bertentangan, urutan yang menang: **keputusan pemilik di TRD (P1–P4) → TRD → DRD → PRD**;
TRD §10 mendaftar butir PRD/DRD yang sudah gugur.

Dipakai oleh `migrate/06-eksekusi.md`: satu tahap per sesi. Setelah tiap tahap, tabel status di bawah
diperbarui dan penyimpangan dicatat di bagian tahap itu.

## Cara membaca

- **21 tahap** (+ 12a, 22, 23 atas permintaan pemilik 2026-10-06), urut mengikuti alur data: aturan dan skema → ingest → agregat → uji kesetaraan → API →
  kerangka tampilan → halaman satu per satu → layar admin → impor → peta, lalu satu peningkatan yang
  diminta pemilik: deteksi serangan berbasis OWASP CRS (Tahap 21).
- Setiap tahap bisa dijalankan dan diperiksa sendiri. Tahap berikutnya tidak dimulai sebelum verifikasi
  tahap ini lulus.
- **Perintah verifikasi** dijalankan dari folder `v2/` kecuali disebut lain. `py` = `.venv/bin/python`,
  `pytest` = `.venv/bin/pytest`.
- Tanda **⚠ bergantung** = tahap memakai ASUMSI atas pertanyaan yang belum dijawab; tahap tetap bisa
  dikerjakan, tetapi jawaban yang berbeda berarti pengerjaan ulang sebesar yang disebut.
- Angka yang diharapkan berlaku untuk **11 folder log per 2026-10-06** (`00-acuan.json`). Folder log
  bertambah tiap hari; bila sudah bertambah, jalankan `python3 tools/acuan_lama.py` dulu dan bandingkan
  dengan acuan baru. Angka untuk 11 folder lama tidak boleh berubah.

Keadaan mesin saat rencana ditulis: Python 3.13.1, Node 22.13, npm 10.9, Docker 29.6 ada; paket `duckdb`
belum terpasang (dipasang di Tahap 2); **disk bebas hanya 17 GB** (berpengaruh ke Tahap 9).

## Status

| # | Tahap | Bergantung pada | Pertanyaan terbuka | Status |
|--:|---|---|---|:-:|
| 1 | Selaraskan PRD dan DRD dengan keputusan pemilik | — | — | ☑ 2026-10-06 |
| 2 | Kerangka proyek dan modul aturan | — | — | ☑ 2026-10-06 |
| 3 | Skema dan parser | 2 | — | ☑ 2026-10-06 |
| 4 | Ingest tabel mentah | 3 | X4, X5 | ☑ 2026-10-06 |
| 5 | Agregat inti | 4 | — | ☑ 2026-10-06 |
| 6 | Agregat fitur: serangan, login, korelasi, bisnis | 5 | — | ☑ 2026-10-06 |
| 7 | Data IP dan berkas peta | 4 | P6 | ☑ 2026-10-06 |
| 8 | Uji kesetaraan E1, E3, E4 | 5, 6, 7 | — | ☑ 2026-10-06 |
| 9 | Gerbang ukuran dan kinerja | 8 | P7 | ☑ 2026-10-06 |
| 10 | API: kerangka, login, peran, ingest dalam proses | 8 | — | ☑ 2026-10-06 |
| 11 | API data semua halaman + uji kesetaraan E2 | 10 | X6 | ☑ 2026-10-06 |
| 12 | Kerangka tampilan dan komponen bersama | 1, 11 | Q6, Q7, Q8 | ◐ 2026-10-06 sebagian: tinggal uji di ponsel sungguhan |
| 12a | Gaya mengikuti referensi desain pemilik (token, ikon, kartu perhatian) untuk seluruh dashboard | 12 | — (R6 terjawab) | ☑ 2026-10-06 |
| 13 | Halaman Layanan dan Overview | 12 | — | ☑ 2026-10-06 (peta halaman layanan: Tahap 20) |
| 12 | Kerangka tampilan dan komponen bersama | 1, 11 | Q6, Q7, Q8 | ☐ |
| 13 | Halaman Layanan dan Overview | 12 | — | ☐ |
| 14 | Halaman Tren | 12 | Q4 | ☑ 2026-10-06 |
| 15 | Halaman Keamanan | 12 | — | ☑ 2026-10-06 |
| 16 | Halaman Akar Masalah dan Ketersediaan | 12 | — | ☑ 2026-10-06 |
| 17 | Halaman Pod, Bisnis, Pelacakan Request | 12 | — | ☑ 2026-10-06 |
| 18 | Layar admin: kelola user, ingest, audit | 12 | — | ☑ 2026-10-06 |
| 19 | Impor dari awalan S3 | 10, 18 | X2, X3 | ◐ 2026-10-06 sebagian: tinggal dua baris Manual dengan kredensial AWS asli |
| 20 | Peta IP | 7, 13 | Q3, Q5, X7 | ☑ 2026-10-06 |
| 21 | Deteksi serangan: aturan OWASP CRS, kategori CAPEC | 8, 15 | **S1** | ☐ |
| 22 | Command Center: layar peta dunia + KPI + yang perlu perhatian (menyerap tab Peta IP) | 12a, 13, 15, 16, 20 | — (R5 terjawab; ASUMSI penggabungan Peta IP) | ☐ baru |
| 23 | Aliran realtime dari Kafka ke Command Center | 22 | R1, R2, R4 | ⏸ ditunda: Kafka untuk ke depan (keputusan 2026-10-06) |

Setelah Tahap 21: `migrate/07-docker-compose.md` (bergantung X2, X3, X8; X2 belum diketahui pemilik dan
harus diperiksa di server: proxy/HTTPS yang ada, akses keluar, disk, memori) dan `migrate/08-kesetaraan.md`.

### Pertanyaan yang paling menentukan

| Pertanyaan | Asumsi yang dipakai | Bila jawabannya lain |
|---|---|---|


| **Command Center** (TRD §11.2, §12) — **diputuskan 2026-10-06**: folder log tetap sumber utama, Kafka ditunda (R3); Overview tetap, Command Center = layar peta dunia (R5); gaya referensi untuk seluruh dashboard (R6). Yang masih ASUMSI: tab "Peta IP" digabung ke Command Center | Satu halaman peta saja; sidebar "Peta IP" menjadi "Command Center" di posisi yang sama | Tahap 20 dan 22: bila Peta IP tetap terpisah, Command Center memakai ulang komponen peta yang sama (tambahan kecil) |
| **S1** deteksi serangan: (a) cara "di skrip" atau juga "di ingress"? (b) tampilan lama diganti atau berdampingan? (c) tingkat paranoia CRS? | (a) di skrip saja; cara di ingress diusulkan ke pengelola klaster. (b) Kategori CAPEC **menggantikan** kategori lama di tampilan; klasifikasi lama tetap disimpan untuk uji. (c) Tingkat paranoia 1 (paling sedikit salah-tuduh) | Tahap 21 saja. Bila ingress kelak menjalankan CRS, dashboard perlu parser log audit ModSecurity/Coraza: tahap baru |

Semua pertanyaan lain hanya mengubah nilai bawaan atau satu komponen.

**Sudah diputuskan pemilik** (tidak lagi asumsi): lokasi IP memakai MaxMind GeoLite2 (akun dan kunci
lisensi sudah ada di `v2/.env`, sudah diuji diterima MaxMind); untuk sementara hanya peran admin dan user, user
melihat seluruh dashboard, admin bisa menambah user; pembatasan per modul ditunda (X10); impor dari awalan S3 dengan kunci akses tetap, wilayah
Jakarta, sehingga bisa otomatis (X9); akun lokal di basis data aplikasi, tanpa SSO (X1);
perbaikan definisi di TRD §4.4 disetujui (X11); tampilan ponsel dikerjakan serius (Q1), jadi DRD §8
berlaku penuh termasuk tabel lebar menjadi kartu baris.

---

## Tahap 1 — Selaraskan PRD dan DRD dengan keputusan pemilik

**Tujuan.** PRD dan DRD ditulis sebelum P1–P4 dijawab. Tahap ini memperbaruinya sesuai TRD §10 dan
merancang layar baru di TRD §8.4, supaya tahap tampilan tidak membaca asumsi yang sudah gugur.
Hanya dokumen; tidak ada kode.

**File diubah**

- `docs/01-prd.md`: A1, A2, A3, A5 menjadi keputusan; T01 dicabut; T03 dan sebagian T05 pindah ke cakupan;
  fitur baru (login dua peran, kelola user, audit, impor S3) masuk §4, hak akses per modul masuk daftar
  ditunda; §5.4, §5.5, §6.2, §7, R7 sesuai
  TRD §10; P1–P4 ditandai terjawab.
- `docs/02-drd.md`: §1 dan §2 (menu user di header; butir admin hanya untuk admin); bagian baru
  "Masuk dan admin" berisi sketsa layar Masuk, Ganti sandi, Kelola user, Ingest & impor; §6.6–§6.7
  ditambah "tidak punya akses" dan "sesi habis"; U8 (keterangan Error, `EXC`, level simpel-loop); tabel
  alur 100 baris; §6.5 memuat per halaman; D7 dan Q2 ditandai gugur; Q1 ditandai terjawab (ponsel serius).

**Verifikasi**

| Perintah (dari folder proyek) | Hasil yang diharapkan |
|---|---|
| `grep -c "hanya dibuka di komputer" v2/docs/01-prd.md` | `0` |
| `grep -n "Kelola user\|Tidak punya akses\|Sesi habis" v2/docs/02-drd.md` | ketiganya ditemukan |
| Baca TRD §10 baris demi baris | setiap baris punya padanan di PRD/DRD |


---

## Tahap 2 — Kerangka proyek dan modul aturan

**Tujuan.** Lingkungan Python jalan, konfigurasi terbaca, dan aturan sistem lama tersalin apa adanya dengan
bukti bahwa salinannya identik (TRD §4.1, §9.2).

**File dibuat**

- `pyproject.toml` (dependensi: `duckdb`, `fastapi`, `uvicorn`; uji: `pytest`, `httpx`), `.gitignore`
  (`data/`, `.venv/`, `web/node_modules/`, `web/dist/`).
- `simpel4/__init__.py`, `simpel4/__main__.py`, `simpel4/cli.py` (baru subperintah `status`).
- `simpel4/config.py` (TRD §6.3; nilai bawaan = konstanta lama), `config.example.toml`.
- `simpel4/rules.py`: salinan regex dan fungsi di TRD §4.1, tiap blok diberi catatan nomor baris asal.
- `tests/test_rules.py`: (a) isi `demo()` lama; (b) perbandingan dengan `build_dashboard.py` untuk
  `classify`, `path_key`, `norm`, `jwt_bucket`, `accounts`, `incidents`, `ip_owner`, `geo_scan` atas masukan
  nyata yang diambil dari log (minimal 5.000 path, 500 UA, 500 pesan); dilewati bila modul lama tidak ada.
- `tests/conftest.py` (lokasi folder log, modul lama).

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `python3 -m venv .venv && .venv/bin/pip install -e ".[test]"` | selesai tanpa galat |
| `pytest tests/test_rules.py -q` | semua lulus, 0 dilewati (modul lama ada) |
| `py -m simpel4 status` | mencetak konfigurasi efektif: folder log, direktori data, cache; "belum ada database" |
| `ls -la ../build_dashboard.py ../dashboard_template.html` | tanggal ubah kedua file lama tetap (tidak disentuh) |

---

## Tahap 3 — Skema dan parser

**Tujuan.** Tabel DuckDB terdefinisi (TRD §2.1–§2.3) dan parser mengubah baris log menjadi baris tabel
dengan penghitung per file yang sama dengan `parse()` lama (TRD §4.2), kecuali perbaikan `crit` (TRD §4.4
butir 3).

**File dibuat**

- `simpel4/schema.sql`: tabel kendali, mentah, dan agregat; view.
- `simpel4/db.py`: membuka database, menerapkan skema (aman diulang), batas memori.
- `simpel4/parse.py`: satu fungsi per jenis layanan; keluaran CSV per tabel + ringkasan file (`lines`,
  `err`, `warn`, `corrupt_lines`, `file_counter`); bisa dijalankan sendiri untuk satu file.
- `tests/fixtures/lines/*.txt`: baris asli per format dari inventaris §3 dan §4.1 (nama akun disamarkan).
- `tests/test_parse.py`: (a) per baris contoh → baris keluaran dan perubahan penghitung yang diharapkan;
  (b) untuk tiap file log nyata di tiga folder (`2026-09-27`, `2026-09-29`, `2026-10-06`): `lines`, `err`,
  `warn`, dan jumlah per level sama dengan `parse()` lama pada file yang sama.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `pytest tests/test_parse.py -q` | semua lulus |
| `py -m simpel4.parse ../2026-10-06/ingress-nginx/nginx-ingress-controller/*5v8j4*.log --out /tmp/s4parse` | ringkasan: `lines=111301`; berkas `nginx_access.csv`, `nginx_error.csv`, `log_message.csv` terbentuk |
| `py -c "from simpel4 import db; db.open(':memory:')"` lalu daftar tabel | semua tabel TRD §2 ada; menjalankan dua kali tidak galat |

Catatan: perbaikan level `crit` di frontend (TRD §4.4 butir 3) tidak mengubah angka pada data sekarang,
karena tidak ada baris `crit`.

---

## Tahap 4 — Ingest tabel mentah

**Tujuan.** `simpel4 ingest` mengisi tabel mentah dan tabel kendali dari folder log, bertahap dan aman
diulang (TRD §3.1–§3.3). Agregat belum.

**File dibuat**

- `simpel4/ingest.py`: pindai dua akar (folder log, kotak masuk), sidik jari (ukuran + mtime, lalu
  SHA-256 isi terdekompresi), parse di subproses, muat CSV, satu transaksi per folder, `ingest_run`.
- `simpel4/cli.py`: subperintah `ingest [--folder] [--force]`, `forget <folder>`, `status` lengkap.
- `tests/fixtures/logs_mini/`: folder log buatan kecil (dua tanggal, semua jenis layanan, satu file rusak,
  satu pasangan `.log`/`.log.gz`, satu folder tanpa namespace).
- `tests/test_ingest.py`: semua butir TRD §9.4.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `pytest tests/test_ingest.py -q` | semua lulus |
| `time py -m simpel4 ingest` (database kosong) | selesai ≤ 3 menit; 11 folder, 195 file, 0 gagal |
| `py -m simpel4 status` | total baris 774.264; `nginx_access` 308.158; `fe_access` 148.049; `sl_event` 114.574; file 0 baris: 52 |
| `time py -m simpel4 ingest` (kedua kali) | ≤ 5 detik; "0 file berubah" |
| `py -m simpel4 status --checksum` sebelum dan sesudah ingest kedua | checksum tiap tabel sama |
| `ls -la ../2026-10-06 ../.cache` | tidak ada berkas baru atau berubah di folder log |

Baris per folder (Σ `ingest_file.lines`) harus sama dengan kolom "total" inventaris §7, mis. `2026-09-29`
= 359.009 dan `2026-10-06` = 191.898.

⚠ **Bergantung X4** (folder hilang → data dipertahankan, T2) dan **X5** (`.log` menang atas `.gz`):
keduanya satu cabang kecil di `ingest.py`.

---

## Tahap 5 — Agregat inti

**Tujuan.** Agregat yang menjadi dasar angka inti dan halaman layanan diturunkan dengan SQL per folder
(TRD §3.4, §4.3): `agg_service`, `agg_hour` (kecuali simpel-loop), `agg_status`, `agg_endpoint`,
`agg_endpoint_error`, `agg_ip`, `agg_upstream`, `agg_ua`, `agg_level`, `agg_message`, `agg_slow`,
`agg_flow`, `agg_pod`, `agg_retry`, `agg_c401`, `agg_uk_hour`, `agg_uk_target`, `folder_state`, dan view
`v_upstream_error`, `v_restart`, `v_dns`.

**File dibuat**

- `simpel4/derive/__init__.py` (menjalankan berkas SQL berurutan untuk satu folder, di dalam transaksi
  ingest) dan satu `simpel4/derive/NN_<tabel>.sql` per agregat di atas.
- `simpel4/cli.py`: subperintah `derive [--folder | --all]`.
- `tests/test_derive_core.py`: pada `logs_mini`, nilai tiap agregat dihitung tangan; persentil memakai
  aturan indeks lama; "yang pertama" mengikuti urutan (`relpath`, `line_no`).

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `pytest tests/test_derive_core.py -q` | semua lulus |
| `py -m simpel4 derive --all` | 11 folder diturunkan tanpa galat |
| `py -m simpel4 status --folder 2026-09-29` | nginx: request 132.203, 4xx 4.635, 5xx 59, error 94, warning 164, IP unik 723, alur 1.762; simpel-loop: request 60.665, warning 9.614 |
| `py -m simpel4 status --folder 2026-09-30` | nginx: error 1.690; error koneksi pod 1.200; retry 825 |
| Jalankan `derive --all` dua kali, bandingkan `status --checksum` | sama |

Memuat perbaikan TRD §4.4 butir 2 dan 4 (chart per jam memuat baris error log; level efektif simpel-loop).

---

## Tahap 6 — Agregat fitur: serangan, login, korelasi, bisnis

**Tujuan.** Sisa agregat: `agg_attack_url`, `agg_attack_ip`, `agg_attack_hour`, `v_attack_cat`,
`agg_login_ip`, `agg_login_hour`, `agg_account` (fungsi `accounts()` lama), `agg_incident` (fungsi
`incidents()` lama), `agg_corr`, `agg_trace`, `agg_hour` simpel-loop (korelasi lintas folder, TRD §3.5),
`agg_biz`, `agg_mail`, `agg_activity`, `agg_jwt`, `agg_report`.

**File dibuat**

- `simpel4/derive/NN_<tabel>.sql` untuk tiap agregat di atas; `simpel4/derive/accounts.py`,
  `simpel4/derive/incidents.py` (memanggil fungsi di `rules.py` atas hasil query kecil).
- Penurunan ulang agregat korelasi untuk folder lain yang terpengaruh (TRD §3.5), di `ingest.py`.
- `tests/test_derive_features.py`: nilai dihitung tangan pada `logs_mini`, termasuk satu request id yang
  cocok lintas folder dan satu request id ganda.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `pytest tests/test_derive_features.py -q` | semua lulus |
| `py -m simpel4 derive --all && py -m simpel4 status --folder 2026-09-29` | serangan 155 request / 77 URL / 12 IP; korelasi 22.638 dari 60.665; jejak 300+ baris (tidak dipotong); login gagal 86, reset 24, sukses 389; akun dianalisis 39; insiden 7; PDF 813 sukses / 32 gagal |
| `py -m simpel4 status --folder 2026-10-06` | serangan 88; korelasi 4.161 dari 5.981; "Laporan Dibuat" 7 |
| `time py -m simpel4 ingest --folder 2026-09-29 --force` | ≤ 60 detik (parse + muat + turunkan) |

Memuat perbaikan TRD §4.4 butir 9 ("lambat ≥ 5 dtk" memuat 3xx); akun dan insiden tetap per folder (butir 7).

---

## Tahap 7 — Data IP dan berkas peta

**Tujuan.** `ip_info` terisi offline untuk semua IP (TRD §3.6) dan lima berkas statis peta tersedia (TRD
§5.7). Tidak ada IP yang dikirim keluar.

**File dibuat**

- `simpel4/refdata.py`: unduhan ke cache (aturan umur lama), pemilik (`ip_owner`), lokasi (`geo_scan`),
  pembuatan `data/map/land.geojson`, `borders-country.geojson`, `borders-province-id.geojson`,
  `labels.json`.
- Pemanggilan di akhir ingest; subperintah `refdata [--offline]`.
- `tests/test_refdata.py`: dengan berkas database mini buatan: IP privat, IP di luar rentang, IPv6, IP
  baru setelah ingest kedua; unduhan gagal → ingest tetap selesai.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `pytest tests/test_refdata.py -q` | semua lulus |
| `py -m simpel4 refdata` (cache lama `../.cache` dipakai) | tanpa unduhan baru; `ip_info` terisi |
| `py -m simpel4 status` | IP dengan pemilik ≥ 1.734; IP dengan lokasi ≥ 1.676; server Jakarta (−6,17494; 106,822) |
| `ls -la data/map/` | 4 berkas; `labels.json` berisi 177 negara / 38 provinsi / 514 kabupaten-kota |
| `py -m simpel4 refdata --offline` dengan jaringan dimatikan | selesai, tanpa galat |

**Diputuskan pemilik (2026-10-06): lokasi IP dari MaxMind GeoLite2** (TRD §3.6), bukan DB-IP. Akibat untuk
tahap ini:

- `refdata.py` mengunduh `GeoLite2-City-CSV` dengan `MAXMIND_ACCOUNT_ID`/`MAXMIND_LICENSE_KEY` dari `.env`,
  mengubah blok CIDR menjadi rentang terurut, dan memakai sapuan `geo_scan()` yang sama. `config.py`
  mendapat dua kunci itu (rahasia: tidak dicetak).
- Verifikasi di tabel atas berubah: `py -m simpel4 refdata` **mengunduh** GeoLite2 (±49 MB) pada jalan
  pertama; "IP dengan lokasi ≥ 1.676" diganti "≥ 95 % IP publik punya lokasi" (angka lama berasal dari
  DB-IP); titik server tetap di Jakarta tetapi koordinatnya boleh berbeda.
- Verifikasi tambahan: tanpa kunci → ingest selesai, lokasi kosong, ada keterangan; kunci tidak muncul di
  keluaran `status`, log, maupun database; 20 IP contoh dibandingkan dengan DB-IP lama, perbedaan kota
  dicatat (bukan kegagalan).
- Pemilik jaringan tetap ip2asn (ASUMSI T15), jadi angka "IP dengan pemilik ≥ 1.734" tetap berlaku.

⚠ **Bergantung P6** (lisensi ip2asn belum dicek; hanya memengaruhi teks atribusi, bukan kode).
Sumber batas provinsi (Natural Earth 10m) adalah unduhan baru, public domain; kecocokan dengan 38 provinsi
dicatat untuk Q3 dan dipakai di Tahap 20.

---

## Tahap 8 — Uji kesetaraan E1, E3, E4

**Tujuan.** Membuktikan angka v2 sama dengan sistem lama sebelum ada API dan tampilan (PRD §6.2, R2, R9;
TRD §9.3).

**File dibuat**

- `tools/ekstrak_dashboard.py`: mengambil objek `D` dari `../dashboard.html` → JSON.
- `tools/acuan_lama.py` (sudah ada): ditambah nilai "seharusnya" untuk butir 2, 4, 9 TRD §4.4, dihitung
  dari statistik mentah sistem lama.
- `tests/test_equivalence.py`:
  - **E1** setiap angka `00-acuan.json` × (folder, layanan) vs query agregat → sama persis.
  - **E3** `D.ipinfo` dan `D.geo` vs `ip_info`.
  - **E4** daftar selisih tertutup (TRD §4.4 butir 1, 2, 3, 4, 9): nilai lama, nilai baru, nilai seharusnya.
- `tools/laporan_kesetaraan.py`: mencetak tabel sama / berbeda / selisih yang diharapkan.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `python3 tools/acuan_lama.py` | `docs/00-acuan.json` diperbarui; angka 11 folder lama tidak berubah |
| `pytest tests/test_equivalence.py -q` | semua lulus |
| `py tools/laporan_kesetaraan.py` | E1: 0 berbeda dari seluruh angka; E3: 0 berbeda; E4: hanya butir yang terdaftar, mis. error koneksi pod `2026-09-30` lama 200 → baru 1.200 |

Bila ada selisih di luar daftar: **berhenti**, cari sebabnya di Tahap 3–6; daftar selisih tidak boleh
ditambah tanpa persetujuan pemilik.


---

## Tahap 9 — Gerbang ukuran dan kinerja

**Tujuan.** Memastikan atau membatalkan ASUMSI T1 (data setahun ≤ 10 GB) dan target kecepatan query,
sebelum API dan tampilan dibangun di atas skema ini (PRD §5.1–§5.3, R4; TRD §9.7).

**File dibuat**

- `tools/simulasi_setahun.py`: menggandakan baris mentah folder `2026-09-29` ke N tanggal folder di
  database **terpisah** (`data/sim.duckdb`), lalu menurunkan agregat.
- `tools/ukur.py`: ukuran file per tabel; waktu query yang akan dipakai tiap halaman (dari agregat); waktu
  ingest satu folder tambahan; waktu ingest tanpa perubahan.
- `docs/04a-hasil-ukur.md`: hasil ukur dan keputusan.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `df -h .` | cukup ruang; **bila bebas < 15 GB, pakai `--folders 90`** dan ekstrapolasi ×4,06 |
| `py tools/simulasi_setahun.py --folders 365` (atau 90) | selesai; database simulasi terbentuk |
| `py tools/ukur.py data/sim.duckdb` | ukuran setahun ≤ 10 GB; query per halaman ≤ 200 ms; Tren 365 folder ≤ 500 ms; ingest satu folder ≤ 60 detik; tanpa perubahan ≤ 5 detik |
| `rm data/sim.duckdb` | ruang dikembalikan |

**Gerbang.** Bila ukuran > 10 GB: terapkan cadangan T1 (tabel kamus untuk `ua`/`path`), ulangi Tahap 4–8,
ukur lagi. Bila tetap meleset: berhenti dan minta keputusan (P7).

⚠ **Bergantung P7** (berapa lama data disimpan, berapa disk tersedia).

---

## Tahap 10 — API: kerangka, login, peran, ingest dalam proses

**Tujuan.** Server berjalan sebagai satu proses pemilik DuckDB (TRD K1), dengan login, sesi, dua
peran (admin, user), audit, dan pemicu ingest (TRD §5.2, §5.5, §5.6, §8.1–§8.3). Belum ada endpoint halaman.

**File dibuat**

- `simpel4/auth.py`: model ORM akun di PostgreSQL/SQLite (TRD §2.6, K11), hash scrypt, sesi JWT di cookie, penguncian, CSRF, audit, token mesin,
  dependensi "butuh sesi" dan "butuh admin".
- `simpel4/api/app.py`: aplikasi FastAPI, satu koneksi DuckDB, format galat, header keamanan (CSP),
  penyajian berkas statis, pemeriksaan "setiap router mendeklarasikan peran" saat mulai.
- `simpel4/api/common.py`: validasi parameter (TRD §8.1), sel IP + pemilik, kerangka endpoint tabel.
- `simpel4/api/session.py` (`/api/auth/*`, `/api/me`), `users.py` (`/api/admin/users`, `audit`),
  `admin.py` (`/api/admin/ingest`, `status`, `derive`, `forget`), endpoint `/api/health`, `/api/meta`,
  `/api/folders/{folder}`.
- `simpel4/cli.py`: `serve`; `user create --admin`; `ingest`/`derive`/`forget` mencoba API dulu (token
  mesin), baru membuka DuckDB sendiri bila server mati.
- `run.sh`: lingkungan, admin pertama, bangun frontend bila ada, `serve`.
- `tests/test_auth.py`, `tests/test_api.py` (bagian kerangka): butir TRD §9.6 kecuali impor.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `pytest tests/test_auth.py tests/test_api.py -q` | semua lulus |
| `S4_ADMIN_USER=admin S4_ADMIN_PASSWORD='<sandi 12+>' S4_COOKIE_SECURE=false py -m simpel4 serve &` | mendengar di `127.0.0.1:8000`; ingest awal "0 file berubah" |
| `curl -s -o /dev/null -w "%{http_code}" localhost:8000/api/meta` | `401` |
| `curl -s -c /tmp/c -H 'Content-Type: application/json' -d '{"username":"admin","password":"…"}' localhost:8000/api/auth/login`, ganti sandi pertama (`POST /api/me/password`), lalu `curl -s -b /tmp/c localhost:8000/api/meta` | daftar 11 folder dengan rentang waktu; `ingest.running: false` |
| `curl -s -b /tmp/c localhost:8000/api/folders/2026-10-06` | 7 layanan; nginx `err` 125; `attack_ip_count` 14 |
| Admin membuat user `uji` (peran user); masuk sebagai `uji`: `GET /api/folders/2026-10-06`, lalu `GET /api/admin/users` | yang pertama 200 dengan 7 layanan (sama dengan admin); yang kedua `403` |
| `py -m simpel4 ingest` saat server berjalan | lewat API; "0 file berubah"; tidak ada galat kunci file |
| `curl -sI -b /tmp/c localhost:8000/api/meta` | header `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy` ada |
| Enam kali login dengan sandi salah | percobaan ke-6 → `429` |

Akun lokal (X1) dan dua peran tanpa pembatasan per modul (X10) sudah diputuskan; tidak ada pertanyaan
terbuka untuk tahap ini.

---

## Tahap 11 — API data semua halaman + uji kesetaraan E2

**Tujuan.** Sepuluh endpoint halaman dan endpoint tabel (TRD §5.3–§5.4), terbuka untuk kedua peran
(TRD §8.3), dan isi daftar terbukti sama dengan sistem lama (E2).

**File dibuat**

- `simpel4/api/overview.py`, `map.py`, `trends.py`, `security.py`, `rootcause.py`, `availability.py`,
  `pods.py`, `business.py`, `tracing.py`, `service.py`: satu modul per halaman.
- `simpel4/api/common.py`: definisi 25 tabel (kolom, kolom yang boleh diurut, kolom teks untuk `q`, batas
  bawaan).
- `tests/test_api.py` (lanjutan): bentuk respons, `available: false`, validasi dan upaya penyisipan pada
  tiap parameter, ukuran respons ≤ 500 KB, **matriks peran** yang dibuat dari tabel TRD §8.3.
- `tests/test_equivalence.py` (lanjutan) **E2**: tiap daftar di `D` vs respons API dengan `limit` = batas
  lama.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `pytest tests/test_api.py -q` | semua lulus; matriks peran mencakup semua endpoint |
| `pytest tests/test_equivalence.py -q` | E1–E4 lulus; E2: tiap daftar sama (urutan boleh beda hanya di antara nilai sama) |
| `curl -s -b /tmp/c localhost:8000/api/folders/2026-10-06/security \| py -m json.tool \| head -20` | `kpi.attack_requests` 88, `attack_ips` 14 |
| `curl -s -b /tmp/c "localhost:8000/api/folders/2026-09-30/availability"` | KPI error koneksi pod 1.200 |
| `curl -s -b /tmp/c "localhost:8000/api/folders/2026-09-28/map"` | `available: false`, `reason: "no_nginx"` |
| `curl -s -b /tmp/c "localhost:8000/api/folders/2026-09-29/tables/c401?limit=5&q=count"` | `total` 653; ≤ 5 baris; `matched` ≤ 653 |
| `curl -s -o /dev/null -w "%{http_code}" -b /tmp/c "localhost:8000/api/folders/2026-09-29/tables/c401?sort=1;drop"` | `400` |
| `py tools/ukur.py --api localhost:8000` | tiap endpoint halaman ≤ 300 ms dan ≤ 500 KB pada folder `2026-09-29` |

⚠ **Bergantung X6** (tabel alur 100 baris pertama; satu angka).

---

## Tahap 12 — Kerangka tampilan dan komponen bersama

**Tujuan.** Aplikasi Svelte dengan kerangka, login, dua bahasa, dua tema, keadaan memuat/kosong/gagal, dan
semua komponen bersama (DRD §2, §4, §5, §6, §8, §9), diuji dengan satu halaman contoh. Belum ada halaman
data.

**File dibuat**

- `web/package.json`, `vite.config.js`, `index.html`; dependensi TRD §6.4.
- `web/src/theme.css` (token DRD §5.1–§5.5), huruf dibundel.
- `web/src/i18n/id.json`, `en.json`, `i18n.js`; `tools/cek_i18n.mjs` (kunci kedua berkas harus sama).
- `web/src/state.js` (tab, folder, modul ↔ URL), `api.js` (401 → layar Masuk; 403 → "tidak punya akses"),
  `format.js` (waktu WIB, durasi, angka, rentang; padanan pemformat lama).
- `web/src/App.svelte`; `web/src/lib/`: `Sidebar`, `Header`, `FolderPicker`, `UserMenu`, `Kpi`,
  `ChartCard`, `HBar`, `DataTable`, `IpCell`, `SeverityTag`, `StatusCode`, `Alert`, `Note`, `Skeleton`,
  `EmptyState`, `ErrorState`.
- `web/src/pages/Login.svelte`, `ChangePassword.svelte`, `Placeholder.svelte`.
- `tests/test_format.mjs`: pemformat vs contoh di inventaris §2.0.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `cd web && npm ci && npm run build` | `web/dist/` terbentuk tanpa peringatan galat |
| `node tools/cek_i18n.mjs` | "kunci sama: N" |
| `node --test tests/test_format.mjs` | lulus (`28 Sep 2026 06.03 WIB`, `2,35 dtk`, `1 mnt 52 dtk`, EN `06:03`) |
| `grep -rEoh "https?://[^\"' )]+" web/dist \| sort -u` | hanya tautan atribusi (maxmind.com, geonames.org, naturalearthdata.com) dan skema XML |
| `./run.sh` lalu buka `http://127.0.0.1:8000` | layar Masuk → setelah masuk: sidebar dua grup dengan lencana (Keamanan `14 IP`), pemilih folder berisi 11 folder, subjudul memuat rentang waktu log |
| Di browser: ganti bahasa, tema, folder; muat ulang halaman | pilihan bahasa/tema diingat; folder dan tab ada di alamat |
| Masuk sebagai user biasa | sidebar sama dengan admin; menu user tanpa "Kelola user" dan "Ingest & impor"; alamat layar admin → "tidak punya akses" |
| Lebar jendela 390 px dan 360 px | laci navigasi; KPI 2 kolom; tabel > 4 kolom tampil sebagai kartu baris; target sentuh ≥ 44 px; tidak ada gulir mendatar halaman |
| Ponsel sungguhan (bukan hanya emulasi), lewat alamat jaringan lokal | masuk, ganti folder, buka laci, gulir tabel: semuanya nyaman dengan satu tangan |
| Tab keyboard dari atas | "Lewati ke isi" → navigasi → header; fokus selalu terlihat |
| Matikan server saat aplikasi terbuka | pita "Tidak tersambung"; pulih sendiri saat server hidup |

Tampilan ponsel serius (Q1, diputuskan): mode tabel-jadi-kartu di `DataTable` dan laci navigasi **wajib**
di tahap ini. ⚠ **Bergantung Q6** ("–" vs 0 di `Kpi`), **Q7** (urut kolom,
salin, `(i)`, "lihat sebagai tabel", pintasan: boleh ditunda tanpa mengubah tahap lain), **Q8** (logo).
Butuh Tahap 1 untuk sketsa layar Masuk.

---

## Tahap 13 — Halaman Layanan dan Overview

**Tujuan.** Templat halaman layanan (DRD §3.10, inventaris §2.10) dan Overview (DRD §3.1, inventaris §2.1),
yang memakai kartu-kartu layanan nginx. Peta di halaman layanan menyusul di Tahap 20.

**File dibuat**

- `web/src/pages/Service.svelte`, `web/src/lib/ServiceCards.svelte` (kartu 2–19, dipakai juga Overview),
  `MessagesTable.svelte` (baris terbuka + contoh log asli), `web/src/pages/Overview.svelte`.
- Kunci kamus baru di `id.json`/`en.json`.
- `docs/04b-daftar-periksa.md`: daftar periksa halaman × {ID, EN} × {gelap, terang} × {lebar, sempit},
  dibuat dari inventaris §2; dipakai Tahap 13–20.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | lulus |
| Buka Overview folder `2026-10-06` di v2 dan `../dashboard.html` berdampingan | KPI sama: baris 191.898, error 2.810, warning 856, HTTP request 124.822, Rate 4xx 3,6 %, Rate 5xx 0,04 %, layanan 7, file 18; delta ▼ vs 5 Okt sama; tabel dan 25 pesan teratas sama |
| Buka halaman `nginx-ingress-controller`, `om-be-simpel-loop`, `om-be-appsmanager`, `coredns` | kartu yang tampil sesuai tabel centang inventaris §2.10; coredns berjudul "domain gagal resolve" |
| Chart "Aktivitas per jam" nginx | garis Error memuat baris error log (selisih yang diharapkan, TRD §4.4 butir 2) |
| Donat level simpel-loop folder `2026-09-29` | WARN 9.614, tanpa ERROR (butir 4) |
| Folder `2026-10-01` | pita "folder ini hanya berisi 4 baris; file rusak"; halaman layanan menampilkan keadaan kosong |
| Filter tabel pesan: ketik `JWT` | hanya baris cocok; "N baris cocok" |
| Daftar periksa `04b` untuk dua halaman ini | semua butir dicentang di 2 bahasa × 2 tema × 2 lebar |

---

## Tahap 14 — Halaman Tren

**Tujuan.** DRD §3.3, inventaris §2.3.

**File dibuat.** `web/src/pages/Trends.svelte`; kunci kamus.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | lulus |
| Buka Tren berdampingan dengan dashboard lama | 6 chart dan 2 tabel sama untuk 11 folder; kolom `2026-09-30` simpel-loop "Tidak Ada"; `2026-10-01` "Rusak"/"Kosong" |
| Pemilih folder di header | nonaktif dengan keterangan |
| Pemilih rentang 14 / 30 / 90 / semua | jumlah kolom berubah; tabel menggulir mendatar, kolom Layanan terkunci |
| Daftar periksa `04b` | lengkap |

⚠ **Bergantung Q4** (rentang bawaan 30; satu nilai).

---

## Tahap 15 — Halaman Keamanan

**Tujuan.** DRD §3.4, inventaris §2.4, termasuk 9 aturan "Temuan utama" disusun dari komponen (bukan HTML
dalam string).

**File dibuat.** `web/src/pages/Security.svelte`, `web/src/lib/Findings.svelte`, `AttackUrl.svelte` (URL
lengkap dengan base host); kunci kamus (kalimat temuan dua bahasa).

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | lulus |
| Folder `2026-10-06` berdampingan dengan lama | 8 KPI: 88, 14, 5, 62, 9, 1, 0, 4; enam butir temuan yang sama (Log4Shell, Rancher, 62 endpoint 2xx, cloud, jaringan Ombudsman, 4 reset); 6 chart; 5 tabel |
| Folder `2026-09-28` (tanpa nginx) | catatan "deteksi serangan per URL tidak tersedia"; bagian login tetap |
| Tabel "Endpoint dengan indikasi serangan": URL berisi `<script>` atau `${jndi:` | tampil sebagai teks; tidak dieksekusi (periksa konsol browser bersih) |
| `grep -rn "@html" web/src` | tidak ada pemakaian pada data log |
| Daftar periksa `04b` | lengkap |

---

## Tahap 16 — Halaman Akar Masalah dan Ketersediaan

**Tujuan.** DRD §3.5–§3.6, inventaris §2.5–§2.6.

**File dibuat.** `web/src/pages/RootCause.svelte`, `Availability.svelte`; kunci kamus.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | lulus |
| Akar Masalah `2026-09-29` berdampingan dengan lama | ringkasan 5 butir sama; chart JWT sama; **baru**: "Refresh token kedaluwarsa: 237"; tabel 401 menampilkan 30 dari 653 dengan "tampilkan berikutnya" |
| Ketersediaan `2026-09-30` | KPI error koneksi pod **1.200** (lama: 200) dan retry **825**; 10 insiden; selain itu sama |
| Ketersediaan `2026-09-28` | catatan "memakai log ingress nginx…" |
| Daftar periksa `04b` | lengkap |

---

## Tahap 17 — Halaman Pod, Bisnis, Pelacakan Request

**Tujuan.** DRD §3.7–§3.9, inventaris §2.7–§2.9.

**File dibuat.** `web/src/pages/Pods.svelte`, `Business.svelte`, `Tracing.svelte`; kunci kamus.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | lulus |
| Pod `2026-10-06` berdampingan dengan lama | KPI sama; label "Pod dengan retry"; status "Rusak" pada file rusak |
| Bisnis `2026-09-29` | Laporan Dibuat 12, Registrasi 108, OTP Diminta 35, OTP Terverifikasi 12, File Diunggah 314, Upload Ditolak 18, Email Terkirim 55, PDF 813 / 32, Login Sukses 389 |
| Bisnis `2026-09-30` (tanpa simpel-loop) | KPI simpel-loop "–" dengan keterangan, bukan 0 |
| Pelacakan `2026-09-29` | 60.665 / 22.638 / 37,3 %; tabel jejak 300 pertama dengan "tampilkan berikutnya" |
| Pelacakan `2026-09-27` | catatan "butuh log simpel-loop dan ingress nginx…" |
| Daftar periksa `04b` | lengkap |

---

## Tahap 18 — Layar admin: kelola user, ingest, audit

**Tujuan.** Layar di TRD §8.4 (dirancang di DRD pada Tahap 1), di atas API Tahap 10.

**File dibuat.** `web/src/pages/AdminUsers.svelte`, `AdminIngest.svelte` (status ingest, tombol "Ingest
sekarang", catatan audit); kunci kamus.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | lulus |
| Sebagai admin: tambah user baru (peran user); masuk sebagai user itu di jendela lain | wajib ganti sandi; lalu melihat seluruh dashboard seperti admin, tanpa menu admin |
| Admin menaikkan user itu menjadi admin, lalu menurunkannya lagi | menu admin muncul lalu hilang pada permintaan berikutnya |
| Admin mereset sandi / menonaktifkan user | sesi user langsung berakhir |
| Coba hapus atau turunkan admin satu-satunya | ditolak dengan pesan |
| Masuk sebagai user biasa, buka alamat layar admin | "tidak punya akses"; `GET /api/admin/users` → 403 |
| "Ingest sekarang" | status berjalan → selesai, "0 file berubah"; dashboard tetap bisa dibuka selama berjalan |
| Catatan audit | semua tindakan di atas tercatat dengan waktu, pelaku, IP; tanpa sandi atau token |
| Daftar periksa `04b` untuk layar admin | lengkap |


---

## Tahap 19 — Impor dari awalan S3

**Tujuan.** TRD §3.8: tautan `s3://simpel4-backup/k8s-logs/<YYYY-MM-DD>/` → daftar objek → unduh ke kotak
masuk → ingest biasa. Kredensial: kunci akses tetap di `.env` server (impor bisa otomatis); admin bisa
menempel kredensial lain sebagai cadangan (di memori saja).

**File dibuat**

- `pyproject.toml`: tambahan opsional `s3` berisi `boto3`.
- `simpel4/importer.py`: pemeriksaan tautan (bentuk, daftar izin bucket dan awalan, tanggal), daftar
  objek, pemilihan (pola kunci, `.log` menang atas `.log.gz`, lewati yang ukuran + ETag-nya sama), unduhan
  berbatas ke direktori sementara, pemindahan atomik ke kotak masuk, `import_job`, mode coba, penyimpanan
  kredensial sementara di memori.
- `simpel4/api/admin.py`: `POST /api/admin/import`, `GET /api/admin/import/{job_id}`,
  `POST`/`DELETE /api/admin/import/credentials`.
- `simpel4/cli.py`: `import [--dry-run] s3://…`.
- `web/src/pages/AdminIngest.svelte`: kolom tautan, tombol "Coba dulu" dan "Impor", status impor, formulir
  kredensial sementara dengan keterangan kedaluwarsa.
- `tests/s3_tiruan.py` (server S3 kecil untuk uji) dan `tests/test_import.py`: butir impor dan kredensial
  di TRD §9.6.
- `README.md` (bagian impor): contoh kebijakan IAM baca-saja dan cara mengisi `.env`.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `.venv/bin/pip install -e ".[test,s3]" && pytest tests/test_import.py -q` | semua lulus, tanpa menghubungi AWS |
| Tanpa `import_buckets`: `py -m simpel4 import s3://simpel4-backup/k8s-logs/2026-09-26/` | ditolak: "impor tidak diaktifkan" |
| `py -m simpel4 import s3://bucket-lain/k8s-logs/2026-09-26/` dan `…/k8s-logs/bukan-tanggal/` | keduanya ditolak dengan alasan |
| Tanpa kredensial: impor tautan sah | pesan cara memberi kredensial; tidak ada berkas tertulis |
| **Manual, dengan kredensial asli**: `py -m simpel4 import --dry-run s3://simpel4-backup/k8s-logs/2026-09-26/` | daftar objek; untuk tiap objek "ambil" / "lewati (alasan)"; susunannya cocok pola folder log (membuktikan T14); 0 byte diunduh |
| **Manual**: impor `2026-09-26` sungguhan ke database uji terpisah (`S4_DATA_DIR` lain, tanpa folder log lokal) | folder `2026-09-26` muncul; angkanya sama dengan acuan folder lokal: 1.203 baris, 6 error, 11 warning |
| Kirim tautan yang sama lagi | "0 objek diunduh"; tidak ada data ganda |
| `grep -rnE "AKIA|ASIA|aws_secret|SessionToken" data/ 2>/dev/null; py -m simpel4 status` | tidak ada kredensial di disk; status hanya menyebut "kredensial: tersedia (lingkungan)" |
| Sebagai user biasa: buka layar impor / panggil endpoint | "tidak punya akses" / 403 |
| Dengan kunci asli (yang bisa melihat semua bucket): `py -m simpel4 import --dry-run s3://<bucket lain di Jakarta>/x/2026-09-26/` | **ditolak oleh daftar izin sebelum menghubungi AWS** |
| Dengan token mesin: `curl -H "Authorization: Bearer $S4_JOB_TOKEN" -d '{"url":"s3://simpel4-backup/k8s-logs/2026-09-26/"}' …/api/admin/import` | 202; impor lalu ingest berjalan tanpa orang (otomatisasi) |
| Mulai ulang server setelah menempel kredensial sementara | kredensial hilang; impor meminta lagi |

Dua baris bertanda **Manual** butuh kredensial AWS asli dan akses internet ke S3; bila belum tersedia saat
tahap dikerjakan, tahap dilaporkan **SEBAGIAN** dan dua baris itu disebut belum diuji.

Kunci yang dipakai baca-saja tetapi bisa melihat semua bucket di wilayah Jakarta, jadi uji daftar izin di atas adalah
verifikasi terpenting tahap ini. README memuat saran mengganti kunci dengan pengguna IAM baca-saja khusus
`simpel4-backup/k8s-logs/`.

⚠ **Bergantung X2** (akses keluar server ke S3 Jakarta; pemilik belum tahu, jadi diperiksa di server
dengan `curl -sI https://s3.ap-southeast-3.amazonaws.com` sebelum mengandalkan fitur ini) dan **X3** (apakah folder yang dipasang tetap
dipakai di samping bucket). Tahap ini tidak menghalangi Tahap 20.

---

## Tahap 20 — Peta IP

**Tujuan.** Komponen peta MapLibre (DRD §7) tanpa permintaan ke domain luar, halaman Peta IP (DRD §3.2,
inventaris §2.2), dan peta terlipat di halaman layanan (DRD §3.10).

**File dibuat**

- `web/public/fonts/<fontstack>/{0-255,256-511}.pbf` (glyph Noto Sans, dua ketebalan) + berkas lisensinya.
- `web/src/lib/MapView.svelte`: gaya tanpa `sprite`/`glyphs` luar; 13 lapisan DRD §7.3; preset Indonesia
  dan Dunia; pengelompokan titik; busur; tooltip; gerakan kooperatif; atribusi; ganti tema tanpa
  kehilangan posisi.
- `web/src/pages/IpMap.svelte`; pembaruan `Service.svelte` (peta modul, terlipat); kunci kamus.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | lulus |
| Peta IP `2026-10-06` berdampingan dengan lama | KPI: 516 IP, 222 lokasi, 12 negara, 9 modul, 15 pod, 124.822 request; "2.030 request dari luar Indonesia · 0 dari IP internal"; titik server di Jakarta; 6 lokasi terbesar berlabel |
| Pilih modul `om-be-simpel-loop` | KPI, titik, dan tabel berganti; posisi dan zoom peta tetap |
| Panel Jaringan di alat pengembang browser, muat ulang halaman peta | **semua** permintaan ke asal yang sama; 0 ke domain lain |
| Matikan jaringan komputer, muat ulang | peta, label, dan titik tetap tampil |
| Roda mouse di atas peta | halaman menggulir; petunjuk "Tahan Ctrl…"; Ctrl + roda memperbesar |
| Ponsel / emulasi sentuh 390 px | satu jari menggulir halaman; dua jari menggeser; cubit memperbesar; peta 4 : 3 |
| Keyboard: fokus ke peta, panah, `+`, `−`, `0`, `Esc` | menggeser, zoom, kembali ke preset, menutup tooltip |
| Zoom dari Dunia ke Jawa | kelompok pecah menjadi titik; label negara → provinsi → kabupaten muncul bertahap tanpa bertumpuk |
| Klik titik → "Lihat di tabel" | filter tabel alur terisi nama kota |
| Folder `2026-09-28` | catatan "Peta butuh log ingress nginx…" |
| Ganti tema dan bahasa | warna peta dan nama negara berganti; atribusi MaxMind · GeoNames · Natural Earth selalu terlihat |
| Halaman layanan `om-be-simpel-loop` | peta terlipat; dibuka → hanya alur modul itu |
| `pytest -q` (seluruh uji) | semua lulus, termasuk kesetaraan E1–E4 |
| Daftar periksa `04b` untuk Peta IP | lengkap |

⚠ **Bergantung Q3** (batas provinsi Papua mungkin belum memuat pemekaran; batas kabupaten tidak digambar),
**Q5** (peta di halaman layanan terlipat), **X7** (huruf label Noto Sans). Ketiganya terbatas pada
`MapView.svelte` dan berkas statis.

---

## Tahap 21 — Deteksi serangan: aturan OWASP CRS, kategori CAPEC

**Asal.** Permintaan pemilik (2026-10-06): deteksi serangan memakai OWASP Core Rule Set (CRS) dan
kategorinya dinamai menurut CAPEC. Rincian teknis di TRD §4.6.

**Mengapa di akhir.** Mengganti aturan deteksi mengubah semua angka di tab Keamanan. Kesetaraan dengan
sistem lama harus terbukti dulu dengan aturan lama (Tahap 8), dan halaman Keamanan harus sudah ada (Tahap
15). Setelah itu aturan baru masuk sebagai perubahan yang disengaja dan terukur.

**Cakupan tahap ini = cara "di skrip"**: pola dari CRS dicocokkan ke URL dan User-Agent di log nginx.
Cara "di ingress" (ModSecurity/Coraza mode deteksi, yang juga memeriksa body, header, dan cookie) **tidak**
dikerjakan di sini karena mengubah konfigurasi klaster, di luar jangkauan proyek dashboard; lihat S1.

**File dibuat**

- `tools/ambil_crs.py`: mengunduh satu rilis CRS yang **versinya dikunci**, mengambil aturan dari berkas
  REQUEST-913 (pemindai), 930 (LFI), 931 (RFI), 932 (RCE), 933 (PHP), 934 (generik), 941 (XSS), 942 (SQLi),
  944 (Java) yang sasarannya URI, argumen, atau User-Agent; menyimpan pola, ID aturan, tingkat keparahan,
  tingkat paranoia, transformasi, dan tag CAPEC. Aturan yang polanya tidak bisa dipakai mesin regex Python
  dicatat dan dilewati, tidak diubah diam-diam.
- `simpel4/crs_rules.json` (hasil alat di atas; ikut repo, sehingga tidak ada unduhan saat jalan) +
  berkas lisensi dan pemberitahuan CRS (Apache 2.0).
- `simpel4/capec.json`: ID CAPEC → nama Indonesia dan Inggris untuk kategori yang dipakai.
- `simpel4/detect.py`: menerapkan transformasi CRS yang dibutuhkan (decode URL, huruf kecil, buang
  komentar, dll.) lalu mencocokkan; keluaran per request: ID aturan yang kena, kategori CAPEC, keparahan,
  skor anomali.
- `simpel4/schema.sql`: kolom baru di `nginx_access` (`crs_rules`, `capec`, `crs_severity`, `crs_score`);
  kolom `attack_cat` lama **dipertahankan** agar uji kesetaraan tetap bisa dijalankan.
- `simpel4/derive/`: agregat serangan dihitung dari klasifikasi baru; `rules_version` naik.
- `web/src/pages/Security.svelte`, kamus: kategori CAPEC, kolom "Aturan" (ID CRS), keterangan metode.
- `tests/test_detect.py`: (a) muatan serangan dikenal per kategori → kena; (b) 22 ribu path nyata yang
  sekarang "bersih" → tingkat salah-tuduh diukur dan dilaporkan; (c) semua request yang kena aturan lama
  → dicatat mana yang juga kena CRS dan mana yang tidak.
- `docs/04c-deteksi-crs.md`: perbandingan lama vs baru per folder, daftar aturan yang dilewati, dan
  keterbatasan.

**Verifikasi**

| Perintah | Hasil yang diharapkan |
|---|---|
| `py tools/ambil_crs.py --check` | versi CRS terkunci; jumlah aturan diambil dan dilewati dicetak; `crs_rules.json` tidak berubah bila dijalankan ulang |
| `pytest tests/test_detect.py -q` | semua lulus; tiap kategori punya contoh yang kena |
| `py -m simpel4 derive --all` lalu `py tools/laporan_kesetaraan.py` | E1–E4 **tetap lulus** untuk angka lama (kolom `attack_cat`); angka serangan baru dilaporkan terpisah |
| Baca `docs/04c-deteksi-crs.md` | untuk tiap folder: request serangan lama vs baru, per kategori; salah-tuduh pada lalu lintas normal < 0,5 % pada tingkat paranoia 1, atau aturan penyebabnya didaftar |
| `time py -m simpel4 ingest --folder 2026-09-29 --force` | tetap ≤ 60 detik |
| Halaman Keamanan folder `2026-10-06` | kategori bernama CAPEC dalam dua bahasa; tiap baris menyebut ID aturan CRS; catatan kaki menyebut CRS, versinya, dan bahwa hanya URL dan User-Agent yang diperiksa |

**Keterbatasan yang tetap ada** (ditulis juga di halaman): body POST, header selain User-Agent, dan cookie
tidak ada di log, jadi tidak diperiksa. Ini bukan pengganti WAF.

⚠ **Bergantung S1** (di bawah). Dengan asumsi yang dipakai, tahap ini bisa dikerjakan tanpa menunggu.

---

## Tahap 12a — Gaya mengikuti referensi desain pemilik

**Tujuan.** Permintaan pemilik 2026-10-06 (DRD §12): tampilan seperti gambar referensi, diterapkan pada token dan
komponen bersama **sebelum** halaman data dibangun, supaya Tahap 13–20 tidak ditata dua kali.
R6 terjawab: berlaku untuk **seluruh dashboard**.

**File diubah**: `web/src/theme.css`, `lib/Sidebar.svelte` (ikon SVG dibundel), `lib/Kpi.svelte` (ikon + badge),
`lib/Alert.svelte` → kartu perhatian bernomor dengan tautan, `App.svelte` (baris status ringkas di bawah judul).

**Verifikasi**: `node tools/uji_browser.cjs` tetap lulus; tangkapan layar 1440/390 px dibandingkan dengan referensi;
kontras token baru dihitung (DRD §5.6); `grep` URL di `web/dist` tetap tanpa domain luar.

---

## Tahap 22 — Command Center (halaman)

**Tujuan.** Layar **peta dunia** (R5): peta asal IP → server sebagai isi utama, dikelilingi KPI utama, kartu "yang
perlu perhatian", dan pemilih modul; memakai endpoint dan komponen yang sudah ada (TRD §12). Overview tetap halaman
terpisah. **ASUMSI**: menyerap tab "Peta IP" (Tahap 20 membangun komponen peta, tahap ini menjadikannya Command Center). Datanya dari folder log (sumber utama); diperbarui saat folder
baru di-ingest atau tombol "Muat ulang", tanpa aliran realtime (Kafka ditunda).
⚠ **Bergantung R5**.

---

## Tahap 23 — Aliran realtime dari Kafka

**DITUNDA** (keputusan pemilik 2026-10-06): folder log tetap sumber utama pembaruan; Kafka hanya untuk ke depan.
Tahap ini tidak dijalankan oleh `migrate/06-eksekusi.md` sampai pemilik membukanya kembali.

**Tujuan (nanti).** Konsumen Kafka di dalam proses server (K1), tabel `rt_*`, endpoint SSE `/api/stream`, penanda
"streaming · kejadian terakhir N detik lalu" di Command Center (TRD §12). Bergantung R1, R2, R4.

---

## Catatan penyimpangan

Diisi `migrate/06-eksekusi.md` setiap tahap selesai: nomor tahap, tanggal, apa yang berbeda dari rencana
atau dari TRD/DRD, dan alasannya.

| Tahap | Tanggal | Penyimpangan |
|--:|---|---|
| 1 | 2026-10-06 | (a) `docs/03-trd.md` §10 ikut diubah dua kalimat: diberi status "sudah diterapkan" dan saran yang sudah dilaksanakan dihapus; isi teknis TRD tidak berubah. (b) DRD mendapat §6.9 (perilaku masuk, sesi, peran) di samping §3.11 yang direncanakan, dan perubahan U28–U32. (c) PRD mendapat risiko baru R11–R13 dan kriteria sukses untuk login, ponsel, dan impor S3, yang tidak disebut di daftar file tahap ini tetapi mengikuti keputusan pemilik. Verifikasi: 3 dari 3 lulus (grep frasa lama = 0; tiga istilah layar ditemukan; 19 baris TRD §10 punya padanan). |
| 2 | 2026-10-06 | (a) Uji `classify` memakai User-Agent dari log nginx **dan** log frontend: log nginx saja hanya punya 359 UA unik, di bawah syarat 500. (b) `rules.py` memuat tiga hal di luar daftar TRD §4.1, semuanya salinan dari sumber lama: 13 pola yang di sistem lama ditulis langsung di dalam `parse()` kini bernama (uji memastikan teks polanya ada di sumber lama); `pod_name()` dan `split_relpath()` dari `build()`. (c) `load_ip2asn()` dan `map_labels()` menerima path berkas sebagai parameter, karena di v2 lokasi cache bisa dikonfigurasi; isinya tidak berubah. (d) Uji tambahan di luar rencana: kesamaan definisi semua pola/tabel, `map_labels` (177/38/514), dan hasil `geo_scan` vs `.cache/geo.json` lama. (e) `fetch()`, `HOSTS`, `SERVER_IP` ikut disalin; uji tidak pernah mengunduh. Verifikasi 4 dari 4 lulus: pemasangan tanpa galat (duckdb 1.5.6, fastapi 0.142, uvicorn 0.54, pytest 9.1); `pytest tests/test_rules.py` 16 lulus, 0 dilewati, 27 detik; `status` mencetak konfigurasi dan "belum ada database"; file lama dan `.cache` tidak berubah. |
| 3 | 2026-10-06 | (a) Python minimal naik ke 3.12: CSV memakai `csv.QUOTE_NOTNULL` agar teks kosong dan NULL terbedakan. (b) CSV parser tidak memuat `file_id` dan `folder`; ingest (Tahap 4) menambahkannya saat memuat. Kolom daftar (`up_addrs`, `up_statuses`) ditulis `a,b` dan dipecah saat muat. (c) Level `alert`/`emerg` dihitung error juga di **ingress** (lama: warning), mengikuti TRD §4.4 butir 3 yang menyamakan kedua layanan; pada data sekarang tidak ada baris seperti itu. (d) `file_counter` jenis `level` menyimpan tag **asli** simpel-loop (sama dengan sistem lama); tingkat efektif (TRD §4.4 butir 4) dihitung di SQL Tahap 5 dari `sl_event`. (e) Template PDF diingat per thread **per file**, bukan per layanan lintas file seperti sistem lama; pada tiga folder uji hasilnya identik. (f) Baris Spring yang cocok lebih dari satu pola login menggagalkan file (bukan kehilangan event diam-diam); tidak terjadi pada data. (g) Kolom `upstream_host`/`kind`/`request` diisi juga untuk error log frontend; view `v_upstream_error` tetap hanya ingress. (h) Catatan untuk Tahap 6: teks error event simpel-loop di sistem lama adalah `f"{name}: {message}"`, jadi nilai kosong harus menjadi teks `None` di SQL. (i) Uji (b) lebih dalam dari rencana: selain baris/error/warning/level per file, isi yang kelak diagregasi (status, IP, endpoint, alur, pod, retry, insiden, serangan, durasi, pesan + contoh, event simpel-loop, login, restart, JWT, PDF) dibandingkan dengan statistik mentah parser lama. Verifikasi 3 dari 3 lulus: `pytest tests/test_parse.py` 36 lulus, 2 dilewati (folder 09-27 memang tanpa nginx dan coredns); parse file 5v8j4: `lines=111301`, 3 CSV, 4 detik; skema: 43 tabel + 4 view, aman dijalankan dua kali. Seluruh uji: 52 lulus, 2 dilewati. |
| 4 | 2026-10-06 | (a) Folder log uji tidak disimpan sebagai berkas di `tests/fixtures/logs_mini/`, melainkan dibangun tiap uji oleh `tests/logs_mini.py` dari baris asli di `fixtures/lines/`, karena uji perlu mengubah berkasnya. (b) Pemindai menelusuri hanya folder teratas berbentuk tanggal (bukan `glob` seluruh pohon), agar `v2/.venv` dan `node_modules` tidak ikut ditelusuri; hasilnya sama dengan aturan lama. (c) Tambahan di luar TRD: saat sebuah `.log` di-parse dan pasangan `.log.gz`-nya ada, pasangan itu ikut di-hash sekali; bila berbeda dicatat peringatan. **Hasil pada data nyata: 0 peringatan, jadi semua pasangan `.log`/`.log.gz` yang ada identik** (menjawab X5/P5 untuk data sekarang). (d) File yang gagal di-parse dicatat `gagal` dan dicoba lagi tiap ingest. (e) Kurang dari 3 file diproses di dalam proses, tanpa subproses. (f) Waktu di database ditulis UTC dari Python, bukan `now()` DuckDB yang mengikuti zona waktu mesin. (g) `derive_folder()` baru mengisi `folder_state`; agregat menyusul di Tahap 5. (h) **Atas permintaan pemilik di tengah tahap**: semua konfigurasi dan rahasia kini bisa (dan sebaiknya) ditaruh di `v2/.env`; `config.py` membaca `.env` sendiri, daftar/kamus ditulis JSON, `.env.example` dibuat, `tests/test_config.py` ditambahkan (11 uji), dan TRD §6.3 diperbarui. Verifikasi 6 dari 6 lulus: `pytest tests/test_ingest.py` 17 lulus; ingest awal 195 file / 11 folder / 0 gagal dalam 11 detik (batas 3 menit); total 774.264 baris, `nginx_access` 308.158, `fe_access` 148.049, `sl_event` 114.574, 52 file 0 baris; ingest kedua 0 file berubah dalam 0,1 detik; checksum 43 tabel sama sebelum dan sesudah; folder log dan file lama tidak berubah. Tambahan: baris/error/warning per (folder, layanan) dan jumlah file sama dengan `00-acuan.json` untuk 81 pasangan; ingest ulang folder terbesar (09-29) 6 detik. Seluruh uji: 80 lulus, 2 dilewati. Catatan untuk Tahap 9: database 52 MB untuk 11 folder, kira-kira 24 MB per folder penuh, jadi ±9 GB setahun **sebelum** agregat; dekat batas 10 GB. |
| 5 | 2026-10-06 | (a) `folder_state` kini diisi oleh paket `derive` (bukan `ingest.py`); `ingest.derive_folder()` hanya memanggilnya. (b) `agg_hour` bisa memuat jam ber-`total = 0`: jam yang hanya berisi baris error log nginx/frontend (akibat TRD §4.4 butir 2). (c) Ditemukan saat menulis SQL dan dipertahankan demi kesetaraan: di sistem lama kunci `perr` **frontend** tidak memuat metode HTTP (hanya `path_key`), berbeda dari ingress dan simpel-loop; inventaris §1.3 menulisnya seragam. (d) `err_http` simpel-loop = event gagal berstatus 5xx; `users_ok` sudah dihitung di tahap ini. (e) `status --folder` kini juga mencetak ringkasan agregat. (f) Uji lebih dalam dari rencana: selain nilai hitung-tangan pada `logs_mini`, semua agregat inti untuk dua folder nyata (09-30 dan 10-06, 11 layanan) dibandingkan dengan statistik mentah parser lama tanpa pemotongan; uji terbukti gagal bila SQL sengaja dirusak (pemotongan UA, indeks persentil). Verifikasi 5 dari 5 lulus: `pytest tests/test_derive_core.py` 14 lulus; `derive --all` 11 folder dalam 1 detik; folder 09-29: nginx request 132.203 / 4xx 4.635 / 5xx 59 / error 94 / warning 164 / IP unik 723 / alur 1.762, simpel-loop request 60.665 / warning 9.614; folder 09-30: error 1.690, error koneksi pod 1.200, retry 825; checksum sama setelah `derive --all` kedua. Tambahan: 910 angka `00-acuan.json` (semua folder × layanan, untuk agregat tahap ini) sama persis, 0 berbeda. Seluruh uji: 94 lulus, 2 dilewati. Catatan untuk Tahap 8: distribusi level simpel-loop sengaja berbeda dari acuan (tingkat efektif), masuk daftar selisih yang diharapkan. |
| 6 | 2026-10-06 | (a) Hanya tiga agregat ditulis sebagai SQL (`17_login`, `18_mail`, `19_report`). Serangan, akun, insiden, korelasi/jejak, bisnis/aktivitas, dan JWT diturunkan di **satu** modul Python `derive/steps.py` (bukan `accounts.py` + `incidents.py` terpisah), karena memakai fungsi `rules.py` apa adanya atau bergantung pada `unquote_plus()` dan urutan kemunculan yang tidak punya padanan persis di SQL. Masukannya hasil query kecil, bukan seluruh log. (b) `rules.accounts()` memotong hasil di 150 baris; dipanggil per akun agar `agg_account` tidak terpotong (TRD K4); logikanya tidak diubah. (c) `agg_login_*`, `agg_account` hanya dari `om-be-appsmanager` dan `agg_report` hanya dari `om-be-report`, seperti yang dibaca tampilan lama. (d) Penyegaran korelasi lintas folder hanya menangkap kecocokan yang bertambah (ditandai `ponytail:`); bila file nginx dihapus, folder lain tidak disegarkan sampai `derive --all`. Pada data nyata kecocokan lintas folder = 0. (e) Dua sumber ketidakstabilan ditemukan lewat pemeriksaan checksum dan diperbaiki: urutan kunci di `agg_incident` (kini mengikuti urutan kemunculan pertama, sama dengan sistem lama) dan `dur_avg` di `agg_endpoint` dari Tahap 5 (rata-rata `DOUBLE` paralel; kini dihitung dari daftar terurut). (f) Uji lebih dalam dari rencana: tiga folder nyata (09-29, 09-30, 10-06) dibandingkan dengan statistik mentah sistem lama termasuk `correlate()`; uji terbukti gagal bila kode sengaja dirusak. Verifikasi 4 dari 4 lulus: `pytest tests/test_derive_features.py` 12 lulus; folder 09-29: serangan 155 request / 77 URL / 12 IP, korelasi 22.638 dari 60.665, jejak 550 baris (lama: dipotong 300), login gagal 86 / reset 24 / sukses 389, akun 39, insiden 7, PDF 813 / 32; folder 10-06: serangan 88, korelasi 4.161 dari 5.981, Laporan Dibuat 7; ingest ulang 09-29 dengan `--force` 6 detik (batas 60). Tambahan: 263 angka `00-acuan.json` untuk agregat tahap ini sama persis; `derive --all` tiga kali berturut-turut menghasilkan checksum identik (4 detik untuk 11 folder). Seluruh uji: 106 lulus, 2 dilewati. |
| 7 | 2026-10-06 | (a) Unduhan MaxMind mengalihkan ke URL bertanda tangan yang **menolak** header `Authorization` (400); `refdata.py` membuang header itu saat mengikuti pengalihan. (b) Sapuan lokasi ditulis ulang untuk rentang `int` (`refdata.sweep`) karena blok GeoLite2 berbentuk CIDR, bukan pasangan IP teks; kesamaannya dengan `rules.geo_scan()` lama dibuktikan uji. (c) Kolom `offline` ditambahkan ke konfigurasi (`S4_OFFLINE`, serta `ingest --offline` dan `refdata --offline`): tanpa itu uji akan mengunduh. Semua uji lama kini berjalan luring. (d) Blok GeoLite2 tanpa `geoname_id` memakai negara terdaftar: menghasilkan negara tanpa nama kota. (e) Berkas peta dibuat ulang hanya bila belum lengkap; kegagalannya tidak membatalkan hasil `ip_info`. (f) Koordinat GeoJSON dibulatkan 2 desimal (≈ 1 km), sama dengan peta lama; `land.geojson` 992 KB, batas negara 304 KB, batas provinsi 342 KB. (g) **Temuan untuk Tahap 20 / Q3**: Natural Earth 10m hanya memuat **33** provinsi Indonesia; dua provinsi hasil pemekaran 2022 (Papua Barat Daya, Papua Pegunungan) punya label GeoNames tetapi belum punya garis batas. (h) **Temuan untuk Tahap 20**: GeoLite2 memberi koordinat untuk IP server tetapi **tanpa nama kota** (blok tingkat negara), jadi label titik server perlu memakai `server_fallback`. 317 IP lain juga berkoordinat tanpa nama kota. (i) Perbandingan dengan DB-IP lama atas 1.676 IP yang sama: **negara sama 99 %** (1.657), kota sama 23 % (393) — selisih antar-vendor yang diharapkan, dicatat sebagai selisih untuk Tahap 8; contoh: Citeureup→Bogor, Cimahi→Bandung, Jakarta→Central Jakarta. Verifikasi 5 dari 5 lulus: `pytest tests/test_refdata.py` 13 lulus (tidak ada uji yang menyentuh jaringan); `refdata` mengisi 2.691 IP (2.689 dapat pemilik dan lokasi) dan membuat 4 berkas peta; `status`: pemilik 2.689 (≥ 1.734), **100 %** IP publik v4 punya lokasi (syarat ≥ 95 %), server di Jakarta (−6,175; 106,8286); `labels.json` 177 negara / 38 provinsi / 514 kabupaten-kota; `refdata --offline` **dan** ingest penuh dengan seluruh koneksi keluar diblokir (proxy ke port mati) selesai tanpa galat. Tambahan: pemilik jaringan **sama persis dengan dashboard lama untuk seluruh 1.734 IP** (0 berbeda, 0 hilang) — bukti awal E3; kunci MaxMind tidak muncul di keluaran `status`, basis data (0 kemunculan di seluruh kolom teks), maupun berkas mana pun selain `.env`. Seluruh uji: 119 lulus, 2 dilewati. |
| 8 | 2026-10-06 | (a) Pembanding ditaruh di satu modul bersama `tools/kesetaraan.py` yang dipakai uji **dan** laporan, supaya definisinya tidak bercabang. (b) Dua kesalahan ditemukan dan diperbaiki saat tahap ini, keduanya di alat pembanding/acuan, bukan di v2: `login_ip` pada `00-acuan.json` ternyata berarti *semua* IP yang punya event login (termasuk sukses saja), bukan KPI "IP dengan login gagal"; dan nilai "seharusnya" untuk `lambat ≥ 5 dtk` semula dihitung dari daftar jejak yang sudah dipotong 300 baris, kini dihitung dari event terkorelasi. (c) E4 butir 1 juga memeriksa dua ukuran yang batasnya **belum** pernah tercapai (IP login gagal 100, akun 150), supaya ketahuan bila kelak tercapai. (d) `tools/ekstrak_dashboard.py` menyimpan hasil ekstraksi ke `data/dashboard-lama.json` (tidak masuk git) dan membuatnya ulang bila `dashboard.html` lebih baru. (e) Uji dilewati dengan keterangan bila database, `dashboard.html`, atau acuan tidak ada, atau bila daftar foldernya tidak sepadan. Verifikasi 3 dari 3 lulus: `tools/acuan_lama.py` dijalankan ulang (11 folder, angka inti tidak berubah); `pytest tests/test_equivalence.py` 12 lulus; laporan: **E1 3.022 angka, 0 berbeda; E3 1.734 IP, 0 berbeda; E4 169 pemeriksaan, 0 tidak sesuai**. Selisih yang diharapkan muncul tepat pada butir 1, 2, 4, dan 9 (butir 3 tidak berubah karena tidak ada baris `crit` di frontend): mis. error koneksi pod 09-30 200 → 1.200, klien 401 09-29 30 → 653, Σ error per jam nginx 09-29 59 → 94, level simpel-loop ERROR 552 → 0 / WARN 0 → 552, lambat ≥ 5 dtk 09-29 15 → 24, jejak 300 → 550 (tidak dipotong lagi). Lokasi IP sengaja tidak dibandingkan (sumber kini GeoLite2): negara sama 99 %, kota sama 23 %, dicatat di laporan. Alat diuji dengan menghapus sebagian baris `agg_c401` dengan sengaja: laporan menangkapnya di E1 **dan** E4 lalu keluar dengan kode 1, dan kembali 0 setelah `derive` memulihkannya. Catatan: E1 membandingkan angka ringkas (jumlah baris, total), bukan tiap nilai di dalam baris; perbandingan isi daftar adalah E2 di Tahap 11. Seluruh uji: 131 lulus, 2 dilewati. |
| 9 | 2026-10-06 | **Gerbang LULUS; ASUMSI T1 terbukti**, cadangan tabel kamus tidak diperlukan. (a) Disk bebas ternyata 32 GB (bukan 17 GB seperti saat rencana ditulis), jadi simulasi dijalankan penuh **365 folder**, tanpa ekstrapolasi. (b) Request id diberi awalan per folder di simulasi agar korelasi tetap di dalam folder seperti data nyata. (c) Waktu ingest diukur dua bagian: parse + muat + turunkan pada database nyata, dan menurunkan agregat satu folder di atas database setahun (bagian yang tumbuh dengan ukuran data). (d) Biaya hash sandi ikut diukur untuk Tahap 10. Verifikasi 4 dari 4 lulus: simulasi 365 folder selesai (19 menit; 48,3 juta baris nginx); ukuran **4,75 GB** (≤ 10 GB); 21 query halaman total **20,5 ms**, paling lambat 7,3 ms (≤ 200 ms); Tren 365 folder **5,4 ms** (≤ 500 ms); ingest folder terbesar 6,9 dtk + 1,7 dtk turunkan pada skala setahun (≤ 60 dtk); ingest tanpa perubahan 0,4 dtk (≤ 5 dtk); `sim.duckdb` dihapus, ruang kembali. Rincian dan batas pengukuran di `docs/04a-hasil-ukur.md`. Catatan jujur: simulasi menggandakan satu folder, jadi data nyata yang lebih beragam bisa lebih besar; waktu query belum memuat lapisan HTTP (diukur lagi di Tahap 11); `derive --all` setahun ±10 menit. Kesetaraan tetap 0 berbeda setelah tahap ini. |
| 10 | 2026-10-06 | **Perubahan atas permintaan pemilik di tengah tahap**: "untuk token gunakan jwt untuk database gunakan postgresql dan pakai orm". (a) Akun, sesi, audit, catatan impor pindah dari `sqlite3` mentah ke **SQLAlchemy ORM**; server memakai **PostgreSQL** (`S4_AUTH_DATABASE_URL`), SQLite lewat ORM yang sama bila kosong (uji, jalan lokal). (b) Token sesi menjadi **JWT HS256** (`S4_JWT_SECRET`, wajib, ≥ 32 karakter) di cookie HttpOnly; baris sesi tetap diperiksa di basis data agar keluar/reset/nonaktif berlaku seketika. (c) **ASUMSI T16**: DuckDB tetap untuk data log (lihat TRD K11); perlu konfirmasi pemilik. (d) Tiga dependensi baru: `sqlalchemy`, `psycopg[binary]`, `pyjwt`; compose (langkah 7) mendapat layanan `postgres` + volume `s4-pgdata` menggantikan `s4-state`. (e) Tabel bernama `app_user`/`app_session` (kata kunci PostgreSQL). (f) Skema dibuat `create_all`, belum ada alat migrasi. (g) Verifikasi rencana disesuaikan: admin pertama wajib ganti sandi sebelum `/api/meta` (sesuai TRD §8.2), dan penguncian diuji pada akun yang ada. Hasil: uji akun + API **64 lulus di SQLite dan 64 lulus di PostgreSQL 17**; seluruh uji 195 lulus, 2 dilewati; server nyata di atas PostgreSQL: 17 dari 17 pemeriksaan lulus (401 tanpa sesi; cookie JWT HttpOnly SameSite=Strict; 11 folder; 2026-10-06 = 7 layanan, nginx err 125, attack_ip_count 14, sama untuk admin dan user; user → `/api/admin/users` 403; `simpel4 ingest` lewat API "0 file berubah"; header CSP/nosniff/Referrer-Policy; login salah ke-6 → 429; sesi mati setelah keluar; tidak ada rahasia di log server). |
| 11 | 2026-10-06 | (a) Endpoint halaman, endpoint tabel, uji Tahap 11 di `test_api.py`, dan E2 di `tools/kesetaraan.py`/`test_equivalence.py` **sudah ada di repositori** saat sesi ini mulai (dikerjakan sebelumnya tetapi belum ditandai selesai); sesi ini membangun ulang database dari nol, menjalankan semua verifikasi, dan melengkapi yang kurang. (b) Semula sepuluh halaman ada dalam satu `api/pages.py`; kini **dipecah satu modul per halaman** sesuai TRD (`overview.py`, `map.py`, `trends.py`, `security.py`, `rootcause.py`, `availability.py`, `pods.py`, `business.py`, `tracing.py`, `service.py`); bantuan bersama (`_all`, `_one`, `_no`, `_has`, jam WIB) pindah ke `common.py`. (c) Definisi 25 tabel dan endpoint tabel ada di `api/tables.py`, **bukan** `common.py` seperti rencana: satu berkas khusus kontrak tabel (kolom urut, kolom `q`, batas lama) lebih mudah ditinjau; `common.py` tetap berisi validasi, peran, sel IP. (d) `tools/ukur.py --api HOST:PORT` ditambahkan: masuk dengan `--user` (sandi dari `S4_UKUR_PASSWORD` atau ditanya), mengukur 19 endpoint (ringkasan folder, 8 halaman, 7 layanan, Tren 30/semua, meta), keluar kode 1 bila ada yang > 300 ms atau > 500 KB. (e) Aturan E2: setiap baris lama harus ada di daftar **lengkap** v2 dengan isi sama persis, dan urutan nilai pengurut N baris pertama sama; daftar v2 boleh lebih panjang (tidak dipotong lagi, TRD K4). Laporan E2 dicetak `py tools/kesetaraan.py` (E1–E4); `tools/laporan_kesetaraan.py` tetap E1/E3/E4. (f) **ASUMSI X6**: tabel alur bawaan 100 baris (`flows.limit`), sisanya lewat halaman tabel. (g) Pencarian `q=count` pada `c401` 09-29 memberi `matched` 208 (≤ 653). (h) Di sesi ini akun memakai SQLite lewat ORM; PostgreSQL tidak diuji ulang (tidak ada perubahan di `auth.py`). Verifikasi 8 dari 8 lulus: `pytest tests/test_api.py tests/test_equivalence.py` 87 lulus (matriks peran mencakup semua rute); E1 3.022 angka 0 berbeda, **E2 601 daftar / 9.889 baris lama, 0 berbeda**, E3 1.734 IP 0 berbeda, E4 169 pemeriksaan 0 tidak sesuai; server nyata: `security` 10-06 `attack_requests` 88 / `attack_ips` 14; `availability` 09-30 error koneksi pod 1.200; `map` 09-28 `available: false, reason: "no_nginx"`; `c401?limit=5&q=count` total 653, 5 baris; `sort=1;drop` → 400; `ukur.py --api`: 19 endpoint, terlambat `security` 112 ms, terbesar `tracing` 178 KB, 0 meleset. Seluruh uji: 239 lulus, 2 dilewati. **Catatan penggabungan**: baris Tahap 11 berikutnya berasal dari sesi lain yang masuk lewat `master`; butir (a)-nya (satu modul `api/pages.py`) sudah tidak berlaku karena modul itu dipecah per halaman di atas, dan `tools/ukur.py --api` kini menggabungkan kedua versi (tanpa host = di dalam proses; dengan host = `S4_COOKIE` atau masuk dengan `--user`). |
| 12 | 2026-10-06 | **SEBAGIAN: belum diuji di ponsel sungguhan** (DRD §8 mewajibkannya; dari lingkungan cloud hanya emulasi Chromium 390/360 px). (a) Alamat memakai hash `#/<tab>?folder=…&modul=…` karena server menyajikan `web/dist` statis tanpa fallback path; slug tab lama (`#keamanan`, `#<layanan>`) tetap terbuka. Folder ikut di alamat juga di Tren dan layar admin agar tetap saat kembali. (b) `/api/me` dan jawaban login kini memuat `session_idle_minutes` (perubahan kecil di `api/session.py` + uji) untuk pita "Sesi berakhir dalam 5 menit". (c) Plugin build kecil membuang `https://` dari tautan dokumentasi galat Svelte (`svelte.dev/e/…`, teks pesan galat, tak pernah diambil) agar `web/dist` bebas alamat luar; sisa URL hanya skema XML. (d) **ASUMSI** "folder praktis kosong" (DRD §6.6) = < 1.000 baris log; file rusak saja tidak memicu pita karena folder penuh pun punya 1–3 file berbaris rusak. (e) Pilihan folder di layar sempit hanya menampilkan tanggal (`6 Okt 2026`) agar tidak terpotong. (f) Q6 "–" untuk angka yang lognya tidak ada, Q7 (urut kolom, salin IP, `(i)`, "Lihat sebagai tabel", pintasan `[` `]` `/`) dikerjakan; Q8 logo tetap "S4". (g) `Placeholder.svelte` sekaligus halaman contoh semua komponen dengan data nyata (satu permintaan `overview`). (h) Skrip uji browser disimpan: `tools/uji_browser.cjs` (50 pemeriksaan) dan `tools/uji_sesi.cjs` (7); Playwright bukan dependensi proyek. (i) Di tengah tahap pemilik meminta gaya mengikuti gambar referensi dan modul Command Center realtime via Kafka: dicatat sebagai Tahap 12a, 22, 23 dan pertanyaan R1–R6 (TRD §11.2, §12; DRD §12), **belum dikerjakan**. Verifikasi: `npm ci && npm run build` tanpa peringatan; `node tools/cek_i18n.mjs` "kunci sama: 148"; `node --test tests/test_format.mjs` 8 lulus; URL di `web/dist` hanya skema XML; `./run.sh` membangun lalu melayani; browser: 50/50 (Masuk tanpa data sebelum masuk, ganti sandi wajib, sidebar dua grup + lencana `14 IP`, 11 folder, subjudul berisi rentang log, folder/tab di alamat, kembali/pintasan, tabel 25 + lanjutan + filter server + aria-sort, ID/EN dan tema diingat, Tab: Lewati ke isi → navigasi → header dengan fokus terlihat, user = sidebar sama tanpa menu admin dan `admin/user` → "Tidak punya akses", 390 & 360 px: tanpa gulir mendatar, KPI 2 kolom, tabel jadi kartu, sentuh ≥ 44 px, laci + Esc, menu ⋯) dan 7/7 (pita sesi, sesi habis → Masuk lalu kembali ke alamat sama, server mati → pita "Tidak tersambung" → pulih sendiri 4 dtk); `pytest tests/test_api.py tests/test_auth.py` 100 lulus. (j) Nama aplikasi diganti menjadi **SIMPeL4 Dashboard** atas keputusan pemilik (satu konstanta di `web/src/brand.js`; tanda logo tetap "S4"). |
| 12a | 2026-10-06 | Dijalankan sebelum uji ponsel sungguhan Tahap 12 (yang tetap terbuka) karena gaya ini mengubah tampilan yang akan diuji; pemilik menjalankan `/loop` setelah diberi tahu langkah berikutnya 12a. (a) Token kedua tema diganti ke gaya referensi: latar netral kehijauan, kartu rata bergaris tipis, radius 16, judul dan angka KPI putih polos (gradien judul/KPI lama ditinggalkan, DRD §12). Nama token tetap; token baru `--icon-bg`, `--icon-border`, `--chip-bg`, `--brand-bg`, `--brand-fg`. (b) `lib/Icon.svelte`: 22 ikon garis digambar sendiri dan dibundel (tanpa pustaka/CDN ikon); dipakai sidebar, KPI, tombol. (c) Sidebar: ikon per butir, logo kotak teal terisi, kartu kaki berisi zona waktu dan status ingest terakhir. (d) Kepala halaman menjadi satu kartu lekat: judul + tanggal folder redup, **baris status ringkas** (● N layanan · ● error · ● warning · ● IP serangan), alat di kanan, avatar inisial di menu user; di bawahnya baris kesegaran "Folder log … · berisi log … · diperbarui …" (pengganti "streaming · last event" selama Kafka ditunda). Di ≤ 900 px bar 52 px tetap. (e) **API**: `/api/meta` kini memuat `derived_at` per folder (WIB) untuk baris kesegaran; uji ditambah. (f) KPI: ikon, akhiran redup, lencana ▲/▼ di sebelah angka, baris titik; `format.delta` mendapat `short`/`rest`. Alert menjadi **kartu perhatian bernomor** dengan tautan tindakan (bentuk daftar biasa tetap tersedia). Komponen baru `SplitBar` (batang proporsi besar). Keping konteks (`chip`) di judul ChartCard/DataTable; kepala tabel huruf kapital kecil; tag bergaris; tombol `.btn.accent`. (g) `tools/cek_kontras.mjs` (baru) menghitung 33 pasangan per tema dari `theme.css`; satu gagal (batas kontrol terang 2,78) diperbaiki menjadi `#7b8794` (3,38). Verifikasi: build tanpa peringatan; URL di `web/dist` hanya skema XML; `cek_i18n` 176 kunci sama; `test_format` 8 lulus; `cek_kontras` semua pasangan memenuhi ambang; `uji_browser.cjs` 50/50 (satu pemeriksaan disesuaikan: jumlah layanan kini di baris status, bukan subjudul); `uji_sesi.cjs` 7/7; tangkapan layar 1440 gelap/terang dan 390 px dibandingkan dengan referensi. Sesudahnya, atas permintaan pemilik: (h) panah pemilih (`select`) digambar sendiri dengan posisi tetap 14 px dari tepi (panah bawaan browser mepet dan berbeda per OS); (i) **nama sistem huruf kecil** (DRD U33): `titleCase` diganti `sysName`, class `sys`; `uji_browser.cjs` kini 51 pemeriksaan termasuk nama layanan huruf kecil di sidebar dan judul. |
| 13 | 2026-10-06 | Dijalankan lewat `/loop` pemilik setelah Tahap 12a; uji ponsel sungguhan Tahap 12 masih terbuka. (a) Overview memakai tiga sumber sesuai TRD §5.3: `/overview`, ringkasan folder yang sudah dimuat kerangka (`/api/folders/{f}`), dan `/services/nginx-ingress-controller` untuk bagian "Traffic HTTP"; dua permintaan halaman berjalan bersamaan dan tampil bersama. (b) Kartu 1 (peta + alur) halaman layanan menyusul di Tahap 20, sesuai rencana. (c) Angka persen di judul dan KPI mengikuti bahasa (`37,3 %` / `37.3%`); lama selalu memakai titik. (d) Tabel "Top pesan error lintas layanan" kini berkolom Layanan, Level, Pesan (bisa dibuka ke baris log asli), Jumlah; lama satu kolom teks `[Layanan] LEVEL | pesan`. Isi dan urutan 25 baris pertama sama. (e) Tambahan kecil di komponen bersama: tombol salin baris log asli; label batang horizontal dipotong sesuai lebar kanvas (Chart.js membiarkan teks hilang di tepi kiri); sumbu logaritmik hanya berlabel kelipatan 10, mulai 0,5 agar jumlah 1 tetap terlihat; nama sistem di tabel tidak dipecah di tengah kata; area ketuk `(i)` 44 px di layar sempit. (f) **ASUMSI**: Overview tidak mendapat kartu "Yang perlu perhatian" (susunan DRD §3.1 dipertahankan); kartu itu milik Command Center (Tahap 22). (g) Dibuat `tools/uji_tahap13.cjs`: membuka `../dashboard.html` lama (Chart.js diganti tiruan, tanpa jaringan) dan v2 berdampingan, lalu membandingkan KPI, perubahan ▲/▼, 25 pesan teratas, dan daftar kartu; dan `docs/04b-daftar-periksa.md`. Verifikasi 7 dari 7 lulus: build dan `cek_i18n` (228 kunci sama); Overview 06 Okt sama dengan lama (191.898 · 2.810 · 856 · 124.822 · 3,6 % · 0,04 % · 7 · 18; baris ▼ 36 %, error ▼ 37 %; 25 pesan sama isi dan urutan; 20 kartu); halaman nginx, simpel-loop, appsmanager, coredns, frontend: KPI dan kartu sama dengan lama (coredns "domain gagal resolve"); garis Error nginx Σ 125 (butir 2); donat simpel-loop 29 Sep WARN 9.614 tanpa ERROR (butir 4); 01 Okt pita "hanya berisi 4 baris log; 4 file rusak" dan layanan kosong menjelaskan sebabnya; filter "JWT" 3 baris + "3 baris cocok"; daftar periksa 8 kombinasi (bahasa × tema × lebar) untuk kedua halaman. Skrip: `uji_tahap13.cjs` 39/39, `uji_browser.cjs` 51/51, `uji_sesi.cjs` 7/7; kontras dan uji pemformat tetap lulus. |
| 14 | 2026-10-06 | (a) **API**: `services` di `/api/trends` kini berurutan seperti lama (kemunculan pertama: folder terlama, lalu urutan file); sebelumnya abjad. Uji ditambah. (b) **ASUMSI Q4**: rentang bawaan 30 folder; pilihan diingat per browser. Kolom pertama sebuah rentang tidak punya ▲/▼ karena folder sebelumnya di luar rentang (dengan 11 folder sama dengan lama). (c) Kelengkapan data: sel berangka diberi tanda "Rusak" bila layanan itu punya file rusak, dan "Rusak" menggantikan "Kosong" bila 0 baris karena rusak (B05); 16 sel pada 11 folder. (d) **Bug ditemukan dan diperbaiki di komponen bersama**: Chart.js memasang properti internal pada array data; array dari state reaktif Svelte menolaknya (galat `state_descriptors_fixed`, lalu "Canvas is already in use"). ChartCard kini selalu menyalin array; Tren menyimpan data sebagai `$state.raw`. (e) Pemilih rentang diuji pada **database simulasi 40 folder** (`tools/simulasi_setahun.py --folders 40` di scratchpad, database asli hanya dibaca, lalu dihapus), karena 11 folder nyata lebih sedikit dari rentang terkecil. (f) Di tengah tahap, cabang menerima merge dari `master` (catatan Tahap 11 sesi lain + `ukur.py --api` versi lain); hasil merge `tools/ukur.py` rusak (dua `ukur_api`, argumen ganda) dan disatukan di commit terpisah. Verifikasi 5 dari 5 lulus: build + `cek_i18n` (250 kunci); `tools/uji_tahap14.cjs` 21/21 berdampingan dengan dashboard lama (6 chart: tiap seri dan angka sama untuk 11 folder; tabel error + perubahan: tiap sel sama; kelengkapan: sama kecuali tanda Rusak; simpel-loop 30 Sep "Tidak ada"; 1 Okt "Rusak"/"Kosong"; pemilih folder nonaktif "Tren menampilkan semua folder"; 390 px tabel tetap menggulir; 8 kombinasi) dan 6/6 pada simulasi (14 / 30 / 90→40 / semua = 40 kolom; tabel mulai di ujung kanan; kolom Layanan terkunci; rentang diingat). Regresi: `uji_tahap13` 39/39, `uji_browser` 51/51; `ukur.py --api` dalam proses dan terhadap server: 21 endpoint, 0 di atas target. |
| 15 | 2026-10-06 | (a) "Temuan utama" disusun dari `Findings.svelte` + kamus berkunci (bagian tebal + kalimat, dua bahasa, nilai data sebagai parameter teks). Daftar IP/upstream/organisasi/akun di kalimat diambil dari tabel halaman pertama bila tabel itu lengkap, supaya urutannya persis seperti lama; bila tidak lengkap, dari `findings` API (urut abjad). (b) `DataTable` mendapat sel kustom lewat *snippet* (komponen, bukan HTML dalam string) dan lebar minimum kolom (`minw`); `IpCell` tidak lagi memecah IP. Tanpa `minw`, URL panjang dan nama akun terpecah per huruf di kolom sempit. (c) Catatan kaki dan kategori serangan, tanda akun, serta kalimat kejadian ("… sukses dari …") diterjemahkan sebagai label; waktu kejadian tetap apa adanya seperti lama. (d) Catatan "tanpa nginx" hanya tampil bila log nginx memang tidak ada (lama: juga saat nginx ada tetapi tanpa serangan, dengan kalimat yang keliru). (e) KPI ditata 4 + 4 (U5) di layar lebar, 2 kolom di ponsel. Verifikasi 5 dari 5 lulus: build + `cek_i18n` (322 kunci); `tools/uji_tahap15.cjs` 35/35 berdampingan dengan lama untuk 06 Okt, 29 Sep, 28 Sep (8 KPI sama: 06 Okt 88 · 14 · 5 · 62 · 9 · 1 · 0 · 4; temuan sama kalimat demi kalimat: 06 Okt 6 butir — Log4Shell, Rancher, 62 endpoint 2xx, cloud, jaringan Ombudsman, 4 reset — dan 29 Sep 11 butir; kartu sama; 5 tabel sama tiap baris pada kolom inti; 28 Sep catatan tanpa nginx + bagian login); URL `<script>alert(…)`/`onerror` di 29 Sep tampil sebagai teks, 0 elemen tersisip, 0 dialog; `grep @html` 0; 8 kombinasi bahasa × tema × lebar. Regresi: `uji_tahap13` 39/39, `uji_tahap14` 21/21, `uji_browser` 51/51, kontras lulus. |
| 16 | 2026-10-06 | (a) "Ringkasan akar masalah" memakai komponen generik `Summary.svelte` (potongan teks / tebal / kode, dua bahasa) karena kalimat lama memuat `<code>` di tengah kalimat. (b) Upstream DNS di kalimat DNS diambil dari konfigurasi (`/api/meta` → `dns_upstream`), lama ditulis mati `10.88.1.100` (nilai bawaan sama). Bila tidak ada domain berdampak, potongan ", termasuk ke …" dihilangkan (lama menulis "termasuk ke ."). (c) `ChartCard` mendapat slot kaki (`footer`) untuk keterangan "Refresh token kedaluwarsa: N" (B07) di bawah chart JWT; bila lebih dari satu layanan, rinciannya ikut. (d) Kelas `.kpis.four` (4 kolom di layar lebar) dipindah ke `theme.css`, dipakai Keamanan dan Ketersediaan. (e) Persentase ketersediaan mengikuti bahasa (`98,000 %` / `98.000%`); lama selalu titik. (f) Alat uji: tabel 401 lama dibandingkan dengan 30 baris pertama v2 menurut aturan E2 (urutan jumlah identik; baris bernilai sama di batas 30 boleh beda pilihan). Pencarian tabel di `uji_tahap15/16` kini melewati kartu chart berjudul mirip (semula satu pemeriksaan lulus kosong). Verifikasi 5 dari 5 lulus: build + `cek_i18n` (389 kunci); `tools/uji_tahap16.cjs` 65/65 berdampingan dengan lama — Akar Masalah 29 Sep: ringkasan 5 butir sama, chart JWT sama, **baru** "Refresh token kedaluwarsa: 237", tabel 401 "Menampilkan 30 dari 653"; 06 Okt, 30 Sep (butir error koneksi 200 → 1.200, diharapkan), 27 Sep juga sama; Ketersediaan 30 Sep: KPI error koneksi pod **1.200** (lama 200), retry **825**, **10** insiden, KPI lain, 3 chart, dan tabel sama; 06 Okt sama; 28 Sep catatan tanpa nginx; 8 kombinasi untuk kedua halaman. |
| 17 | 2026-10-06 | (a) **ASUMSI (Pelacakan)**: folder yang punya simpel-loop tetapi tidak satu pun requestId-nya cocok dengan nginx (`matched = 0`, mis. 27 dan 28 Sep) menampilkan catatan "Pelacakan butuh log om-be-simpel-loop dan ingress nginx …" (DRD §6.6, rencana 27 Sep); dashboard lama untuk folder itu menampilkan halaman berisi KPI nol karena `corr` = `[0, N]`. (b) KPI Pelacakan gagal / IP gagal / lambat dan dua chart-nya dihitung dari **semua** jejak (TRD §4.4 butir 1, 9): 29 Sep gagal 3.245 → 3.479, IP 150 → 176, lambat 15 → 24; chart IP dan jenis error berbeda sedikit dari lama karena lama memakai 300 jejak; 06 Okt (111 jejak) sama persis. (c) Bisnis: KPI yang lognya tidak ada tampil "–" + "Log <layanan> tidak ada di folder ini" per sumber (simpel-loop 7 KPI, report 2, appsmanager 2), bukan 0 (U16); perubahan vs folder sebelumnya hanya untuk metrik simpel-loop dengan aturan "sebanding" lama. Label metrik bisnis dari kamus `biz.<slug>`; metrik yang belum ada di kamus tampil apa adanya. (d) Pod: status file "Rusak" menggantikan "Ada Log"/"Tanpa Log" lama (B05; 06 Okt: 3 file rusak berisi 1 baris, di lama "Ada Log"); "Pod dengan retry" mendapat keterangan (i). (e) Tabel jejak: kolom URL memakai `AttackUrl` (host dari konfigurasi + path, UA di bawahnya), URL dipotong 200 dengan teks lengkap di tooltip; kolom waktu boleh dua baris agar tabel muat di 1440 px. (f) Alat uji: tabel aktivitas dibandingkan dengan aturan E2 (seri di batas 20 boleh beda pilihan); server lokal menyimpan `index.html` saat mulai, jadi server dijalankan ulang setelah build. Peringatan a11y `tabindex` di `Trends.svelte` (sejak Tahap 14) belum diubah. Verifikasi 7 dari 7 lulus: build + `cek_i18n` (443 kunci); `tools/uji_tahap17.cjs` **91/91** berdampingan dengan lama — Pod 06 Okt / 29 Sep / 28 Sep: 5 KPI, 2 chart, 3 tabel sama, status "Rusak" 3 file; Bisnis 29 Sep: 12 / 108 / 35 / 12 / 314 / 18 / 55 / PDF 813 / 32 / login 389, perubahan, 5 chart, 2 tabel sama; 30 Sep: 9 KPI "–" + keterangan, login 110 / 66; Pelacakan 29 Sep: 60.665 / 22.638 / 37,3 %, tabel "Menampilkan 300 dari 550" dan setelah dimuat semua 300 baris lama ada di v2; 27 Sep catatan (ASUMSI) dan 30 Sep tanpa simpel-loop catatan seperti lama; 8 kombinasi untuk ketiga halaman. Regresi lulus: `uji_browser` 51/51, `uji_sesi` 7/7 (server dengan `S4_SESSION_IDLE_MINUTES=5`), `uji_tahap13` 39/39, `uji_tahap14` 21/21, `uji_tahap15` 35/35, `uji_tahap16` 65/65; `test_format` 8/8; `cek_kontras` semua pasangan; URL di `web/dist` hanya skema XML. |
| 18 | 2026-10-06 | (a) **API ditambah** di luar daftar berkas: `GET /api/admin/ingest/status` kini memuat `last_run` (ingest terakhir yang selesai, dibaca dari tabel `ingest_run`: waktu UTC, status, file dilihat/berubah, peringatan), karena status di memori kosong setelah server dimulai ulang; uji di `test_api.py` ditambah. (b) **ASUMSI "permintaan berikutnya"**: App membaca ulang `/api/me` setiap pindah tab dan muat ulang; halaman yang dibiarkan terbuka tanpa navigasi tetap memakai menu lama sampai itu (API tetap menolak 403 seketika). (c) **ASUMSI**: menonaktifkan akun sendiri tidak ditawarkan (server mengizinkan bila masih ada admin lain), sama seperti menghapus diri sendiri. (d) Catatan audit memuat 500 entri terbaru; tabel menampilkan 50 + "tampilkan berikutnya" dan memfilter di browser; bila lebih dari 500, keterangan "500 terbaru dari N". (e) Kartu "Impor dari S3" berisi catatan Tahap 19. (f) Komponen baru `lib/Dialog.svelte` (`<dialog>` bawaan + `showModal()`: fokus terkunci, Esc, fokus kembali ke pemicu; layar penuh di ≤ 560 px) dan `lib/RowMenu.svelte` (menu ⋯ `position: fixed` agar tidak terpotong tabel; butir nonaktif dengan sebab). `DataTable`: sel kartu baris ponsel kini `justify-items: start` (tag tidak melebar penuh) — berlaku di semua halaman, regresi dijalankan. (g) `format.utcToWib()` (waktu akun/ingest disimpan UTC) + uji. (h) Pesan galat server berbahasa Indonesia; layar memetakan kode galat ke kamus agar dua bahasa. (i) Kunci `placeholder.admin` dihapus. (j) Kaki sidebar "Ingest terakhir …" masih dari status di memori (`/api/meta`), belum memakai `last_run`. (k) Alat uji: ingest tanpa perubahan selesai < 0,5 dtk sehingga status "berjalan" tidak selalu terbaca di antara dua pembacaan; dibuktikan dengan tombol nonaktif + `run_id` baru, sedangkan "dashboard tetap terbuka selama ingest" dibuktikan lebih kuat oleh `test_ingest_lewat_api_dan_dashboard_tetap_terbuka` (ingest paksa). Verifikasi 9 dari 9 lulus: build + `cek_i18n` (523 kunci); `tools/uji_tahap18.cjs` **33/33** (dua kali berturut-turut) dengan dua jendela — tambah rina → wajib ganti sandi → dashboard tanpa menu admin; naik/turun peran berlaku pada pindah tab berikutnya; user biasa di layar admin "Tidak punya akses" + 403; reset sandi dan nonaktifkan mengakhiri sesi seketika, sandi sementara tampil sekali; admin terakhir tidak ditawarkan, PATCH → 409, daftar basi → pesan di dialog; "Ingest sekarang" → "0 file berubah", data 200 selama berjalan; audit 11 jenis tindakan dengan waktu, pelaku, IP, tanpa sandi/token; 8 kombinasi untuk kedua layar; dialog layar penuh di 390 px. Regresi lulus: `pytest` 239 lulus, 2 dilewati; `uji_browser` 51/51, `uji_sesi` 7/7, `uji_tahap13` 39/39, `uji_tahap14` 21/21, `uji_tahap15` 35/35, `uji_tahap16` 65/65, `uji_tahap17` 91/91 (setelah perubahan `DataTable`); `test_format` 9/9; `cek_kontras` semua pasangan. |
| 19 | 2026-10-06 | **SEBAGIAN.** (a) **Belum diuji: dua baris Manual** (mode coba dan impor `2026-09-26` dengan kredensial asli, termasuk pembuktian ASUMSI T14 dan angka 1.203 / 6 / 11). `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` di lingkungan sesi ini hanya nilai pengisi (14 karakter, bukan bentuk kunci AWS); S3 menjawab `InvalidAccessKeyId`. Titik akhir S3 Jakarta **terjangkau** dari lingkungan ini (lewat proxy), tetapi X2 tetap harus diperiksa di server. Langkah untuk pemilik: isi kunci asli di `.env` + `S4_IMPORT_BUCKETS`, lalu `py -m simpel4 import --dry-run s3://simpel4-backup/k8s-logs/2026-09-26/` dan impor ke `S4_DATA_DIR` terpisah (README §Impor). (b) **Tambahan API**: `GET /api/admin/import` (hanya admin: aktif?, bentuk tautan yang diterima, status kredensial, 20 job terakhir) untuk riwayat di layar; `/api/meta` mendapat `imports` (aktif, kredensial tersedia + sumber). (c) Konfigurasi baru `import_timeout_minutes` (30). (d) Rencana objek per job (ambil/lewati + alasan) disimpan di **memori** (20 job terakhir), basis data `import_job` menyimpan ringkasan; status job `berjalan` / `coba` / `selesai` / `gagal`. (e) "Sama dengan unduhan sebelumnya" dicatat di manifest `.s3-import.json` di folder kotak masuk (ukuran + ETag + berkas masih ada). (f) Kunci objek tidak aman (`..`, `//`, karakter kendali) **membatalkan seluruh impor** (TRD §9.6), objek di luar pola hanya dilewati. (g) Ingest setelah impor memakai `IngestManager.run_blocking` (menunggu ingest lain, berbagi kunci). (h) Kredensial tempel: ID kunci harus huruf besar/angka 16–128, rahasia 16–128; diaudit tanpa nilai. (i) Pesan galat: bahasa Indonesia = pesan server (memuat rincian), EN = kamus per kode; pesan ringkas job di riwayat tetap teks server berbahasa Indonesia. (j) `tools/server_uji_impor.py` menjalankan dashboard + S3 tiruan untuk uji browser; titik akhir S3 dialihkan lewat `importer.ENDPOINT` yang sengaja **tidak** tersedia di konfigurasi. (k) `README.md` dibuat (belum ada) dengan contoh kebijakan IAM baca-saja `simpel4-backup/k8s-logs/`. Verifikasi yang bisa dijalankan, semuanya lulus: `pip install -e ".[test,s3]"` + `pytest tests/test_import.py` **28 lulus** tanpa menghubungi AWS (uji terbukti gagal bila aturan `.gz` berpasangan atau daftar izin awalan dirusak); tanpa `import_buckets` → "Impor tidak diaktifkan"; `bucket-lain`, `bukan-tanggal`, dan bucket Jakarta lain → ditolak sebelum menghubungi AWS; tanpa kredensial → pesan cara memberi, tidak ada berkas tertulis; tidak ada kunci AWS di `data/` (pola kunci 0; "ASIA" hanya nama ISP) dan `status` menyebut "kredensial impor: tersedia (lingkungan)"; user biasa → 403 (uji); token mesin → **202** di server sungguhan (job lalu gagal di S3 karena kunci pengisi), token mesin ke endpoint kredensial → 401; kredensial tempel hilang setelah server dimulai ulang dan tidak ada di log server maupun basis data akun; `tools/uji_tahap19.cjs` **22/22** (coba dulu 0 byte, impor + konfirmasi + ingest → folder muncul, impor ulang 0 objek, tempel/hapus kredensial, galat EN, audit tanpa rahasia, 8 kombinasi). Regresi: `pytest` 267 lulus, 2 dilewati; `uji_tahap18` 33/33; `cek_i18n` 582 kunci; `test_format` 9/9; `cek_kontras` semua pasangan. |
| 20 | 2026-10-06 | (a) **Selisih yang diharapkan**: KPI rencana "222 lokasi, 12 negara, 2.030 request dari luar Indonesia" adalah angka DB-IP dashboard lama; v2 memakai MaxMind GeoLite2 (rencana Tahap 7 butir i) sehingga 06 Okt = **166 lokasi, 9 negara, 1.293** dari luar Indonesia. IP asal (516), modul (9), pod (15), total request (124.822), dan 0 dari IP internal **sama** dengan lama. (b) **Keputusan pemilik di tengah tahap**: lingkaran kelompok **tanpa angka** (DRD §7.5/ASUMSI D5 berubah; ukuran tetap menurut request, angka di tooltip); label lokasi terbesar bergaya contoh pemilik: nama tebal + baris kecil "N IP · N req". (c) **ASUMSI**: label 6 lokasi terbesar ikut aturan tabrakan (DRD §7.3 "tanpa bertumpuk"); di tampilan Indonesia tampil 5, label ke-6 (Serang, ±15 px dari Jakarta + label server) muncul saat diperbesar — dashboard lama menggambarnya bertumpuk. (d) **Pertanyaan pemilik: OpenStreetMap?** Ubin OSM daring tidak dipakai (mengirim IP pembuka dashboard ke pihak ketiga, melanggar aturan proyek; kebijakan ubin OSM); data OSM bisa menyusul sebagai ubin vektor yang dilayani sendiri (mis. PMTiles) bila pemilik memutuskan — mesin peta tetap MapLibre. Sampai itu ASUMSI D4 (Natural Earth) tetap. (e) **Kelancaran zoom**: di lingkungan uji tanpa GPU (WebGL perangkat lunak) animasi zoom ±10–12 frame/detik; hampir seluruh beban dari pengisian poligon daratan (tanpa daratan 30 fps, latar saja 60 fps). Uji penyederhanaan geometri (`tolerance` 1 dan 2) tidak memberi perbaikan yang konsisten, jadi tidak diterapkan; **perlu dicoba pemilik di perangkat ber-GPU**. (f) Glyph Noto Sans Regular/Bold rentang 0–255, 256–511, 7680–7935 (nama kota Vietnam), 8192–8447 dari openmaptiles/fonts v2.0 + `OFL.txt` (780 KB). (g) MapLibre 5.24 (BSD-3) dimuat sebagai chunk terpisah (±1 MB) hanya saat peta dibuka; plugin build membuang tautan maplibre.org/GitHub yang tak terpakai, sehingga di hasil build hanya tersisa skema XML + tautan atribusi MaxMind dan GeoNames. (h) Tooltip lewat kursor/ketukan; titik **tidak** bisa difokus satu per satu dengan keyboard (ASUMSI: tabel alur adalah padanannya, §7.9, dengan tautan "Lewati peta"); keyboard di peta: panah, +/−, 0, Esc. (i) Tombol layar penuh ⛶ di ≤ 900 px terpisah dari ⤢ (kembali ke preset). (j) Teks gerakan kooperatif dua bahasa diganti lewat kamus UI MapLibre (`map._locale`) lalu diaktifkan ulang. (k) Halaman layanan: respons `services/{svc}` mendapat `has_flows` (API ditambah + uji) agar layanan tanpa alur tidak meminta `/map` (yang menjawab 404). (l) `DataTable` mendapat `search` (filter dari luar). (m) Kait uji `box.__map`. (n) Halaman `Placeholder` dan 14 kunci `placeholder.*` dihapus (semua tab sudah punya halaman). (o) Catatan tabel alur menyebut MaxMind; "maksimal 3.000 alur" dihapus (v2 tidak memotong; 100 pertama + lanjutan, X6). (p) Yang belum diuji otomatis: cubit memperbesar (yang diuji: geser dua jari, satu jari tidak menggeser peta). Verifikasi: build + `cek_i18n` (608 kunci); `tools/uji_tahap20.cjs` **26/26** — KPI dan tabel alur vs lama, ganti modul (kamera tetap), roda mouse + petunjuk Ctrl, keyboard, klik titik → "Lihat di tabel", dunia → Jawa (kelompok pecah, label bertahap), tema/bahasa (posisi tetap, atribusi), **internet diputus → peta tetap tampil**, **0 permintaan ke domain lain**, 28 Sep catatan, layanan om-be-simpel-loop terlipat → alur modul itu, 390 px sentuh (CDP), 8 kombinasi. Regresi lulus setelah perubahan `DataTable` dan halaman layanan: `pytest` 267 lulus, 2 dilewati (termasuk kesetaraan E1–E4); `uji_browser` 51/51, `uji_sesi` 7/7, `uji_tahap13` 39/39 (semula 38/39: 404 di konsol halaman layanan non-modul, diperbaiki dengan `has_flows`), `uji_tahap14` 21/21, `uji_tahap15` 35/35, `uji_tahap16` 65/65, `uji_tahap17` 91/91, `uji_tahap18` 33/33; `test_format` 9/9; `cek_kontras` semua pasangan. |
| 11 | 2026-10-06 | (a) **Berkas**: sepuluh endpoint halaman ditulis di satu modul `api/pages.py` dan 25 definisi tabel + endpoint tabel di `api/tables.py` (rencana: satu modul per halaman + definisi di `common.py`); isinya sama, kodenya jauh lebih sedikit. (b) **Selisih tampilan yang belum tertulis di TRD §4.4**, kini ditambahkan ke butir 1: tabel/chart *kinerja endpoint* mengambil 25 P95 tertinggi dari SEMUA endpoint ber-≥5 request (TRD §5.4), sedangkan dashboard lama memilih dari 150 endpoint tersibuk; isinya berbeda untuk nginx pada 5 dari 11 folder. Setiap baris lama tetap ada di daftar lengkap v2 (E2). **Perlu diketahui pemilik.** (c) Chart "Respons 5xx per jam" (Ketersediaan) dibaca dari tabel mentah `nginx_access` folder itu, karena `agg_hour.err` kini memuat juga baris error log (butir 2); 9 ms pada folder terbesar. (d) `ETag` dikirim, jawaban 304 belum dibuat. (e) Filter `q` ikut mencari nama pemilik jaringan IP. (f) Tabel berbatas "semua" memakai batas 500. (g) Keamanan/Akar Masalah/Bisnis selalu `available: true` dengan penanda sumber (`nginx`, `sources`), karena halaman itu tetap berisi walau satu sumber tidak ada. (h) `tools/ukur.py --api` bawaannya menjalankan aplikasi di dalam proses; terhadap server berjalan butuh cookie sesi di `S4_COOKIE`. (i) ASUMSI X6 tetap: tabel alur 100 baris pertama. Hasil: `pytest` **239 lulus, 2 dilewati**; matriks peran mencakup 28 rute; **E2: 601 daftar, 9.889 baris lama, 0 berbeda** (E1 3.022 / E3 1.734 / E4 169 tetap 0); server nyata + curl: security 10-06 = 88 request / 14 IP, error koneksi pod 09-30 = 1.200, peta 09-28 `no_nginx`, `c401` 09-29 total 653 (208 cocok `count`, 5 baris), `sort=1;drop` → 400, tanpa sesi → 401; lapisan HTTP pada folder terbesar (09-29): endpoint terlama 56 ms (target 300), respons terbesar 174 KB (target 500). |
