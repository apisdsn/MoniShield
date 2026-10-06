# DRD — Kebutuhan desain dashboard log SIMPEL4 (v2)

Tampilan dan interaksi v2. Dasarnya: [`00-inventaris.md`](00-inventaris.md) (isi tiap tab), [`01-prd.md`](01-prd.md)
(prioritas dan asumsi), CSS di `dashboard_template.html`, dan tangkapan layar `dashboard.html` hasil build
2026-10-06 (tab Overview, Peta IP, Keamanan, Ketersediaan, halaman ingress nginx pada lebar 1440 px; Peta IP
pada 390 px; semuanya tema gelap, bahasa Indonesia).

Kebutuhan data dan teknis (skema, endpoint, struktur komponen kode) bukan bagian dokumen ini.

**Prinsip**: tampilan lama sudah baik dan dikenali penggunanya. v2 mempertahankan susunan, warna, dan
istilahnya; yang berubah hanya yang (a) rusak di layar sempit, (b) tidak terbaca, (c) dituntut PRD, atau
(d) tak terhindarkan karena data kini dimuat per tab. Semua perubahan terdaftar di [§10](#10-yang-berubah-dari-tampilan-lama).

> **Revisi 2026-10-06 (Tahap 1 rencana).** Diselaraskan dengan keputusan pemilik dan [`03-trd.md`](03-trd.md):
> dashboard dibuka dari banyak komputer dengan **login** (dua peran: admin dan user; user melihat seluruh
> dashboard), tampilan **ponsel dikerjakan serius**, definisi janggal diperbaiki, dan ada **impor dari S3**.
> Tambahan utama: layar Masuk, Ganti sandi, Kelola user, Ingest & impor (§3.11), perilaku sesi (§6.9), dan
> perubahan U28–U32 (§10).

Rujukan: "inv. §x" = inventaris, "F/B/T/A/P-nn" = nomor di PRD. **ASUMSI** dirangkum di [§11](#11-asumsi-dan-pertanyaan-terbuka).

Belum dilihat langsung: tema terang dan bahasa Inggris (dinilai dari CSS dan kamus, bukan tangkapan layar).

---

## 1. Navigasi dan daftar halaman

### 1.1 Struktur

Satu aplikasi satu layar: kerangka tetap (navigasi + header), isi berganti. Tidak ada halaman bertingkat.

```
Analisis                         Layanan (yang ada di folder terpilih)
├─ Overview            /         ├─ Nginx-Ingress-Controller
├─ Peta IP                       ├─ Coredns
├─ Tren      (lintas folder)     ├─ Om-Be-Appsmanager
├─ Keamanan     [N IP]           ├─ Om-Be-Referensi
├─ Akar Masalah                  ├─ Om-Be-Report
├─ Ketersediaan                  ├─ Om-Be-Simpel-Loop
├─ Pod                           └─ Om-Fe-Inhouse
├─ Bisnis                           (lencana = jumlah error)
└─ Pelacakan Request
```

Urutan, nama, dan lencana sama dengan sistem lama (inv. §2.0). Sembilan tab analisis + satu templat
halaman layanan = **10 halaman data**. Sidebar ini sama untuk admin dan user.

Di luar sidebar ada **4 layar akun dan admin** (§3.11), dicapai dari layar Masuk atau dari menu user di
header:

```
(belum masuk)  →  Masuk  →  [Ganti sandi, bila wajib]  →  dashboard
Menu user ▾ ├─ Ganti sandi
            ├─ Kelola user        (hanya admin)
            ├─ Ingest & impor     (hanya admin)
            └─ Keluar
```

### 1.2 Daftar halaman

| # | Halaman | Bergantung folder | Butuh log | Sketsa |
|--:|---|:-:|---|---|
| 1 | Overview | ya | — | §3.1 |
| 2 | Peta IP | ya | ingress nginx | §3.2 |
| 3 | Tren | **tidak** | — | §3.3 |
| 4 | Keamanan | ya | nginx (serangan), appsmanager (login) | §3.4 |
| 5 | Akar Masalah | ya | nginx, Spring, coredns | §3.5 |
| 6 | Ketersediaan | ya | ingress nginx | §3.6 |
| 7 | Pod | ya | — | §3.7 |
| 8 | Bisnis | ya | simpel-loop, report, appsmanager | §3.8 |
| 9 | Pelacakan Request | ya | simpel-loop + nginx | §3.9 |
| 10 | Layanan `<nama>` | ya | layanan itu | §3.10 |
| 11 | Masuk | — | — | §3.11 |
| 12 | Ganti sandi | — | — | §3.11 |
| 13 | Kelola user (admin) | — | — | §3.11 |
| 14 | Ingest & impor (admin) | — | — | §3.11 |

### 1.3 Alamat (URL)

Alamat menyimpan **tab, folder, dan modul peta**, sehingga tautan yang dibagikan membuka tampilan yang sama
dan tombol kembali browser berfungsi. Di sistem lama hanya tab yang tersimpan; folder selalu kembali ke yang
terbaru (perubahan U1). Bahasa dan tema tetap pilihan per browser, tidak masuk alamat.

- Tanpa folder di alamat → folder terbaru.
- Folder di alamat tidak ada → folder terbaru + pemberitahuan singkat.
- Tab layanan yang tidak ada di folder terpilih → Overview (perilaku lama).
- Belum masuk → layar Masuk; setelah berhasil, kembali ke alamat yang tadi diminta.
- Layar admin punya alamat sendiri (`admin/user`, `admin/ingest`); dibuka user biasa → keadaan
  "Tidak punya akses" (§6.6).

---

## 2. Kerangka

### 2.1 Layar lebar (> 900 px)

```
┌────────────────┬──────────────────────────────────────────────────────────────────┐
│ [S4] SIMPEL4   │  Judul Tab (38px, gradien)   [◀][Folder ▾][▶] [ID|EN] [☀|☾] [👤▾] │
│      Log       │  Folder log 6 Okt 2026 · berisi log 5 Okt 09.00–6 Okt 00.59 WIB  │
│                │  · 7 layanan                                                     │
│ ANALISIS       │ ──────────────────────────────────────────────────────────────── │
│ ● Overview     │                                                                  │
│ ○ Peta IP      │  <main>  isi halaman:                                            │
│ ○ Tren         │    baris KPI  → peringatan/catatan → grid kartu 2 kolom          │
│ ○ Keamanan 14IP│    (kartu "lebar" mengisi 2 kolom)                               │
│ ○ …            │                                                                  │
│ LAYANAN        │                                                                  │
│ ○ Nginx-…  125 │                                                                  │
│ ○ Coredns  191 │                                                                  │
│ ○ …            │                                                                  │
│                │                                                                  │
│ Semua waktu    │                                                                  │
│ dalam WIB      │                                                                  │
└────────────────┴──────────────────────────────────────────────────────────────────┘
   236 px tetap     isi maks. 1560 px, padding 26/34 px, grid kartu min. 520 px
```

Dipertahankan: lebar sidebar 236 px, sidebar tetap saat isi digulir, grup "Analisis"/"Layanan", titik
penanda, lencana merah muda, judul bergradien, pemilih folder berbentuk pil berwarna aksen, grid kartu
`auto-fit` minimal 520 px, KPI `auto-fit` minimal 170 px.

Berubah:

- **Subjudul memuat rentang waktu log sebenarnya** (B06, perubahan U2). Nama folder bukan tanggal isinya.
- **Baris header menempel di atas** saat digulir (hanya pemilih folder, bahasa, tema; tinggi 56 px), supaya
  folder bisa diganti dari tengah halaman panjang (U3).
- Teks "Semua waktu dalam WIB (UTC+7)" cukup sekali di kaki sidebar; tidak diulang di subjudul.
- **Menu user** di ujung kanan header (U28): tombol berisi nama tampilan; terbuka menjadi daftar: nama +
  peran, "Ganti sandi", lalu untuk admin "Kelola user" dan "Ingest & impor", lalu "Keluar". Pola menu
  standar: `Enter`/`Spasi` membuka, panah berpindah, `Esc` menutup dan mengembalikan fokus.

### 2.2 Layar sempit (≤ 900 px)

Lihat §8.

---

## 3. Sketsa tiap halaman

Notasi: `[KPI]` kartu angka · `╔ chart ╗` kartu chart · `┌ tabel ┐` kartu tabel · `(f)` punya filter ·
`▌peringatan` kotak temuan · `┆catatan┆` kartu catatan bergaris putus. Isi tiap elemen dan sumber datanya ada
di inventaris pada nomor yang disebut; di sini hanya tata letak.

### 3.1 Overview (inv. §2.1)

```
Periode log: 5 Okt 2026 00.00 WIB – 6 Okt 2026 00.59 WIB
[Total baris ▼36%] [Error ▼37%] [Warning/4xx] [HTTP request] [Rate 4xx] [Rate 5xx]
[Layanan] [File log] [File kosong] [File rusak*]
╔ Error per jam per layanan (batang bertumpuk)                    lebar ╗
╔ Error & warning per layanan ╗      ╔ Baris log per layanan ╗
┌ Ringkasan layanan ┐                ┌ File log ┐
┌ Top pesan error lintas layanan (25, batang proporsi)            lebar ┐
── Traffic HTTP seluruh sistem ── (sumber: ingress nginx)
   … kartu halaman layanan nginx, tanpa peta dan tanpa kartu pesan (§3.10 no. 2–18)
```

\* B05: KPI baru "File rusak", hanya tampil bila > 0.

### 3.2 Peta IP (inv. §2.2)

```
[Modul: Semua Modul ▾]
[IP asal unik] [Lokasi asal] [Negara asal] [Modul tujuan] [IP tujuan unik] [Total request]
┌ Peta IP Asal → IP Tujuan                      [Indonesia | Dunia]  lebar ┐
│ ┌──────────────────────────────────────────────────────────── [+][−][⤢] │
│ │                 peta (lihat §7)                                      │ │
│ └──────────────────────────────── © MaxMind · GeoNames · Natural Earth ─┘ │
│ ◉ Lokasi IP asal  ◉ Server tujuan  ⬤ Kelompok lokasi                     │
│ 2.030 request dari luar Indonesia · 0 dari IP internal / tanpa lokasi    │
└──────────────────────────────────────────────────────────────────────────┘
┌ Alur IP Asal → IP Tujuan (f)                                       lebar ┐
┆ Lokasi adalah perkiraan tingkat kota … IP tujuan adalah IP pod …         ┆
```

### 3.3 Tren (inv. §2.3)

```
Perbandingan antar folder log. Data tiap hari tidak selalu lengkap …
[Rentang: 30 folder terakhir ▾]*
╔ Error per hari per layanan ╗       ╔ Warning per hari per layanan ╗
╔ Request HTTP per hari ╗            ╔ Keamanan per hari ╗
╔ Aktivitas bisnis per hari ╗        ╔ Baris log per hari per layanan ╗
┌ Error per layanan & perubahan vs hari sebelumnya                  lebar ┐
┌ Kelengkapan data (jumlah baris; Kosong / Rusak* / Tidak ada)      lebar ┐
```

\* Perubahan U4: dengan 365 folder, chart batang dan tabel selebar 365 kolom tidak terbaca. Pemilih rentang
(14 / 30 / 90 folder terakhir / semua; bawaan 30). Kedua tabel menggulir mendatar dengan kolom "Layanan"
terkunci di kiri dan folder terbaru di kanan. Pemilih folder di header **dinonaktifkan** di tab ini, dengan
keterangan "Tren menampilkan semua folder".

### 3.4 Keamanan (inv. §2.4)

```
[Request serangan] [IP sumber unik] [Serangan kritis] [Endpoint 2xx]
[IP login gagal] [Akun sukses ≥3 gagal] [Sukses dari IP berbeda] [Reset password]
▌Temuan utama: • Percobaan Log4Shell … • Panel Rancher … • 62 endpoint 2xx …
╔ Request per kategori serangan ╗    ╔ Timeline indikasi serangan per jam ╗
╔ Top 10 IP sumber serangan ╗        ╔ Sumber serangan per pemilik jaringan ╗
╔ Password salah per jam ╗           ╔ Top 10 IP dengan password salah ╗
┌ Endpoint dengan indikasi serangan (f)                             lebar ┐
┌ IP sumber serangan (f)                                            lebar ┐
┌ Analisis akun (f)                                                 lebar ┐
┌ Login gagal / brute force (f)                                     lebar ┐
┌ IP dengan respons 4xx terbanyak                                   lebar ┐
Deteksi berbasis pola (signature) … (catatan kaki)
```

Delapan KPI ditata **4 + 4** pada layar lebar (sekarang 6 + 2 yang menyisakan baris yatim; U5).

### 3.5 Akar Masalah (inv. §2.5)

```
▌Ringkasan akar masalah: • 401 berulang … • token JWT … • PDF gagal … • DNS … • koneksi pod …
╔ Klien dengan 401 berulang ╗        ╔ Umur token JWT saat ditolak ╗
╔ PDF report per template ╗          ╔ Error koneksi nginx → pod per jenis ╗
┌ Klien dengan 401 berulang (f)                                     lebar ┐
┌ Status pembuatan PDF per template (f) ┐   ┌ DNS timeout per domain ┐
```

B07: chart umur JWT mendapat keterangan di bawahnya "Refresh token kedaluwarsa: N" (angka yang sekarang
dihitung tetapi tidak tampil).

### 3.6 Ketersediaan (inv. §2.6)

```
[Ketersediaan %] [Total 5xx] [Insiden 5xx] [Retry ke pod lain]
[Error koneksi pod] [Cek Uptime-Kuma] [Cek uptime gagal]
╔ Respons 5xx per jam                                               lebar ╗
╔ Respons 5xx per upstream ╗         ╔ Health check Uptime-Kuma per jam ╗
┌ Ketersediaan per upstream ┐        ┌ Target health check Uptime-Kuma ┐
┌ Daftar insiden 5xx                                                lebar ┐
┌ Error koneksi nginx → pod (f)                                     lebar ┐
```

### 3.7 Pod (inv. §2.7)

```
[Pod (file log)] [Pod tanpa log] [Pod backend di nginx] [Pod dengan retry*] [Restart]
┆ Nama pod diambil dari nama file log. Nginx hanya mencatat IP pod …      ┆
╔ Error per pod (15) ╗               ╔ Sebaran request per pod (IP) (15) ╗
┌ Kesehatan per pod (f) — Status: Ada log / Tanpa log / Rusak*      lebar ┐
┌ Sebaran traffic per pod backend                                   lebar ┐
┌ Restart / start aplikasi                                          lebar ┐
```

\* B10: label "Pod dengan retry 502" → "Pod dengan retry". B05: status "Rusak".

### 3.8 Bisnis (inv. §2.8)

```
[Laporan dibuat ▲] [Registrasi ▲] [OTP diminta] [OTP terverifikasi] [File diunggah] [Upload ditolak]
[Email terkirim] [PDF dibuat] [PDF gagal] [Login sukses] [Pengguna unik login]
┆ Dihitung dari event aplikasi (respons 2xx) … hanya pod yang lognya ada  ┆
╔ Ringkasan aktivitas layanan publik ╗   ╔ Email notifikasi per jenis ╗
╔ Top aktivitas proses laporan ╗         ╔ Login sukses per jam ╗
╔ PDF report per template ╗
┌ Aktivitas proses laporan ┐             ┌ PDF report per template ┐
```

### 3.9 Pelacakan Request (inv. §2.9)

```
[RequestId simpel-loop] [Cocok dengan nginx] [Tingkat kecocokan]
[Request gagal terlacak] [IP unik (gagal)] [Lambat ≥ 5 dtk]
┆ Setiap event aplikasi simpel-loop punya requestId … X % tidak cocok …   ┆
╔ Top 10 IP dengan request gagal ╗   ╔ Request gagal per jenis error ╗
┌ Jejak request gagal / lambat (f)                                  lebar ┐
```

### 3.10 Halaman layanan (inv. §2.10)

Satu templat; kartu yang tidak berlaku untuk layanan itu tidak dirender (tabel centang di inv. §2.10).

```
[Baris log] [Error] [Warning] [HTTP request] [Rate 4xx] [Rate 5xx] [level 1..4]
 1 ┌ Peta modul ini + ┌ tabel alur (f)                              lebar ┐
 2 ╔ Aktivitas per jam: Total & Error                               lebar ╗
 3 ╔ Status code HTTP ╗               4 ╔ Traffic per upstream (donat) ╗
 5 ╔ Distribusi level (donat) ╗       6 ╔ Top 10 endpoint ╗
 7 ╔ Top 10 endpoint 4xx/5xx ╗        8 ╔ Top 10 IP klien ╗
 9 ╔ Top 10 pesan error/warning ╗
10 ┌ Top endpoint ┐                  11 ┌ Endpoint dengan status 4xx/5xx ┐
12 ╔ P95 – 10 endpoint paling lambat ╗ 13 ╔ Error rate tertinggi ╗
14 ┌ Kinerja endpoint                                               lebar ┐
15 ┌ Endpoint dengan error rate tertinggi                           lebar ┐
16 ┌ Request lambat ≥ 1 dtk ┐        17 ┌ Top IP klien ┐
18 ┌ Top User-Agent ┐
19 ┌ Pesan error / warning (dikelompokkan) (f)                      lebar ┐
```

Perubahan U6: peta di halaman layanan **terlipat secara bawaan** ("Tampilkan peta asal pengguna modul ini").
Alasan: peta adalah elemen terberat, sudah ada di tab Peta IP dengan pemilih modul, dan di halaman layanan
ia mendorong chart utama ke bawah lipatan. Tabel alurnya ikut terlipat. Pilihan buka/tutup diingat per browser.

### 3.11 Masuk dan admin (TRD §8.2–§8.4)

Layar-layar ini memakai token, kartu, tabel, dan tombol yang sama dengan halaman data. Semuanya dua bahasa
dan dua tema. Tidak ada sidebar di layar Masuk dan Ganti sandi wajib.

**Masuk**

```
                         ┌────────────────────────────────────┐
        [ID|EN] [☀|☾]    │  [S4]  SIMPEL4 Log                 │
                         │                                    │
                         │  Nama user                         │
                         │  [______________________________]  │
                         │  Sandi                             │
                         │  [__________________________] [👁] │
                         │                                    │
                         │  ▌Nama user atau sandi salah.      │  ← hanya setelah gagal
                         │                                    │
                         │  [            Masuk             ]  │
                         │  Lupa sandi? Hubungi admin.        │
                         └────────────────────────────────────┘
```

- Satu kartu di tengah, lebar maksimum 380 px; di ponsel selebar layar dengan tepi 16 px.
- Pesan gagal **satu kalimat yang sama** untuk nama salah maupun sandi salah. Saat dibatasi: "Terlalu banyak
  percobaan. Coba lagi dalam N menit." Saat sesi habis: keterangan biru di atas formulir "Sesi Anda
  berakhir. Silakan masuk lagi."
- Kolom memakai `<label>` terlihat, `autocomplete="username"` / `"current-password"`; `Enter` mengirim;
  tombol 👁 menampilkan sandi dan punya nama aksesibel. Pesan gagal memakai `role="alert"` dan fokus
  kembali ke kolom sandi.
- Tidak ada "ingat saya", pendaftaran, atau tautan lupa sandi lewat email.
- Selama mengirim: tombol nonaktif dengan teks "Memeriksa…".

**Ganti sandi**

```
┌ Ganti sandi ───────────────────────────────────────┐
│ ┆ Anda harus mengganti sandi sebelum melanjutkan. ┆ │  ← hanya bila wajib
│ Sandi sekarang     [_________________________]     │
│ Sandi baru         [_________________________]     │
│   Minimal 12 karakter. Kalimat panjang lebih baik. │
│ Ulangi sandi baru  [_________________________]     │
│ [ Simpan ]   [ Batal ]                             │  ← "Batal" tidak ada bila wajib
└────────────────────────────────────────────────────┘
```

- Wajib saat masuk pertama dan setelah sandi direset admin: layar ini tampil sendirian sampai selesai
  (satu-satunya jalan lain adalah "Keluar").
- Aturan ditulis sebelum pengguna mengetik, bukan sebagai galat sesudahnya. Galat per kolom, di bawah
  kolomnya, terhubung dengan `aria-describedby`.
- Berhasil → pemberitahuan singkat "Sandi diganti"; sesi di perangkat lain berakhir.

**Kelola user** (admin)

```
Kelola User                                                    [+ Tambah user]
┌──────────────────────────────────────────────────────────────────────────────┐
│ NAMA USER   NAMA TAMPILAN   PERAN     STATUS      TERAKHIR MASUK       AKSI  │
│ admin       Administrator   ● Admin   ● Aktif     6 Okt 2026 18.40 WIB  [⋯]  │
│ rina        Rina            User      ● Aktif     5 Okt 2026 09.12 WIB  [⋯]  │
│ budi        Budi            User      ○ Nonaktif  –                     [⋯]  │
└──────────────────────────────────────────────────────────────────────────────┘
 [⋯] → Ubah · Reset sandi · Nonaktifkan / Aktifkan · Hapus

┌ Tambah user ────────────────────────────────┐
│ Nama user       [______________]            │  huruf kecil, angka, titik, strip; 3–32
│ Nama tampilan   [______________]            │
│ Peran           (•) User   ( ) Admin        │
│   User melihat seluruh dashboard.           │
│   Admin juga mengelola user, ingest, impor. │
│ Sandi awal      [______________] [Buat acak]│
│   User wajib menggantinya saat masuk pertama│
│ [ Simpan ]  [ Batal ]                       │
└─────────────────────────────────────────────┘
```

- Tabel memakai komponen tabel (§4.3) dengan filter. Peran admin dan status memakai tag (§4.5): admin =
  tag netral bertitik, aktif = tag ok, nonaktif = teks `muted`.
- Formulir tambah/ubah tampil sebagai dialog (di ponsel: layar penuh). Fokus terkunci di dalam dialog;
  `Esc` menutup; fokus kembali ke tombol pemicu.
- **Reset sandi** menampilkan sandi sementara **sekali**, dengan tombol salin dan peringatan "Sandi ini
  tidak akan ditampilkan lagi".
- **Hapus** dan **Nonaktifkan** meminta konfirmasi yang menyebut nama user. Menghapus diri sendiri, atau
  menghapus/menurunkan/menonaktifkan admin terakhir, **tidak ditawarkan** (butir menu nonaktif dengan
  keterangan sebabnya).
- Di ponsel tabel menjadi kartu baris (§8.2); tombol "+ Tambah user" menempel di bawah layar.
- Kosong tidak mungkin (selalu ada minimal satu admin).

**Ingest & impor** (admin)

```
Ingest & Impor
┌ Ingest ──────────────────────────────────────────────────────────────────────┐
│ Terakhir: 6 Okt 2026 17.51 WIB · berhasil · 0 file berubah     [Ingest sekarang]
│ ▓▓▓▓▓▓▓▓░░░░  Folder 2026-10-06 · 12 dari 18 file        ← hanya saat berjalan │
│ ▌2 peringatan: pasangan .log/.log.gz berbeda (…); layanan tak dikenal (…)     │
└──────────────────────────────────────────────────────────────────────────────┘
┌ Impor dari S3 ───────────────────────────────────────────────────────────────┐
│ Kredensial AWS: ● tersedia (konfigurasi server)                               │
│ Tautan  [ s3://simpel4-backup/k8s-logs/2026-10-07/            ]               │
│         Hanya s3://simpel4-backup/k8s-logs/<tanggal>/                         │
│ [ Coba dulu ]  [ Impor ]                                                      │
│ Hasil coba: 18 objek akan diambil (104 MB) · 19 dilewati (.gz berpasangan)    │
│ ┌ Riwayat impor: WAKTU · TAUTAN · FOLDER · OBJEK · UKURAN · STATUS ─────────┐ │
└──────────────────────────────────────────────────────────────────────────────┘
┌ Catatan audit (f) ─ WAKTU · USER · TINDAKAN · RINCIAN · IP ──────────────────┐
```

- **Ingest**: status terakhir, tombol "Ingest sekarang" (nonaktif saat berjalan), kemajuan saat berjalan
  (diperbarui tiap 2 detik; diumumkan sopan ke pembaca layar), dan daftar peringatan yang bisa dibuka.
  Dashboard tetap bisa dipakai selama ingest.
- **Impor**: kolom tautan dengan contoh bentuk yang diterima; "Coba dulu" hanya mendaftar objek dan
  menampilkan ringkasan; "Impor" meminta konfirmasi lalu menampilkan kemajuan. Galat ditulis sebagai sebab
  dan tindakan ("Bucket ini tidak diizinkan. Yang diizinkan: …").
- **Kredensial**: hanya status (tersedia / tidak, sumbernya). Bila tidak tersedia, muncul formulir tempel
  kredensial sementara (tiga kolom bertipe sandi, tanpa `autocomplete`) dengan keterangan "disimpan di
  memori server saja, hilang saat server dimulai ulang". Nilai kredensial tidak pernah ditampilkan kembali.
- Bila impor dimatikan di konfigurasi: kartu Impor diganti catatan cara mengaktifkannya.
- **Catatan audit**: tabel berfilter, terbaru di atas, 50 baris pertama + "tampilkan berikutnya".
- Di ponsel ketiga kartu bertumpuk; riwayat dan audit menjadi kartu baris.

---

## 4. Komponen yang dipakai ulang

Setiap komponen punya empat keadaan: **berisi**, **memuat**, **kosong**, **gagal** (§6.5–6.7).

### 4.1 Kartu KPI

```
┌──────────────────────┐
│ Label (13,5px, 500)  │   ← maks. 2 baris
│ 124.822   (34px,600) │   ← angka tabular; warna = makna (§5.3)
│ ▼ 36% vs 5 Okt 2026  │   ← opsional, 11,5px
└──────────────────────┘
```

- Warna nilai: gradien aksen (netral), `err`, `warn`, `ok`, `muted`. Sama dengan lama.
- Baris perbandingan: empat bentuk dari inv. §2.0 (▲/▼ %, ≈ sama, baru, tidak lengkap). Panah **selalu
  disertai kata** ("naik"/"turun" untuk pembaca layar) dan warna bukan satu-satunya penanda.
- Perubahan U7: KPI yang nilainya kini berbeda dari sistem lama karena B03 tidak diberi tanda apa pun di
  tampilan; selisihnya hidup di laporan kesetaraan, bukan di antarmuka.
- Perubahan U8: KPI boleh punya **keterangan `(i)`** (tooltip + fokus keyboard) berisi definisi satu
  kalimat. Wajib untuk yang definisinya tidak jelas dari label: Error (nginx dan frontend = respons 5xx +
  baris error log, **dengan rinciannya**: "51 respons 5xx + 74 baris error log"), Warning / 4xx app,
  Ketersediaan (non-5xx), IP tujuan unik, Tingkat kecocokan. Di luar KPI, keterangan yang sama wajib pada:
  judul donat level simpel-loop ("request gagal 4xx dihitung WARN, 5xx ERROR") dan level `EXC` di tabel
  pesan ("rincian exception; tidak menambah jumlah Error") (TRD §4.4).

### 4.2 Kartu chart

- Kerangka: judul kiri, aksi kanan (bila ada), kanvas tinggi 280 px. Sama dengan lama.
- Jenis dan gaya dipertahankan (inv. §2.0): garis area bergradien, batang bersudut bulat (maks. 34 px),
  donat 74 % dengan persentase di tengah, batang horizontal top-N dengan label dipotong 48 karakter.
- Warna dari token (§5.4), bukan nilai tulis-mati; ganti tema tanpa memuat ulang data.
- Legenda hanya bila > 1 seri atau donat. Tooltip mode indeks.
- Perubahan U9: tiap chart punya **alternatif teks**: `aria-label` berisi judul + ringkasan satu kalimat
  (nilai terbesar dan total), dan tombol "Lihat sebagai tabel" yang membuka data chart dalam tabel. Chart
  kanvas tidak terbaca pembaca layar dan tidak bisa disalin.
- Perubahan U10: sumbu waktu memakai jam saja (`13.00`) bila semua titik satu tanggal; tanggal ditulis
  sekali di bawah sumbu. Sekarang tiap label mengulang `5 Okt` dan dimiringkan.
- Batang horizontal untuk IP: klik batang menggulir ke baris IP itu di tabel terkait pada halaman yang
  sama (bila ada). Tidak pindah halaman.

### 4.3 Tabel dengan filter

```
┌ Judul tabel                              [🔍 filter…        ] ┐
│ KOLOM A ▾        KOLOM B        JUMLAH                        │  ← header lekat
│ baris …                                              1.234    │
│ …                                                             │  ← maks. 440–600px, gulir di dalam kartu
│ Menampilkan 30 dari 653   [Tampilkan 100 berikutnya]          │  ← baru (B04)
└───────────────────────────────────────────────────────────────┘
```

- Dipertahankan: header lekat, angka rata kanan tabular, sorot baris saat hover, kolom pertama
  `word-break`, batang proporsi di bawah sel pertama untuk tabel "Jumlah", pewarnaan kode status.
- **Jumlah awal = batas lama** (inv. §5.2), supaya tampilan pertama identik. Satu pengecualian: tabel
  alur IP tampil **100** baris pertama, bukan 3.000 (U30). Di bawahnya baris status
  "Menampilkan N dari M" dan tombol untuk memuat berikutnya (B04). Bila M ≤ N baris status tidak tampil.
- **Filter** mencari di **seluruh data** tabel itu, bukan hanya baris yang tampil (B04). Substring, tanpa
  beda huruf besar/kecil, pada semua kolom teks; jeda ketik 250 ms; tombol × untuk mengosongkan; hasil
  "N baris cocok". Tanpa hasil: "Tidak ada baris yang cocok dengan '…'".
- Perubahan U11: **urut per kolom** dengan klik header (angka dan waktu). Urutan bawaan = urutan lama.
- Tabel lebar (≥ 6 kolom) menggulir mendatar di dalam kartu dengan kolom pertama terkunci; lihat §8.
- Sel yang terpotong (URL, UA, pesan) menampilkan teks lengkap saat diklik/fokus, bukan hanya lewat `title`.

Tabel pesan terkelompok (F19) memakai komponen ini dengan baris yang bisa dibuka: klik pesan → contoh baris
log asli dalam blok monospace berlabel "Baris log asli (waktu UTC)", dengan tombol salin.

### 4.4 Sel IP dengan pemilik jaringan

```
103.160.147.100                      ← tebal, monospace-tabular
AS141576 · ID · IDNIC-OMBUDSMAN-AS-ID Ombudsman Republik Indonesia   ← 11px, muted
● Jaringan Ombudsman                 ← tag hijau, hanya bila pemiliknya Ombudsman
```

- Varian: tanpa pemilik (IP saja); IP privat → "Jaringan Internal (IP Privat)"; `+N` IP lain di tabel
  serangan. Sama dengan lama.
- Teks pemilik dipotong 2 baris; lengkapnya saat diklik/fokus.
- Perubahan U12: tombol salin kecil muncul saat hover/fokus. Tidak ada tautan keluar ke layanan pencari IP
  (melanggar aturan privasi).
- Di chart, tooltip IP menampilkan pemilik di baris kedua (lama).

### 4.5 Tag tingkat bahaya

| Tingkat | Kategori | Gelap (teks / latar) | Terang (teks / latar) |
|---|---|---|---|
| 3 kritis | Log4Shell / RCE, SQL Injection, Path Traversal / LFI, XSS | `#fda4af` / err 14 % | `#be123c` / err 14 % |
| 2 sedang | Probe file sensitif, Scan CMS / WordPress, Probe PHP / CGI | `#fcd34d` / warn 14 % | `#b45309` / warn 14 % |
| 1 rendah | UA tool/scanner otomatis; tag netral ("Multi-akun", tanda akun) | `#cbd5e1` / abu 14 % | `#44546a` / abu 14 % |
| ok | "Jaringan Ombudsman", "Ada log" | `#6ee7b7` / ok 14 % | `#047857` / ok 14 % |

Bentuk pil, 11 px tebal, titik kecil di kiri. Sama dengan lama. Tambahan: tingkat dibedakan juga oleh
**teks** (nama kategori selalu tampil), jadi tidak bergantung warna. Tag baru "Rusak" (B05) memakai tingkat 2.

### 4.6 Peringatan dan catatan

- **Peringatan** ("Temuan utama", "Ringkasan akar masalah"): kartu dengan garis kiri merah 3 px, judul
  tebal, daftar butir. Sama. IP dan akun di dalam kalimat memakai gaya data (tidak dikapitalisasi).
- **Catatan**: kartu bergaris putus-putus, teks `muted` 13 px. Dipakai untuk penjelasan metode dan
  keadaan kosong.

### 4.7 Peta

Satu komponen untuk tab Peta IP dan halaman layanan; spesifikasi di §7.

### 4.8 Kontrol

| Kontrol | Bentuk | Catatan |
|---|---|---|
| Pemilih folder | `select` pil, teks aksen | §6.1 |
| Pemilih modul | `select` pil | §6.2 |
| Bahasa, tema, preset peta | grup tombol pil (segmented) | `role="radiogroup"`, panah kiri/kanan berpindah |
| Filter | input pil dengan ikon kaca pembesar | §4.3 |
| Tombol sekunder | pil bergaris, teks `fg` | "Tampilkan berikutnya", "Coba lagi", "Lihat sebagai tabel" |

---

## 5. Token desain

Diambil dari `:root` dan `:root[data-theme="light"]` di `dashboard_template.html`. Nama dipertahankan.
Kolom "Δ" menandai nilai yang **berubah atau baru**, dengan alasan di §5.6.

### 5.1 Warna dasar

| Token | Gelap | Terang | Pakai | Δ |
|---|---|---|---|:-:|
| `--bg` | `#0a1120` | `#f3f6fb` | latar halaman | |
| `--bg2` | `#0d1628` | `#ffffff` | latar input, grup tombol | |
| `--card` | `#101b2e` | `#ffffff` | latar kartu | |
| `--card2` | `#0c1524` | `#eef3fa` | latar peta, blok kode | |
| `--fg` | `#e2ecf3` | `#0f1b2d` | teks utama | |
| `--muted` | `#7d8fa6` | `#5b6b80` | teks sekunder | |
| `--line` | `#1c2a40` | `#dbe3ee` | garis pemisah (dekoratif) | |
| `--line-strong` | `#5a7299` | `#8794a8` | batas input dan tombol | baru |
| `--accent` | `#2dd4bf` | `#0d9488` | aksen, grafik, fokus | |
| `--accent2` | `#22d3ee` | `#0891b2` | gradien | |
| `--accent-text` | `#2dd4bf` | `#0f766e` | aksen sebagai **teks kecil** | baru |
| `--violet` | `#8b5cf6` | `#7c3aed` | seri kedua | |
| `--err` | `#f43f5e` | `#e11d48` | error, 5xx | |
| `--warn` | `#f59e0b` | `#b45309` | peringatan, 4xx | |
| `--ok` | `#34d399` | `#059669` | sukses, 2xx (grafik, angka besar) | |
| `--ok-text` | `#34d399` | `#047857` | sukses sebagai teks kecil | baru |
| `--neutral` | `#7a8699` | `#7a8699` | 3xx, keparahan 1 di chart | dinamai |
| `--land` | `#1b2d4a` | `#cfdff5` | daratan peta | |
| `--coast` | `#5a7299` | `#6f86ab` | garis pantai dan batas wilayah | baru |
| `--glow` | `0 0 0 1px rgba(45,212,191,.06), 0 12px 32px rgba(0,0,0,.35)` | `0 1px 2px rgba(15,27,45,.05), 0 8px 24px rgba(15,27,45,.06)` | bayangan kartu | |

Latar halaman tema gelap tetap memakai dua gradien radial halus (cyan kanan-atas, violet kiri-bawah).
Kartu tema gelap tetap gradien `rgba(20,34,56,.92) → rgba(11,20,35,.92)`; tema terang putih polos.

### 5.2 Warna turunan yang sekarang ditulis langsung

Di CSS lama nilai-nilai ini tersebar sebagai heksadesimal; v2 menamainya.

| Token | Gelap | Terang |
|---|---|---|
| `--side-bg` | gradien `#0b1424 → #080e1a` | `#ffffff` |
| `--nav-fg` | `#b6c4d4` | `#44546a` |
| `--kpi-label` | `#c4d2e0` | `#44546a` |
| `--heading` | `#dbe7f0` | `--fg` |
| `--th-fg` / `--th-bg` | `#9fb1c4` / `#0f1a2c` | `--muted` / `#f6f8fc` |
| `--code-fg` | `#c7d7e4` | `#44546a` |
| `--pre-bg` | `#08101d` | `#f6f8fc` |
| `--row-hover` | `rgba(45,212,191,.03)` | sama |
| `--badge-fg` / `--badge-bg` | `#fda4af` / `rgba(244,63,94,.12)` | `#be123c` / sama |
| `--title-grad` | `#2dd4bf → #a5f3fc → #e2e8f0` | `#0d9488 → #0891b2 → #1e3a8a` |
| `--kpi-grad` | `#2dd4bf → #67e8f9` | `#0d9488 → #0891b2` |
| `--tooltip-bg` | `rgba(8,16,29,.95)`, garis `rgba(45,212,191,.3)` | sama (tooltip gelap di kedua tema) |
| `--grid` | `rgba(148,163,184,.08)` | `rgba(15,27,45,.08)` |

### 5.3 Warna bermakna

| Makna | Token |
|---|---|
| 2xx / sukses / ada log | `--ok` |
| 3xx / netral | `--neutral` |
| 4xx / WARN / keparahan 2 | `--warn` |
| 5xx / ERROR / EXC / keparahan 3 | `--err` |
| Level INFO | `--accent`; PERFORMANCE `--ok`; DEBUG `--muted` |
| Titik server di peta | `--warn` |
| Titik lokasi dan busur | `--accent` |

### 5.4 Palet seri chart

| # | Gelap (lama) | Terang | Δ |
|--:|---|---|:-:|
| 1 | `#2dd4bf` | `#0d9488` | terang baru |
| 2 | `#8b5cf6` | `#7c3aed` | |
| 3 | `#22d3ee` | `#0891b2` | |
| 4 | `#f472b6` | `#db2777` | |
| 5 | `#f59e0b` | `#b45309` | |
| 6 | `#34d399` | `#059669` | |
| 7 | `#60a5fa` | `#2563eb` | |
| 8 | `#f43f5e` | `#e11d48` | |
| 9 | `#a3e635` | `#65a30d` | |
| 10 | `#fb923c` | `#ea580c` | |

Ungu batang "IP klien" `#8a5cd6` yang ditulis mati diganti `--violet`.

### 5.5 Tipografi, ukuran, bentuk

| Token | Nilai | Catatan |
|---|---|---|
| Huruf antarmuka | Outfit 400/500/600/700, lalu `system-ui` | **dibundel**, bukan dari Google Fonts (B09) |
| Huruf data | JetBrains Mono, lalu `ui-monospace` | lama menyebutnya tetapi tidak memuatnya; v2 membundel satu berat (400) |
| Teks dasar | 14 px / 1,5 | |
| Judul halaman | 38 px / 600 (28 px di layar sempit) | |
| Nilai KPI | 34 px / 600, angka tabular | |
| Judul kartu | 15,5 px / 500 | |
| Label KPI, navigasi | 13,5 px | |
| Sel tabel | 13 px; header 12 px / 600, jarak huruf .06em | |
| Teks kecil | 12 px (kode, waktu), 11,5 px (delta), 11 px (tag, pemilik IP) | **minimum 11 px** |
| Radius | kartu 20 · peta/blok/gulir 12 · pil 999 · batang 6 | |
| Jarak | grid kartu 18 · KPI 14 · padding kartu 20/22 · KPI 18/20 · sel 10 | |
| Tinggi | chart 280 · tabel maks. 440 (560–600 untuk tabel besar) | |
| Lebar | sidebar 236 · isi maks. 1560 · kartu min. 520 · KPI min. 170 | |
| Titik henti | 900 px (lama) dan 560 px (baru) | §8 |
| Fokus | garis 2 px `--accent` + jarak 2 px | baru, §9 |
| Gerak | transisi 150 ms; dimatikan bila `prefers-reduced-motion` | |

Kapitalisasi: teks antarmuka *Capitalize Each Word* lewat CSS, data tidak (lama). Pengecualian baru: kalimat
panjang (catatan, butir temuan, keterangan kosong) **tidak** dikapitalisasi; sekarang ikut terkapitalisasi
dan sulit dibaca ("Lokasi Adalah Perkiraan Tingkat Kota Dari Database…") (U13).

### 5.6 Mengapa ada token baru

Rasio kontras dihitung dari nilai lama (WCAG 2.1; teks kecil butuh ≥ 4,5, grafik dan batas kontrol ≥ 3):

| Pasangan lama | Rasio | Masalah | Perbaikan |
|---|--:|---|---|
| Terang: `--accent` `#0d9488` di putih | 3,74 | dipakai sebagai teks 13,5 px (nav aktif, pemilih folder) | `--accent-text` `#0f766e` = 5,47 |
| Terang: `--ok` `#059669` di putih | 3,77 | teks kecil hijau | `--ok-text` `#047857` = 5,48 |
| Terang: seri chart 1 `#2dd4bf` di putih | 1,86 | batang hampir tak terlihat | palet terang §5.4 (semua ≥ 3) |
| Terang: seri `#f59e0b` di putih | 2,15 | sama | `#b45309` = 5,02 |
| `--line` terhadap kartu | 1,2–1,3 | batas input tidak terlihat | `--line-strong` (gelap 3,6; terang 3,1) |
| `--land` terhadap `--card2` | 1,2–1,3 | daratan nyaris menyatu dengan laut | garis pantai `--coast` (gelap 3,7; terang 3,3) |

Yang sudah memenuhi dan tidak diubah: `--fg` (14,4 / 17,3), `--muted` (5,2 / 5,4), header tabel (7,9 / 5,1),
navigasi (10,4 / 7,7), `--err` dan `--warn` sebagai teks di kedua tema (≥ 4,7), palet gelap (≥ 4,1).

---

## 6. Perilaku

### 6.1 Pemilih folder

- Isi: semua folder, terbaru di atas. Label: `Folder log 6 Okt 2026`; di daftar terbuka ditambah keterangan
  kecil `log 5 Okt` dan tanda `kosong` / `rusak` bila folder itu praktis tanpa data (B05, B06).
- Bawaan: folder terbaru. **ASUMSI D1**: tetap `select` bawaan browser, bukan kalender; cukup untuk puluhan
  folder dan gratis aksesibilitasnya. Bila folder sudah ratusan, opsi dikelompokkan per bulan (`optgroup`).
- Ganti folder: tab tetap; isi berganti; posisi gulir kembali ke atas; daftar "Layanan" di sidebar dan
  lencana menyesuaikan; alamat diperbarui. Filter tabel dikosongkan; pilihan modul dipertahankan bila modul
  itu ada di folder baru.
- Panah ◀ ▶ di samping pemilih untuk folder sebelumnya/berikutnya (U14); berguna saat membandingkan hari
  berurutan. Pintasan `[` dan `]`.
- Di tab Tren: nonaktif (§3.3).

### 6.2 Pemilih modul (Peta IP)

- Isi: "Semua Modul" + modul tujuan yang ada di folder itu, urut abjad (lama).
- Ganti modul: KPI, peta, legenda, dan tabel alur berganti bersama; **posisi dan zoom peta dipertahankan**
  (sekarang peta dirender ulang; preset tetap tetapi zoom manual hilang).
- Pilihan tersimpan di alamat. Modul yang tidak ada di folder baru → kembali ke "Semua Modul" (lama).

### 6.3 Ganti bahasa

- Tombol ID / EN di header; berlaku seketika tanpa memuat ulang data; diingat per browser; bawaan ID.
- Yang diterjemahkan: semua teks antarmuka, kalimat temuan otomatis, label dan legenda chart, format angka
  (`1.234` / `1,234`), tanggal dan jam (`06.03` / `06:03`), satuan durasi (`dtk` / `s`), nama negara, nama
  bulan (`Okt` / `Oct`).
- Yang **tidak** diterjemahkan: data log (URL, pesan, UA, nama template), nama layanan, nama kota dan
  provinsi dari database lokasi, label provinsi/kabupaten di peta.
- Kategori serangan, tanda akun, metrik bisnis, dan kelompok umur JWT adalah **label**, jadi diterjemahkan
  (lama juga begitu).
- Perubahan U15: teks berasal dari kamus berkunci, bukan penggantian teks di DOM setelah render. Tidak
  terlihat pengguna, tetapi menghilangkan kedipan teks Indonesia sebelum berganti dan risiko data yang
  kebetulan sama dengan kunci kamus ikut "diterjemahkan".
- Atribut `lang` dokumen mengikuti pilihan.

### 6.4 Ganti tema

- Tombol ☀ / ☾; seketika; diingat per browser.
- Bawaan saat pertama dibuka: **gelap** (lama). **ASUMSI D2**: tidak mengikuti preferensi sistem, agar
  tampilan pertama sama dengan yang dikenal.
- Chart dan peta berganti warna tanpa mengambil data lagi dan tanpa kehilangan posisi peta.
- Tombol memakai `aria-pressed` dan label teks ("Tema terang", "Tema gelap"), bukan hanya ikon.

### 6.5 Memuat

Sistem lama tidak punya keadaan memuat (semua data sudah di halaman). v2 mengambil data per tab, jadi:

- **Kerangka langsung tampil**: sidebar, header, judul tab. Tidak pernah layar kosong.
- **Kerangka abu (skeleton)** seukuran isi akhirnya: baris KPI, kartu chart 280 px, tabel 6 baris. Tidak ada
  pemutar di tengah layar. Ukuran tetap supaya halaman tidak melompat ketika data tiba.
- Kerangka abu baru muncul bila data belum tiba dalam **200 ms**, agar perpindahan cepat tidak berkedip.
- **Satu permintaan per halaman** (TRD §5.3): seluruh kartu halaman tampil bersamaan ketika datanya tiba
  (U31). Yang dimuat terpisah hanya lanjutan tabel ("tampilkan berikutnya", filter, urut): saat itu hanya
  badan tabel tersebut yang meredup.
- Ganti folder di tab yang sama: isi lama tetap terlihat tetapi diredupkan (60 %) sampai yang baru tiba.
- Sidebar: selama daftar layanan folder baru belum tiba, daftar lama tetap tampil.
- `aria-busy` pada `<main>`; pembaca layar mendapat "Memuat …" lalu "Selesai" lewat wilayah `aria-live` sopan.

### 6.6 Kosong

Kosong selalu **menjelaskan sebabnya** dan, bila ada, apa yang bisa dilakukan. Teks lama dipertahankan.

| Halaman | Kondisi | Tampilan |
|---|---|---|
| Semua | Belum ada folder ter-ingest | Satu kartu di tengah: "Belum ada data." Untuk admin: tombol ke layar Ingest & impor; untuk user: "Hubungi admin." |
| Layar admin | **Tidak punya akses**: user biasa membuka alamat layar admin | Di `<main>`: "Tidak punya akses. Halaman ini hanya untuk admin." + tombol "Ke Overview". Sidebar dan header tetap |
| Semua | Folder terpilih praktis kosong atau rusak | Pita kuning di atas isi: "Folder ini hanya berisi N baris; M file rusak" + tautan ke tab Pod |
| Overview | Tanpa ingress nginx | KPI HTTP dan bagian "Traffic HTTP" tidak tampil (lama) |
| Peta IP | Tanpa ingress nginx | Catatan: "Peta butuh log ingress nginx; folder ini tidak memilikinya." |
| Peta IP | Data peta dasar atau database lokasi belum ada | Peta diganti catatan; KPI dan tabel alur tetap tampil, kolom Lokasi "Tidak diketahui" |
| Tren | Hanya satu folder | Chart tetap tampil; kolom perubahan kosong |
| Keamanan | Tanpa nginx | Catatan "deteksi serangan per URL tidak tersedia"; bagian login tetap |
| Keamanan | Tanpa temuan | Kotak "Temuan utama" tidak tampil (lama) |
| Akar Masalah | Tidak ada pola | Catatan "Tidak ada pola akar masalah yang terdeteksi untuk folder ini." |
| Ketersediaan | Tanpa nginx | Catatan "Analisis ketersediaan memakai log ingress nginx…" |
| Pod | — | Selalu ada isi selama ada file |
| Bisnis | Tanpa simpel-loop | KPI bernilai 0 (lama) + catatan baru "Log simpel-loop tidak ada di folder ini" |
| Pelacakan | Tanpa korelasi | Catatan "Pelacakan butuh log om-be-simpel-loop dan ingress nginx…" |
| Layanan | 0 baris | "Tidak ada log untuk layanan ini di tanggal ini (file kosong)." |
| Layanan | Hanya baris rusak | Sama + tag "Rusak" dan jumlah file rusak |
| Tabel mana pun | 0 baris | Satu baris `muted` "Tidak ada data" (lama) |
| Chart mana pun | 0 titik | Kartu tidak dirender (lama) |

Perubahan U16: angka 0 karena **log tidak ada** dibedakan dari 0 karena **memang tidak terjadi**. Yang
pertama tampil sebagai "–" dengan keterangan; sekarang keduanya "0" (contoh: tab Bisnis pada folder tanpa
simpel-loop). **ASUMSI D3**; ini mengubah tampilan beberapa KPI, bukan angkanya.

### 6.7 Gagal

Sistem lama tidak bisa gagal sebagian. v2 bisa:

| Kegagalan | Tampilan |
|---|---|
| Seluruh halaman gagal mengambil data | Di `<main>`: judul, penjelasan satu kalimat, **Coba lagi**; sidebar dan header tetap berfungsi |
| Lanjutan tabel gagal ("tampilkan berikutnya", filter, urut) | Baris pesan di bawah tabel itu + **Coba lagi**; baris yang sudah tampil tetap |
| **Sesi habis** (server menjawab "belum masuk" di tengah pemakaian) | Pindah ke layar Masuk dengan keterangan "Sesi Anda berakhir"; setelah masuk kembali ke alamat yang sama (tab, folder, modul) |
| Tindakan admin gagal (simpan user, ingest, impor) | Pesan di dalam dialog/kartu tindakan itu, menyebut sebab dan tindakan; isian tidak hilang |
| Server dashboard tidak terjangkau | Pita merah di atas: "Tidak tersambung ke server dashboard" + coba lagi otomatis tiap 5 detik (maks. 1 menit), lalu manual |
| Folder di alamat tidak ada | Pindah ke folder terbaru + pemberitahuan (§1.3) |
| Peta gagal dirender (WebGL tidak ada) | Peta diganti catatan; tabel alur tetap sebagai pengganti |

Pesan gagal ditulis untuk pengguna, bukan pengembang: tanpa kode galat mentah di teks utama; rincian teknis
di bawah "Detail" yang bisa dibuka. Pesan gagal memakai `role="alert"`.

### 6.8 Lain-lain

- Pindah tab: posisi gulir ke atas; fokus pindah ke judul halaman.
- Angka yang berubah tidak dianimasikan.
- Pembaruan data: tidak ada pembaruan otomatis (A7). Tombol kecil "Muat ulang" di header mengambil ulang
  tab aktif dan daftar folder; berguna setelah ingest folder baru.

### 6.9 Masuk, sesi, dan peran

- **Sebelum masuk** tidak ada data dashboard yang dimuat; hanya layar Masuk. Bahasa dan tema bisa diganti
  di layar itu dan terbawa setelah masuk.
- **Setelah masuk**: ke alamat yang tadi diminta, atau Overview folder terbaru. Bila sandi wajib diganti,
  layar Ganti sandi dulu.
- **Sesi** berakhir setelah 60 menit tanpa aktivitas atau 12 jam (TRD §8.2). Lima menit sebelum berakhir
  karena tidak aktif, pita kecil di atas: "Sesi berakhir dalam 5 menit" + "Tetap masuk". Sesi habis → §6.7.
- **Keluar**: langsung, tanpa konfirmasi; kembali ke layar Masuk; data di layar dibersihkan.
- **Peran**: user dan admin melihat dashboard yang sama. Bedanya hanya menu user (dua butir admin) dan dua
  layar admin. Tidak ada elemen yang "abu-abu karena tidak berhak" di halaman data.
- Perubahan peran atau penonaktifan oleh admin berlaku pada permintaan berikutnya: user yang dinonaktifkan
  diperlakukan seperti sesi habis.
- Pemberitahuan singkat ("User ditambahkan", "Sandi diganti") muncul di pojok selama 4 detik, memakai
  `role="status"`, dan tidak menutupi tombol.

---

## 7. Peta IP asal → IP tujuan (MapLibre)

### 7.1 Yang dipertahankan dari peta lama

Tema sama (laut `--card2`, daratan `--land`), titik bercincin aksen per lokasi, titik server oranye
berlabel "Server SIMPEL4 + IP", busur melengkung dari lokasi ke server dengan tebal 1–4 px menurut jumlah
request, preset **Indonesia** dan **Dunia**, tombol +/−, label negara → provinsi → kabupaten/kota yang
muncul bertahap, legenda, dan kalimat "N request dari luar Indonesia · M dari IP internal / tanpa lokasi".

### 7.2 Peta dasar: tanpa mengirim data pengguna

Syarat (PRD §5.4 butir 3): browser tidak boleh meminta apa pun ke domain luar. Peta ubin daring (OSM,
MapTiler, Carto) mengirim alamat IP pembuka dashboard dan koordinat yang dilihat ke pihak ketiga, jadi
**tidak dipakai**. Ada dua sumber yang memenuhi syarat:

| Pilihan | Isi | Ukuran | Lisensi | Penilaian |
|---|---|--:|---|---|
| **A. GeoJSON Natural Earth, dilayani dashboard sendiri** | daratan, batas negara, batas provinsi | ±2–4 MB | public domain | **Dipilih.** Sama dengan sumber peta lama; cukup untuk peta titik tingkat kota |
| B. Ubin vektor satu file (Protomaps/OSM) dilayani sendiri | jalan, kota, sungai, batas rinci | ratusan MB untuk Indonesia | ODbL, wajib atribusi OSM | Lebih rinci daripada akurasi data (lokasi IP hanya tingkat kota); ditunda |

**ASUMSI D4**: pilihan A. Gaya peta tidak memuat `sprite` maupun `glyphs` dari luar; huruf label dibundel
bersama aplikasi.

### 7.3 Lapisan

| Urutan | Lapisan | Sumber | Tampil pada |
|--:|---|---|---|
| 1 | Laut (latar) | — | selalu |
| 2 | Daratan | Natural Earth 50m land | selalu |
| 3 | Garis pantai | sama | selalu, 0,5 px `--coast` |
| 4 | Batas negara | Natural Earth 50m admin-0 boundary lines | selalu, 0,75 px `--coast` |
| 5 | Batas provinsi Indonesia | Natural Earth 10m admin-1, disaring Indonesia | zoom ≥ 4, garis putus 0,5 px |
| 6 | Busur lokasi → server | data alur | selalu, aksen 45 % |
| 7 | Kelompok titik | data alur | §7.5 |
| 8 | Titik lokasi | data alur | §7.5 |
| 9 | Titik server | konfigurasi | selalu, di atas semua titik |
| 10 | Label negara | Natural Earth | selalu; negara kecil mulai zoom ≥ 3 |
| 11 | Label provinsi | GeoNames | zoom ≥ 4 |
| 12 | Label kabupaten/kota | GeoNames | zoom ≥ 7 |
| 13 | Label lokasi IP | data alur | 6 terbesar selalu; lainnya saat tidak bertabrakan |

Catatan:

- **Garis batas baru**: peta lama hanya punya daratan tanpa batas apa pun. Batas negara dan provinsi
  ditambahkan karena diminta dan karena membantu membaca "titik ini di provinsi mana".
- **Batas kabupaten/kota tidak digambar**; hanya labelnya (seperti sekarang). Data batas kabupaten yang
  lisensinya bebas dan bisa dibundel belum dipastikan (pertanyaan Q3).
- Natural Earth mungkin belum memuat pemekaran provinsi Papua (2022), sedangkan label GeoNames sudah 38
  provinsi. Bila begitu, garis batas dan label di Papua tidak cocok (Q3).
- **Tabrakan label diatur mesin peta**: label yang bertumpuk disembunyikan menurut prioritas (lokasi IP >
  negara > provinsi > kabupaten). Di peta lama semua label digambar sehingga saling menimpa, terlihat jelas
  di tangkapan layar (Jawa dan Sulawesi tidak terbaca).
- Label negara: nama Indonesia atau Inggris mengikuti bahasa; huruf besar berjarak, seperti sekarang.
- Huruf label di dalam peta adalah **Noto Sans**, bukan Outfit: mesin peta butuh berkas huruf dalam format
  khusus yang ikut dibundel (TRD §6.4, T4). Label titik dan tooltip di atas peta tetap Outfit.

### 7.4 Proyeksi dan tampilan awal

- Proyeksi **Web Mercator** (bawaan MapLibre). Peta lama memakai derajat lurus (equirectangular), jadi
  bentuk di lintang tinggi berbeda; untuk Indonesia (dekat khatulistiwa) praktis sama (U17).
- Preset **Indonesia**: bujur 94–142, lintang −12–8 (sama dengan kotak lama). Preset **Dunia**: bujur
  −168–168, lintang −60–80. Preset memakai *fit bounds* sehingga menyesuaikan ukuran wadah.
- Zoom dibatasi: minimum = seluruh dunia terlihat; maksimum zoom 10 (± tingkat kota). Lebih dalam tidak
  ada isinya dan memberi kesan akurasi yang tidak dimiliki data.
- Peta tidak bisa dimiringkan atau diputar.
- Rasio wadah 2,4 : 1 pada layar lebar (lama); di layar sempit lihat §8.

### 7.5 Titik dan pengelompokan

Peta lama menggabungkan IP hanya bila koordinatnya **persis sama** (satu kota). Kota-kota berdekatan tetap
bertumpuk; di tampilan Indonesia, Jabodetabek dan Jawa menjadi gumpalan.

- **Titik lokasi** = satu kota (IP dengan koordinat sama), seperti lama. Ukuran tetap 14 px.
- **Kelompok**: titik lokasi yang berjarak < 40 px di layar digabung menjadi satu lingkaran berisi angka
  **jumlah request** (disingkat: `18,9 rb`). Diameter 24–44 px menurut jumlah request (skala akar).
  Warna aksen pekat, teks gelap. Pengelompokan dihitung ulang tiap zoom.
- Klik/ketuk kelompok → peta memperbesar sampai kelompok itu pecah.
- Zoom ≥ 8: pengelompokan mati; semua titik lokasi tampil.
- **Busur**: tetap satu per lokasi (bukan per kelompok), supaya gambaran "dari mana saja" tidak hilang saat
  titik dikelompokkan. Tebal 1–4 px menurut request lokasi itu; opasitas 45 %; lokasi kecil (< 1 % dari
  terbesar) 25 %.
- **Titik server** tidak pernah masuk kelompok; label selalu tampil, di kiri titik.
- Urutan gambar: lokasi terbesar paling atas (lama).

**ASUMSI D5**: angka di kelompok = request, bukan jumlah IP. Request adalah ukuran yang juga dipakai tebal
busur dan kolom tabel.

### 7.6 Zoom, geser, sentuh

| Masukan | Perilaku |
|---|---|
| Seret (mouse) | menggeser |
| Roda mouse | **Ctrl/⌘ + roda** memperbesar ke arah kursor. Roda saja menggulir halaman, dengan petunjuk singkat "Tahan Ctrl untuk memperbesar peta" |
| Klik ganda | memperbesar satu tingkat |
| Tombol + / − | memperbesar / memperkecil satu tingkat |
| Tombol ⤢ | kembali ke preset aktif |
| Cubit dua jari | memperbesar / memperkecil |
| Geser dua jari | menggeser peta |
| Geser satu jari | menggulir **halaman**, dengan petunjuk "Gunakan dua jari untuk menggeser peta" |
| Keyboard (peta terfokus) | panah menggeser; `+` `−` zoom; `0` kembali ke preset; `Esc` menutup tooltip |

Perubahan U18: di peta lama roda mouse langsung memperbesar dan satu jari langsung menggeser, sehingga
pengguna yang menggulir halaman **terjebak** di peta; di ponsel halaman tidak bisa digulir melewati peta
(`touch-action: none`). MapLibre menyediakan mode "gerakan kooperatif" untuk tepat masalah ini.

### 7.7 Tooltip

Muncul saat kursor di atas titik (mouse), saat titik diketuk (sentuh), atau saat titik terfokus (keyboard).

```
┌───────────────────────────────────────┐
│ Pagatan, Kalimantan Selatan, Indonesia│
│ 1 IP asal · 6.425 request             │
│ → om-be-simpel-loop (5.277)           │
│   om-fe-inhouse (1.148)               │
│ [Lihat di tabel]                      │
└───────────────────────────────────────┘
```

- Isi sama dengan tooltip lama (`title`), ditambah tombol **Lihat di tabel** yang mengisi filter tabel alur
  dengan nama kota itu dan menggulir ke tabel.
- Kelompok: "N lokasi · N IP asal · N request" + tiga lokasi terbesar + "Klik untuk memperbesar".
- Server: "Server tujuan `<ip>` · Jakarta, ID".
- Tooltip lama memakai atribut `title`: muncul lambat, tidak bisa di layar sentuh, tidak terbaca di tema
  gelap sistem. Diganti kotak bergaya tooltip chart (U19).
- Hanya satu tooltip terbuka; tertutup saat peta digeser, `Esc`, atau ketuk di luar.

### 7.8 Atribusi

Kontrol atribusi di pojok kanan bawah **setiap** peta, selalu terlihat (tidak dilipat):
"Data GeoLite2 oleh MaxMind · GeoNames · Natural Earth", dua yang pertama bertaut ke situsnya (B08, F22).
Sumber lokasi IP diganti dari DB-IP ke MaxMind GeoLite2 atas keputusan pemilik (TRD §3.6); catatan di
bawah tabel alur menyebut MaxMind, bukan DB-IP.
Tautan dibuka di tab baru dengan `rel="noreferrer"`. Catatan panjang di bawah tabel alur dipertahankan.

### 7.9 Pengganti peta

Peta bukan satu-satunya jalan ke informasinya: tabel "Alur IP asal → IP tujuan" memuat data yang sama dan
selalu ada di bawahnya. Peta diberi `role="application"` dengan label "Peta asal request; data yang sama ada
di tabel di bawah", dan tautan lompat "Lewati peta".

---

## 8. Layar sempit

Titik henti: **900 px** (lama) dan **560 px** (baru, ponsel).

**Diputuskan pemilik: tampilan ponsel dikerjakan serius.** Seluruh bagian ini wajib, termasuk tabel lebar
menjadi kartu baris, dan diperiksa di ponsel sungguhan (bukan hanya emulasi) pada lebar 360–390 px.

### 8.1 Masalah yang terlihat di tangkapan layar 390 px

1. Baris alat header meluber: tombol tema terpotong di tepi kanan.
2. Peta tingginya ±130 px; label saling menimpa sampai tidak terbaca.
3. Tabel alur 5 kolom terpotong; kolom ke-3 dst. hanya terlihat bila digulir, tanpa petunjuk.
4. Navigasi mendatar menampilkan 4 dari 16 butir tanpa tanda bahwa bisa digulir; tab layanan praktis
   tersembunyi.
5. Subjudul dan teks WIB memakan tiga baris sebelum isi.

### 8.2 Tata letak ≤ 900 px

```
┌──────────────────────────────────────┐
│ [☰] SIMPEL4 Log      [Folder ▾] [⋯] │  ← bar atas lekat, 52px
├──────────────────────────────────────┤
│ Peta IP                              │
│ Folder 6 Okt · log 5 Okt 09.00–00.59 │
│ [Semua Modul ▾]                      │
│ [KPI] [KPI]                          │  ← 2 kolom
│ [KPI] [KPI]                          │
│ ┌ peta, rasio 4:3, min. 300px ─────┐ │
│ └──────────────────────────────────┘ │
│ ┌ tabel → kartu baris (≤560px) ────┐ │
└──────────────────────────────────────┘
```

- **Navigasi**: tombol ☰ membuka laci dari kiri berisi sidebar lengkap (dua grup, lencana). Menggantikan
  pita gulir mendatar (U20). Laci menutup setelah memilih, dengan `Esc`, atau ketuk di luar; fokus terkunci
  di dalam selama terbuka.
- **Bar atas**: pemilih folder tetap terlihat; bahasa, tema, muat ulang, dan isi menu user (nama, ganti
  sandi, butir admin, keluar) masuk menu `⋯`.
- **Layar Masuk dan dialog** (tambah user, konfirmasi): selebar layar; kolom isian tinggi ≥ 44 px dan huruf
  ≥ 16 px agar ponsel tidak memperbesar halaman saat kolom disentuh; papan ketik tidak menutupi tombol kirim.
- **KPI**: 2 kolom (≥ 360 px), 1 kolom di bawahnya. Nilai 28 px.
- **Grid kartu**: 1 kolom. Chart tetap 280 px; label sumbu waktu dikurangi otomatis.
- **Chart batang horizontal**: label dipotong 28 karakter (bukan 48).
- **Peta**: rasio 4 : 3, tinggi minimum 300 px; tombol layar penuh ⤢ membuka peta setinggi layar. Tombol
  +/− berukuran 44 px.
- **Tabel ≤ 4 kolom**: tetap tabel; kolom pertama membungkus.
- **Tabel > 4 kolom pada ≤ 560 px**: tiap baris menjadi **kartu** bertumpuk: kolom pertama sebagai judul,
  kolom lain sebagai pasangan "label: nilai". Berlaku untuk: alur IP, endpoint serangan, IP sumber serangan,
  analisis akun, login gagal, jejak request, insiden, error koneksi, kinerja endpoint, kesehatan pod,
  sebaran traffic pod, daftar user, riwayat impor, catatan audit.
- **Tabel > 4 kolom pada 561–900 px**: gulir mendatar di dalam kartu, kolom pertama terkunci, bayangan di
  tepi kanan sebagai tanda masih ada isi.
- **Tabel Tren** (kolom = folder): selalu gulir mendatar dengan kolom "Layanan" terkunci.
- Target sentuh minimum **44 × 44 px** untuk tombol, butir navigasi, dan kontrol peta.
- Tidak ada gulir mendatar pada tingkat halaman di lebar ≥ 320 px.

---

## 9. Dasar aksesibilitas

Target: WCAG 2.1 tingkat AA untuk hal-hal di bawah. Bukan audit penuh.

### 9.1 Kontras

- Teks ≥ 4,5 : 1; teks besar (≥ 24 px, atau ≥ 18,7 px tebal) dan elemen grafik ≥ 3 : 1. Nilai token di §5
  sudah dihitung; yang gagal sudah diganti (§5.6).
- Teks `muted` hanya di atas `--card`, `--bg`, `--bg2`; tidak di atas warna.
- Navigasi grup ("ANALISIS") sekarang `muted` dengan opasitas 70 % (≈ 3,0–3,4 : 1): opasitas dihapus.
- Angka KPI bergradien: ujung gradien paling terang pun ≥ 3 : 1 terhadap kartu (teks besar).

### 9.2 Tidak bergantung warna

- Status HTTP selalu menampilkan kodenya; tag bahaya selalu menampilkan nama kategori; ▲/▼ selalu disertai
  persen dan kata; "Rusak"/"Kosong" berupa teks.
- Chart bertumpuk multi-seri: legenda bisa diklik untuk menyembunyikan seri; tooltip menyebut nama seri.
- Batang sukses/gagal (PDF, Uptime-Kuma) dibedakan juga oleh urutan tetap (sukses dulu) dan label tooltip.

### 9.3 Keyboard

- Urutan tab: tautan "Lewati ke isi" → navigasi → header (folder, bahasa, tema) → isi.
- Semua kontrol bisa dicapai dan dijalankan dengan keyboard: butir navigasi, pemilih, grup tombol, filter,
  header tabel yang bisa diurut, baris pesan yang bisa dibuka, tombol "Tampilkan berikutnya", legenda chart,
  kontrol peta.
- **Fokus selalu terlihat**: garis 2 px `--accent` (terang: `--accent-text`) berjarak 2 px. CSS lama
  menghapus `outline` pada input dan menggantinya bayangan tipis; tombol navigasi tidak punya gaya fokus (U21).
- Pintasan: `[` `]` folder sebelumnya/berikutnya; `/` fokus ke filter pertama di halaman; `g` lalu huruf
  awal tab tidak dipakai (hindari bentrok dengan pembaca layar). Pintasan tidak aktif saat mengetik di input.
- Tidak ada jebakan fokus; laci navigasi dan tooltip peta menutup dengan `Esc`.

### 9.4 Struktur dan pembaca layar

- Tengara: `<nav>` (sidebar), `<header>`, `<main>`. Satu `<h1>` per halaman (judul tab); judul kartu `<h2>`.
  Sekarang judul kartu `<h3>` tanpa `<h2>`.
- Tab aktif: `aria-current="page"`. Lencana punya teks tersembunyi: "14 IP sumber serangan", "125 error".
- Tabel: `<th scope="col">`, `<caption>` tersembunyi = judul kartu; header yang bisa diurut memakai
  `aria-sort`.
- Filter: `<label>` tersembunyi "Filter tabel <judul>"; jumlah hasil diumumkan lewat `aria-live`.
- Baris pesan yang bisa dibuka: `<details>/<summary>` (lama, sudah benar).
- Chart: alternatif teks (§4.2). Peta: §7.9.
- Ikon saja (☀ ☾ + − ⤢ ☰ ⋯ ×) selalu punya nama aksesibel.
- Bahasa dokumen mengikuti pilihan; data berbahasa lain tidak ditandai (terlalu banyak, manfaat kecil).

### 9.5 Lain-lain

- Teks bisa diperbesar sampai 200 % tanpa kehilangan isi; ukuran memakai `rem`.
- `prefers-reduced-motion`: transisi, animasi chart, dan gerak terbang peta dimatikan.
- Tooltip yang muncul saat hover juga muncul saat fokus, bisa ditutup `Esc`, dan tidak hilang saat kursor
  pindah ke atasnya.
- Tidak ada isi yang berkedip atau bergerak sendiri.

---

## 10. Yang berubah dari tampilan lama

Semua yang tidak disebut di sini **sama dengan tampilan lama**.

| # | Perubahan | Alasan | Sifat |
|--:|---|---|---|
| U1 | Alamat menyimpan folder dan modul, bukan hanya tab | Tautan bisa dibagikan; tombol kembali berfungsi | tambahan |
| U2 | Subjudul memuat rentang waktu log sebenarnya | Nama folder bukan tanggal isinya (B06) | tambahan |
| U3 | Bar pemilih folder menempel saat digulir | Halaman panjang; folder sering diganti | tata letak |
| U4 | Tren: pemilih rentang; tabel gulir mendatar; pemilih folder nonaktif | 365 folder tidak muat; pemilih folder memang tidak berpengaruh di sini | tambahan |
| U5 | Baris KPI seimbang (mis. 4 + 4), tanpa baris yatim | Keterbacaan | tata letak |
| U6 | Peta di halaman layanan terlipat secara bawaan | Elemen terberat; duplikat tab Peta IP; mendorong chart utama ke bawah | perilaku |
| U7 | Tidak ada tanda "berbeda dari sistem lama" di antarmuka | Selisih dicatat di laporan kesetaraan | keputusan |
| U8 | Keterangan `(i)` pada KPI yang definisinya tidak jelas | Beberapa definisi mengejutkan (inv. §8 butir 7, 9) | tambahan |
| U9 | Chart punya alternatif teks dan "Lihat sebagai tabel" | Aksesibilitas; data chart bisa disalin | tambahan |
| U10 | Sumbu waktu tanpa pengulangan tanggal | Label miring dan berulang sulit dibaca | tampilan |
| U11 | Tabel bisa diurut; "Menampilkan N dari M" + muat berikutnya; filter mencari seluruh data | B04 | tambahan |
| U12 | Tombol salin pada IP dan baris log | Pekerjaan paling sering setelah menemukan IP | tambahan |
| U13 | Kalimat panjang tidak lagi *Capitalize Each Word* | Sulit dibaca | tampilan |
| U14 | Panah ◀ ▶ dan pintasan untuk folder sebelum/berikut | Membandingkan hari berurutan | tambahan |
| U15 | Terjemahan dari kamus berkunci, bukan penggantian teks di DOM | Tanpa kedipan; data tidak ikut diterjemahkan | internal |
| U16 | "–" untuk angka yang tidak ada karena log tidak ada | 0 yang menyesatkan (ASUMSI D3) | tampilan |
| U17 | Proyeksi peta Web Mercator | Bawaan MapLibre | tak terhindarkan |
| U18 | Zoom peta dengan Ctrl + roda; geser dengan dua jari | Peta lama menjebak gulir halaman, terutama di ponsel | perilaku |
| U19 | Tooltip peta berupa kotak, bukan atribut `title` | Tidak berfungsi di layar sentuh | perbaikan |
| U20 | Layar sempit: navigasi laci; tabel lebar jadi kartu baris; peta 4 : 3 | §8.1 | tata letak |
| U21 | Gaya fokus terlihat; struktur judul dan tengara | Aksesibilitas | perbaikan |
| U22 | Peta: garis pantai, batas negara dan provinsi; tabrakan label diatur; titik berdekatan dikelompokkan | Diminta; label dan titik bertumpuk di peta lama | perbaikan |
| U23 | Atribusi di setiap peta | B08 | kepatuhan |
| U24 | Keadaan memuat dan gagal per halaman (dan per lanjutan tabel) | Data kini diambil per halaman | tak terhindarkan |
| U25 | Token warna baru untuk teks aksen, batas kontrol, garis pantai, palet chart terang | Kontras (§5.6) | perbaikan |
| U26 | Huruf dan pustaka dibundel; JetBrains Mono benar-benar dimuat | B09 | internal |
| U27 | Label dan tanda baru: "File rusak", "Pod dengan retry", "Refresh token kedaluwarsa" | B05, B10, B07 | tambahan |
| U28 | Layar Masuk dan Ganti sandi; menu user di header; peringatan sesi | Dashboard dibuka banyak komputer (keputusan pemilik) | baru |
| U29 | Layar admin: Kelola user, Ingest & impor (termasuk impor S3 dan catatan audit) | Keputusan pemilik | baru |
| U30 | Tabel alur IP menampilkan 100 baris pertama, bukan 3.000 | Kini bisa dilanjutkan dan difilter di seluruh data; 3.000 baris adalah beban render terbesar | perilaku |
| U31 | Kartu satu halaman tampil bersamaan, bukan satu per satu | Satu permintaan per halaman (TRD) | perilaku |
| U32 | Angka dan chart yang berubah karena perbaikan definisi: chart error per jam nginx/frontend memuat baris error log; donat level simpel-loop memakai tingkat efektif; "lambat ≥ 5 dtk" memuat 3xx | Keputusan pemilik (TRD §4.4); diberi keterangan `(i)` | perbaikan |

Tidak berubah meski sempat dipertimbangkan: urutan dan nama tab; warna dan gaya kartu; jenis chart tiap
kartu; isi kolom tabel; batas top-N tampilan awal; teks temuan otomatis; tema bawaan gelap; bahasa bawaan ID.

---

## 11. Asumsi dan pertanyaan terbuka

### 11.1 ASUMSI desain

| # | ASUMSI | Bila salah |
|--:|---|---|
| D1 | Pemilih folder tetap `select` (dikelompokkan per bulan bila banyak), bukan kalender | Ganti komponen; halaman lain tidak terpengaruh |
| D2 | Tema bawaan gelap, tidak mengikuti preferensi sistem | Satu baris logika |
| D3 | "–" menggantikan 0 bila lognya tidak ada | Kembalikan ke 0 |
| D4 | Peta dasar = GeoJSON Natural Earth yang dilayani sendiri (tanpa ubin) | Pilihan B di §7.2; komponen peta sama |
| D5 | Angka kelompok titik = jumlah request | Ganti ke jumlah IP |
| D6 | Semua perubahan U1–U27 boleh masuk sebelum uji kesetaraan karena tidak mengubah **angka** | Tunda yang "tambahan" sampai setelah serah terima (PRD R9) |
| D7 | **[Gugur sebagian]** Per folder kini keputusan. "Hanya lokal tanpa login" gugur: ada login dua peran (§3.11, §6.9). Tanpa internet/tanpa domain luar (A4) tetap asumsi | — |

### 11.2 Pertanyaan untuk pemilik produk

| # | Pertanyaan | Asumsi sementara |
|--:|---|---|
| Q1 | ~~Seberapa serius tampilan ponsel?~~ **Terjawab: serius.** §8 wajib seluruhnya | — |
| Q2 | ~~Perlu login?~~ **Terjawab: ya**, dua peran, akun lokal. Layarnya di §3.11 | — |
| Q3 | Batas wilayah: cukup negara + provinsi dari Natural Earth? Bolehkah garis provinsi Papua belum memuat pemekaran 2022? Perlukah batas kabupaten/kota (butuh sumber data berlisensi jelas)? | Negara + provinsi; kabupaten hanya label |
| Q4 | Tren: rentang bawaan 30 folder terakhir sudah sesuai? | 30 |
| Q5 | Peta di halaman layanan: setuju terlipat secara bawaan (U6), atau justru dihapus dari sana? | Terlipat |
| Q6 | "–" vs 0 (U16): setuju? Ini satu-satunya perubahan yang mengubah apa yang tertulis di KPI. | Ya |
| Q7 | Perubahan "tambahan" di §10 (urut tabel, salin, pintasan, `(i)`): dikerjakan dalam migrasi, atau setelah kesetaraan terbukti? | Dalam migrasi, setelah P0 |
| Q8 | Adakah identitas visual Ombudsman RI (logo, warna resmi) yang harus dipakai? Sekarang logonya kotak "S4". | Tetap "S4" |

---

## 12. Permintaan 2026-10-06: gaya referensi dan Command Center (belum diterapkan)

Pemilik mengirim gambar referensi (dashboard gelap bergaya "Fleet Overview") dan meminta modul **Command Center**
realtime. Yang terlihat di referensi dan dampaknya ke dokumen ini:

| Unsur referensi | Bandingkan dengan v2 sekarang | Usulan |
|---|---|---|
| Latar navy gelap, aksen teal, kartu bersudut besar, garis tipis | Sudah sama arah (token §5) | Pertahankan token; kontras §5.6 tetap berlaku |
| Sidebar bergrup dengan **ikon** per butir, logo kiri atas, kartu aksi di kaki | Sidebar tanpa ikon, titik penanda | Tambah ikon garis (SVG dibundel, tanpa CDN) |
| Bar judul berisi **baris status ringkas** (`37/40 healthy · 2 failing …`) | Subjudul folder + rentang waktu | Baris status ringkas di bawah judul halaman |
| KPI ringkas dengan ikon, angka besar + badge perubahan, menu `⋯` | KPI tanpa ikon | Ikon + badge perubahan berwarna (tetap disertai teks, §9.2) |
| Kartu **"What needs your attention"** bernomor dengan tautan aksi | "Temuan utama" berupa daftar | Kartu perhatian bernomor; tiap butir menaut ke halaman/tabel terkait |
| Tabel status ringkas + pil status (Healthy / Stuck / Cost spike) | Tag keparahan §4.5 | Pil status memakai tag §4.5 |
| Penanda **"streaming · last event 2s ago"** dan tombol **Live** | Tidak ada pembaruan otomatis (A7, §6.8) | Hanya di Command Center, setelah aliran Kafka ada (TRD §12) |

Ini menyimpang dari prinsip "tampilan lama dipertahankan" di awal dokumen, jadi butuh persetujuan pemilik (TRD R6).
**ASUMSI**: gaya baru diterapkan pada token dan komponen bersama (satu tahap, sebelum halaman data dibangun ulang),
susunan dan isi tiap halaman tetap menurut §3; Command Center menjadi halaman ke-11, paling atas di grup Analisis.

