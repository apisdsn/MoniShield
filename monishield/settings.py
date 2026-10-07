"""Layar Konfigurasi -> file .env (permintaan pemilik 2026-10-07: "ubah semua yang berbau configuration … ke dalam .env").

Semua setelan yang bisa diubah dari layar (kredensial AWS + wilayah, MaxMind, pengecualian daftar blokir, folder induk S3
otomatis, notifikasi) DISIMPAN KE FILE .env — satu sumber kebenaran yang juga dibaca CLI dan Docker. Sesudah ditulis,
nilainya langsung ditimpakan ke objek konfigurasi server yang sedang berjalan, jadi tidak perlu mulai ulang.

Rahasia tidak pernah dikirim balik ke browser: hanya "sudah diisi" + sumbernya (Access Key ID / Account ID tersamar).
Variabel lingkungan proses yang BERBEDA dari .env mengalahkan .env saat server dimulai (config.load); layar menandainya
(sumber 'environment') agar admin tahu nilai layar tidak akan bertahan setelah mulai ulang.
Yang TIDAK bisa diubah dari layar (dasar keamanan server): S4_JWT_SECRET, S4_JOB_TOKEN, S4_AUTH_DATABASE_URL,
S4_ADMIN_PASSWORD, S4_IMPORT_BUCKETS — layar hanya menampilkan statusnya.

Setelan lama yang dulu disimpan di basis data akun (app_setting 'config' / 'alerts' / 's3_watch') dipindah sekali ke .env
saat server mulai (`migrate`).
"""
import ipaddress, os, re

from . import alerts, config, envfile

GROUPS = {
    'aws': ('aws_access_key_id', 'aws_secret_access_key', 'aws_session_token', 'import_region'),
    'maxmind': ('maxmind_account_id', 'maxmind_license_key'),
    'blocklist': ('blocklist_exclude', 'blocklist_exclude_org'),
    'watch': ('s3_watch', 's3_watch_minutes', 's3_watch_enabled'),
    'alerts': tuple(alerts.to_fields(alerts.load(config.Config()))),
}
SCREEN = {k for g in ('aws', 'maxmind', 'blocklist') for k in GROUPS[g]}   # PUT /api/admin/config
SECRET = set(config.SECRETS)
MASKED = ('aws_access_key_id', 'maxmind_account_id')
ENV_ONLY = ('jwt_secret', 'job_token', 'auth_database_url', 'admin_password')   # hanya status terisi/kosong
BASE = config.Config()


class SettingsFail(Exception):
    def __init__(self, message, code='invalid_config'):
        super().__init__(message); self.code = code


def env_path(app): return app.state.env_path


def file_values(app):
    try: return config.read_dotenv(env_path(app))
    except SystemExit: return {}


def source(field, fv):
    """'environment' (variabel lingkungan proses mengalahkan .env) | 'file' (.env) | None (nilai bawaan)."""
    name = config.env_name(field)
    if name in os.environ and os.environ[name] != fv.get(name): return 'environment'
    return 'file' if name in fv else None


def _mask(v):
    return f'{v[:4]}…{v[-4:]}' if v and len(v) > 10 else ('••••' if v else '')


def view(app):
    """Untuk browser: nilai non-rahasia apa adanya; rahasia hanya {set, source[, masked]}."""
    cfg, fv, out = app.state.cfg, file_values(app), {}
    for grp in ('aws', 'maxmind', 'blocklist'):
        for k in GROUPS[grp]:
            item = dict(set=bool(getattr(cfg, k))) if k in SECRET else dict(value=getattr(cfg, k))
            if k in MASKED: item['masked'] = _mask(getattr(cfg, k))
            item.update(source=source(k, fv), env=config.env_name(k))
            out.setdefault(grp, {})[k] = item
    out['server'] = {k: bool(getattr(cfg, k)) for k in ENV_ONLY}
    out['server']['import_buckets'] = cfg.import_buckets
    path = env_path(app)
    override = sorted(config.env_name(k) for g in GROUPS.values() for k in g if source(k, fv) == 'environment')
    out['file'] = dict(path=path, exists=os.path.exists(path), writable=envfile.writable(path), environment_override=override,
                       pending=getattr(app.state, 'settings_pending', []))
    return out


def write(app, values):
    """{kolom: nilai | None}: tulis ke .env (None = baris dinonaktifkan -> bawaan) lalu terapkan ke server. Hanya kolom
    yang nilainya berubah yang ditulis. -> daftar nama variabel yang berubah."""
    cfg = app.state.cfg
    values = {k: v for k, v in values.items() if (getattr(BASE, k) if v is None else v) != getattr(cfg, k) or v is None}
    if not values: return []
    path = env_path(app)
    if not envfile.writable(path):
        raise SettingsFail(f'File {path} tidak bisa ditulis oleh server. Beri izin tulis (lihat docs/06-docker.md) atau ubah file itu langsung.', 'env_not_writable')
    try: changed = envfile.update(path, {config.env_name(k): None if v is None else envfile.fmt(v) for k, v in values.items()})
    except envfile.EnvFileFail as e: raise SettingsFail(str(e)) from None
    for k, v in values.items(): setattr(cfg, k, getattr(BASE, k) if v is None else v)
    return changed


def update(app, body):
    """PUT /api/admin/config. body: {kolom: nilai} + clear: [kolom]. Rahasia kosong = tidak diubah; kolom biasa kosong =
    kembali ke bawaan. Diperiksa dulu (gabungan dengan nilai sekarang), lalu ditulis ke .env. -> kelompok yang berubah."""
    cfg, values = app.state.cfg, {}
    for k, v in (body or {}).items():
        if k not in SCREEN: continue
        v = '' if v is None else str(v).strip()
        if k in SECRET and v == '': continue                      # rahasia dibiarkan kosong: tetap
        values[k] = v if v != '' else None
    for k in body.get('clear') or []:
        if k in SCREEN: values[k] = None
    cand = {k: getattr(cfg, k) for k in SCREEN}
    cand.update({k: getattr(BASE, k) if v is None else v for k, v in values.items()})
    _validate(cand)
    changed = write(app, values)
    names = set(changed)
    return sorted({g for g, ks in GROUPS.items() for k in ks if config.env_name(k) in names})


def write_alerts(app, d):
    """Setelan notifikasi (sudah diperiksa alerts.merge) -> .env."""
    return write(app, alerts.to_fields(d))


def write_watch(app, url, minutes, enabled):
    return write(app, dict(s3_watch=url, s3_watch_minutes=int(minutes), s3_watch_enabled=bool(enabled)))


def _validate(s):
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


# ------------------------------------------------------------------ pindahan dari basis data akun (sekali)
OLD_KEYS = ('config', 'alerts', 's3_watch')


def migrate(app):
    """Setelan lama di app_setting -> .env. Bila .env tidak bisa ditulis: tetap dipakai dari memori (tanpa hilang) dan
    layar menampilkan peringatan; baris di basis data baru dihapus sesudah berhasil ditulis."""
    auth, cfg = app.state.auth, app.state.cfg
    try: old = {k: auth.setting_get(k) for k in OLD_KEYS}
    except Exception: return   # noqa: BLE001  basis data akun belum siap
    old = {k: v['value'] for k, v in old.items() if v}
    if not old: return
    values = {}
    for k, v in (old.get('config') or {}).items():
        if k in SCREEN and v not in (None, ''): values[k] = v
    if 'alerts' in old: values.update(alerts.to_fields(alerts.from_db(cfg, old['alerts'])))
    if 's3_watch' in old:
        w = old['s3_watch']
        values.update(s3_watch=w.get('url', ''), s3_watch_minutes=int(w.get('minutes') or cfg.s3_watch_minutes), s3_watch_enabled=bool(w.get('enabled')))
    try:
        write(app, values)
        for k in old: auth.setting_delete(k)
        app.state.settings_pending = []
    except SettingsFail:
        for k, v in values.items(): setattr(cfg, k, v)
        app.state.settings_pending = sorted(config.env_name(k) for k in values)


