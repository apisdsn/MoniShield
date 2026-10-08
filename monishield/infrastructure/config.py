"""Configuration (TRD §6.3). Priority order: environment variables > v2/.env > v2/config.toml > defaults.

Defaults = old system behavior. Every key can be set via the environment/.env as S4_<NAME>
(lists and dicts are written as JSON). Naming exception: third-party credentials use their standard names
(MAXMIND_*, AWS_*). Secrets come only from the environment/.env and are never printed.
"""
import dataclasses, os, re, tomllib

from monishield.domain.config_model import ALERT_EVENTS, SECRETS, Config, env_name   # noqa: F401  (re-exported through this module)
from monishield.domain.config_model import cast as _cast
from monishield.domain import alerts, retention

V2_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # project root (formerly the v2/ folder in the dashboard-logging repo)
DOTENV = os.path.join(V2_DIR, '.env')   # read by load(); the Configuration page writes here (monishield/envfile.py)


def read_dotenv(path):
    """KEY=VALUE per line; '# comment' lines/tails are dropped; quotes around the value are dropped. No variable expansion."""
    out = {}
    if not os.path.exists(path): return out
    with open(path, encoding='utf-8') as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith('#'): continue
            k, sep, v = line.removeprefix('export ').partition('=')
            if not sep or not k.strip().replace('_', '').isalnum(): raise SystemExit(f'{path}:{n}: not KEY=VALUE')
            v = v.strip()
            if v[:1] in ('"', "'") and v.find(v[0], 1) > 0: v = v[1:v.find(v[0], 1)]  # quoted: up to the closing quote
            else: v = re.split(r'(^|\s+)#', v, maxsplit=1)[0].strip()                  # unquoted: drop the trailing comment
            out[k.strip()] = v
    return out


def load(env=None, dotenv=None):
    """default env = os.environ; default dotenv = v2/.env (skip with dotenv=False)."""
    env = os.environ if env is None else env
    file_env = {} if dotenv is False else read_dotenv(dotenv or DOTENV)
    get = lambda name: env.get(name, file_env.get(name))  # the environment beats .env
    cfg = Config()
    names = {f.name: getattr(cfg, f.name) for f in dataclasses.fields(cfg)}
    path = get('S4_CONFIG') or os.path.join(V2_DIR, 'config.toml')
    if os.path.exists(path):
        with open(path, 'rb') as fh:
            for k, v in tomllib.load(fh).items():
                if k not in names: raise SystemExit(f'{path}: unknown key: {k}')
                if k in SECRETS: raise SystemExit(f'{path}: {k} may only be set via environment variables or .env')
                setattr(cfg, k, v)
    for k, default in names.items():
        raw = get(env_name(k))
        if raw is None or (raw == '' and not isinstance(default, (str, bool))): continue
        try: setattr(cfg, k, _cast(raw, default))
        except ValueError as e: raise SystemExit(f'{env_name(k)}: {e}')  # the value is not printed: it may be secret
    unknown = sorted(k for k in file_env if k.startswith('S4_') and k != 'S4_CONFIG' and k not in {env_name(n) for n in names})
    if unknown: raise SystemExit(f'.env: unknown keys: {", ".join(unknown)}')
    cfg.log_dir = os.path.abspath(cfg.log_dir or os.path.join(V2_DIR, 'logs'))
    cfg.data_dir = os.path.abspath(cfg.data_dir or os.path.join(V2_DIR, 'data'))
    cfg.cache_dir = os.path.abspath(cfg.cache_dir or os.path.join(cfg.log_dir, '.cache'))
    cfg.state_dir = os.path.abspath(cfg.state_dir or cfg.data_dir)
    cfg.inbox_dir = os.path.abspath(cfg.inbox_dir or os.path.join(cfg.data_dir, 'inbox'))
    if cfg.attack_rules not in ('crs', 'lama'): raise SystemExit("S4_ATTACK_RULES must be 'crs' or 'lama'")
    if not 1 <= cfg.attack_paranoia <= 4: raise SystemExit('S4_ATTACK_PARANOIA must be 1..4')
    if cfg.kafka_security not in ('plaintext', 'sasl_plaintext', 'sasl_ssl', 'ssl'): raise SystemExit('S4_KAFKA_SECURITY must be plaintext, sasl_plaintext, sasl_ssl, or ssl')
    if cfg.kafka_sasl_mechanism.upper() not in ('PLAIN', 'SCRAM-SHA-256', 'SCRAM-SHA-512'): raise SystemExit('S4_KAFKA_SASL_MECHANISM must be PLAIN, SCRAM-SHA-256, or SCRAM-SHA-512')
    if cfg.kafka_offset_reset not in ('earliest', 'latest'): raise SystemExit("S4_KAFKA_OFFSET_RESET must be 'earliest' or 'latest'")
    if not 1 <= cfg.kafka_ingest_minutes <= 1440: raise SystemExit('S4_KAFKA_INGEST_MINUTES must be 1..1440')
    if msg := retention.validate(cfg.retention_days, cfg.retention_inbox_days): raise SystemExit(f'S4_RETENTION_DAYS / S4_RETENTION_INBOX_DAYS: {msg}')
    try: alerts.parse_spike(cfg.alert_spike); alerts.parse_service_spike(cfg.alert_service_spike)
    except alerts.AlertFail as e: raise SystemExit(f'S4_ALERT_SPIKE / S4_ALERT_SERVICE_SPIKE: {e}') from None
    if not 1 <= cfg.geo_max_age_days <= 30: raise SystemExit('S4_GEO_MAX_AGE_DAYS must be 1..30 (GeoLite2 license)')
    if cfg.url_maxmind.count('{}') != 1: raise SystemExit('S4_URL_MAXMIND must contain exactly one {} (edition name)')
    for k in ('url_maxmind', 'url_ip2asn', 'url_land', 'url_borders', 'url_provinces', 'url_countries', 'url_geonames', 'telegram_api'):
        if not re.match(r'https?://', getattr(cfg, k)): raise SystemExit(f'{env_name(k)} must start with http:// or https://')
    return cfg
