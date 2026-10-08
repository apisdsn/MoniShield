"""Notification rules (pure): settings, input validation, bilingual texts, and per-folder event evaluation.
Delivery: monishield/infrastructure/notify_channels.py; scheduling: monishield/application/alert_service.py.

Notifications to Telegram, Discord, and email (owner request 2026-10-07: "cukup isi kredensialnya" (just fill in the credentials)).

Settings (channels + their credentials, events sent, language, dashboard address) live in .env (S4_ALERT_*, S4_SMTP_*,
TELEGRAM_BOT_TOKEN, DISCORD_WEBHOOK_URL, SMTP_PASSWORD, S4_DASHBOARD_URL); the Configuration page -> Notifications writes there
(monishield/application/settings_service.py). Credentials (bot token, webhook URL, SMTP password) are NEVER sent back to the browser; only
"set".

PROJECT RULE: user IP addresses must not be sent to third-party services. Messages are built from aggregate numbers (request
count, IP count, categories), without IP addresses; as a last safeguard every IPv4/IPv6 address pattern is replaced by "[IP]"
before sending (`scrub`).

Events:
  spike           a number in the new folder ≥ 2× the average of comparable folders (Command Center `baseline`) and up by at least N
  critical        critical-severity attack requests in the new folder
  ingest_failed   ingest failed or some file failed to parse
  sync_failed     the S3 sync check ended with an error / failed folder
  folder_missing  today's log folder is still missing after a given hour (WIB)
  summary         summary of each new folder (off by default)
An event is sent once per key (e.g. 'spike:2026-10-06'); recorded in the alert_log table (history on the page).
"""
import json, re, urllib.parse

from monishield.domain.config_model import ALERT_EVENTS
from monishield.domain.errors import Fail

TELEGRAM_API = 'https://api.telegram.org'   # default; the address used = S4_TELEGRAM_API (cfg.telegram_api)
DISCORD_HOSTS = ('discord.com', 'discordapp.com', 'ptb.discord.com', 'canary.discord.com')
EVENTS = ALERT_EVENTS
DEFAULT = dict(
    channels=dict(telegram=dict(enabled=False, bot_token='', chat_id=''),
                  discord=dict(enabled=False, webhook_url=''),
                  email=dict(enabled=False, host='', port=587, security='starttls', username='', password='', sender='', to='')),
    events=dict(spike=True, critical=True, ingest_failed=True, sync_failed=True, folder_missing=True, summary=False),
    lang='id', dashboard_url='', missing_hour=10)
SECRETS = {'telegram': ('bot_token',), 'discord': ('webhook_url',), 'email': ('password',)}
# spike threshold per number: (times the average, minimum increase)
SPIKE = dict(n5xx=(2, 20), errors=(2, 100), upstream_errors=(2, 20), atk_req=(2, 20), attack_ips=(2, 3), login_fail_ips=(2, 5))

# IPv4; IPv6 full (8 groups) or compressed (contains '::'). Times like 10:00:59 do not match.
_IP = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}\b|(?:[0-9a-f]{1,4}:){1,7}:(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4}){0,6})?|::(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4}){0,6})', re.I)


def scrub(text):
    """Last safeguard of the "no IPs to third parties" rule: every IP address pattern is replaced by [IP]."""
    return _IP.sub('[IP]', text)


class AlertFail(Fail):
    def __init__(self, message, code='invalid_alerts', status=400): super().__init__(code, message, status)

    def __str__(self): return self.message

# ------------------------------------------------------------------ settings
def load(cfg):
    """Notification settings from the server configuration (.env) -> the dict shape used by this module and the page."""
    on = {x.strip() for x in (cfg.alert_events or '').split(',')}
    return dict(
        channels=dict(telegram=dict(enabled=cfg.alert_telegram, bot_token=cfg.telegram_bot_token, chat_id=cfg.alert_telegram_chat_id, api=cfg.telegram_api),
                      discord=dict(enabled=cfg.alert_discord, webhook_url=cfg.discord_webhook_url),
                      email=dict(enabled=cfg.alert_email, host=cfg.smtp_host, port=cfg.smtp_port, security=cfg.smtp_security,
                                 username=cfg.smtp_username, password=cfg.smtp_password, sender=cfg.smtp_from, to=cfg.smtp_to)),
        events={e: e in on for e in EVENTS}, lang=cfg.alert_lang, dashboard_url=cfg.dashboard_url, missing_hour=cfg.alert_missing_hour)


def to_fields(d):
    """Inverse of load: settings dict -> {config field: value} (to be written to .env)."""
    c = d['channels']
    t, dc, e = c['telegram'], c['discord'], c['email']
    return dict(alert_telegram=bool(t['enabled']), telegram_bot_token=t['bot_token'], alert_telegram_chat_id=t['chat_id'],
                alert_discord=bool(dc['enabled']), discord_webhook_url=dc['webhook_url'],
                alert_email=bool(e['enabled']), smtp_host=e['host'], smtp_port=int(e['port']), smtp_security=e['security'],
                smtp_username=e['username'], smtp_password=e['password'], smtp_from=e['sender'], smtp_to=e['to'],
                alert_events=','.join(k for k in EVENTS if d['events'].get(k)), alert_lang=d['lang'], dashboard_url=d['dashboard_url'],
                alert_missing_hour=int(d['missing_hour']))


def from_db(cfg, v):
    """Old settings from the account database (app_setting 'alerts', before the move to .env) merged into the current settings."""
    out = load(cfg)
    for ch, d in (v.get('channels') or {}).items():
        if ch in out['channels']: out['channels'][ch].update({k: d[k] for k in d if k in out['channels'][ch]})
    out['events'].update({k: bool(x) for k, x in (v.get('events') or {}).items() if k in EVENTS})
    for k in ('lang', 'dashboard_url', 'missing_hour'):
        if k in v: out[k] = v[k]
    return out


def public(cfg):
    """For the browser: credentials only as 'set' (True/False), their values are never returned."""
    out = json.loads(json.dumps(cfg))
    out['channels']['telegram'].pop('api', None)   # API address from .env, not a page field
    for ch, keys in SECRETS.items():
        for k in keys: out['channels'][ch][k] = bool(cfg['channels'][ch][k])
    return out


def merge(cfg, body):
    """Merge page input into the settings. Empty credential field = unchanged (not erased); `clear: [channel.field]`
    to erase. -> new settings (validated)."""
    new = json.loads(json.dumps(cfg))
    for ch, d in (body.get('channels') or {}).items():
        if ch not in new['channels'] or not isinstance(d, dict): continue
        for k, v in d.items():
            if k not in new['channels'][ch] or k == 'api': continue
            if k in SECRETS.get(ch, ()) and (v is None or v == '' or v is True): continue   # empty / "set" = unchanged
            new['channels'][ch][k] = v
    for item in body.get('clear') or []:
        ch, _, k = str(item).partition('.')
        if k in SECRETS.get(ch, ()): new['channels'][ch][k] = ''
    if isinstance(body.get('events'), dict): new['events'].update({k: bool(x) for k, x in body['events'].items() if k in EVENTS})
    if body.get('lang') in ('id', 'en'): new['lang'] = body['lang']
    if 'dashboard_url' in body: new['dashboard_url'] = str(body['dashboard_url'] or '').strip()[:300]
    if 'missing_hour' in body: new['missing_hour'] = int(body['missing_hour'])
    validate(new)
    return new


def validate(cfg):
    c = cfg['channels']
    if cfg['dashboard_url'] and not re.fullmatch(r'https?://[^\s"<>]+', cfg['dashboard_url']):
        raise AlertFail('Dashboard address must start with http:// or https://.')
    if not 0 <= int(cfg['missing_hour']) <= 23: raise AlertFail('Folder check hour must be 0–23.')
    t = c['telegram']
    t['bot_token'], t['chat_id'] = str(t['bot_token']).strip(), str(t['chat_id']).strip()
    if t['bot_token'] and not re.fullmatch(r'\d{5,15}:[A-Za-z0-9_-]{20,80}', t['bot_token']):
        raise AlertFail('Telegram bot token is not of the form 123456789:ABC… (from @BotFather).')
    if t['chat_id'] and not re.fullmatch(r'-?\d{3,20}|@[A-Za-z][A-Za-z0-9_]{4,31}', t['chat_id']):
        raise AlertFail('Telegram chat ID must be a number (e.g. -1001234567890) or @channel_name.')
    if t['enabled'] and not (t['bot_token'] and t['chat_id']): raise AlertFail('Telegram is on but the bot token / chat ID is not set.')
    d = c['discord']
    d['webhook_url'] = str(d['webhook_url']).strip()
    if d['webhook_url']:
        u = urllib.parse.urlsplit(d['webhook_url'])
        if u.scheme != 'https' or u.hostname not in DISCORD_HOSTS or not u.path.startswith('/api/webhooks/'):
            raise AlertFail('Discord webhook URL must be https://discord.com/api/webhooks/… (Channel settings → Integrations → Webhooks).')
    if d['enabled'] and not d['webhook_url']: raise AlertFail('Discord is on but the webhook URL is not set.')
    e = c['email']
    for k in ('host', 'username', 'sender', 'to'): e[k] = str(e[k] or '').strip()
    e['port'] = int(e['port'] or 0)
    if e['security'] not in ('starttls', 'ssl', 'none'): raise AlertFail('SMTP security must be starttls, ssl, or none.')
    if e['host'] and not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', e['host']): raise AlertFail('Invalid SMTP server.')
    if e['to'] and not all(re.fullmatch(r'[^@\s,]+@[^@\s,]+\.[^@\s,]+', x.strip()) for x in e['to'].split(',') if x.strip()):
        raise AlertFail('Email recipients must be email addresses, comma-separated.')
    if e['enabled'] and not (e['host'] and 1 <= e['port'] <= 65535 and e['sender'] and e['to']):
        raise AlertFail('Email is on but the SMTP server / port / sender / recipient is incomplete.')


# ------------------------------------------------------------------ texts (bilingual; metric names from this small dictionary)
T = dict(
    id=dict(spike='Lonjakan di folder {d}', critical='Serangan kritis di folder {d}', ingest_failed='Ingest gagal',
            sync_failed='Sinkron S3 bermasalah', folder_missing='Folder log {d} belum datang', summary='Ringkasan folder {d}',
            test='Pesan uji MoniShield', test_text='Saluran ini sudah tersambung. Notifikasi berikutnya akan dikirim ke sini.',
            avg='rata-rata {n} folder: {v}', open='Buka', n5xx='Respons 5xx', errors='Error (semua layanan)', upstream_errors='Error koneksi upstream',
            atk_req='Request serangan', attack_ips='IP sumber serangan', login_fail_ips='IP dengan login gagal', requests='Request HTTP',
            crit='{n} request serangan kritis dari {ips} IP. Kategori: {cats}.', newest='Folder terbaru: {d}. Periksa kiriman log / sinkron S3.',
            failed_files='{n} file gagal di-parse', run='ingest #{id}', folders='Folder: {list}'),
    en=dict(spike='Spike in folder {d}', critical='Critical attacks in folder {d}', ingest_failed='Ingest failed',
            sync_failed='S3 sync problem', folder_missing='Log folder {d} has not arrived', summary='Summary of folder {d}',
            test='MoniShield test message', test_text='This channel is connected. Future notifications will be sent here.',
            avg='{n}-folder average: {v}', open='Open', n5xx='5xx responses', errors='Errors (all services)', upstream_errors='Upstream connection errors',
            atk_req='Attack requests', attack_ips='Attack source IPs', login_fail_ips='IPs with failed logins', requests='HTTP requests',
            crit='{n} critical attack requests from {ips} IPs. Categories: {cats}.', newest='Newest folder: {d}. Check log delivery / S3 sync.',
            failed_files='{n} files failed to parse', run='ingest #{id}', folders='Folders: {list}'))


def _t(cfg, k, **p): return T[cfg['lang'] if cfg['lang'] in T else 'id'][k].format(**p)


def _num(v, lang): return f'{v:,.0f}'.replace(',', '.' if lang == 'id' else ',') if isinstance(v, (int, float)) else str(v)


def _link(cfg, folder, tab='peta'):
    return f"\n{_t(cfg, 'open')}: {cfg['dashboard_url'].rstrip('/')}/#/{tab}?folder={folder}" if cfg['dashboard_url'] else ''


# ------------------------------------------------------------------ evaluation
def folder_events(cfg, folder, facts):
    """Events for one folder: [(event, key, title, text)]. facts = the folder's aggregate numbers (no IPs), from the warehouse:
    dict(kpi=<Command Center KPI>, base=<average baseline>, ngx_keys=<ingress KPI keys>, crit_cats=[top categories])."""
    a, b, ngx_keys = facts['kpi'], facts['base'], facts['ngx_keys']
    lang, out = cfg['lang'], []
    vals = dict(a['kpi'], atk_req=a['atk_req'])
    avgs = dict(b['kpi'], atk_req=b['atk_req'])
    lines = []
    for k, (fac, add) in SPIKE.items():
        v, m = vals.get(k), avgs.get(k)
        if v is None or m is None: continue
        if v >= fac * m and v - m >= add:
            n = b['n_nginx'] if k in ngx_keys or k == 'atk_req' else b['n_all']
            fac_txt = f'; ×{v / m:.1f}' if m else ''
            lines.append(f"• {_t(cfg, k)}: {_num(v, lang)} ({_t(cfg, 'avg', n=n, v=_num(m, lang))}{fac_txt})")
    if lines and cfg['events']['spike']:
        out.append(('spike', f'spike:{folder}', _t(cfg, 'spike', d=folder), '\n'.join(lines) + _link(cfg, folder)))
    if a['crit_req'] and cfg['events']['critical']:
        text = _t(cfg, 'crit', n=_num(a['crit_req'], lang), ips=_num(a['kpi']['attack_ips'], lang), cats=', '.join(facts['crit_cats']) or '-')
        out.append(('critical', f'critical:{folder}', _t(cfg, 'critical', d=folder), text + _link(cfg, folder, 'keamanan')))
    if cfg['events']['summary']:
        rows = [f"• {_t(cfg, k)}: {_num(vals[k], lang)}" for k in ('requests', 'n5xx', 'errors', 'atk_req', 'attack_ips', 'login_fail_ips') if vals.get(k) is not None]
        out.append(('summary', f'summary:{folder}', _t(cfg, 'summary', d=folder), '\n'.join(rows) + _link(cfg, folder)))
    return out


def ingest_failed(cfg, result, error):
    """Ingest-failed event -> (key, title, text) or None."""
    if not ((error or (result and result.get('files_failed'))) and cfg['events']['ingest_failed']): return None
    rid = (result or {}).get('run_id', '?')
    text = '\n'.join(x for x in [_t(cfg, 'run', id=rid), error or '', _t(cfg, 'failed_files', n=result['files_failed']) if result and result.get('files_failed') else ''] if x)
    return f'ingest_failed:{rid}', _t(cfg, 'ingest_failed'), text


def sync_failed(cfg, res):
    """S3 sync problem event -> (key, title, text) or None."""
    if not cfg['events']['sync_failed'] or not (res.get('errors') or res.get('failed')): return None
    lines = [f"• {e.get('where') + ': ' if e.get('where') else ''}{e.get('message', '')}" for e in res.get('errors', [])]
    if res.get('failed'): lines.append(_t(cfg, 'folders', list=', '.join(res['failed'])))
    return f"sync_failed:{res.get('at')}", _t(cfg, 'sync_failed'), '\n'.join(lines)


def folder_missing(cfg, now_wib, newest):
    """Folder dated today (WIB) still missing after `missing_hour` -> (key, title, text) or None."""
    if not cfg['events']['folder_missing'] or now_wib.hour < int(cfg['missing_hour']): return None
    today = now_wib.date().isoformat()
    if newest is None or str(newest) >= today: return None
    return f'folder_missing:{today}', _t(cfg, 'folder_missing', d=today), _t(cfg, 'newest', d=str(newest))


def active(cfg): return bool(cfg) and any(c['enabled'] for c in cfg['channels'].values())


TEST_NEEDS = dict(telegram=('bot_token', 'chat_id'), discord=('webhook_url',), email=('host', 'sender', 'to'))
