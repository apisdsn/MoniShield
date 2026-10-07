"""Notifikasi ke Telegram, Discord, dan email (permintaan pemilik 2026-10-07: "cukup isi kredensialnya").

Setelan (saluran + kredensialnya, kejadian yang dikirim, bahasa, alamat dashboard) diisi admin dari layar Notifikasi dan
disimpan di basis data akun (app_setting 'alerts'). Kredensial (token bot, URL webhook, sandi SMTP) TIDAK pernah dikirim
balik ke browser; hanya "sudah diisi".

ATURAN PROYEK: alamat IP pengguna tidak boleh dikirim ke layanan pihak ketiga. Pesan disusun dari angka agregat (jumlah
request, jumlah IP, kategori), tanpa alamat IP; sebagai pengaman terakhir setiap pola alamat IPv4/IPv6 diganti "[IP]"
sebelum dikirim (`scrub`).

Kejadian:
  spike           angka folder baru ≥ 2× rata-rata folder sebanding (Command Center `baseline`) dan bertambah minimal N
  critical        ada request serangan berkeparahan kritis di folder baru
  ingest_failed   ingest gagal atau ada file yang gagal di-parse
  sync_failed     pemeriksaan sinkron S3 berakhir dengan galat / folder gagal
  folder_missing  folder log hari ini belum ada setelah jam tertentu (WIB)
  summary         ringkasan tiap folder baru (bawaan mati)
Satu kejadian dikirim sekali per kunci (mis. 'spike:2026-10-06'); dicatat di tabel alert_log (riwayat di layar).
"""
import datetime, json, re, smtplib, ssl, threading, urllib.error, urllib.parse, urllib.request
from email.message import EmailMessage

TELEGRAM_API = 'https://api.telegram.org'   # diganti di uji (server tiruan lokal)
DISCORD_HOSTS = ('discord.com', 'discordapp.com', 'ptb.discord.com', 'canary.discord.com')
TIMEOUT = 15
EVENTS = ('spike', 'critical', 'ingest_failed', 'sync_failed', 'folder_missing', 'summary')
DEFAULT = dict(
    channels=dict(telegram=dict(enabled=False, bot_token='', chat_id=''),
                  discord=dict(enabled=False, webhook_url=''),
                  email=dict(enabled=False, host='', port=587, security='starttls', username='', password='', sender='', to='')),
    events=dict(spike=True, critical=True, ingest_failed=True, sync_failed=True, folder_missing=True, summary=False),
    lang='id', dashboard_url='', missing_hour=10)
SECRETS = {'telegram': ('bot_token',), 'discord': ('webhook_url',), 'email': ('password',)}
# ambang lonjakan per angka: (kali rata-rata, tambahan minimal)
SPIKE = dict(n5xx=(2, 20), errors=(2, 100), upstream_errors=(2, 20), atk_req=(2, 20), attack_ips=(2, 3), login_fail_ips=(2, 5))

# IPv4; IPv6 lengkap (8 kelompok) atau ringkas (memuat '::'). Jam seperti 10:00:59 tidak cocok.
_IP = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}\b|(?:[0-9a-f]{1,4}:){1,7}:(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4}){0,6})?|::(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4}){0,6})', re.I)


def scrub(text):
    """Pengaman terakhir aturan "IP tidak ke pihak ketiga": semua pola alamat IP diganti [IP]."""
    return _IP.sub('[IP]', text)


class AlertFail(Exception):
    pass


# ------------------------------------------------------------------ setelan
def load(auth):
    """Setelan tersimpan digabung dengan bawaan (kunci baru otomatis ada)."""
    st = auth.setting_get('alerts')
    cfg = json.loads(json.dumps(DEFAULT))
    if st:
        v = st['value']
        for ch, d in (v.get('channels') or {}).items():
            if ch in cfg['channels']: cfg['channels'][ch].update({k: d[k] for k in d if k in cfg['channels'][ch]})
        cfg['events'].update({k: bool(x) for k, x in (v.get('events') or {}).items() if k in EVENTS})
        for k in ('lang', 'dashboard_url', 'missing_hour'):
            if k in v: cfg[k] = v[k]
    return cfg


def public(cfg):
    """Untuk browser: kredensial hanya 'sudah diisi' (True/False), nilainya tidak pernah dikembalikan."""
    out = json.loads(json.dumps(cfg))
    for ch, keys in SECRETS.items():
        for k in keys: out['channels'][ch][k] = bool(cfg['channels'][ch][k])
    return out


def merge(cfg, body):
    """Gabungkan isian layar ke setelan. Kolom kredensial kosong = tetap (tidak terhapus); `clear: [saluran.kolom]`
    untuk menghapus. -> setelan baru (sudah diperiksa)."""
    new = json.loads(json.dumps(cfg))
    for ch, d in (body.get('channels') or {}).items():
        if ch not in new['channels'] or not isinstance(d, dict): continue
        for k, v in d.items():
            if k not in new['channels'][ch]: continue
            if k in SECRETS.get(ch, ()) and (v is None or v == '' or v is True): continue   # kosong / "sudah diisi" = tidak diubah
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
        raise AlertFail('Alamat dashboard harus diawali http:// atau https://.')
    if not 0 <= int(cfg['missing_hour']) <= 23: raise AlertFail('Jam pemeriksaan folder harus 0–23.')
    t = c['telegram']
    t['bot_token'], t['chat_id'] = str(t['bot_token']).strip(), str(t['chat_id']).strip()
    if t['bot_token'] and not re.fullmatch(r'\d{5,15}:[A-Za-z0-9_-]{20,80}', t['bot_token']):
        raise AlertFail('Token bot Telegram tidak berbentuk 123456789:ABC… (dari @BotFather).')
    if t['chat_id'] and not re.fullmatch(r'-?\d{3,20}|@[A-Za-z][A-Za-z0-9_]{4,31}', t['chat_id']):
        raise AlertFail('Chat ID Telegram harus angka (mis. -1001234567890) atau @nama_kanal.')
    if t['enabled'] and not (t['bot_token'] and t['chat_id']): raise AlertFail('Telegram aktif tetapi token bot / chat ID belum diisi.')
    d = c['discord']
    d['webhook_url'] = str(d['webhook_url']).strip()
    if d['webhook_url']:
        u = urllib.parse.urlsplit(d['webhook_url'])
        if u.scheme != 'https' or u.hostname not in DISCORD_HOSTS or not u.path.startswith('/api/webhooks/'):
            raise AlertFail('URL webhook Discord harus https://discord.com/api/webhooks/… (Pengaturan kanal → Integrasi → Webhook).')
    if d['enabled'] and not d['webhook_url']: raise AlertFail('Discord aktif tetapi URL webhook belum diisi.')
    e = c['email']
    for k in ('host', 'username', 'sender', 'to'): e[k] = str(e[k] or '').strip()
    e['port'] = int(e['port'] or 0)
    if e['security'] not in ('starttls', 'ssl', 'none'): raise AlertFail('Keamanan SMTP harus starttls, ssl, atau none.')
    if e['host'] and not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', e['host']): raise AlertFail('Server SMTP tidak sah.')
    if e['to'] and not all(re.fullmatch(r'[^@\s,]+@[^@\s,]+\.[^@\s,]+', x.strip()) for x in e['to'].split(',') if x.strip()):
        raise AlertFail('Penerima email harus alamat email, dipisah koma.')
    if e['enabled'] and not (e['host'] and 1 <= e['port'] <= 65535 and e['sender'] and e['to']):
        raise AlertFail('Email aktif tetapi server SMTP / port / pengirim / penerima belum lengkap.')


# ------------------------------------------------------------------ kirim
def _post_json(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'User-Agent': 'MoniShield'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r: return r.status
    except urllib.error.HTTPError as x:
        raise AlertFail(f'ditolak HTTP {x.code}') from None
    except (urllib.error.URLError, OSError) as x:
        raise AlertFail(f'tidak terjangkau ({type(getattr(x, "reason", x)).__name__})') from None


def send_telegram(ch, title, text):
    _post_json(f"{TELEGRAM_API}/bot{ch['bot_token']}/sendMessage",
               dict(chat_id=ch['chat_id'], text=f'{title}\n\n{text}'[:4000], disable_web_page_preview=True))


def send_discord(ch, title, text):
    _post_json(ch['webhook_url'], dict(content=f'**{title}**\n{text}'[:1990], allowed_mentions=dict(parse=[])))


def send_email(ch, title, text):
    m = EmailMessage()
    m['Subject'], m['From'], m['To'] = title, ch['sender'], ', '.join(x.strip() for x in ch['to'].split(',') if x.strip())
    m.set_content(text)
    try:
        ctx = ssl.create_default_context()
        cls = smtplib.SMTP_SSL if ch['security'] == 'ssl' else smtplib.SMTP
        kw = dict(context=ctx) if ch['security'] == 'ssl' else {}
        with cls(ch['host'], ch['port'], timeout=TIMEOUT, **kw) as s:
            if ch['security'] == 'starttls': s.starttls(context=ctx)
            if ch['username']: s.login(ch['username'], ch['password'])
            s.send_message(m)
    except smtplib.SMTPAuthenticationError:
        raise AlertFail('SMTP menolak nama pengguna / sandi') from None
    except (smtplib.SMTPException, OSError) as x:
        raise AlertFail(f'SMTP gagal ({type(x).__name__})') from None


SENDERS = dict(telegram=send_telegram, discord=send_discord, email=send_email)


def deliver(auth, cfg, key, event, title, text, channels=None, force=False):
    """Kirim ke semua saluran aktif (atau `channels`). Sudah pernah berhasil untuk `key` -> dilewati (kecuali force).
    -> {saluran: None (berhasil) | pesan galat}. Galat tidak pernah memuat kredensial."""
    if not force and auth.alert_seen(key): return {}
    title, text = scrub(title), scrub(text)
    out = {}
    for name, ch in cfg['channels'].items():
        if (channels and name not in channels) or (not channels and not ch['enabled']): continue
        try: SENDERS[name](ch, title, text); out[name] = None
        except AlertFail as e: out[name] = str(e)
        except Exception as e: out[name] = type(e).__name__   # noqa: BLE001
        auth.alert_add(key, event, name, out[name] is None, summary=title, error=out[name])
    return out


# ------------------------------------------------------------------ teks (dua bahasa; nama metrik dari kamus kecil ini)
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


# ------------------------------------------------------------------ penilaian
def folder_events(cur, cfg, folder, crs):
    """Kejadian untuk satu folder: [(event, key, judul, teks)]. Angka dari Command Center (agregat), tanpa IP."""
    from .api import command
    a = command._kpi(cur, folder, crs)
    b = command.baseline(cur, folder, crs, a)
    lang, out = cfg['lang'], []
    vals = dict(a['kpi'], atk_req=a['atk_req'])
    avgs = dict(b['kpi'], atk_req=b['atk_req'])
    lines = []
    for k, (fac, add) in SPIKE.items():
        v, m = vals.get(k), avgs.get(k)
        if v is None or m is None: continue
        if v >= fac * m and v - m >= add:
            n = b['n_nginx'] if k in command.NGX_KEYS or k == 'atk_req' else b['n_all']
            fac_txt = f'; ×{v / m:.1f}' if m else ''
            lines.append(f"• {_t(cfg, k)}: {_num(v, lang)} ({_t(cfg, 'avg', n=n, v=_num(m, lang))}{fac_txt})")
    if lines and cfg['events']['spike']:
        out.append(('spike', f'spike:{folder}', _t(cfg, 'spike', d=folder), '\n'.join(lines) + _link(cfg, folder)))
    if a['crit_req'] and cfg['events']['critical']:
        U = 'agg_crs_url' if crs else 'agg_attack_url'
        cats = [r[0] for r in cur.execute(f"""SELECT category, sum(hits) h FROM {U} WHERE folder = ? AND {'severity' if crs else '1'} = 3
                                               GROUP BY 1 ORDER BY h DESC LIMIT 3""", [folder]).fetchall()] if crs else []
        text = _t(cfg, 'crit', n=_num(a['crit_req'], lang), ips=_num(a['kpi']['attack_ips'], lang), cats=', '.join(cats) or '-')
        out.append(('critical', f'critical:{folder}', _t(cfg, 'critical', d=folder), text + _link(cfg, folder, 'keamanan')))
    if cfg['events']['summary']:
        rows = [f"• {_t(cfg, k)}: {_num(vals[k], lang)}" for k in ('requests', 'n5xx', 'errors', 'atk_req', 'attack_ips', 'login_fail_ips') if vals.get(k) is not None]
        out.append(('summary', f'summary:{folder}', _t(cfg, 'summary', d=folder), '\n'.join(rows) + _link(cfg, folder)))
    return out


class Notifier:
    """Dipanggil IngestManager / ImportManager sesudah pekerjaan selesai, dan penjadwal tiap jam (folder belum datang).
    Semua pengiriman di thread latar: ingest dan layar tidak pernah menunggu Telegram/SMTP."""

    def __init__(self, app):
        self.app, self._lock = app, threading.Lock()

    def _cfg(self):
        try: return load(self.app.state.auth)
        except Exception: return None   # noqa: BLE001  basis data akun belum siap

    def _bg(self, fn, *a):
        threading.Thread(target=self._safe, args=(fn, *a), name='alerts', daemon=True).start()

    def _safe(self, fn, *a):
        with self._lock:
            try: fn(*a)
            except Exception: pass   # noqa: BLE001  notifikasi tidak boleh menjatuhkan server; galat kirim tercatat di alert_log

    def active(self, cfg): return cfg and any(c['enabled'] for c in cfg['channels'].values())

    def after_ingest(self, result, error=None): self._bg(self._after_ingest, result, error)

    def _after_ingest(self, result, error):
        cfg = self._cfg()
        if not self.active(cfg): return
        auth = self.app.state.auth
        if (error or (result and result.get('files_failed'))) and cfg['events']['ingest_failed']:
            rid = (result or {}).get('run_id', '?')
            text = '\n'.join(x for x in [_t(cfg, 'run', id=rid), error or '', _t(cfg, 'failed_files', n=result['files_failed']) if result and result.get('files_failed') else ''] if x)
            deliver(auth, cfg, f'ingest_failed:{rid}', 'ingest_failed', _t(cfg, 'ingest_failed'), text)
        if error or not result: return
        changed = sorted(result.get('folders_changed') or [])
        if not changed: return
        cur = self.app.state.con.cursor()
        try:
            newest = str(cur.execute('SELECT max(folder) FROM folder_state').fetchone()[0])
            floor = (datetime.date.fromisoformat(newest) - datetime.timedelta(days=2)).isoformat()
            crs = self.app.state.cfg.attack_rules == 'crs'
            for f in (x for x in changed if x >= floor):   # folder lama yang di-ingest ulang tidak memicu notifikasi
                for ev, key, title, text in folder_events(cur, cfg, f, crs): deliver(auth, cfg, key, ev, title, text)
        finally: cur.close()

    def after_sync(self, res): self._bg(self._after_sync, res)

    def _after_sync(self, res):
        cfg = self._cfg()
        if not self.active(cfg) or not cfg['events']['sync_failed'] or not (res.get('errors') or res.get('failed')): return
        lines = [f"• {e.get('where') + ': ' if e.get('where') else ''}{e.get('message', '')}" for e in res.get('errors', [])]
        if res.get('failed'): lines.append(_t(cfg, 'folders', list=', '.join(res['failed'])))
        deliver(self.app.state.auth, cfg, f"sync_failed:{res.get('at')}", 'sync_failed', _t(cfg, 'sync_failed'), '\n'.join(lines))

    def check_missing(self, now_utc=None):
        """Folder bertanggal hari ini (WIB) belum ada setelah `missing_hour` -> sekali per hari."""
        cfg = self._cfg()
        if not self.active(cfg) or not cfg['events']['folder_missing']: return None
        wib = (now_utc or datetime.datetime.now(datetime.timezone.utc)) + datetime.timedelta(hours=7)
        if wib.hour < int(cfg['missing_hour']): return None
        today = wib.date().isoformat()
        cur = self.app.state.con.cursor()
        try: newest = cur.execute('SELECT max(folder) FROM folder_state').fetchone()[0]
        finally: cur.close()
        if newest is None or str(newest) >= today: return None
        return deliver(self.app.state.auth, cfg, f'folder_missing:{today}', 'folder_missing', _t(cfg, 'folder_missing', d=today), _t(cfg, 'newest', d=str(newest)))

    def start(self):
        self._stop = threading.Event()
        def loop():
            while not self._stop.wait(3600):
                self._safe(self.check_missing)
        threading.Thread(target=loop, name='alerts-hourly', daemon=True).start()

    def stop(self):
        if getattr(self, '_stop', None): self._stop.set()
