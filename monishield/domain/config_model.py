"""Model konfigurasi MoniShield (TRD §6.3): semua setelan beserta nilai bawaannya. Murni data; MEMBACA dari
lingkungan / .env / config.toml dilakukan pemuat di monishield/infrastructure/config.py.

Setiap kolom bisa diatur lewat lingkungan/.env sebagai S4_<NAMA> (daftar dan kamus ditulis sebagai JSON). Pengecualian
nama: kredensial pihak lain memakai nama standarnya (MAXMIND_*, AWS_*, TELEGRAM_BOT_TOKEN, …). Rahasia tidak pernah dicetak.
"""
import dataclasses, os

from monishield.domain import rules

# rahasia -> nama variabel lingkungannya
SECRETS = {'admin_password': 'S4_ADMIN_PASSWORD', 'job_token': 'S4_JOB_TOKEN', 'jwt_secret': 'S4_JWT_SECRET',
           'auth_database_url': 'S4_AUTH_DATABASE_URL',   # memuat sandi PostgreSQL
           'maxmind_account_id': 'MAXMIND_ACCOUNT_ID', 'maxmind_license_key': 'MAXMIND_LICENSE_KEY',
           'aws_access_key_id': 'AWS_ACCESS_KEY_ID', 'aws_secret_access_key': 'AWS_SECRET_ACCESS_KEY', 'aws_session_token': 'AWS_SESSION_TOKEN',
           'telegram_bot_token': 'TELEGRAM_BOT_TOKEN', 'discord_webhook_url': 'DISCORD_WEBHOOK_URL', 'smtp_password': 'SMTP_PASSWORD',
           'kafka_password': 'KAFKA_PASSWORD'}


ALERT_EVENTS = ('spike', 'critical', 'ingest_failed', 'sync_failed', 'folder_missing', 'summary')


@dataclasses.dataclass
class Config:
    log_dir: str = ''     # folder log YYYY-MM-DD/…; bawaan (diisi pemuat konfigurasi): logs/ di folder proyek
    data_dir: str = ''    # bawaan (diisi pemuat konfigurasi): data/ di folder proyek
    cache_dir: str = ''   # bawaan: <log_dir>/.cache (cache sistem lama, agar tidak mengunduh ulang ±100 MB)
    state_dir: str = ''   # bawaan: data_dir
    inbox_dir: str = ''   # bawaan: data_dir/inbox
    bind: str = '127.0.0.1:8000'
    api_url: str = ''     # alamat API untuk perintah baris (Docker: http://app:8000); kosong = dari bind. Diisi -> tidak pernah membuka DuckDB sendiri
    ingest_on_start: bool = True
    offline: bool = False  # jangan mengunduh apa pun (database IP, berkas peta); pakai yang sudah ada di cache
    cookie_secure: bool = True
    trust_proxy: bool = False  # true bila ada reverse proxy di depan: IP klien diambil dari X-Forwarded-For
    admin_user: str = ''
    admin_password: str = ''
    job_token: str = ''
    jwt_secret: str = ''          # rahasia penanda tangan JWT sesi (HS256), minimal 32 karakter
    auth_database_url: str = ''   # postgresql+psycopg://user:sandi@host:5432/db ; kosong = SQLite di state_dir (uji/lokal)
    session_idle_minutes: int = 60
    session_max_hours: int = 12
    server_ip: str = rules.SERVER_IP
    server_fallback: list = dataclasses.field(default_factory=lambda: list(rules.SERVER_FALLBACK))
    hosts: dict = dataclasses.field(default_factory=lambda: dict(rules.HOSTS))
    dns_upstream: str = '10.88.1.100'
    upstream_prefix: str = 'ombudsman-ombudsman-'
    maxmind_account_id: str = ''
    maxmind_license_key: str = ''
    attack_rules: str = 'crs'      # tampilan Keamanan: 'crs' (OWASP CRS + CAPEC, Tahap 21) atau 'lama' (aturan sistem lama; uji kesetaraan)
    attack_paranoia: int = 1       # tingkat paranoia CRS 1..4 (ASUMSI S1: 1, paling sedikit salah-tuduh)
    import_buckets: dict = dataclasses.field(default_factory=dict)  # bucket -> [awalan yang boleh]; kosong = impor mati
    import_region: str = 'ap-southeast-3'
    import_max_objects: int = 500
    import_max_object_mb: int = 1024
    import_max_total_mb: int = 5120
    import_timeout_minutes: int = 30
    duckdb_snapshot: bool = False  # salinan baca DuckDB (data/snapshot/) tiap selesai ingest, untuk DbGate di docker compose
    import_extract: bool = True    # .log.gz hasil impor langsung diekstrak menjadi .log di kotak masuk (permintaan pemilik 2026-10-07)
    blocklist_exclude: str = ''              # IP/CIDR yang tidak pernah masuk daftar blokir (koma), mis. IP kantor, pemantau uptime
    blocklist_exclude_org: str = 'OMBUDSMAN'   # pemilik jaringan (regex, abaikan besar/kecil) yang tidak pernah diblokir; kosong = tidak ada
    s3_watch: str = ''              # awalan induk S3 yang dipantau, mis. s3://nama-bucket/k8s-logs/ (koma untuk >1); kosong = mati
    s3_watch_minutes: int = 60      # jeda pemeriksaan otomatis (menit); 0 = hanya lewat tombol "Periksa S3 sekarang" / cron
    s3_watch_days: int = 30         # hanya folder bertanggal dalam N hari terakhir yang diambil otomatis (0 = semua riwayat)
    s3_watch_max_folders: int = 3   # folder baru maksimal per putaran (terbaru dulu); sisanya menyusul putaran berikutnya
    s3_watch_recheck_days: int = 1  # folder hasil sinkron bertanggal >= hari ini - N diperiksa ulang tiap putaran (file yang datang belakangan)
    s3_watch_enabled: bool = True   # false = sinkron otomatis dimatikan tanpa menghapus alamat S4_S3_WATCH (tombol "Matikan" di layar)
    aws_access_key_id: str = ''
    aws_secret_access_key: str = ''
    aws_session_token: str = ''
    # notifikasi (layar Konfigurasi -> Notifikasi menulis ke sini; monishield/alerts.py)
    alert_telegram: bool = False
    telegram_bot_token: str = ''
    alert_telegram_chat_id: str = ''
    alert_discord: bool = False
    discord_webhook_url: str = ''
    alert_email: bool = False
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_security: str = 'starttls'   # starttls | ssl | none
    smtp_username: str = ''
    smtp_password: str = ''
    smtp_from: str = ''
    smtp_to: str = ''                 # penerima, dipisah koma
    alert_events: str = 'spike,critical,ingest_failed,sync_failed,folder_missing'   # dari ALERT_EVENTS, dipisah koma
    alert_lang: str = 'id'
    dashboard_url: str = ''           # alamat dashboard untuk tautan di pesan, mis. https://monishield.kantor.go.id
    alert_missing_hour: int = 10      # jam (WIB) pemeriksaan "folder log hari ini belum datang"
    # log dari Kafka (Rancher cluster logging -> Kafka; monishield/kafka_in.py)
    kafka_enabled: bool = True        # false = konsumen dimatikan tanpa menghapus alamat broker
    kafka_brokers: str = ''           # host:9092[,host2:9092]; kosong = Kafka tidak dipakai
    kafka_topic: str = ''
    kafka_group: str = 'monishield'   # grup konsumen (posisi baca disimpan di Kafka)
    kafka_security: str = 'plaintext' # plaintext | sasl_plaintext | sasl_ssl | ssl
    kafka_sasl_mechanism: str = 'PLAIN'   # PLAIN | SCRAM-SHA-256 | SCRAM-SHA-512
    kafka_username: str = ''
    kafka_password: str = ''
    kafka_ca_file: str = ''           # sertifikat CA (PEM) untuk ssl/sasl_ssl; kosong = CA sistem
    kafka_offset_reset: str = 'earliest'   # grup baru mulai dari: earliest (semua pesan yang masih disimpan) | latest
    kafka_ingest_minutes: int = 5     # jeda ingest berkala file yang bertambah dari Kafka
    # alamat sumber unduhan & layanan luar (dulu tertulis di kode; bawaan = alamat resmi)
    url_maxmind: str = 'https://download.maxmind.com/geoip/databases/{}/download?suffix=zip'   # {} = nama edisi GeoLite2
    url_ip2asn: str = rules.IP2ASN_URL
    url_land: str = rules.LAND_URL
    url_borders: str = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_boundary_lines_land.geojson'
    url_provinces: str = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson'
    url_countries: str = rules.COUNTRIES_URL
    url_geonames: str = rules.GEONAMES_URL
    telegram_api: str = 'https://api.telegram.org'
    # pembaruan data rujukan & batas lain
    geo_max_age_days: int = 7         # GeoLite2 diunduh ulang bila lebih tua (lisensi MaxMind: maks. 30)
    asn_max_age_days: int = 7         # ip2asn diunduh ulang bila lebih tua
    map_max_age_days: int = 3650      # berkas peta (daratan, batas, label)
    upload_session_hours: int = 6     # sesi unggah folder yang ditinggalkan dibersihkan setelah ini

    @property
    def db_path(self): return os.path.join(self.data_dir, 'monishield.duckdb')

    @property
    def auth_url(self):
        """URL SQLAlchemy basis data akun: PostgreSQL bila dikonfigurasi, selain itu berkas SQLite lewat ORM yang sama."""
        return self.auth_database_url or 'sqlite:///' + os.path.join(self.state_dir, 'auth.db')

    def public(self):
        """Isi konfigurasi untuk dicetak: rahasia hanya 'diisi' / 'kosong'."""
        d = dataclasses.asdict(self)
        return {k: ('diisi' if v else 'kosong') if k in SECRETS else v for k, v in d.items()}


def env_name(key): return SECRETS.get(key) or 'S4_' + key.upper()
