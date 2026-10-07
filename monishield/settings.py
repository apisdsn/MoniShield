"""Setelan yang diisi admin dari layar Konfigurasi (permintaan pemilik 2026-10-07: "satu halaman untuk semua kredensial").

Disimpan di basis data akun (app_setting 'config'), lalu DITIMPAKAN ke objek konfigurasi server yang sedang berjalan
(`apply`), sehingga semua kode yang membaca `cfg.aws_*`, `cfg.maxmind_*`, dst. langsung memakai nilai baru tanpa mulai
ulang. Urutan: isian layar > .env/variabel lingkungan > bawaan. Mengosongkan isian layar = kembali ke nilai .env.

Kredensial tidak pernah dikirim balik ke browser: hanya "sudah diisi" + sumbernya (Access Key ID ditampilkan tersamar).
Yang TETAP hanya lewat .env (tidak bisa dari layar, karena menjadi dasar keamanan server itu sendiri): S4_JWT_SECRET,
S4_JOB_TOKEN, sandi PostgreSQL, S4_ADMIN_PASSWORD, dan daftar izin bucket S4_IMPORT_BUCKETS — layar hanya menampilkan
statusnya.
"""
import dataclasses, ipaddress, re

# kolom yang boleh diisi dari layar: nama di cfg -> (kelompok, rahasia?)
FIELDS = {
    'aws_access_key_id': ('aws', True), 'aws_secret_access_key': ('aws', True), 'aws_session_token': ('aws', True),
    'import_region': ('aws', False),
    'maxmind_account_id': ('maxmind', True), 'maxmind_license_key': ('maxmind', True),
    'blocklist_exclude': ('blocklist', False), 'blocklist_exclude_org': ('blocklist', False),
}
ENV_ONLY = ('jwt_secret', 'job_token', 'auth_database_url', 'admin_password')   # hanya status terisi/kosong


class SettingsFail(Exception):
    pass


def stored(auth):
    st = auth.setting_get('config')
    return {k: v for k, v in (st['value'] if st else {}).items() if k in FIELDS}


def _overlay(cfg, base, s):
    for k in FIELDS: setattr(cfg, k, s[k] if s.get(k) not in (None, '') else getattr(base, k))
    return {k for k in FIELDS if s.get(k) not in (None, '')}


def apply(app):
    """Timpakan isian layar ke app.state.cfg; kolom tanpa isian layar kembali ke nilai awal (.env)."""
    try: s = stored(app.state.auth)
    except Exception: s = {}   # noqa: BLE001  basis data akun belum siap: tetap .env
    app.state.cfg_layar = _overlay(app.state.cfg, app.state.cfg_env, s)


def origin(app, key):
    """'layar' | 'env' | None — asal nilai kolom yang sedang dipakai."""
    if key in getattr(app.state, 'cfg_layar', ()): return 'layar'
    return 'env' if getattr(app.state.cfg_env, key) else None


def for_cli(cfg):
    """CLI tanpa server (ingest/impor lokal): pakai juga isian layar yang tersimpan di basis data akun, bila terjangkau."""
    from . import auth as authmod
    try:
        a = authmod.Auth(cfg.auth_url)
        try: s = stored(a)
        finally: a.close()
    except Exception: return cfg   # noqa: BLE001  basis data akun tidak terjangkau: .env saja
    out = dataclasses.replace(cfg)
    _overlay(out, cfg, s)
    return out


def _mask(v):
    return f'{v[:4]}…{v[-4:]}' if v and len(v) > 10 else ('••••' if v else '')


def view(app):
    """Untuk browser: nilai non-rahasia apa adanya; rahasia hanya {set, source[, masked]}."""
    cfg = app.state.cfg
    out = {}
    for k, (grp, secret) in FIELDS.items():
        src = origin(app, k)
        if secret:
            item = dict(set=bool(getattr(cfg, k)), source=src)
            if k in ('aws_access_key_id', 'maxmind_account_id'): item['masked'] = _mask(getattr(cfg, k))
        else:
            item = dict(value=getattr(cfg, k), source=src)
        out.setdefault(grp, {})[k] = item
    out['server'] = {k: bool(getattr(cfg, k)) for k in ENV_ONLY}
    out['server']['import_buckets'] = cfg.import_buckets
    return out


def update(app, body, by):
    """body: {kolom: nilai} + clear: [kolom]. Rahasia kosong = tidak diubah. Diperiksa dulu, lalu disimpan + diterapkan."""
    s = stored(app.state.auth)
    for k, v in (body or {}).items():
        if k == 'clear' or k not in FIELDS: continue
        v = '' if v is None else str(v).strip()
        if FIELDS[k][1] and v == '': continue                        # rahasia dibiarkan kosong: tetap
        s[k] = v
    for k in body.get('clear') or []:
        if k in FIELDS: s.pop(k, None)
    _validate(s)
    app.state.auth.setting_set('config', s, by)
    apply(app)
    return sorted({FIELDS[k][0] for k in body if k in FIELDS} | {FIELDS[k][0] for k in body.get('clear') or [] if k in FIELDS})


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
    for net in (x.strip() for x in s.get('blocklist_exclude', '').split(',') if x.strip()):
        try: ipaddress.ip_network(net, strict=False)
        except ValueError: raise SettingsFail(f'"{net[:60]}" bukan IP atau CIDR.') from None
    v = s.get('blocklist_exclude_org')
    if v:
        try: re.compile(v)
        except re.error: raise SettingsFail('Pola pemilik jaringan bukan regex yang sah.') from None
