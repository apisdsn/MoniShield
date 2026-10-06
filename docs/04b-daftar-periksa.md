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

## Keamanan (inv. §2.4, DRD §3.4) — Tahap 15 ☑

| Butir | Acuan | Cara | Hasil |
|---|---|---|:-:|
| 8 KPI ditata 4 + 4 (U5), angka sama dengan lama | 06 Okt: 88 · 14 · 5 · 62 · 9 · 1 · 0 · 4 | `tools/uji_tahap15.cjs` (06 Okt, 29 Sep, 28 Sep) | ☑ |
| "Temuan utama": 9 aturan, kalimat sama dengan lama dalam 2 bahasa; dari komponen + kamus, bukan HTML dalam string | inv. §2.4 | skrip (6 butir 06 Okt, 11 butir 29 Sep) | ☑ |
| 6 chart: kategori (warna keparahan), timeline per jam, top 10 IP, per pemilik jaringan, password salah per jam, top 10 IP password salah | inv. §2.4 | skrip (judul kartu) | ☑ |
| 5 tabel: endpoint serangan (URL lengkap + base host + UA, "2xx – verifikasi"), IP sumber, analisis akun (ISP Sama), login gagal (Multi-akun), IP 4xx | inv. §2.4 | skrip (kolom inti tiap baris) | ☑ |
| Tanpa nginx: catatan "deteksi serangan per URL tidak tersedia"; bagian login tetap | DRD §6.6 | skrip (28 Sep) | ☑ |
| URL berisi `<script>` / `onerror` / `${jndi:` tampil sebagai teks, tidak dieksekusi; tidak ada `@html` | rencana Tahap 15 | skrip (29 Sep) + `grep` | ☑ |
| Kategori serangan dan tanda akun diterjemahkan (label, DRD §6.3) | DRD §6.3 | lihat | ☑ |
| 8 kombinasi bahasa × tema × lebar | U1–U3 | skrip | ☑ |

## Akar Masalah (inv. §2.5, DRD §3.5) — Tahap 16 ☑

| Butir | Acuan | Cara | Hasil |
|---|---|---|:-:|
| "Ringkasan akar masalah" hingga 5 butir, kalimat sama dengan lama (dua bahasa, kode sebagai `<code>`); kosong → "Tidak ada pola …" | inv. §2.5 | `tools/uji_tahap16.cjs` (29 Sep, 06 Okt, 30 Sep, 27 Sep) | ☑ |
| Butir error koneksi memakai jumlah penuh (30 Sep 200 → 1.200) | TRD §4.4 butir 1 | skrip | ☑ |
| 4 chart: 401 berulang, umur JWT (bertumpuk per layanan), PDF per template, error koneksi per jenis | inv. §2.5 | skrip (data chart vs lama) | ☑ |
| Baru: "Refresh token kedaluwarsa: N" di bawah chart JWT | DRD §3.5 B07 | skrip (29 Sep: 237) | ☑ |
| Tabel 401: 30 baris pertama sama (seri boleh beda urutan) + "Menampilkan 30 dari N"; PDF; DNS + dampak | inv. §2.5, B04 | skrip | ☑ |
| Upstream DNS dari konfigurasi (`S4_DNS_UPSTREAM`), bukan tulis mati | inv. §2.5 | lihat | ☑ |

## Ketersediaan (inv. §2.6, DRD §3.6) — Tahap 16 ☑

| Butir | Acuan | Cara | Hasil |
|---|---|---|:-:|
| 7 KPI (4 + 3) sama dengan lama kecuali error koneksi pod (30 Sep 200 → 1.200); retry 825; 10 insiden | inv. §2.6, TRD §4.4 butir 1 | skrip (30 Sep, 06 Okt) | ☑ |
| 3 chart: 5xx per jam, 5xx per upstream, Uptime-Kuma per jam (berhasil/gagal) — data sama | inv. §2.6 | skrip | ☑ |
| Tabel per upstream, insiden (durasi menit), target Uptime-Kuma — sama; error koneksi 200 pertama + lanjutan | inv. §2.6 | skrip | ☑ |
| Tanpa nginx: catatan "Analisis ketersediaan memakai log ingress nginx …" | DRD §6.6 | skrip (28 Sep) | ☑ |
| 8 kombinasi bahasa × tema × lebar (kedua halaman) | U1–U3 | skrip | ☑ |

## Pod (inv. §2.7, DRD §3.7) — Tahap 17 ☑

| Butir | Acuan | Cara | Hasil |
|---|---|---|:-:|
| 5 KPI sama dengan lama; label "Pod dengan retry" (bukan "… retry 502") + keterangan (i) | inv. §2.7, B10 | `tools/uji_tahap17.cjs` (06 Okt, 29 Sep, 28 Sep) | ☑ |
| Catatan "Nama pod diambil dari nama file log …" | inv. §2.7 | lihat | ☑ |
| 2 chart: error per pod (15), sebaran request per pod (IP) (15) — data sama | inv. §2.7 | skrip | ☑ |
| Kesehatan per pod: baris, error, warning, ukuran sama; status "Rusak" untuk file rusak (06 Okt: 3; lama "Ada Log"), status lain sama | inv. §2.7, B05 | skrip | ☑ |
| Sebaran traffic per pod backend (porsi, 5xx, retry) dan restart — sama | inv. §2.7 | skrip | ☑ |

## Bisnis (inv. §2.8, DRD §3.8) — Tahap 17 ☑

| Butir | Acuan | Cara | Hasil |
|---|---|---|:-:|
| 11 KPI + perubahan vs folder sebelumnya sama dengan lama; 29 Sep: 12 / 108 / 35 / 12 / 314 / 18 / 55 / 813 / 32 / 389 | inv. §2.8 | skrip (29 Sep, 06 Okt, 28 Sep) | ☑ |
| Log simpel-loop / report / appsmanager tidak ada → KPI "–" + "Log … tidak ada di folder ini", bukan 0 | DRD U16 | skrip (30 Sep: 9 KPI "–") | ☑ |
| 5 chart (ringkasan, email, top aktivitas, login per jam, PDF per template) — data sama; label metrik dari kamus | inv. §2.8, DRD §6.3 | skrip | ☑ |
| Tabel aktivitas (20 teratas; seri di batas boleh beda pilihan, aturan E2) dan PDF per template sama | inv. §2.8 | skrip | ☑ |

## Pelacakan Request (inv. §2.9, DRD §3.9) — Tahap 17 ☑

| Butir | Acuan | Cara | Hasil |
|---|---|---|:-:|
| KPI 1–3 sama dengan lama; 29 Sep: 60.665 / 22.638 / 37,3 % | inv. §2.9 | skrip (29 Sep, 06 Okt) | ☑ |
| KPI gagal / IP / lambat dari SEMUA jejak (29 Sep: 3.245 → 3.479, 150 → 176, lambat 15 → 24) | TRD §4.4 butir 1, 9 | skrip (= API) | ☑ |
| Catatan "… X % event tidak cocok …" sama dengan lama | inv. §2.9 | skrip | ☑ |
| Tabel jejak: 300 pertama + "Menampilkan 300 dari 550"; setelah dimuat semua, setiap baris lama ada | inv. §2.9, B04 | skrip | ☑ |
| URL jejak tampil sebagai teks (tanpa eksekusi), dipotong 200, UA di bawahnya | inv. §2.9 | skrip + lihat | ☑ |
| Tanpa kecocokan (27 Sep) atau tanpa simpel-loop (30 Sep): catatan "Pelacakan butuh log om-be-simpel-loop dan ingress nginx …" (ASUMSI; lama 27 Sep menampilkan KPI nol) | DRD §6.6 | skrip | ☑ |
| 8 kombinasi bahasa × tema × lebar (ketiga halaman) | U1–U3 | skrip | ☑ |

## Halaman berikutnya

| Halaman | Acuan | Tahap |
|---|---|:-:|
| Kelola user, Ingest & impor | DRD §3.11 | 18 |
| Peta IP / Command Center | inv. §2.2, DRD §3.2, §7, §12 | 20, 22 |

Tiap tahap menambah bagiannya di sini dengan bentuk yang sama, dan skrip `tools/uji_tahapNN.cjs` bila halamannya
punya padanan di dashboard lama.
