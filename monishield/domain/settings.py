"""Configuration page rules (pure): fields that may be set from the page per group, which are secret, input
validation, and translation of page input / old settings into field values. Writing to the .env file is in
monishield/application/settings_service.py (through the EnvStore port, adapter monishield/infrastructure/envfile.py).

Secrets are never sent back to the browser: only "set" + their source (Access Key ID / Account ID masked).
What CANNOT be changed from the page (server security basics): S4_JWT_SECRET, S4_JOB_TOKEN, S4_AUTH_DATABASE_URL,
S4_ADMIN_PASSWORD, S4_IMPORT_BUCKETS — the page only shows their status.
"""
import ipaddress, re

from monishield.domain import alerts, retention
from monishield.domain.config_model import SECRETS, Config, cast, env_name
from monishield.domain.errors import Fail

GROUPS = {
    'aws': ('aws_access_key_id', 'aws_secret_access_key', 'aws_session_token', 'import_region'),
    'maxmind': ('maxmind_account_id', 'maxmind_license_key'),
    'blocklist': ('blocklist_exclude', 'blocklist_exclude_org'),
    'watch': ('s3_watch', 's3_watch_minutes', 's3_watch_enabled'),
    'alerts': tuple(alerts.to_fields(alerts.load(Config()))),
    'retention': ('retention_days', 'retention_inbox_days'),
    'smtp': ('smtp_host', 'smtp_port', 'smtp_security', 'smtp_username', 'smtp_password', 'smtp_from'),
    'kafka': ('kafka_enabled', 'kafka_brokers', 'kafka_topic', 'kafka_group', 'kafka_security', 'kafka_sasl_mechanism', 'kafka_username',
              'kafka_password', 'kafka_offset_reset', 'kafka_ingest_minutes'),
}
SCREEN_GROUPS = ('aws', 'maxmind', 'blocklist', 'kafka', 'retention', 'smtp')
SCREEN = {k for g in SCREEN_GROUPS for k in GROUPS[g]}   # PUT /api/admin/config
SECRET = set(SECRETS)
MASKED = ('aws_access_key_id', 'maxmind_account_id')
ENV_ONLY = ('jwt_secret', 'job_token', 'auth_database_url', 'admin_password')   # only set/empty status
BASE = Config()
OLD_KEYS = ('config', 'alerts', 's3_watch')   # old settings in the account database (app_setting), moved once to .env


SENDER = re.compile(r'(?:[^<>@\r\n]{1,80} <)?[^@\s<>,]{1,64}@[^@\s<>,]{1,190}\.[A-Za-z]{2,24}>?')


class SettingsFail(Fail):
    def __init__(self, message, code='invalid_config', status=400): super().__init__(code, message, status)

    def __str__(self): return self.message


def source(field, file_values, environ):
    """'environment' (a process environment variable overrides .env) | 'file' (.env) | None (default value)."""
    name = env_name(field)
    if name in environ and environ[name] != file_values.get(name): return 'environment'
    return 'file' if name in file_values else None


def mask(v):
    return f'{v[:4]}…{v[-4:]}' if v and len(v) > 10 else ('••••' if v else '')


def changed_only(cfg, values):
    """Fields whose value differs from the running settings (None = back to default, always written)."""
    return {k: v for k, v in values.items() if (getattr(BASE, k) if v is None else v) != getattr(cfg, k) or v is None}


def screen_values(cfg, body):
    """PUT /api/admin/config input -> {field: value | None}. Empty secret = unchanged; empty ordinary field = back to
    default; `clear: [field]` = erased. Validated together with the values currently in effect, using only the rules
    of the sections being saved."""
    values = {}
    for k, v in (body or {}).items():
        if k not in SCREEN: continue
        v = '' if v is None else str(v).strip()
        if k in SECRET and v == '': continue                      # secret left empty: unchanged
        if v == '': values[k] = None; continue
        try: values[k] = cast(v, getattr(BASE, k))              # bool/number as when read from .env
        except ValueError: raise SettingsFail(f'{env_name(k)}: invalid value.') from None
    for k in (body or {}).get('clear') or []:
        if k in SCREEN: values[k] = None
    cand = {k: getattr(cfg, k) for k in SCREEN}
    cand.update({k: getattr(BASE, k) if v is None else v for k, v in values.items()})
    validate(cand, sections_of(values))   # only the sections being saved: a bad value elsewhere does not block this
    return values


def sections_of(fields):
    """The saved fields plus every other field of their Configuration section: saving the AWS secret alone still checks
    the AWS key next to it, but not the mail server."""
    fields = set(fields)
    return fields | {k for ks in GROUPS.values() if fields.intersection(ks) for k in ks}


def groups_of(env_names):
    names = set(env_names)
    return sorted({g for g, ks in GROUPS.items() for k in ks if env_name(k) in names})


def watch_values(url, minutes, enabled): return dict(s3_watch=url, s3_watch_minutes=int(minutes), s3_watch_enabled=bool(enabled))


def from_old(cfg, old):
    """Old settings {app_setting: value} -> {field: value} for .env."""
    values = {}
    for k, v in (old.get('config') or {}).items():
        if k in SCREEN and v not in (None, ''): values[k] = v
    if 'alerts' in old: values.update(alerts.to_fields(alerts.from_db(cfg, old['alerts'])))
    if 's3_watch' in old:
        w = old['s3_watch']
        values.update(watch_values(w.get('url', ''), int(w.get('minutes') or cfg.s3_watch_minutes), bool(w.get('enabled'))))
    return values


def _cidrs(v):
    for net in (x.strip() for x in (v or '').split(',') if x.strip()):
        try: ipaddress.ip_network(net, strict=False)
        except ValueError: return f'"{net[:60]}" is not an IP or CIDR.'


def _regex(v):
    try: re.compile(v)
    except re.error: return 'The network owner pattern is not a valid regex.'


# (fields a rule reads, check -> message | None). A save only runs the rules of the sections being saved, so a bad
# value elsewhere (for example an AWS key from the process environment) does not block saving another section.
RULES = [
    (('aws_access_key_id',), lambda s: s.get('aws_access_key_id') and not re.fullmatch(r'[A-Z0-9]{16,128}', s['aws_access_key_id'])
        and 'AWS Access Key ID is 16–128 uppercase letters/digits (e.g. AKIA…).'),
    (('aws_secret_access_key',), lambda s: (v := s.get('aws_secret_access_key')) and not (16 <= len(v) <= 128 and re.fullmatch(r'[A-Za-z0-9/+=]+', v))
        and 'AWS Secret Access Key does not look like a secret key (16–128 characters).'),
    (('aws_session_token',), lambda s: s.get('aws_session_token') and len(s['aws_session_token']) > 4096 and 'Session token is too long.'),
    (('aws_access_key_id', 'aws_secret_access_key'), lambda s: bool(s.get('aws_access_key_id')) != bool(s.get('aws_secret_access_key'))
        and 'Set Access Key ID and Secret Access Key together.'),
    (('import_region',), lambda s: s.get('import_region') and not re.fullmatch(r'[a-z]{2}(-[a-z]+)+-\d', s['import_region'])
        and 'Invalid AWS region (e.g. ap-southeast-3).'),
    (('maxmind_account_id',), lambda s: s.get('maxmind_account_id') and not re.fullmatch(r'\d{3,12}', s['maxmind_account_id'])
        and 'MaxMind Account ID must be a number.'),
    (('maxmind_license_key',), lambda s: s.get('maxmind_license_key') and not re.fullmatch(r'[A-Za-z0-9_]{10,64}', s['maxmind_license_key'])
        and 'Invalid MaxMind license key.'),
    (('maxmind_account_id', 'maxmind_license_key'), lambda s: bool(s.get('maxmind_account_id')) != bool(s.get('maxmind_license_key'))
        and 'Set MaxMind Account ID and License key together.'),
    (('blocklist_exclude',), lambda s: _cidrs(s.get('blocklist_exclude'))),
    (('blocklist_exclude_org',), lambda s: s.get('blocklist_exclude_org') and _regex(s['blocklist_exclude_org'])),
    (('kafka_brokers',), lambda s: (v := s.get('kafka_brokers')) and not all(re.fullmatch(r'[A-Za-z0-9._-]{1,253}:\d{1,5}', x.strip()) for x in v.split(',') if x.strip())
        and 'Kafka brokers are written host:port, comma-separated (e.g. 10.10.1.5:9092).'),
    (('kafka_topic',), lambda s: s.get('kafka_topic') and not re.fullmatch(r'[A-Za-z0-9._-]{1,249}', s['kafka_topic']) and 'Invalid Kafka topic name.'),
    (('kafka_group',), lambda s: s.get('kafka_group') and not re.fullmatch(r'[A-Za-z0-9._-]{1,249}', s['kafka_group']) and 'Invalid Kafka consumer group name.'),
    (('kafka_security',), lambda s: 'kafka_security' in s and s['kafka_security'] not in ('plaintext', 'sasl_plaintext', 'sasl_ssl', 'ssl')
        and 'Kafka security must be plaintext, sasl_plaintext, sasl_ssl, or ssl.'),
    (('kafka_sasl_mechanism',), lambda s: 'kafka_sasl_mechanism' in s and str(s['kafka_sasl_mechanism']).upper() not in ('PLAIN', 'SCRAM-SHA-256', 'SCRAM-SHA-512')
        and 'SASL mechanism must be PLAIN, SCRAM-SHA-256, or SCRAM-SHA-512.'),
    (('kafka_security', 'kafka_username', 'kafka_password'), lambda s: str(s.get('kafka_security', '')).startswith('sasl')
        and not (s.get('kafka_username') and s.get('kafka_password')) and 'SASL security needs a Kafka username and password.'),
    (('kafka_offset_reset',), lambda s: 'kafka_offset_reset' in s and s['kafka_offset_reset'] not in ('earliest', 'latest')
        and "Start position must be 'earliest' or 'latest'."),
    (('kafka_ingest_minutes',), lambda s: 'kafka_ingest_minutes' in s and not 1 <= int(s['kafka_ingest_minutes']) <= 1440
        and 'Kafka ingest interval must be 1–1440 minutes.'),
    (('smtp_host',), lambda s: s.get('smtp_host') and not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', s['smtp_host'])
        and 'Invalid mail server address (e.g. smtp.example.go.id).'),
    (('smtp_port',), lambda s: 'smtp_port' in s and not 1 <= int(s['smtp_port']) <= 65535 and 'Mail server port must be 1–65535.'),
    (('smtp_security',), lambda s: 'smtp_security' in s and s['smtp_security'] not in ('starttls', 'ssl', 'none')
        and 'Mail server security must be starttls, ssl, or none.'),
    (('smtp_from',), lambda s: s.get('smtp_from') and not SENDER.fullmatch(s['smtp_from'])
        and 'Sender must be an email address, e.g. monishield@example.go.id or MoniShield <monishield@example.go.id>.'),
    (('retention_days', 'retention_inbox_days'), lambda s: 'retention_days' in s
        and retention.validate(int(s['retention_days']), int(s.get('retention_inbox_days') or 0))),
]


def validate(s, fields=None):
    """Raise SettingsFail on the first broken rule. fields = the fields being saved: only rules that read one of them
    run (None = every rule)."""
    for keys, check in RULES:
        if fields is not None and not fields.intersection(keys): continue
        if msg := check(s): raise SettingsFail(msg)
