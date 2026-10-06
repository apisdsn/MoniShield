"""Konfigurasi (TRD §6.3). Urutan prioritas: variabel lingkungan > v2/.env > v2/config.toml > nilai bawaan.

Nilai bawaan = perilaku sistem lama. Setiap kunci bisa diatur lewat lingkungan/.env sebagai S4_<NAMA>
(daftar dan kamus ditulis sebagai JSON). Pengecualian nama: kredensial pihak lain memakai nama standarnya
(MAXMIND_*, AWS_*). Rahasia hanya dari lingkungan/.env dan tidak pernah dicetak.
"""
import dataclasses, json, os, re, tomllib

from . import rules

V2_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# rahasia -> nama variabel lingkungannya
SECRETS = {'admin_password': 'S4_ADMIN_PASSWORD', 'job_token': 'S4_JOB_TOKEN', 'jwt_secret': 'S4_JWT_SECRET',
           'auth_database_url': 'S4_AUTH_DATABASE_URL',   # memuat sandi PostgreSQL
           'maxmind_account_id': 'MAXMIND_ACCOUNT_ID', 'maxmind_license_key': 'MAXMIND_LICENSE_KEY',
           'aws_access_key_id': 'AWS_ACCESS_KEY_ID', 'aws_secret_access_key': 'AWS_SECRET_ACCESS_KEY', 'aws_session_token': 'AWS_SESSION_TOKEN'}


@dataclasses.dataclass
class Config:
    log_dir: str = os.path.dirname(V2_DIR)  # folder induk v2/ = folder log sistem lama
    data_dir: str = os.path.join(V2_DIR, 'data')
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
    aws_access_key_id: str = ''
    aws_secret_access_key: str = ''
    aws_session_token: str = ''

    @property
    def db_path(self): return os.path.join(self.data_dir, 'simpel4.duckdb')

    @property
    def auth_url(self):
        """URL SQLAlchemy basis data akun: PostgreSQL bila dikonfigurasi, selain itu berkas SQLite lewat ORM yang sama."""
        return self.auth_database_url or 'sqlite:///' + os.path.join(self.state_dir, 'auth.db')

    def public(self):
        """Isi konfigurasi untuk dicetak: rahasia hanya 'diisi' / 'kosong'."""
        d = dataclasses.asdict(self)
        return {k: ('diisi' if v else 'kosong') if k in SECRETS else v for k, v in d.items()}


def env_name(key): return SECRETS.get(key) or 'S4_' + key.upper()


def read_dotenv(path):
    """KEY=VALUE per baris; baris/ujung '# komentar' dibuang; kutip di sekeliling nilai dibuang. Tanpa ekspansi variabel."""
    out = {}
    if not os.path.exists(path): return out
    with open(path, encoding='utf-8') as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith('#'): continue
            k, sep, v = line.removeprefix('export ').partition('=')
            if not sep or not k.strip().replace('_', '').isalnum(): raise SystemExit(f'{path}:{n}: bukan KEY=VALUE')
            v = v.strip()
            if v[:1] in ('"', "'") and v.find(v[0], 1) > 0: v = v[1:v.find(v[0], 1)]  # berkutip: sampai kutip penutup
            else: v = re.split(r'(^|\s+)#', v, maxsplit=1)[0].strip()                  # tanpa kutip: buang komentar di ujung
            out[k.strip()] = v
    return out


def _cast(value, default):
    if isinstance(default, bool):
        if value.strip().lower() in ('1', 'true', 'yes', 'ya'): return True
        if value.strip().lower() in ('0', 'false', 'no', 'tidak', ''): return False
        raise ValueError('harus true atau false')
    if isinstance(default, int): return int(value)
    if isinstance(default, (list, dict)):
        v = json.loads(value)
        if not isinstance(v, type(default)): raise ValueError(f'harus JSON berbentuk {type(default).__name__}')
        return v
    return value


def load(env=None, dotenv=None):
    """env bawaan = os.environ; dotenv bawaan = v2/.env (lewati dengan dotenv=False)."""
    env = os.environ if env is None else env
    file_env = {} if dotenv is False else read_dotenv(dotenv or os.path.join(V2_DIR, '.env'))
    get = lambda name: env.get(name, file_env.get(name))  # lingkungan mengalahkan .env
    cfg = Config()
    names = {f.name: getattr(cfg, f.name) for f in dataclasses.fields(cfg)}
    path = get('S4_CONFIG') or os.path.join(V2_DIR, 'config.toml')
    if os.path.exists(path):
        with open(path, 'rb') as fh:
            for k, v in tomllib.load(fh).items():
                if k not in names: raise SystemExit(f'{path}: kunci tidak dikenal: {k}')
                if k in SECRETS: raise SystemExit(f'{path}: {k} hanya boleh lewat variabel lingkungan atau .env')
                setattr(cfg, k, v)
    for k, default in names.items():
        raw = get(env_name(k))
        if raw is None or (raw == '' and not isinstance(default, (str, bool))): continue
        try: setattr(cfg, k, _cast(raw, default))
        except ValueError as e: raise SystemExit(f'{env_name(k)}: {e}')  # nilainya tidak dicetak: bisa rahasia
    unknown = sorted(k for k in file_env if k.startswith('S4_') and k != 'S4_CONFIG' and k not in {env_name(n) for n in names})
    if unknown: raise SystemExit(f'.env: kunci tidak dikenal: {", ".join(unknown)}')
    cfg.log_dir = os.path.abspath(cfg.log_dir); cfg.data_dir = os.path.abspath(cfg.data_dir)
    cfg.cache_dir = os.path.abspath(cfg.cache_dir or os.path.join(cfg.log_dir, '.cache'))
    cfg.state_dir = os.path.abspath(cfg.state_dir or cfg.data_dir)
    cfg.inbox_dir = os.path.abspath(cfg.inbox_dir or os.path.join(cfg.data_dir, 'inbox'))
    if cfg.attack_rules not in ('crs', 'lama'): raise SystemExit("S4_ATTACK_RULES harus 'crs' atau 'lama'")
    if not 1 <= cfg.attack_paranoia <= 4: raise SystemExit('S4_ATTACK_PARANOIA harus 1..4')
    return cfg
