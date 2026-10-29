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
  spike           a number in the new folder ≥ 2× the average of comparable folders (Command Center `baseline`) and up by at least N;
                  also the errors of each service against that service's average (thresholds: S4_ALERT_SPIKE, S4_ALERT_SERVICE_SPIKE)
  critical        critical-severity attack requests in the new folder
  ingest_failed   ingest failed or some file failed to parse
  sync_failed     the S3 sync check ended with an error / failed folder
  folder_missing  today's log folder is still missing after a given hour (WIB)
  summary         daily report of each new folder (off by default): status, numbers vs the 7-day average, what needs a look,
                  ingest result, backup / S3 sync / Kafka health. Emoji and **bold** section titles for Telegram and Discord;
                  the email letter drops the emoji and turns the sections into headings (domain/letters.py)
An event is sent once per key (e.g. 'spike:2026-10-06'); recorded in the alert_log table (history on the page).
"""
import datetime, json, re, urllib.parse

from monishield.domain.config_model import ALERT_EVENTS
from monishield.domain.errors import Fail

TELEGRAM_API = 'https://api.telegram.org'   # default; the address used = S4_TELEGRAM_API (cfg.telegram_api)
DISCORD_HOSTS = ('discord.com', 'discordapp.com', 'ptb.discord.com', 'canary.discord.com')
EVENTS = ALERT_EVENTS
SECRETS = {'telegram': ('bot_token',), 'discord': ('webhook_url',), 'email': ('password',)}
# spike threshold per number: (times the average, minimum increase); S4_ALERT_SPIKE overrides them, "off" turns one off
SPIKE = dict(n5xx=(2, 20), errors=(2, 100), upstream_errors=(2, 20), atk_req=(2, 20), attack_ips=(2, 3), login_fail_ips=(2, 5))
# errors of ONE service vs that service's own average (owner request 2026-10-08): a busy service and a quiet one need
# different thresholds. S4_ALERT_SERVICE_SPIKE: default=2:50 plus per-service overrides; "off" mutes a service.
SERVICE_DEFAULT = (2, 50)
_SERVICE = re.compile(r'[a-z0-9][a-z0-9._-]{0,99}')
MAX_SERVICE_LINES = 5

# IPv4; IPv6 full (8 groups) or compressed (contains '::'). Times like 10:00:59 do not match.
_IP = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}\b|(?:[0-9a-f]{1,4}:){1,7}:(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4}){0,6})?|::(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4}){0,6})', re.I)


def scrub(text):
    """Last safeguard of the "no IPs to third parties" rule: every IP address pattern is replaced by [IP]."""
    return _IP.sub('[IP]', text)


class AlertFail(Fail):
    def __init__(self, message, code='invalid_alerts', status=400): super().__init__(code, message, status)

    def __str__(self): return self.message


class AlertUnconfirmed(AlertFail):
    """The channel received the message but did not confirm it (email: connection ended after the message was sent).
    Counted as sent, so it is not sent again; the note is kept in the history."""

# ------------------------------------------------------------------ thresholds
def _pair(name, value):
    """'2:50' -> (2.0, 50); 'off' -> None. Bad text -> AlertFail."""
    v = str(value).strip().lower()
    if v == 'off': return None
    f, sep, m = v.partition(':')
    try:
        f, m = float(f), int(m) if sep else 0
    except ValueError: raise AlertFail(f'Threshold for {name} must look like 2:50 (times the average : minimum increase) or off.') from None
    if not (1 < f <= 100 and 0 <= m <= 10 ** 9): raise AlertFail(f'Threshold for {name}: the factor must be above 1 and at most 100, the minimum increase 0 or more.')
    return (int(f) if f == int(f) else round(f, 2), m)


def _items(text):
    for part in (p.strip() for p in str(text or '').split(',')):
        if not part: continue
        k, sep, v = part.partition('=')
        if not sep: raise AlertFail(f'"{part[:60]}" must be name=factor:minimum (e.g. n5xx=3:50).')
        yield k.strip().lower(), v


def parse_spike(text):
    """S4_ALERT_SPIKE -> {number: (factor, minimum) | None}, defaults filled in."""
    out = dict(SPIKE)
    for k, v in _items(text):
        if k not in SPIKE: raise AlertFail(f'Unknown number "{k[:40]}" in the spike thresholds; use {", ".join(SPIKE)}.')
        out[k] = _pair(k, v)
    return out


def parse_service_spike(text):
    """S4_ALERT_SERVICE_SPIKE -> dict(default=(factor, minimum) | None, services={service: (factor, minimum) | None})."""
    out = dict(default=SERVICE_DEFAULT, services={})
    for k, v in _items(text):
        if k == 'default': out['default'] = _pair('all services', v); continue
        if not _SERVICE.fullmatch(k): raise AlertFail(f'"{k[:60]}" is not a service name.')
        out['services'][k] = _pair(k, v)
    return out


def _fmt(pair): return 'off' if pair is None else f'{pair[0]}:{pair[1]}'


def format_spike(d): return ','.join(f'{k}={_fmt(d[k])}' for k in SPIKE if d.get(k, SPIKE[k]) != SPIKE[k])


def format_service_spike(d):
    return ','.join([f"default={_fmt(d['default'])}"] + [f'{s}={_fmt(p)}' for s, p in sorted(d['services'].items())])


def service_threshold(d, service):
    """(factor, minimum) for one service, or None when its spikes are not reported."""
    s = str(service).lower()
    return d['services'][s] if s in d['services'] else d['default']


def is_spike(value, avg, pair):
    return pair is not None and value is not None and avg is not None and value >= pair[0] * avg and value - avg >= pair[1]


def _pairs_json(d): return {k: None if p is None else dict(factor=p[0], min=p[1]) for k, p in d.items()}


def _pair_in(name, v):
    if v is None or v == 'off': return None
    if isinstance(v, dict): return _pair(name, f"{v.get('factor')}:{v.get('min', 0)}")
    return _pair(name, v)


# ------------------------------------------------------------------ settings
def load(cfg):
    """Notification settings from the server configuration (.env) -> the dict shape used by this module and the page."""
    on = {x.strip() for x in (cfg.alert_events or '').split(',')}
    return dict(
        channels=dict(telegram=dict(enabled=cfg.alert_telegram, bot_token=cfg.telegram_bot_token, chat_id=cfg.alert_telegram_chat_id, api=cfg.telegram_api),
                      discord=dict(enabled=cfg.alert_discord, webhook_url=cfg.discord_webhook_url),
                      email=dict(enabled=cfg.alert_email, host=cfg.smtp_host, port=cfg.smtp_port, security=cfg.smtp_security,
                                 username=cfg.smtp_username, password=cfg.smtp_password, sender=cfg.smtp_from, to=cfg.smtp_to)),
        events={e: e in on for e in EVENTS}, lang=cfg.alert_lang, dashboard_url=cfg.dashboard_url, missing_hour=cfg.alert_missing_hour, summary_hour=cfg.alert_summary_hour,
        spike=parse_spike(cfg.alert_spike), service_spike=parse_service_spike(cfg.alert_service_spike))


def to_fields(d):
    """Inverse of load: settings dict -> {config field: value} (to be written to .env)."""
    c = d['channels']
    t, dc, e = c['telegram'], c['discord'], c['email']
    return dict(alert_telegram=bool(t['enabled']), telegram_bot_token=t['bot_token'], alert_telegram_chat_id=t['chat_id'],
                alert_discord=bool(dc['enabled']), discord_webhook_url=dc['webhook_url'],
                alert_email=bool(e['enabled']), smtp_host=e['host'], smtp_port=int(e['port']), smtp_security=e['security'],
                smtp_username=e['username'], smtp_password=e['password'], smtp_from=e['sender'], smtp_to=e['to'],
                alert_events=','.join(k for k in EVENTS if d['events'].get(k)), alert_lang=d['lang'], dashboard_url=d['dashboard_url'],
                alert_missing_hour=int(d['missing_hour']), alert_summary_hour=int(d['summary_hour']), alert_spike=format_spike(d['spike']), alert_service_spike=format_service_spike(d['service_spike']))


def from_db(cfg, v):
    """Old settings from the account database (app_setting 'alerts', before the move to .env) merged into the current settings."""
    out = load(cfg)
    for ch, d in (v.get('channels') or {}).items():
        if ch in out['channels']: out['channels'][ch].update({k: d[k] for k in d if k in out['channels'][ch]})
    out['events'].update({k: bool(x) for k, x in (v.get('events') or {}).items() if k in EVENTS})
    for k in ('lang', 'dashboard_url', 'missing_hour', 'summary_hour'):
        if k in v: out[k] = v[k]
    return out


def public(cfg):
    """For the browser: credentials only as 'set' (True/False), their values are never returned."""
    out = json.loads(json.dumps(dict(cfg, spike=None, service_spike=None)))
    out['spike'] = _pairs_json(cfg['spike'])
    out['service_spike'] = dict(default=_pairs_json(dict(d=cfg['service_spike']['default']))['d'], services=_pairs_json(cfg['service_spike']['services']))
    out['channels']['telegram'].pop('api', None)   # API address from .env, not a page field
    for ch, keys in SECRETS.items():
        for k in keys: out['channels'][ch][k] = bool(cfg['channels'][ch][k])
    return out


def merge(cfg, body):
    """Merge page input into the settings. Empty credential field = unchanged (not erased); `clear: [channel.field]`
    to erase. -> new settings (validated)."""
    new = json.loads(json.dumps(dict(cfg, spike=None, service_spike=None)))
    new['spike'], new['service_spike'] = dict(cfg['spike']), dict(default=cfg['service_spike']['default'], services=dict(cfg['service_spike']['services']))
    if isinstance(body.get('spike'), dict):
        for k, v in body['spike'].items():
            if k in SPIKE: new['spike'][k] = _pair_in(k, v)
    if isinstance(body.get('service_spike'), dict):
        s = body['service_spike']
        if 'default' in s: new['service_spike']['default'] = _pair_in('all services', s['default'])
        if isinstance(s.get('services'), dict):
            svc = {}
            for name, v in s['services'].items():
                name = str(name).strip().lower()
                if not _SERVICE.fullmatch(name): raise AlertFail(f'"{name[:60]}" is not a service name.')
                svc[name] = _pair_in(name, v)
            new['service_spike']['services'] = svc
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
    if 'summary_hour' in body: new['summary_hour'] = int(body['summary_hour'])
    validate(new)
    return new


def validate(cfg):
    c = cfg['channels']
    if cfg['dashboard_url'] and not re.fullmatch(r'https?://[^\s"<>]+', cfg['dashboard_url']):
        raise AlertFail('Dashboard address must start with http:// or https://.')
    if not 0 <= int(cfg['missing_hour']) <= 23: raise AlertFail('Folder check hour must be 0–23.')
    if not 0 <= int(cfg['summary_hour']) <= 23: raise AlertFail('Daily report hour must be 0–23.')
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
    id=dict(spike='Lonjakan di log {d}', critical='Serangan kritis di log {d}', ingest_failed='Ingest gagal',
            sync_failed='Sinkron S3 bermasalah', backup_failed='Backup gagal', folder_missing='Log tanggal {d} belum datang', summary='Ringkasan log {d}',
            test='Pesan uji MoniShield', test_text='Saluran ini sudah tersambung. Notifikasi berikutnya akan dikirim ke sini.',
            avg='rata-rata {n} hari: {v}', open='Buka', n5xx='Respons 5xx', errors='Error (semua layanan)', upstream_errors='Error koneksi upstream',
            atk_req='Request serangan', attack_ips='IP sumber serangan', login_fail_ips='IP dengan login gagal', requests='Request HTTP',
            crit='{n} request serangan kritis dari {ips} IP. Kategori: {cats}.', newest='Log terbaru: {d}. Periksa kiriman log / sinkron S3.',
            failed_files='{n} file gagal di-parse', run='ingest #{id}', folders='Log tanggal: {list}',
            svc_head='Error per layanan:', svc_more='… dan {n} layanan lain',
            st_ok='AMAN', st_check='PERLU DICEK', st_crit='KRITIS', st_n=' ({n} hal)', status='Status',
            s_sum='Ringkasan', s_vs=' (vs rata-rata {n} hari)', s_check='Perlu dicek', s_ingest='Hasil ingest', s_sys='Sistem',
            warn='Warning / 4xx app', attacks='Serangan', atk_line='{n} request · {ips} IP · {crit} kritis', login_ips='IP login gagal',
            c_spike='{what} naik: {v} (×{f} rata-rata)', c_crit='{n} request serangan kritis{cats}', c_corrupt='{n} file log rusak',
            c_partial='Data belum lengkap: {pct}% dari rata-rata baris', c_backup='Backup gagal', c_sync='Sinkron S3 bermasalah',
            c_r5='Respons 5xx {p}: server sering gagal menjawab', svc_err='Error {s}',
            i_s3='S3 {d}: {files} file · {lines} baris · {secs} dtk', i_full='Kelengkapan {pct}% dari rata-rata', i_corrupt='{n} file rusak',
            i_kafka='Kafka {d}: {files} file · {lines} baris', i_kafka_none='Kafka {d}: belum ada data',
            b_ok='Backup {d}: berhasil ✅ · {size}', b_fail='Backup {d}: gagal ❌', b_none='Backup: belum ada',
            y_ok='Sinkron S3: OK ✅', y_fail='Sinkron S3: bermasalah ❌', y_off='Sinkron S3: mati',
            k_ok='Kafka: tersambung ✅', k_bad='Kafka: {state} ❌', k_off='Kafka: tidak dipakai',
            k_state=dict(connecting='menyambung', error='error', off='mati'),
            short_sum='Request {req} · 5xx {r5} · Error {err} · Serangan {atk} ({crit} kritis)', short_ing='Ingest S3 {files} file{full}',
            short_full=', lengkap', short_sys='Backup {b} · Sinkron S3 {y}', ok_word='berhasil ✅', fail_word='gagal ❌', sync_ok='OK ✅',
            sync_bad='bermasalah ❌', none_word='belum ada', off_word='mati'),
    en=dict(spike='Spike in the logs of {d}', critical='Critical attacks in the logs of {d}', ingest_failed='Ingest failed',
            sync_failed='S3 sync problem', backup_failed='Backup failed', folder_missing='Logs of {d} have not arrived', summary='Summary of the logs of {d}',
            test='MoniShield test message', test_text='This channel is connected. Future notifications will be sent here.',
            avg='{n}-day average: {v}', open='Open', n5xx='5xx responses', errors='Errors (all services)', upstream_errors='Upstream connection errors',
            atk_req='Attack requests', attack_ips='Attack source IPs', login_fail_ips='IPs with failed logins', requests='HTTP requests',
            crit='{n} critical attack requests from {ips} IPs. Categories: {cats}.', newest='Newest logs: {d}. Check log delivery / S3 sync.',
            failed_files='{n} files failed to parse', run='ingest #{id}', folders='Log days: {list}',
            svc_head='Errors per service:', svc_more='… and {n} more services',
            st_ok='ALL CLEAR', st_check='NEEDS A LOOK', st_crit='CRITICAL', st_n=' ({n} items)', status='Status',
            s_sum='Summary', s_vs=' (vs {n}-day average)', s_check='Needs a look', s_ingest='Ingest result', s_sys='System',
            warn='Warnings / 4xx app', attacks='Attacks', atk_line='{n} requests · {ips} IPs · {crit} critical', login_ips='IPs with failed logins',
            c_spike='{what} up: {v} (×{f} the average)', c_crit='{n} critical attack requests{cats}', c_corrupt='{n} corrupt log file(s)',
            c_partial='Data incomplete: {pct}% of the average lines', c_backup='Backup failed', c_sync='S3 sync problem',
            c_r5='5xx responses {p}: the server often fails to answer', svc_err='Errors in {s}',
            i_s3='S3 {d}: {files} files · {lines} lines · {secs} s', i_full='Completeness {pct}% of the average', i_corrupt='{n} corrupt file(s)',
            i_kafka='Kafka {d}: {files} files · {lines} lines', i_kafka_none='Kafka {d}: no data yet',
            b_ok='Backup {d}: succeeded ✅ · {size}', b_fail='Backup {d}: failed ❌', b_none='Backup: none yet',
            y_ok='S3 sync: OK ✅', y_fail='S3 sync: problem ❌', y_off='S3 sync: off',
            k_ok='Kafka: connected ✅', k_bad='Kafka: {state} ❌', k_off='Kafka: not used',
            k_state=dict(connecting='connecting', error='error', off='off'),
            short_sum='Requests {req} · 5xx {r5} · Errors {err} · Attacks {atk} ({crit} critical)', short_ing='Ingest S3 {files} files{full}',
            short_full=', complete', short_sys='Backup {b} · S3 sync {y}', ok_word='succeeded ✅', fail_word='failed ❌', sync_ok='OK ✅',
            sync_bad='problem ❌', none_word='none yet', off_word='off'))


def _t(cfg, k, **p): return T[cfg['lang'] if cfg['lang'] in T else 'id'][k].format(**p)


def _num(v, lang): return f'{v:,.0f}'.replace(',', '.' if lang == 'id' else ',') if isinstance(v, (int, float)) else str(v)


def _day(folder):
    """Folder name -> the day its logs cover (an S3/Kafka folder D holds (D-1 00:00, D 00:00] WIB). Messages name that day, like the
    dashboard; links keep the folder name."""
    try: return (datetime.date.fromisoformat(str(folder)) - datetime.timedelta(days=1)).isoformat()
    except ValueError: return str(folder)


def _link(cfg, folder, tab='command-center', source='s3'):
    src = '' if source == 's3' else f'&source={source}'   # the link opens the same data source as the message
    return f"\n{_t(cfg, 'open')}: {cfg['dashboard_url'].rstrip('/')}/{tab}?folder={folder}{src}" if cfg['dashboard_url'] else ''


# ------------------------------------------------------------------ evaluation
def _spikes(cfg, facts):
    """-> (kpi spikes [(key, value, average)], service spikes [(service, errors, average)]) by the configured thresholds."""
    a, b = facts['kpi'], facts['base']
    vals, avgs = dict(a['kpi'], atk_req=a['atk_req']), dict(b['kpi'], atk_req=b['atk_req'])
    kpi = [(k, vals.get(k), avgs.get(k)) for k in SPIKE if is_spike(vals.get(k), avgs.get(k), cfg['spike'].get(k))]
    svc = sorted(((e - b['svc'][s], s, e, b['svc'][s]) for s, (e, _) in (a.get('svc') or {}).items()
                  if is_spike(e, (b.get('svc') or {}).get(s), service_threshold(cfg['service_spike'], s))), reverse=True)
    return kpi, [(s, e, m) for _, s, e, m in svc]


def folder_events(cfg, folder, facts, source='s3'):
    """Events for one folder: [(event, key, title, text)]. facts = the folder's aggregate numbers (no IPs), from the warehouse:
    dict(kpi=<Command Center KPI>, base=<average baseline>, ngx_keys=<ingress KPI keys>, crit_cats=[top categories]).
    The daily summary is built separately (`summary`), with the ingest and system facts the application layer adds."""
    a, b, ngx_keys = facts['kpi'], facts['base'], facts['ngx_keys']
    lang, out, lines = cfg['lang'], [], []
    kpi, svc = _spikes(cfg, facts)
    for k, v, m in kpi:
        n = b['n_nginx'] if k in ngx_keys or k == 'atk_req' else b['n_all']
        fac_txt = f'; ×{v / m:.1f}' if m else ''
        lines.append(f"• {_t(cfg, k)}: {_num(v, lang)} ({_t(cfg, 'avg', n=n, v=_num(m, lang))}{fac_txt})")
    # errors per service, each against its own average and threshold (largest increase first)
    if svc:
        lines.append(_t(cfg, 'svc_head'))
        for s, e, m in svc[:MAX_SERVICE_LINES]:
            fac_txt = f'; ×{e / m:.1f}' if m else ''
            lines.append(f"• {s}: {_num(e, lang)} ({_t(cfg, 'avg', n=b['n_all'], v=_num(m, lang))}{fac_txt})")
        if len(svc) > MAX_SERVICE_LINES: lines.append(_t(cfg, 'svc_more', n=len(svc) - MAX_SERVICE_LINES))
    if lines and cfg['events']['spike']:
        out.append(('spike', f'spike:{folder}', _t(cfg, 'spike', d=_day(folder)), '\n'.join(lines) + _link(cfg, folder, source=source)))
    if a['crit_req'] and cfg['events']['critical']:
        text = _t(cfg, 'crit', n=_num(a['crit_req'], lang), ips=_num(a['kpi']['attack_ips'], lang), cats=', '.join(facts['crit_cats']) or '-')
        out.append(('critical', f'critical:{folder}', _t(cfg, 'critical', d=_day(folder)), text + _link(cfg, folder, 'security', source)))
    return out


# ------------------------------------------------------------------ daily report (event 'summary')
KEYCAPS = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣']
MAX_CHECKS = 6
CRIT_5XX, MIN_REQUESTS, PARTIAL = 0.05, 50, 50   # 5xx rate that is critical; requests a rate needs; % of average lines that is "incomplete"


def _dec(x, digits, lang):
    s = f'{x:.{digits}f}'
    return s.replace('.', ',') if lang == 'id' else s


def _change(v, avg, lang):
    """' (▲ 41%)' / ' (▼ 3%)' / ' (≈)' against the average; '' without one."""
    if v is None or not avg: return ''
    p = (v - avg) / avg * 100
    return ' (≈)' if abs(p) < 5 else f" ({'▲' if p > 0 else '▼'} {abs(p):.0f}%)"


def _size(n, lang):
    for u in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or u == 'TB': return f"{_dec(n, 0 if u == 'B' else 1, lang)} {u}"
        n /= 1024


def summary_key(folder): return f'summary:{folder}'   # one daily report per folder (per source: see alert_service._named)


def summary(cfg, folder, facts, extra, source='s3'):
    """Daily report of one folder -> (key, title, text), or None when the event is off.
    facts: folder_facts() of the folder plus files, warn, lines_avg. extra (from the application layer, all optional):
    seconds (ingest run), kafka=dict(files, lines) | None, backup=dict(ok, day, bytes) | None,
    sync=dict(enabled, ok), kafka_state='running'|'connecting'|'error'|'off'|None (None = Kafka not configured)."""
    if not cfg['events']['summary']: return None
    lang, a, b = cfg['lang'], facts['kpi'], facts['base']
    k, m, day = a['kpi'], b['kpi'], _day(folder)
    n = lambda v: _num(v, lang)
    req, n5 = k.get('requests'), k.get('n5xx')
    r5 = n5 / req if req else None
    r5_txt = f"{_dec(r5 * 100, 2, lang)}%" if r5 is not None else '–'
    lines, lines_avg = a.get('lines') or 0, facts.get('lines_avg')
    pct = round(lines / lines_avg * 100) if lines_avg else None

    # what needs a look
    checks, crit = [], False
    if r5 is not None and req >= MIN_REQUESTS and r5 >= CRIT_5XX:
        checks.append(_t(cfg, 'c_r5', p=r5_txt)); crit = True
    kspikes, sspikes = _spikes(cfg, facts)
    for key, v, avg in kspikes:
        if key == 'n5xx' and crit: continue
        checks.append(_t(cfg, 'c_spike', what=_t(cfg, key), v=n(v), f=_dec(v / avg, 1, lang) if avg else '–'))
    for s, e, avg in sspikes:
        checks.append(_t(cfg, 'c_spike', what=_t(cfg, 'svc_err', s=s), v=n(e), f=_dec(e / avg, 1, lang) if avg else '–'))
    if a['crit_req']:
        cats = facts.get('crit_cats') or []
        checks.append(_t(cfg, 'c_crit', n=n(a['crit_req']), cats=': ' + ', '.join(cats) if cats else '')); crit = True
    if a.get('corrupt'): checks.append(_t(cfg, 'c_corrupt', n=n(a['corrupt'])))
    if pct is not None and pct < PARTIAL: checks.append(_t(cfg, 'c_partial', pct=pct))
    bk, sy = extra.get('backup'), extra.get('sync') or {}
    if bk and not bk.get('ok'): checks.append(_t(cfg, 'c_backup'))
    if sy.get('enabled') and sy.get('ok') is False: checks.append(_t(cfg, 'c_sync'))
    level = 'crit' if crit else 'check' if checks else 'ok'
    head = (f"{dict(ok='🟢', check='🟡', crit='🔴')[level]} {_t(cfg, 'status')}: **{_t(cfg, 'st_' + level)}"
            + (_t(cfg, 'st_n', n=len(checks)) if checks else '') + '**')
    link = _link(cfg, folder, source=source).replace('\n', '\n🔗 ', 1)
    title = _t(cfg, 'summary', d=day)

    backup_word = (_t(cfg, 'ok_word') if bk and bk.get('ok') else _t(cfg, 'fail_word') if bk else _t(cfg, 'none_word'))
    sync_word = (_t(cfg, 'off_word') if not sy.get('enabled') else _t(cfg, 'sync_ok') if sy.get('ok') is not False else _t(cfg, 'sync_bad'))
    if level == 'ok':   # short version: nothing needs a look
        body = [head, '',
                '📊 ' + _t(cfg, 'short_sum', req=n(req) if req is not None else '–', r5=r5_txt, err=n(k.get('errors')), atk=n(a['atk_req']), crit=n(a['crit_req'])),
                '📥 ' + _t(cfg, 'short_ing', files=n(facts.get('files', 0)), full=_t(cfg, 'short_full') if pct is None or pct >= 90 else f' · {pct}%'),
                '⚙️ ' + _t(cfg, 'short_sys', b=backup_word, y=sync_word)]
        return summary_key(folder), title, '\n'.join(body) + link

    body = [head, '', f"**📊 {_t(cfg, 's_sum')}**" + (_t(cfg, 's_vs', n=b['n_all']) if b.get('n_all') else '')]
    if req is not None:
        body.append(f"🌐 {_t(cfg, 'requests')}: {n(req)}{_change(req, m.get('requests'), lang)}")
        body.append(f"💥 {_t(cfg, 'n5xx')}: {n(n5)} · {r5_txt}{_change(n5, m.get('n5xx'), lang)}")
    body.append(f"❌ {_t(cfg, 'errors')}: {n(k.get('errors'))}{_change(k.get('errors'), m.get('errors'), lang)}")
    if facts.get('warn') is not None: body.append(f"🟠 {_t(cfg, 'warn')}: {n(facts['warn'])}")
    body.append(f"🚨 {_t(cfg, 'attacks')}: " + _t(cfg, 'atk_line', n=n(a['atk_req']), ips=n(k.get('attack_ips')), crit=n(a['crit_req'])))
    body.append(f"🔑 {_t(cfg, 'login_ips')}: {n(k.get('login_fail_ips'))}")
    body += ['', f"**👀 {_t(cfg, 's_check')}**"] + [f'{KEYCAPS[i]} {c}' for i, c in enumerate(checks[:MAX_CHECKS])]
    secs = extra.get('seconds')
    body += ['', f"**📥 {_t(cfg, 's_ingest')}**",
             '🪣 ' + _t(cfg, 'i_s3', d=day, files=n(facts.get('files', 0)), lines=n(lines), secs=_dec(secs, 1, lang) if secs is not None else '–')]
    full = [_t(cfg, 'i_full', pct=pct)] if pct is not None else []
    if a.get('corrupt'): full.append(_t(cfg, 'i_corrupt', n=n(a['corrupt'])))
    if full: body.append('🧩 ' + ' · '.join(full))
    if 'kafka' in extra:
        kf = extra['kafka']
        body.append('📨 ' + (_t(cfg, 'i_kafka', d=day, files=n(kf['files']), lines=n(kf['lines'])) if kf else _t(cfg, 'i_kafka_none', d=day)))
    body += ['', f"**⚙️ {_t(cfg, 's_sys')}**",
             '💾 ' + (_t(cfg, 'b_ok', d=bk['day'], size=_size(bk.get('bytes') or 0, lang)) if bk and bk.get('ok')
                     else _t(cfg, 'b_fail', d=bk['day']) if bk else _t(cfg, 'b_none')),
             '🔄 ' + (_t(cfg, 'y_off') if not sy.get('enabled') else _t(cfg, 'y_ok') if sy.get('ok') is not False else _t(cfg, 'y_fail'))]
    ks = extra.get('kafka_state')
    if ks is not None:
        body.append('📡 ' + (_t(cfg, 'k_ok') if ks == 'running' else _t(cfg, 'k_off') if ks == 'off'
                             else _t(cfg, 'k_bad', state=T[lang if lang in T else 'id']['k_state'].get(ks, ks))))
    return summary_key(folder), title, '\n'.join(body) + link


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
    if res.get('failed'): lines.append(_t(cfg, 'folders', list=', '.join(_day(f) for f in res['failed'])))
    return f"sync_failed:{res.get('at')}", _t(cfg, 'sync_failed'), '\n'.join(lines)


def folder_missing(cfg, now_wib, newest):
    """Folder dated today (WIB) still missing after `missing_hour` -> (key, title, text) or None."""
    if not cfg['events']['folder_missing'] or now_wib.hour < int(cfg['missing_hour']): return None
    today = now_wib.date().isoformat()
    if newest is None or str(newest) >= today: return None
    return f'folder_missing:{today}', _t(cfg, 'folder_missing', d=_day(today)), _t(cfg, 'newest', d=_day(newest))


def report_due(cfg, now_wib):
    """Is the scheduled daily report due? (event on and the report hour reached, WIB)"""
    return bool(cfg['events']['summary']) and now_wib.hour >= int(cfg['summary_hour'])


def report_target(s3_newest, kafka_folders, today_local):
    """Folder of the scheduled daily report -> (folder, source) or None. S3 when it has data (an S3 folder arrives complete);
    otherwise the newest complete Kafka folder: dated today or earlier (the folder dated tomorrow is still filling up)."""
    if s3_newest: return s3_newest, 's3'
    done = [f for f in kafka_folders if f <= today_local.isoformat()]
    return (max(done), 'kafka') if done else None


def active(cfg): return bool(cfg) and any(c['enabled'] for c in cfg['channels'].values())


TEST_NEEDS = dict(telegram=('bot_token', 'chat_id'), discord=('webhook_url',), email=('host', 'sender', 'to'))


def backup_failed(cfg, day, error):
    """Daily backup failed -> (key, title, text) or None. Once per day; the text is the error (no data, no IPs)."""
    if not cfg['events'].get('backup_failed'): return None
    return f'backup_failed:{day}', _t(cfg, 'backup_failed'), error
