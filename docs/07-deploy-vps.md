# Deploy MoniShield ke VPS baru sampai bisa dibuka lewat domain

Alur: **DNS → siapkan VPS (pengguna, firewall, Docker) → ambil kode → isi `.env` → build + jalankan profil `https`
(sertifikat Let's Encrypt otomatis) → masuk → atur sumber data (S3 / Kafka)**. Perkiraan waktu: 30–60 menit.

Semua perintah di bawah dijalankan di VPS kecuali disebut lain. Ganti `monishield.domainanda.id`, `IP_VPS`, dan
`admin@domainanda.id` dengan milik Anda.

---

## 0. Yang dibutuhkan

| Kebutuhan | Minimal | Catatan |
|---|---|---|
| VPS | Ubuntu 24.04 LTS (atau 22.04), 2 vCPU, **4 GB RAM**, 40 GB SSD | +2 GB RAM bila memakai Kafka di VPS yang sama (profil `kafka`) |
| Domain | satu (sub)domain, mis. `monishield.domainanda.id` | akses ke pengaturan DNS-nya |
| Akses GitHub | repo `apisdsn/dashboard-logging` | repo privat: token GitHub (fine-grained, *Contents: read*) atau deploy key |
| Port terbuka dari internet | 22 (SSH), 80, 443 | 80 wajib untuk verifikasi Let's Encrypt + pengalihan ke https |
| Akses keluar VPS | internet | unduh image/paket saat build, data rujukan peta & IP (lihat `06-docker.md` §7) |

---

## 1. Arahkan domain ke VPS

Di panel DNS domain Anda buat record:

| Tipe | Nama | Nilai | TTL |
|---|---|---|---|
| `A` | `monishield` | `IP_VPS` | 300 |
| `AAAA` (bila VPS punya IPv6) | `monishield` | IPv6 VPS | 300 |

Cek dari komputer Anda (boleh menunggu beberapa menit):

```sh
dig +short monishield.domainanda.id      # harus menampilkan IP_VPS
```

> **Cloudflare**: saat pertama kali, set record ke **DNS only** (awan abu-abu) agar Let's Encrypt bisa memverifikasi.
> Bila ingin memakai proxy Cloudflare (awan oranye) sesudahnya, set SSL/TLS ke **Full (strict)**.

---

## 2. Siapkan VPS (sekali)

Masuk sebagai root (atau pengguna sudo dari penyedia VPS):

```sh
ssh root@IP_VPS

# pengguna khusus + kunci SSH yang sama
adduser monishield
usermod -aG sudo monishield
rsync --archive --chown=monishield:monishield ~/.ssh /home/monishield

# pembaruan + alat
apt update && apt -y upgrade
apt -y install git curl ufw fail2ban unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades        # pembaruan keamanan otomatis: pilih "Yes"

# firewall: hanya SSH, http, https
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw enable

# RAM 4 GB: tambah swap 2 GB agar build dan ingest pertama tidak kehabisan memori
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Keluar, lalu masuk lagi sebagai pengguna baru: `ssh monishield@IP_VPS`.
(Opsional, disarankan: matikan login root & sandi SSH — `PermitRootLogin no`, `PasswordAuthentication no` di
`/etc/ssh/sshd_config`, lalu `sudo systemctl restart ssh`. Pastikan login dengan kunci sudah berhasil dulu.)

---

## 3. Pasang Docker

```sh
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker monishield
newgrp docker                                   # atau keluar-masuk SSH
docker version && docker compose version       # Docker 24+ dan Compose v2
```

> **Penting — Docker melewati ufw** untuk port yang dipublikasikan container. Compose MoniShield sengaja hanya
> mempublikasikan 80/443 (proxy https) ke internet; app, pgAdmin, DbGate, dan Kafka terikat ke `127.0.0.1`.
> Jangan mengubah ikatan itu ke `0.0.0.0` tanpa aturan `DOCKER-USER` (lihat §9).

---

## 4. Ambil kode

```sh
sudo mkdir -p /srv && sudo chown monishield: /srv
cd /srv
git clone https://github.com/apisdsn/dashboard-logging.git      # repo privat: username GitHub + token sebagai sandi
cd dashboard-logging
git checkout claude/magical-euler-hkpo4j                         # atau "main" setelah perubahan digabung
cd v2
```

Repo ini juga berisi folder log lama (`2026-09-26/` …) di akar repo; folder itu bisa langsung dipakai sebagai folder
log awal (`DOCKER_LOG_DIR=/srv/dashboard-logging`, langkah 5). Bila ingin folder log terpisah:
`sudo mkdir -p /srv/logs && sudo chown monishield: /srv/logs`.

---

## 5. Isi `.env`

```sh
cp .env.example .env
# tiga rahasia acak (jalankan 3 kali, salin masing-masing)
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
nano .env
```

Isi minimal (cari barisnya di `.env.example`; baris berawalan `#` dihapus `#`-nya):

```sh
DOCKER_LOG_DIR=/srv/dashboard-logging          # folder log di host (dipasang hanya-baca)
POSTGRES_PASSWORD=<rahasia acak 1>
S4_JWT_SECRET=<rahasia acak 2>
S4_JOB_TOKEN=<rahasia acak 3>
S4_ADMIN_USER=admin
S4_ADMIN_PASSWORD=<sandi admin pertama, min. 12 karakter>
S4_COOKIE_SECURE=true                          # wajib true di https
DOCKER_DOMAIN=monishield.domainanda.id
DOCKER_ACME_EMAIL=admin@domainanda.id          # pemberitahuan Let's Encrypt
```

Opsional sekarang (bisa juga nanti dari layar **Konfigurasi**): `MAXMIND_ACCOUNT_ID`/`MAXMIND_LICENSE_KEY` (lokasi IP
di peta), `S4_IMPORT_BUCKETS` + kunci AWS (impor S3), `S4_KAFKA_*` (log dari Rancher), notifikasi.
`S4_IMPORT_BUCKETS` hanya bisa diisi di `.env`.

Izinkan container (uid/gid 10001) membaca **dan menulis** `.env` (layar Konfigurasi menyimpan ke sana):

```sh
sudo chgrp 10001 .env && chmod 660 .env
```

---

## 6. Build dan jalankan

```sh
docker compose build                           # ±3–6 menit pertama kali
docker compose --profile https up -d           # app + PostgreSQL + Caddy (https otomatis)
docker compose ps                              # app "healthy", https "running"
docker compose logs -f https                   # tunggu "certificate obtained successfully", lalu Ctrl+C
```

Saat mulai pertama app meng-ingest semua folder di `DOCKER_LOG_DIR` dan mengunduh data rujukan peta/IP; lihat
kemajuannya dengan `docker compose logs -f app`. Docker menyalakan ulang semua layanan sendiri setelah VPS reboot
(`restart: unless-stopped`).

> Docker Hub membatasi unduhan anonim. Bila build/up gagal `429 Too Many Requests`: `docker login` (akun gratis),
> lalu ulangi.

---

## 7. Cek dari internet

```sh
curl -I http://monishield.domainanda.id        # 308 -> https://…
curl -s https://monishield.domainanda.id/api/health    # {"ok":true}
```

Buka `https://monishield.domainanda.id` → masuk `admin` + `S4_ADMIN_PASSWORD` → ganti sandi saat diminta.

---

## 8. Setelah masuk pertama kali

1. **Menu user → Konfigurasi** (semua disimpan ke `.env`, langsung berlaku):
   - **AWS S3** + **Folder S3 otomatis** (mis. `s3://simpel4-backup/k8s-logs`) → *Uji koneksi*.
   - **Kafka** (bila log realtime dari Rancher; §9) → *Cek pesan di topic*.
   - **MaxMind GeoLite2** → *Uji koneksi*.
   - **Notifikasi**: alamat dashboard = `https://monishield.domainanda.id`; Telegram/Discord/email → *Kirim uji*.
2. **Menu user → Kelola user**: buat akun untuk anggota tim (peran *user* = hanya melihat).
3. **Ingest & impor**: periksa status ingest, kartu S3 dan Kafka.

---

## 9. (Opsional) Log realtime dari Rancher lewat Kafka

**A. Kafka kantor sudah ada (disarankan, ber-SASL/TLS)**: isi broker, topic, keamanan, nama pengguna & sandi di
**Konfigurasi → Kafka**. VPS hanya perlu bisa menghubungi broker itu (keluar).

**B. Kafka di VPS ini** (profil `kafka`). Tambahkan ke `.env`:

```sh
DOCKER_KAFKA_HOST=IP_VPS                       # alamat yang diisi di Rancher
DOCKER_KAFKA_BIND=0.0.0.0
DOCKER_KAFKA_PORT=9094
S4_KAFKA_BROKERS=kafka:9092
S4_KAFKA_TOPIC=k8s-logs
```

```sh
docker compose --profile https --profile kafka up -d
```

Listener ini **tanpa sandi dan tanpa enkripsi** — log berisi alamat IP pengguna. Batasi port 9094 hanya untuk IP keluar
node cluster (ufw tidak berlaku untuk port Docker, jadi pakai rantai `DOCKER-USER`):

```sh
IP_CLUSTER=203.0.113.10                         # IP publik keluar node Rancher (tanya admin jaringan)
sudo iptables -I DOCKER-USER -p tcp -m conntrack --ctorigdstport 9094 -j DROP
sudo iptables -I DOCKER-USER -p tcp -m conntrack --ctorigdstport 9094 -s $IP_CLUSTER -j ACCEPT
sudo apt -y install iptables-persistent && sudo netfilter-persistent save
```

Lebih aman lagi: hubungkan cluster dan VPS lewat VPN (mis. WireGuard) dan isi `DOCKER_KAFKA_HOST` dengan alamat VPN.

Di **Rancher → Cluster → Tools → Logging → Kafka**: Endpoint Type **Broker**, Endpoint `IP_VPS:9094`, Topic
`k8s-logs`, Flush Interval **5–10** detik, **Enable JSON Parsing tidak dicentang** → Save. Dalam beberapa detik kartu
**Log dari Kafka** di layar Ingest & impor menunjukkan pesan masuk; peta menampilkan lencana **LANGSUNG**.

---

## 10. Cadangan

```sh
mkdir -p /srv/backup
# akun, sesi, audit, riwayat (wajib): tiap malam pukul 01.30
( crontab -l 2>/dev/null; echo '30 1 * * * cd /srv/dashboard-logging/v2 && docker compose exec -T postgres pg_dump -U monishield monishield | gzip > /srv/backup/pg-$(date +\%F).sql.gz && find /srv/backup -name "pg-*.sql.gz" -mtime +14 -delete' ) | crontab -
cp /srv/dashboard-logging/v2/.env /srv/backup/env-$(date +%F)    # setelah mengubah konfigurasi (berisi rahasia: simpan aman)
```

Log mentah hasil impor S3/Kafka ada di volume `monishield_s4-inbox`; basis data DuckDB (`s4-data`) bisa dibangun ulang
dari log. Rincian: `06-docker.md` §8.

---

## 11. Pembaruan aplikasi

```sh
cd /srv/dashboard-logging && git pull
cd v2 && docker compose build && docker compose --profile https up -d     # tambahkan --profile kafka bila dipakai
```

Data, akun, dan sertifikat tetap (ada di volume).

---

## 12. Masalah umum

| Gejala | Penyebab / tindakan |
|---|---|
| `https` gagal mendapat sertifikat (`docker compose logs https`) | DNS belum mengarah ke VPS (`dig`), port 80/443 tertutup di firewall penyedia VPS, atau proxy Cloudflare oranye saat pertama. Perbaiki lalu `docker compose restart https`. Jangan mengulang terlalu sering (batas Let's Encrypt). |
| Container `https` langsung berhenti: "isi DOCKER_DOMAIN dan DOCKER_ACME_EMAIL" | Dua baris itu belum diisi di `.env`. |
| Halaman 502 | app belum sehat: `docker compose ps`, `docker compose logs app` (ingest pertama bisa beberapa menit). |
| Masuk berhasil tapi langsung keluar lagi | `S4_COOKIE_SECURE` harus `true` di https dan alamat dibuka lewat `https://`. |
| Layar Konfigurasi: "file .env tidak bisa ditulis" | `sudo chgrp 10001 .env && chmod 660 .env` di folder `v2`. |
| Peta tanpa lokasi | MaxMind belum diisi (Konfigurasi → MaxMind) atau VPS tidak bisa keluar ke `download.maxmind.com`. |
| Membuka pgAdmin / DbGate | hanya dari VPS: dari komputer Anda `ssh -L 5050:127.0.0.1:5050 -L 5051:127.0.0.1:5051 monishield@IP_VPS`, lalu `docker compose --profile pgadmin --profile dbgate up -d` dan buka `http://localhost:5050` / `:5051`. |

---

*Diverifikasi 2026-10-07 di lingkungan pengembang (Docker 29.8.2): profil `https` dengan Caddy 2.10.2 — http → https
(308), HSTS, login dengan cookie `Secure; HttpOnly` lewat https; sertifikat Let's Encrypt sungguhan tidak bisa diuji di
sana (butuh domain publik), jadi langkah 6–7 adalah pemeriksaan pertama di VPS Anda.*
