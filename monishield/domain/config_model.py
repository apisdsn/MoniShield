"""MoniShield configuration model (TRD §6.3): all settings with their default values. Pure data; READING from the
environment / .env / config.toml is done by the loader in monishield/infrastructure/config.py.

Every field can be set through the environment/.env as S4_<NAME> (lists and dicts written as JSON). Naming
exception: third-party credentials use their standard names (MAXMIND_*, AWS_*, TELEGRAM_BOT_TOKEN, …). Secrets are never printed.
"""
import dataclasses, json, os

from monishield.domain import rules

# secret -> its environment variable name
SECRETS = {'admin_password': 'S4_ADMIN_PASSWORD', 'job_token': 'S4_JOB_TOKEN', 'jwt_secret': 'S4_JWT_SECRET',
           'auth_database_url': 'S4_AUTH_DATABASE_URL',   # contains the PostgreSQL password
           'maxmind_account_id': 'MAXMIND_ACCOUNT_ID', 'maxmind_license_key': 'MAXMIND_LICENSE_KEY',
           'aws_access_key_id': 'AWS_ACCESS_KEY_ID', 'aws_secret_access_key': 'AWS_SECRET_ACCESS_KEY', 'aws_session_token': 'AWS_SESSION_TOKEN',
           'telegram_bot_token': 'TELEGRAM_BOT_TOKEN', 'discord_webhook_url': 'DISCORD_WEBHOOK_URL', 'smtp_password': 'SMTP_PASSWORD',
           'kafka_password': 'KAFKA_PASSWORD'}


ALERT_EVENTS = ('spike', 'critical', 'ingest_failed', 'sync_failed', 'folder_missing', 'summary')


@dataclasses.dataclass
class Config:
    log_dir: str = ''     # log folder YYYY-MM-DD/…; default (set by the config loader): logs/ in the project folder
    data_dir: str = ''    # default (set by the config loader): data/ in the project folder
    cache_dir: str = ''   # default: <log_dir>/.cache (old system cache, to avoid re-downloading ±100 MB)
    state_dir: str = ''   # default: data_dir
    inbox_dir: str = ''   # default: data_dir/inbox
    bind: str = '127.0.0.1:8000'
    api_url: str = ''     # API address for command-line commands (Docker: http://app:8000); empty = from bind. Set -> never opens DuckDB itself
    ingest_on_start: bool = True
    offline: bool = False  # never download anything (IP databases, map files); use what is already in the cache
    cookie_secure: bool = True
    trust_proxy: bool = False  # true when a reverse proxy is in front: client IP is taken from X-Forwarded-For
    admin_user: str = ''
    admin_password: str = ''
    job_token: str = ''
    jwt_secret: str = ''          # signing secret for session JWTs (HS256), at least 32 characters
    auth_database_url: str = ''   # postgresql+psycopg://user:password@host:5432/db ; empty = SQLite in state_dir (test/local)
    session_idle_minutes: int = 60
    session_max_hours: int = 12
    password_reset: bool = True       # "forgot password" on the sign-in page emails a temporary password (needs the mail server)
    password_reset_minutes: int = 30  # how long that temporary password works
    server_ip: str = rules.SERVER_IP
    server_fallback: list = dataclasses.field(default_factory=lambda: list(rules.SERVER_FALLBACK))
    hosts: dict = dataclasses.field(default_factory=lambda: dict(rules.HOSTS))
    dns_upstream: str = '10.88.1.100'
    upstream_prefix: str = 'ombudsman-ombudsman-'
    maxmind_account_id: str = ''
    maxmind_license_key: str = ''
    attack_rules: str = 'crs'      # Security view: 'crs' (OWASP CRS + CAPEC, Stage 21) or 'lama' (old system rules; parity test)
    attack_paranoia: int = 1       # CRS paranoia level 1..4 (ASSUMPTION S1: 1, fewest false positives)
    import_buckets: dict = dataclasses.field(default_factory=dict)  # bucket -> [allowed prefixes]; empty = import off
    import_region: str = 'ap-southeast-3'
    import_max_objects: int = 500
    import_max_object_mb: int = 1024
    import_max_total_mb: int = 5120
    import_timeout_minutes: int = 30
    duckdb_snapshot: bool = False  # DuckDB read-only copy (data/snapshot/) after each ingest, for DbGate in docker compose
    import_extract: bool = True    # imported .log.gz is extracted to .log in the inbox right away (owner request 2026-10-07)
    blocklist_exclude: str = ''              # IP/CIDR never put on the blocklist (comma-separated), e.g. office IPs, uptime monitors
    blocklist_exclude_org: str = 'OMBUDSMAN'   # network owners (regex, case-insensitive) never blocked; empty = none
    s3_watch: str = ''              # watched S3 parent prefix, e.g. s3://bucket-name/k8s-logs/ (comma for >1); empty = off
    s3_watch_minutes: int = 60      # automatic check interval (minutes); 0 = only via the "Check S3 now" button / cron
    s3_watch_days: int = 30         # only folders dated within the last N days are fetched automatically (0 = all history)
    s3_watch_max_folders: int = 3   # max new folders per round (newest first); the rest follow in later rounds
    s3_watch_recheck_days: int = 1  # synced folders dated >= today - N are re-checked every round (files that arrive late)
    s3_watch_enabled: bool = True   # false = automatic sync turned off without erasing the S4_S3_WATCH address (the "Turn off" button on the page)
    aws_access_key_id: str = ''
    aws_secret_access_key: str = ''
    aws_session_token: str = ''
    # notifications (the Configuration page -> Notifications writes here; monishield/alerts.py)
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
    smtp_to: str = ''                 # recipients, comma-separated
    alert_events: str = 'spike,critical,ingest_failed,sync_failed,folder_missing'   # from ALERT_EVENTS, comma-separated
    alert_lang: str = 'id'
    dashboard_url: str = ''           # dashboard address for links in messages, e.g. https://monishield.kantor.go.id
    alert_missing_hour: int = 10      # hour (WIB) of the "today's log folder has not arrived" check
    alert_spike: str = ''             # spike thresholds per number, "key=factor:minimum increase", e.g. n5xx=3:50,errors=off; empty = defaults
    alert_service_spike: str = 'default=2:50'   # service errors vs their own average, e.g. default=2:50,om-be-report=3:200,coredns=off
    # logs from Kafka (Rancher cluster logging -> Kafka; monishield/kafka_in.py)
    kafka_enabled: bool = True        # false = consumer turned off without erasing the broker address
    kafka_brokers: str = ''           # host:9092[,host2:9092]; empty = Kafka not used
    kafka_topic: str = ''
    kafka_group: str = 'monishield'   # consumer group (read position stored in Kafka)
    kafka_security: str = 'plaintext' # plaintext | sasl_plaintext | sasl_ssl | ssl
    kafka_sasl_mechanism: str = 'PLAIN'   # PLAIN | SCRAM-SHA-256 | SCRAM-SHA-512
    kafka_username: str = ''
    kafka_password: str = ''
    kafka_ca_file: str = ''           # CA certificate (PEM) for ssl/sasl_ssl; empty = system CA
    kafka_offset_reset: str = 'earliest'   # a new group starts from: earliest (all messages still retained) | latest
    kafka_ingest_minutes: int = 5     # interval of periodic ingest of files grown from Kafka
    # download source & external service addresses (formerly hard-coded; default = official addresses)
    url_maxmind: str = 'https://download.maxmind.com/geoip/databases/{}/download?suffix=zip'   # {} = GeoLite2 edition name
    url_ip2asn: str = rules.IP2ASN_URL
    url_land: str = rules.LAND_URL
    url_borders: str = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_boundary_lines_land.geojson'
    url_provinces: str = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson'
    url_countries: str = rules.COUNTRIES_URL
    url_geonames: str = rules.GEONAMES_URL
    telegram_api: str = 'https://api.telegram.org'
    # reference data refresh & other limits
    geo_max_age_days: int = 7         # GeoLite2 re-downloaded when older (MaxMind license: max. 30)
    asn_max_age_days: int = 7         # ip2asn re-downloaded when older
    map_max_age_days: int = 3650      # map files (land, borders, labels)
    upload_session_hours: int = 6     # abandoned folder upload sessions are cleaned up after this
    api_encryption: bool = True       # web UI request/response bodies encrypted with a per-page AES-GCM key (monishield/interfaces/api/wire.py)
    # data retention (monishield/domain/retention.py); 0 = keep forever
    retention_days: int = 0           # folders older than N days are removed from the database (log files are not touched)
    retention_inbox_days: int = 0     # inbox folders (S3 imports, uploads, Kafka) older than N days are deleted from disk

    @property
    def db_path(self): return os.path.join(self.data_dir, 'monishield.duckdb')

    @property
    def auth_url(self):
        """SQLAlchemy URL of the account database: PostgreSQL when configured, otherwise an SQLite file through the same ORM."""
        return self.auth_database_url or 'sqlite:///' + os.path.join(self.state_dir, 'auth.db')

    def public(self):
        """Configuration contents for printing: secrets only as 'set' / 'empty'."""
        d = dataclasses.asdict(self)
        return {k: ('set' if v else 'empty') if k in SECRETS else v for k, v in d.items()}


def env_name(key): return SECRETS.get(key) or 'S4_' + key.upper()


def cast(value, default):
    """Text from .env / the page -> the type of the field's default value (bool, int, JSON list/dict, text)."""
    if isinstance(default, bool):
        if value.strip().lower() in ('1', 'true', 'yes', 'ya'): return True
        if value.strip().lower() in ('0', 'false', 'no', 'tidak', ''): return False
        raise ValueError('must be true or false')
    if isinstance(default, int): return int(value)
    if isinstance(default, (list, dict)):
        v = json.loads(value)
        if not isinstance(v, type(default)): raise ValueError(f'must be JSON of type {type(default).__name__}')
        return v
    return value
