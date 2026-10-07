"""Aturan layar Konfigurasi (murni): kolom yang boleh diisi dari layar per kelompok, mana yang rahasia, pemeriksaan
isian, dan penerjemahan isian layar / setelan lama menjadi nilai kolom. Penulisan ke file .env ada di
monishield/application/settings_service.py (lewat port EnvStore, adapter monishield/infrastructure/envfile.py).

Rahasia tidak pernah dikirim balik ke browser: hanya "sudah diisi" + sumbernya (Access Key ID / Account ID tersamar).
Yang TIDAK bisa diubah dari layar (dasar keamanan server): S4_JWT_SECRET, S4_JOB_TOKEN, S4_AUTH_DATABASE_URL,
S4_ADMIN_PASSWORD, S4_IMPORT_BUCKETS — layar hanya menampilkan statusnya.
"""
import ipaddress, re

from monishield.domain import alerts
from monishield.domain.config_model import SECRETS, Config, cast, env_name
from monishield.domain.errors import Fail

GROUPS = {
    'aws': ('aws_access_key_id', 'aws_secret_access_key', 'aws_session_token', 'import_region'),
    'maxmind': ('maxmind_account_id', 'maxmind_license_key'),
    'blocklist': ('blocklist_exclude', 'blocklist_exclude_org'),
    'watch': ('s3_watch', 's3_watch_minutes', 's3_watch_enabled'),
    'alerts': tuple(alerts.to_fields(alerts.load(Config()))),
    'kafka': ('kafka_enabled', 'kafka_brokers', 'kafka_topic', 'kafka_group', 'kafka_security', 'kafka_sasl_mechanism', 'kafka_username',
              'kafka_password', 'kafka_offset_reset', 'kafka_ingest_minutes'),
}
SCREEN_GROUPS = ('aws', 'maxmind', 'blocklist', 'kafka')
SCREEN = {k for g in SCREEN_GROUPS for k in GROUPS[g]}   # PUT /api/admin/config
SECRET = set(SECRETS)
MASKED = ('aws_access_key_id', 'maxmind_account_id')
ENV_ONLY = ('jwt_secret', 'job_token', 'auth_database_url', 'admin_password')   # hanya status terisi/kosong
BASE = Config()
OLD_KEYS = ('config', 'alerts', 's3_watch')   # setelan lama di basis data akun (app_setting), dipindah sekali ke .env


class SettingsFail(Fail):
    def __init__(self, message, code='invalid_config', status=400): super().__init__(code, message, status)

    def __str__(self): return self.message


def source(field, file_values, environ):
    """'environment' (variabel lingkungan proses mengalahkan .env) | 'file' (.env) | None (nilai bawaan)."""
    name = env_name(field)
    if name in environ and environ[name] != file_values.get(name): return 'environment'
    return 'file' if name in file_values else None


def mask(v):
    return f'{v[:4]}…{v[-4:]}' if v and len(v) > 10 else ('••••' if v else '')


def changed_only(cfg, values):
    """Kolom yang nilainya berbeda dari setelan berjalan (None = kembali ke bawaan, selalu ditulis)."""
    return {k: v for k, v in values.items() if (getattr(BASE, k) if v is None else v) != getattr(cfg, k) or v is None}


def screen_values(cfg, body):
    """Isian PUT /api/admin/config -> {kolom: nilai | None}. Rahasia kosong = tidak diubah; kolom biasa kosong = kembali ke
    bawaan; `clear: [kolom]` = dihapus. Diperiksa bersama nilai yang sedang berlaku."""
    values = {}
    for k, v in (body or {}).items():
        if k not in SCREEN: continue
        v = '' if v is None else str(v).strip()
        if k in SECRET and v == '': continue                      # rahasia dibiarkan kosong: tetap
        if v == '': values[k] = None; continue
        try: values[k] = cast(v, getattr(BASE, k))              # bool/angka seperti saat dibaca dari .env
        except ValueError: raise SettingsFail(f'{env_name(k)}: nilai tidak sah.') from None
    for k in (body or {}).get('clear') or []:
        if k in SCREEN: values[k] = None
    cand = {k: getattr(cfg, k) for k in SCREEN}
    cand.update({k: getattr(BASE, k) if v is None else v for k, v in values.items()})
    validate(cand)
    return values


def groups_of(env_names):
    names = set(env_names)
    return sorted({g for g, ks in GROUPS.items() for k in ks if env_name(k) in names})


def watch_values(url, minutes, enabled): return dict(s3_watch=url, s3_watch_minutes=int(minutes), s3_watch_enabled=bool(enabled))


def from_old(cfg, old):
    """Setelan lama {app_setting: nilai} -> {kolom: nilai} untuk .env."""
    values = {}
    for k, v in (old.get('config') or {}).items():
        if k in SCREEN and v not in (None, ''): values[k] = v
    if 'alerts' in old: values.update(alerts.to_fields(alerts.from_db(cfg, old['alerts'])))
    if 's3_watch' in old:
        w = old['s3_watch']
        values.update(watch_values(w.get('url', ''), int(w.get('minutes') or cfg.s3_watch_minutes), bool(w.get('enabled'))))
    return values


def validate(s):
    v = s.get('aws_access_key_id')
    if v and not re.fullmatch(r'[A-Z0-9]{16,128}', v): raise SettingsFail('Access Key ID AWS berupa 16–128 huruf besar/angka (mis. AKIA…).')
    v = s.get('aws_secret_access_key')
    if v and not (16 <= len(v) <= 128 and re.fullmatch(r'[A-Za-z0-9/+=]+', v)): raise SettingsFail('Secret Access Key AWS tidak berbentuk kunci rahasia (16–128 karakter).')
    if s.get('aws_session_token') and len(s['aws_session_token']) > 4096: raise SettingsFail('Session token terlalu panjang.')
    if bool(s.get('aws_access_key_id')) != bool(s.get('aws_secret_access_key')):
        raise SettingsFail('Isi Access Key ID dan Secret Access Key bersama-sama.')
    v = s.get('import_region')
    if v and not re.fullmatch(r'[a-z]{2}(-[a-z]+)+-\d', v): raise SettingsFail('Wilayah AWS tidak sah (mis. ap-southeast-3).')
    v = s.get('maxmind_account_id')
    if v and not re.fullmatch(r'\d{3,12}', v): raise SettingsFail('Account ID MaxMind berupa angka.')
    v = s.get('maxmind_license_key')
    if v and not re.fullmatch(r'[A-Za-z0-9_]{10,64}', v): raise SettingsFail('License key MaxMind tidak sah.')
    if bool(s.get('maxmind_account_id')) != bool(s.get('maxmind_license_key')):
        raise SettingsFail('Isi Account ID dan License key MaxMind bersama-sama.')
    for net in (x.strip() for x in (s.get('blocklist_exclude') or '').split(',') if x.strip()):
        try: ipaddress.ip_network(net, strict=False)
        except ValueError: raise SettingsFail(f'"{net[:60]}" bukan IP atau CIDR.') from None
    v = s.get('blocklist_exclude_org')
    if v:
        try: re.compile(v)
        except re.error: raise SettingsFail('Pola pemilik jaringan bukan regex yang sah.') from None
    v = s.get('kafka_brokers')
    if v and not all(re.fullmatch(r'[A-Za-z0-9._-]{1,253}:\d{1,5}', x.strip()) for x in v.split(',') if x.strip()):
        raise SettingsFail('Broker Kafka ditulis host:port, dipisah koma (mis. 10.10.1.5:9092).')
    if s.get('kafka_topic') and not re.fullmatch(r'[A-Za-z0-9._-]{1,249}', s['kafka_topic']): raise SettingsFail('Nama topic Kafka tidak sah.')
    if s.get('kafka_group') and not re.fullmatch(r'[A-Za-z0-9._-]{1,249}', s['kafka_group']): raise SettingsFail('Nama grup konsumen Kafka tidak sah.')
    if 'kafka_security' in s and s['kafka_security'] not in ('plaintext', 'sasl_plaintext', 'sasl_ssl', 'ssl'): raise SettingsFail('Keamanan Kafka harus plaintext, sasl_plaintext, sasl_ssl, atau ssl.')
    if 'kafka_sasl_mechanism' in s and str(s['kafka_sasl_mechanism']).upper() not in ('PLAIN', 'SCRAM-SHA-256', 'SCRAM-SHA-512'): raise SettingsFail('Mekanisme SASL harus PLAIN, SCRAM-SHA-256, atau SCRAM-SHA-512.')
    if str(s.get('kafka_security', '')).startswith('sasl') and not (s.get('kafka_username') and s.get('kafka_password')):
        raise SettingsFail('Keamanan SASL butuh nama pengguna dan sandi Kafka.')
    if 'kafka_offset_reset' in s and s['kafka_offset_reset'] not in ('earliest', 'latest'): raise SettingsFail("Posisi awal harus 'earliest' atau 'latest'.")
    if 'kafka_ingest_minutes' in s and not 1 <= int(s['kafka_ingest_minutes']) <= 1440: raise SettingsFail('Jeda ingest Kafka 1–1440 menit.')
