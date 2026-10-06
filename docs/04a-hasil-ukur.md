# Hasil ukur — gerbang ukuran dan kinerja (Tahap 9)

Diukur 2026-10-06 di laptop pengembang (Apple Silicon, 8 inti; mesin yang sama dengan pengukuran acuan
sistem lama: build 14 detik). Alat: `tools/simulasi_setahun.py` dan `tools/ukur.py`.

## Keputusan

**Gerbang LULUS. ASUMSI T1 terbukti: data setahun 4,75 GB, di bawah batas 10 GB.** Cadangan tabel kamus
untuk `ua`/`path` **tidak diperlukan**; skema Tahap 3 dipakai apa adanya dan Tahap 10 boleh dimulai.

| Ukuran | Target (PRD §5) | Terukur | Hasil |
|---|--:|--:|:-:|
| Ukuran database 365 folder | ≤ 10 GB | **4,75 GB** (13,3 MB per folder) | LULUS |
| Semua query satu halaman | ≤ 200 ms | paling lambat 7,3 ms (tabel alur peta); **20,5 ms untuk seluruh 21 query** | LULUS |
| Tab Tren pada 365 folder | ≤ 500 ms | **5,4 ms** untuk 5 query | LULUS |
| Ingest satu folder terbesar | ≤ 60 detik | 6,9 dtk (parse + muat + turunkan) + **1,7 dtk** turunkan di atas data setahun | LULUS |
| Ingest tanpa perubahan | ≤ 5 detik | 0,4 dtk | LULUS |

## Cara simulasi

Baris mentah folder terbesar (`2026-09-29`: 359 ribu baris log, 132 ribu request nginx) disalin ke 365
tanggal berurutan lewat query, lalu agregat diturunkan seperti biasa. Hasil: 48,3 juta baris `nginx_access`,
31,4 juta `fe_access`, 22,1 juta `sl_event`. Request id diberi awalan per folder supaya korelasi tetap di
dalam folder, seperti data nyata (0 kecocokan lintas folder). Membuat simulasi: 19 menit (9 menit salin,
10 menit menurunkan agregat). Database simulasi dihapus setelah diukur.

## Rincian

### Ukuran per tabel (10 terbesar, perkiraan dari blok)
    nginx_access             48,254,095 baris    3481.0 MB
    sl_event                 22,142,725 baris     639.2 MB
    fe_access                31,413,360 baris     247.8 MB
    spring_line               2,638,585 baris      48.5 MB
    log_message               5,205,995 baris      34.2 MB
    agg_endpoint                467,200 baris      12.2 MB
    agg_flow                  1,995,090 baris       8.5 MB
    agg_ip                      666,125 baris       5.5 MB
    agg_trace                   200,750 baris       4.2 MB
    agg_c401                    238,345 baris       3.5 MB
    (agregat saja)            4,165,745 baris      49.2 MB

### Waktu query per halaman (folder terakhir; min / median dari 5, ms); target ≤ 200 ms
    Overview: layanan                          0.3 /     0.3
    Overview: error per jam                    0.2 /     0.2
    Overview: pesan lintas layanan             0.6 /     0.6
    Overview: file                             0.2 /     0.2
    Layanan: endpoint                          0.6 /     0.6
    Layanan: kinerja endpoint                  0.6 /     0.7
    Layanan: IP klien                          0.5 /     0.5
    Layanan: pesan                             0.5 /     0.5
    Keamanan: KPI                              0.7 /     0.8
    Keamanan: URL serangan                     0.8 /     0.8
    Keamanan: IP penyerang + pemilik           0.7 /     0.7
    Keamanan: analisis akun                    0.5 /     0.5
    Akar masalah: 401                          0.7 /     0.8
    Akar masalah: JWT                          0.2 /     0.2
    Ketersediaan: insiden                      0.3 /     0.4
    Ketersediaan: error koneksi pod            0.3 /     0.3
    Pod: sebaran traffic                       0.7 /     0.7
    Bisnis: ringkasan                          0.8 /     0.9
    Pelacakan: jejak                           0.9 /     0.9
    Peta: titik                                2.4 /     2.5
    Peta: tabel alur                           6.9 /     7.3
    JUMLAH semua query halaman                          20.5

### Tren (semua 365 folder); target ≤ 500 ms
    Tren: baris/error/warning per hari         1.0 /     1.1
    Tren: HTTP per hari                        0.9 /     0.9
    Tren: keamanan per hari                    1.9 /     2.0
    Tren: bisnis per hari                      1.0 /     1.1
    Daftar folder                              0.3 /     0.3
    JUMLAH query tab Tren                                5.4

Halaman di atas target: tidak ada

### Biaya hash sandi (scrypt)
    n=2^14 r=8 p=1: 36 ms
    n=2^15 r=8 p=1: 76 ms
    n=2^16 r=8 p=1: 147 ms

### Waktu ingest
    tanpa perubahan (database nyata)                 0.4 dtk
    folder terbesar dipaksa ulang (database nyata)   6.9 dtk
    turunkan agregat satu folder di atas 365 folder    1.7 dtk  (termasuk korelasi terhadap 48 juta baris nginx)
    baca satu folder dari tabel mentah 48 juta baris   1 ms (132203 baris)

## Catatan dan batas pengukuran

- **Hampir seluruh ukuran adalah tabel mentah** (nginx 3,5 GB dari 4,75 GB); semua agregat hanya 49 MB.
  Karena API hanya membaca agregat, kecepatan halaman tidak bergantung pada banyaknya data mentah. Bila
  kelak ruang menjadi masalah, data mentah lama bisa dibuang tanpa mengubah tampilan (PRD T09).
- **Simulasi menggandakan satu folder yang sama.** Data nyata lebih beragam (lebih banyak path, User-Agent,
  dan IP unik), jadi ukuran sebenarnya bisa lebih besar dari 4,75 GB. Masih ada kelonggaran dua kali lipat
  sebelum batas 10 GB. Sebaliknya, folder nyata sering lebih kecil dari folder terbesar ini.
- Waktu query diukur langsung ke DuckDB dengan cache hangat, tanpa lapisan HTTP dan serialisasi JSON; angka
  ujung-ke-ujung diukur lagi di Tahap 11.
- `derive --all` pada data setahun butuh ±10 menit (1,7 dtk per folder). Ini operasi langka (hanya saat
  definisi agregat berubah); ingest harian hanya menurunkan satu folder.
- Membaca satu folder dari tabel mentah 48 juta baris hanya 1 ms: penyaringan per folder dilayani statistik
  blok DuckDB karena baris dimuat urut folder (TRD §2).
- **Hash sandi (Tahap 10)**: scrypt `n=2^15, r=8, p=1` = 76 ms di laptop ini; dipilih sebagai nilai awal
  (sasaran TRD ±100 ms per verifikasi). Di server perlu diukur ulang; parameternya disimpan per akun
  sehingga bisa dinaikkan tanpa mereset sandi.
- Mesin uji adalah laptop, bukan server tujuan (spesifikasi server belum diketahui, PRD R13). Kelonggaran
  terhadap target sangat besar (puluhan kali), jadi kesimpulan tidak peka terhadap perbedaan mesin.

## Lapisan HTTP (Tahap 11)

`python3 tools/ukur.py --api` pada folder terbesar (2026-09-29), aplikasi sungguhan di dalam proses, median dari 5.
Target PRD §5.1–§5.2: tiap endpoint halaman ≤ 300 ms dan ≤ 500 KB.

| Endpoint | Waktu (ms) | Ukuran (KB) |
|---|--:|--:|
| `/api/meta` | 3,5 | 2,5 |
| `/api/folders/{folder}` | 7,1 | 5,4 |
| `overview` | 4,3 | 12,2 |
| `map` | 32,3 | 68,5 |
| `security` | 37,5 | 65,3 |
| `rootcause` | 12,1 | 10,3 |
| `availability` | 9,4 | 11,9 |
| `pods` | 7,9 | 2,7 |
| `business` | 6,7 | 4,9 |
| `tracing` | 31,7 | 173,6 |
| `services/{layanan}` (7 layanan) | 13,3 – 18,0 | 2,5 – 17,6 |
| `/api/trends?last=all` | 4,1 | 2,6 |
| `tables/flows?limit=500` | 55,6 | 159,3 |
| `tables/trace?q=…` | 28,5 | 172,6 |

Semua di bawah target. Batas pengukuran: 11 folder nyata, bukan setahun (query agregatnya sudah diukur pada 365
folder di atas: 20,5 ms); tanpa jaringan dan tanpa proxy HTTPS.

