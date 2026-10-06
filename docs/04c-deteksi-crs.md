# 04c — Deteksi serangan: OWASP CRS + CAPEC (Tahap 21)

Laporan perbandingan aturan deteksi lama (pola sistem lama, `attack_cat`) dengan aturan OWASP Core Rule Set
(CRS) yang dipakai v2 sejak Tahap 21. Rincian teknis: TRD §4.6; rencana: `04-rencana.md` Tahap 21.
Angka di bawah dihitung dari database nyata (11 folder, 308.158 baris log ingress nginx) dengan tingkat
paranoia 1 dan ambang skor anomali 5.

## Ringkasan

- **Sumber aturan**: OWASP CRS **v4.30.0**, commit `e03a4f6dabc7a30ebd8c52c97d28a154f590a48f`, lisensi Apache 2.0
  (`simpel4/CRS-LICENSE.txt`). Diolah sekali oleh `tools/ambil_crs.py` menjadi `simpel4/crs_rules.json`, yang
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
  `simpel4/capec.json`.
- **Aturan lama tetap ada**: kolom `attack_cat` dan agregat `agg_attack_*` tidak diubah, sehingga uji
  kesetaraan E1–E4 tetap berjalan dengan `S4_ATTACK_RULES=lama`. Tampilan bawaan memakai CRS
  (`S4_ATTACK_RULES=crs`, keputusan S1b).

<!-- TABEL -->

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
