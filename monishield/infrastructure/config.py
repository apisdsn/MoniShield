"""Konfigurasi (TRD §6.3). Urutan prioritas: variabel lingkungan > v2/.env > v2/config.toml > nilai bawaan.

Nilai bawaan = perilaku sistem lama. Setiap kunci bisa diatur lewat lingkungan/.env sebagai S4_<NAMA>
(daftar dan kamus ditulis sebagai JSON). Pengecualian nama: kredensial pihak lain memakai nama standarnya
(MAXMIND_*, AWS_*). Rahasia hanya dari lingkungan/.env dan tidak pernah dicetak.
"""
import dataclasses, os, re, tomllib

from monishield.domain.config_model import ALERT_EVENTS, SECRETS, Config, env_name   # noqa: F401  (dipakai ulang lewat modul ini)
from monishield.domain.config_model import cast as _cast

V2_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # akar proyek (dulu folder v2/ di repo dashboard-logging)
DOTENV = os.path.join(V2_DIR, '.env')   # dibaca load(); layar Konfigurasi menulis ke sini (monishield/envfile.py)


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


def load(env=None, dotenv=None):
    """env bawaan = os.environ; dotenv bawaan = v2/.env (lewati dengan dotenv=False)."""
    env = os.environ if env is None else env
    file_env = {} if dotenv is False else read_dotenv(dotenv or DOTENV)
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
    cfg.log_dir = os.path.abspath(cfg.log_dir or os.path.join(V2_DIR, 'logs'))
    cfg.data_dir = os.path.abspath(cfg.data_dir or os.path.join(V2_DIR, 'data'))
    cfg.cache_dir = os.path.abspath(cfg.cache_dir or os.path.join(cfg.log_dir, '.cache'))
    cfg.state_dir = os.path.abspath(cfg.state_dir or cfg.data_dir)
    cfg.inbox_dir = os.path.abspath(cfg.inbox_dir or os.path.join(cfg.data_dir, 'inbox'))
    if cfg.attack_rules not in ('crs', 'lama'): raise SystemExit("S4_ATTACK_RULES harus 'crs' atau 'lama'")
    if not 1 <= cfg.attack_paranoia <= 4: raise SystemExit('S4_ATTACK_PARANOIA harus 1..4')
    if cfg.kafka_security not in ('plaintext', 'sasl_plaintext', 'sasl_ssl', 'ssl'): raise SystemExit('S4_KAFKA_SECURITY harus plaintext, sasl_plaintext, sasl_ssl, atau ssl')
    if cfg.kafka_sasl_mechanism.upper() not in ('PLAIN', 'SCRAM-SHA-256', 'SCRAM-SHA-512'): raise SystemExit('S4_KAFKA_SASL_MECHANISM harus PLAIN, SCRAM-SHA-256, atau SCRAM-SHA-512')
    if cfg.kafka_offset_reset not in ('earliest', 'latest'): raise SystemExit("S4_KAFKA_OFFSET_RESET harus 'earliest' atau 'latest'")
    if not 1 <= cfg.kafka_ingest_minutes <= 1440: raise SystemExit('S4_KAFKA_INGEST_MINUTES harus 1..1440')
    if not 1 <= cfg.geo_max_age_days <= 30: raise SystemExit('S4_GEO_MAX_AGE_DAYS harus 1..30 (lisensi GeoLite2)')
    if cfg.url_maxmind.count('{}') != 1: raise SystemExit('S4_URL_MAXMIND harus memuat tepat satu {} (nama edisi)')
    for k in ('url_maxmind', 'url_ip2asn', 'url_land', 'url_borders', 'url_provinces', 'url_countries', 'url_geonames', 'telegram_api'):
        if not re.match(r'https?://', getattr(cfg, k)): raise SystemExit(f'{env_name(k)} harus diawali http:// atau https://')
    return cfg
