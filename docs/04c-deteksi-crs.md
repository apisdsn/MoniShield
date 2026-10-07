# 04c — Deteksi serangan: OWASP CRS + CAPEC (Tahap 21)

Laporan perbandingan aturan deteksi lama (pola sistem lama, `attack_cat`) dengan aturan OWASP Core Rule Set
(CRS) yang dipakai v2 sejak Tahap 21. Rincian teknis: TRD §4.6; rencana: `04-rencana.md` Tahap 21.
Angka di bawah dihitung dari database nyata (11 folder, 308.158 baris log ingress nginx) dengan tingkat
paranoia 1 dan ambang skor anomali 5.

## Ringkasan

- **Sumber aturan**: OWASP CRS **v4.30.0**, commit `e03a4f6dabc7a30ebd8c52c97d28a154f590a48f`, lisensi Apache 2.0
  (`monishield/CRS-LICENSE.txt`). Diolah sekali oleh `tools/ambil_crs.py` menjadi `monishield/crs_rules.json`, yang
  ikut repo: dashboard tidak mengunduh apa pun saat berjalan. `py tools/ambil_crs.py --check` membuktikan berkas
  di repo sama dengan hasil olah ulang rilis yang dikunci.
- **Aturan**: dari 203 aturan di berkas REQUEST-913, 930–934, 941, 942, 944 yang relevan, **176 diambil**
  (tingkat paranoia 1: 91, 2: 61, 3: 22, 4: 2) dan **27 dilewati** beserta alasannya (daftar di bawah).
- **Yang diperiksa**: hanya bagian request yang tercatat di log nginx: URI, argumen query (nama dan nilai),
  nama berkas, baris request, dan User-Agent. Body POST, cookie, dan header lain tidak tercatat. **Ini bukan
  pengganti WAF**; kalimat yang sama ada di catatan kaki halaman Keamanan.
- **Cara mencocokkan** (seperti ModSecurity): nilai dicocokkan sebagai byte, transformasi `t:` diterapkan
  berurutan, skor anomali = jumlah skor aturan yang kena (CRITICAL 5, ERROR 4, WARNING 3, NOTICE 2); request
  dianggap serangan bila skornya ≥ 5 (ambang bawaan CRS).
- **Kategori** = CAPEC dari tag aturan, ditambah keluarga serangan CRS bila CAPEC-nya umum (mis. CAPEC-242
  Injeksi kode · XSS). CAPEC dipilih dari aturan yang jumlah skornya terbesar. Nama CAPEC dua bahasa ada di
  `monishield/capec.json`.
- **Aturan lama tetap ada**: kolom `attack_cat` dan agregat `agg_attack_*` tidak diubah, sehingga uji
  kesetaraan E1–E4 tetap berjalan dengan `S4_ATTACK_RULES=lama`. Tampilan bawaan memakai CRS
  (`S4_ATTACK_RULES=crs`, keputusan S1b).

## Lama vs CRS per folder

Hanya 5 dari 11 folder yang punya log ingress nginx; folder lain tidak punya data untuk deteksi per URL.
"Kena keduanya" = request yang ditandai aturan lama **dan** CRS.

| Folder | Request lama | IP lama | Request CRS | IP CRS | Kena keduanya | Hanya lama | Hanya CRS |
|---|--:|--:|--:|--:|--:|--:|--:|
| 2026-09-29 | 155 | 12 | 27 | 5 | 25 | 130 | 2 |
| 2026-09-30 | 32 | 9 | 28 | 7 | 27 | 5 | 1 |
| 2026-10-03 | 10 | 4 | 2 | 1 | 2 | 8 | 0 |
| 2026-10-05 | 30 | 3 | 3 | 1 | 3 | 27 | 0 |
| 2026-10-06 | 88 | 14 | 50 | 4 | 29 | 59 | 21 |
| **Total** | **315** | | **110** | | **86** | **229** | **24** |

**Mengapa CRS lebih sedikit.** Sebagian besar "hanya lama" adalah User-Agent alat umum (`Go-http-client` 49,
`curl` 33, `python-requests` 1) dan probe CMS/WordPress berupa path biasa (`/wp-login.php`, `/phpmyadmin/`, `/pma/`) yang
CRS tidak anggap serangan tanpa muatan berbahaya. **Mengapa ada "hanya CRS".** 24 request adalah probe berkas
sensitif yang namanya **di-encode persen** untuk mengelabui pola (mis. `/%61%77%73-%63%6f%6e%66%69%67.%6a%73%6f%6e`
= `/aws-config.json`, `/%70%68%70%69%6e%66%6f` = `/phpinfo`); CRS menerapkan `urlDecode` sebelum mencocokkan,
pola lama tidak.

## Per kategori CRS (semua folder)

| Kategori | Nama (ID) | Request | IP | Folder |
|---|---|--:|--:|--:|
| CAPEC-126 / lfi | Path traversal | 59 | 9 | 5 |
| CAPEC-88 / rce | Injeksi perintah sistem operasi · RCE | 25 | 8 | 3 |
| CAPEC-310 / reputation-scanner | Pemindaian perangkat lunak rentan | 13 | 1 | 1 |
| CAPEC-6 / rce | Injeksi argumen · RCE (Log4Shell ter-obfuskasi di User-Agent, aturan 944150) | 11 | 5 | 3 |
| CAPEC-242 / xss | Injeksi kode · XSS | 1 | 1 | 1 |
| CAPEC-66 / sqli | Injeksi SQL | 1 | 1 | 1 |

## Kategori lama → juga kena CRS?

| Aturan lama | Request | Juga kena CRS | Kategori CRS yang dipakai |
|---|--:|--:|---|
| UA tool/scanner otomatis | 85 | 0 | – (UA alat umum, lihat Keterbatasan 3) |
| Scan CMS / WordPress | 82 | 1 | CAPEC-126/lfi |
| Probe file sensitif | 64 | 36 | CAPEC-126/lfi, CAPEC-310 |
| Probe PHP / CGI | 47 | 13 | CAPEC-310, CAPEC-126/lfi |
| Log4Shell / RCE | 33 | **33** | CAPEC-6/rce, CAPEC-88/rce |
| SQL Injection | 2 | **2** | CAPEC-66/sqli, CAPEC-88/rce |
| Path Traversal / LFI | 1 | 0 | – (URL `/etc/passwd` langsung; aturan 930120 PL1 hanya memeriksa argumen) |
| XSS | 1 | **1** | CAPEC-242/xss |

Semua serangan berkeparahan tinggi menurut aturan lama (Log4Shell, SQLi, XSS) juga ditangkap CRS.

## Aturan CRS yang paling sering kena

930130 (akses berkas terlarang) 60 · 944150 (Log4j) 25 · 932130 (ekspresi shell Unix) 16 · 933135 (variabel
PHP) 14 · 913100 (UA pemindai) 13 · 932160 dan 932235 (perintah shell) 9 · selebihnya ≤ 2 (25 aturan berbeda).

## Salah-tuduh pada lalu lintas normal

Dari **30.512** pasangan (metode, path) unik yang **bersih** menurut aturan lama, CRS tingkat paranoia 1
menandai **13 (0,043 %)**; syarat rencana < 0,5 % terpenuhi. Penyebab: 930130 ×11 (path aplikasi yang memuat
nama mirip berkas sistem) dan 932130 ×2. Diukur ulang tiap `pytest tests/test_detect.py` (uji
`test_salah_tuduh_lalu_lintas_normal`, berjalan bila database nyata tersedia).

## Kinerja

`derive --all` (11 folder, termasuk klasifikasi CRS) 39 detik; `ingest --folder 2026-09-29 --force` 24 detik
(syarat ≤ 60). Klasifikasi per pasangan unik (metode, path, UA) dengan cache; pola `@pm` disusun sebagai regex
berbentuk trie (≈ 1 ms per path).


## Aturan yang dilewati (27)

| Alasan | Jumlah | ID aturan |
|---|--:|---|
| Rantai aturan (`chain`): aturan kedua memeriksa hal yang tidak ada di log, atau hasilnya bergantung pada variabel transaksi | 15 | 931130, 932200, 932205, 932206, 932207, 932240, 933150, 941310, 942130, 942131, 942200, 942440, 942521, 944110, 944120 |
| Sasaran tidak ada di log nginx (berkas unggahan, header `X-Filename`, cookie) | 7 | 932180, 933110, 933111, 933220, 942420, 942421, 944140 |
| Operator libinjection (`@detectSQLi`, `@detectXSS`): pustaka C, tidak ada padanan setara di Python | 4 | 941100, 941101, 942100, 942101 |
| Operator negasi `!@validateByteRange` (aturan pemeriksa karakter, tanpa tingkat paranoia) | 1 | 941010 |

Tidak ada pola yang ditolak mesin regex Python: semua escape `\x{HH}` satu byte diubah ke `\xHH` yang
maknanya sama untuk pencocokan byte. Alat akan mencatat (bukan mengubah diam-diam) bila rilis berikutnya
memuat pola yang tidak bisa dipakai.

## Keterbatasan

1. **Tautologi SQL klasik** (`' OR 1=1--`) tidak tertangkap di tingkat paranoia 1, karena di CRS asli yang
   menangkapnya adalah libinjection (942100). Di tingkat paranoia 2 tertangkap oleh aturan regex (diuji di
   `tests/test_detect.py::test_keterbatasan_tautologi_sql_tanpa_libinjection`). Muatan SQLi lain (UNION
   SELECT, WAITFOR DELAY, komentar) tetap tertangkap di tingkat 1.
2. **Body, cookie, header lain** tidak tercatat di log nginx, jadi serangan yang hanya ada di sana tidak
   terlihat. Cara "di ingress" (ModSecurity/Coraza mode deteksi) dapat melihatnya; diusulkan ke pengelola
   klaster (S1a), di luar tahap ini.
3. **Pemindai yang hanya ditandai User-Agent umum** (`curl`, `python-requests`, `Go-http-client`) tidak
   dianggap serangan oleh CRS (aturan 913100 hanya memuat nama alat pemindai seperti sqlmap, Nikto, Nuclei).
   Aturan lama menandai sebagian UA itu sebagai "UA scanner", sehingga jumlah request dan IP penyerang turun.
4. **Respons 2xx** pada URL serangan biasanya fallback SPA (`index.html`), sama seperti sebelumnya: kolom
   ukuran respons tetap ditampilkan untuk verifikasi.
5. Tingkat paranoia dan ambang bisa diatur (`S4_ATTACK_PARANOIA` 1–4). Mengubahnya membuat ingest
   berikutnya menurunkan ulang agregat CRS semua folder (kolom `folder_state.crs_version`).
