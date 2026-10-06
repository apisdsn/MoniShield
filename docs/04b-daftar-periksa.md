# Daftar periksa halaman (Tahap 13–20)

Dibuat dari inventaris §2 dan DRD §3, §6, §8. Setiap halaman diperiksa pada **8 kombinasi**: {ID, EN} × {gelap,
terang} × {lebar 1440 px, sempit 390 px}. Yang bisa diotomatiskan diperiksa skrip Playwright (kolom "Cara");
yang hanya bisa dinilai mata ditandai **lihat**, dengan tangkapan layar sebagai bukti.

Butir umum untuk **setiap** halaman dan setiap kombinasi:

| # | Butir | Cara |
|--:|---|---|
| U1 | Tidak ada gulir mendatar halaman; KPI 2 kolom di 390 px; tabel > 4 kolom jadi kartu baris | skrip |
| U2 | Atribut `lang` dan tema sesuai pilihan; tidak ada judul kartu yang tertinggal bahasa lain | skrip |
| U3 | Tidak ada galat halaman/konsol | skrip |
| U4 | Nama sistem (layanan, pod, upstream) huruf kecil apa adanya (DRD U33) | skrip + lihat |
| U5 | Angka berformat bahasa (`1.234` / `1,234`), waktu WIB, durasi `dtk` / `s` | lihat |
| U6 | Memuat: kerangka abu setelah 200 ms; ganti folder: isi lama redup sampai yang baru tiba | lihat |
| U7 | Label chart tidak terpotong di tepi; sumbu waktu tanpa pengulangan tanggal bila satu hari | lihat |

## Overview (inv. §2.1, DRD §3.1) — Tahap 13 ☑

| Butir | Acuan | Cara | Hasil |
|---|---|---|:-:|
| Periode log: jam pertama – jam terakhir | inv. §2.1 | lihat | ☑ |
| KPI sama dengan lama: baris, error, warning/4xx app, HTTP request, rate 4xx (1 desimal), rate 5xx (2 desimal), layanan, file log, file kosong | 06 Okt: 191.898 · 2.810 · 856 · 124.822 · 3,6 % · 0,04 % · 7 · 18 · 1 | `tools/uji_tahap13.cjs` (vs `dashboard.html`) | ☑ |
| KPI baru "File rusak" hanya bila > 0 (B05) | DRD §3.1 | lihat | ☑ |
| Perubahan ▲/▼ vs folder sebelumnya hanya atas layanan sebanding; sama dengan lama | 06 Okt: baris ▼ 36 %, error ▼ 37 %, warning tanpa perubahan | skrip | ☑ |
| `(i)` pada Error (5xx + baris error log) dan Warning / 4xx app | DRD §4.1 U8 | lihat | ☑ |
| Error per jam per layanan (batang bertumpuk, lebar) | inv. §2.1; berubah: memuat baris error log (U32) | lihat | ☑ |
| Error & warning per layanan; Baris log per layanan | inv. §2.1 | skrip (judul kartu) | ☑ |
| Ringkasan layanan; File log | inv. §2.1 | skrip | ☑ |
| Top pesan error lintas layanan: 25 teratas sama isi dan urutan jumlahnya; "Tampilkan berikutnya" | inv. §2.1, B04 | skrip | ☑ |
| Bagian "Traffic HTTP seluruh sistem" + catatan sumber + kartu nginx tanpa peta dan tanpa kartu pesan | inv. §2.1 | skrip (20 kartu = lama) | ☑ |
| Tanpa ingress nginx: KPI HTTP dan bagian traffic tidak tampil | DRD §6.6 | skrip (folder 27 Sep) | ☑ |
| Folder praktis kosong: pita kuning "hanya berisi N baris; M file rusak" + tautan ke Pod | DRD §6.6 | skrip (01 Okt) | ☑ |
| 8 kombinasi bahasa × tema × lebar | U1–U3 | skrip | ☑ |

## Halaman layanan (inv. §2.10, DRD §3.10) — Tahap 13 ☑ (kecuali peta, Tahap 20)

| Butir | Acuan | Cara | Hasil |
|---|---|---|:-:|
| KPI: baris, error, warning; HTTP + rate 4xx/5xx bila ada request; 4 entri pertama level | inv. §2.10 | skrip, 5 layanan (nginx, simpel-loop, appsmanager, coredns, frontend) | ☑ |
| Kartu yang tampil sama dengan lama (tabel centang inv. §2.10) | nginx 16, simpel-loop 16, frontend 10, appsmanager 4, coredns 4 kartu | skrip | ☑ |
| coredns: "Top 10 domain gagal resolve", tabel "Domain gagal resolve" | inv. §2.10 no. 6, 10 | skrip | ☑ |
| simpel-loop: judul per jam "dari X % request yang terlacak di nginx" | inv. §2.10 no. 2 | skrip | ☑ |
| nginx: garis Error per jam memuat baris error log (Σ = KPI Error 125) | TRD §4.4 butir 2 | skrip | ☑ |
| simpel-loop 29 Sep: donat level WARN 9.614, tanpa ERROR; `(i)` menjelaskan | TRD §4.4 butir 4 | skrip | ☑ |
| Status code: sumbu logaritmik, warna per kelas, kode selalu tertulis | inv. §2.10 no. 3, DRD §9.2 | lihat | ☑ |
| Kinerja endpoint: P95 ≥ 1 dtk kuning, P99 ≥ 5 dtk merah; error rate merah bila ada 5xx | inv. §2.10 no. 14 | lihat | ☑ |
| Tabel pesan: baris terbuka → baris log asli (UTC) + tombol salin; filter "JWT" hanya baris cocok + "N baris cocok" | DRD §4.3 | skrip | ☑ |
| 0 baris: "Tidak ada log untuk layanan ini …"; hanya rusak: + tag "Rusak" | DRD §6.6 | skrip (01 Okt) | ☑ |
| Peta modul ini, terlipat secara bawaan (U6) | DRD §3.10 no. 1 | — | Tahap 20 |
| 8 kombinasi bahasa × tema × lebar | U1–U3 | skrip | ☑ |

## Tren (inv. §2.3, DRD §3.3) — Tahap 14 ☑

| Butir | Acuan | Cara | Hasil |
|---|---|---|:-:|
| Catatan "Data tiap hari tidak selalu lengkap …" | inv. §2.3 | lihat | ☑ |
| 6 chart: error, warning, baris log per hari per layanan (bertumpuk); request HTTP (Total, 4xx, 5xx); keamanan (serangan, password salah, reset); bisnis (5 metrik) — seri dan angka sama dengan lama | inv. §2.3 | `tools/uji_tahap14.cjs` | ☑ |
| Tabel "Error per layanan & perubahan": angka dan ▲/▼ % sama dengan lama | inv. §2.3 | skrip | ☑ |
| Tabel "Kelengkapan data": angka / Kosong / Tidak ada sama; tanda baru "Rusak" (B05) | inv. §2.3, DRD §3.3 | skrip | ☑ |
| simpel-loop 30 Sep "Tidak ada"; 1 Okt "Rusak"/"Kosong" | rencana Tahap 14 | skrip | ☑ |
| Pemilih folder di header nonaktif dengan keterangan | DRD §3.3 | skrip | ☑ |
| Pemilih rentang 14 / 30 / 90 / semua (bawaan 30, diingat per browser): jumlah kolom berubah | DRD §3.3 U4 | skrip, database simulasi 40 folder | ☑ |
| Tabel menggulir mendatar, kolom Layanan terkunci, folder terbaru di kanan; juga di 390 px (bukan kartu) | DRD §3.3, §8.2 | skrip | ☑ |
| 8 kombinasi bahasa × tema × lebar | U1–U3 | skrip | ☑ |

## Halaman berikutnya

| Halaman | Acuan | Tahap |
|---|---|:-:|
| Keamanan | inv. §2.4, DRD §3.4 | 15 |
| Akar Masalah, Ketersediaan | inv. §2.5–§2.6, DRD §3.5–§3.6 | 16 |
| Pod, Bisnis, Pelacakan Request | inv. §2.7–§2.9, DRD §3.7–§3.9 | 17 |
| Kelola user, Ingest & impor | DRD §3.11 | 18 |
| Peta IP / Command Center | inv. §2.2, DRD §3.2, §7, §12 | 20, 22 |

Tiap tahap menambah bagiannya di sini dengan bentuk yang sama, dan skrip `tools/uji_tahapNN.cjs` bila halamannya
punya padanan di dashboard lama.
