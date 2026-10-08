# Measurement results — size and performance gate (Stage 9)

Measured 2026-10-06 on the developer laptop (Apple Silicon, 8 cores; the same machine as the reference measurement
of the old system: 14-second build). Tools: `tools/simulasi_setahun.py` and `tools/ukur.py`.

## Decision

**Gate PASSED. ASSUMPTION T1 confirmed: one year of data is 4.75 GB, below the 10 GB limit.** The fallback dictionary
tables for `ua`/`path` are **not needed**; the Stage 3 schema is used as-is and Stage 10 may begin.

| Measure | Target (PRD §5) | Measured | Result |
|---|--:|--:|:-:|
| Database size for 365 folders | ≤ 10 GB | **4.75 GB** (13.3 MB per folder) | PASS |
| All queries of one page | ≤ 200 ms | slowest 7.3 ms (map flow table); **20.5 ms for all 21 queries** | PASS |
| Trends tab over 365 folders | ≤ 500 ms | **5.4 ms** for 5 queries | PASS |
| Ingest of the largest folder | ≤ 60 s | 6.9 s (parse + load + derive) + **1.7 s** derive on top of one year of data | PASS |
| Ingest with no changes | ≤ 5 s | 0.4 s | PASS |

## How the simulation works

The raw rows of the largest folder (`2026-09-29`: 359 thousand log lines, 132 thousand nginx requests) were copied to 365
consecutive dates by query, then the aggregates were derived as usual. Result: 48.3 million `nginx_access` rows,
31.4 million `fe_access`, 22.1 million `sl_event`. Request ids were given a per-folder prefix so that correlation stays
inside the folder, as with real data (0 cross-folder matches). Building the simulation: 19 minutes (9 minutes copying,
10 minutes deriving aggregates). The simulation database was deleted after measuring.

## Details

### Size per table (10 largest, estimated from blocks)
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

### Query time per page (latest folder; min / median of 5, ms); target ≤ 200 ms
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
    TOTAL of all page queries                          20.5

### Trends (all 365 folders); target ≤ 500 ms
    Tren: baris/error/warning per hari         1.0 /     1.1
    Tren: HTTP per hari                        0.9 /     0.9
    Tren: keamanan per hari                    1.9 /     2.0
    Tren: bisnis per hari                      1.0 /     1.1
    Daftar folder                              0.3 /     0.3
    JUMLAH query tab Tren                                5.4

Pages above target: none

### Password hashing cost (scrypt)
    n=2^14 r=8 p=1: 36 ms
    n=2^15 r=8 p=1: 76 ms
    n=2^16 r=8 p=1: 147 ms

### Ingest time
    tanpa perubahan (database nyata)                 0.4 dtk
    folder terbesar dipaksa ulang (database nyata)   6.9 dtk
    turunkan agregat satu folder di atas 365 folder    1.7 dtk  (termasuk korelasi terhadap 48 juta baris nginx)
    baca satu folder dari tabel mentah 48 juta baris   1 ms (132203 baris)

## Notes and measurement limits

- **Almost all of the size is raw tables** (nginx 3.5 GB of 4.75 GB); all aggregates together are only 49 MB.
  Because the API reads only aggregates, page speed does not depend on the amount of raw data. If space
  ever becomes a problem, old raw data can be dropped without changing what is displayed (PRD T09).
- **The simulation duplicates one and the same folder.** Real data is more varied (more unique paths, User-Agents
  and IPs), so the actual size could be larger than 4.75 GB. There is still a twofold margin
  before the 10 GB limit. Conversely, real folders are often smaller than this largest folder.
- Query times were measured directly against DuckDB with a warm cache, without the HTTP layer and JSON serialization;
  end-to-end figures are measured again in Stage 11.
- `derive --all` over one year of data takes ±10 minutes (1.7 s per folder). This is a rare operation (only when an
  aggregate definition changes); the daily ingest derives only one folder.
- Reading one folder from the 48-million-row raw table takes only 1 ms: per-folder filtering is served by DuckDB block
  statistics because rows are loaded in folder order (TRD §2).
- **Password hashing (Stage 10)**: scrypt `n=2^15, r=8, p=1` = 76 ms on this laptop; chosen as the initial value
  (TRD target ±100 ms per verification). It must be re-measured on the server; the parameters are stored per account
  so they can be raised without resetting passwords.
- The test machine is a laptop, not the target server (server specification still unknown, PRD R13). The margin
  against the targets is very large (tens of times), so the conclusion is not sensitive to machine differences.

## HTTP layer (Stage 11)

`python3 tools/ukur.py --api` on the largest folder (2026-09-29), the real application in-process, median of 5.
PRD target §5.1–§5.2: each page endpoint ≤ 300 ms and ≤ 500 KB.

| Endpoint | Time (ms) | Size (KB) |
|---|--:|--:|
| `/api/meta` | 3.5 | 2.5 |
| `/api/folders/{folder}` | 7.1 | 5.4 |
| `overview` | 4.3 | 12.2 |
| `map` | 32.3 | 68.5 |
| `security` | 37.5 | 65.3 |
| `rootcause` | 12.1 | 10.3 |
| `availability` | 9.4 | 11.9 |
| `pods` | 7.9 | 2.7 |
| `business` | 6.7 | 4.9 |
| `tracing` | 31.7 | 173.6 |
| `services/{service}` (7 services) | 13.3 – 18.0 | 2.5 – 17.6 |
| `/api/trends?last=all` | 4.1 | 2.6 |
| `tables/flows?limit=500` | 55.6 | 159.3 |
| `tables/trace?q=…` | 28.5 | 172.6 |

All below target. Measurement limits: 11 real folders, not one year (their aggregate queries were already measured on 365
folders above: 20.5 ms); no network and no HTTPS proxy.

