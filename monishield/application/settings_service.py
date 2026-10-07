"""Layar Konfigurasi -> file .env (permintaan pemilik 2026-10-07: "ubah semua yang berbau configuration … ke dalam .env").

Semua setelan yang bisa diubah dari layar (kredensial AWS + wilayah, MaxMind, pengecualian daftar blokir, Kafka, folder
induk S3 otomatis, notifikasi) DISIMPAN KE FILE .env (ctx.env) — satu sumber kebenaran yang juga dibaca CLI dan Docker.
Sesudah ditulis, nilainya langsung ditimpakan ke objek konfigurasi server yang sedang berjalan, jadi tidak perlu mulai ulang.

Variabel lingkungan proses yang BERBEDA dari .env mengalahkan .env saat server dimulai; layar menandainya (sumber
'environment') agar admin tahu nilai layar tidak akan bertahan setelah mulai ulang. Aturan kolom dan pemeriksaan isian:
monishield/domain/settings.py.

Setelan lama yang dulu disimpan di basis data akun (app_setting 'config' / 'alerts' / 's3_watch') dipindah sekali ke .env
saat server mulai (`migrate`).
"""
from monishield.domain import alerts, s3_import, settings as rules
from monishield.domain.config_model import env_name
from monishield.domain.errors import Fail
from monishield.domain.settings import SettingsFail


def source(ctx, field):
    return rules.source(field, ctx.env.values(), ctx.env.environ())


def view(ctx):
    """Untuk browser: nilai non-rahasia apa adanya; rahasia hanya {set, source[, masked]}."""
    cfg, env, out = ctx.cfg, ctx.env, {}
    fv, environ = env.values(), env.environ()
    for grp in rules.SCREEN_GROUPS:
        for k in rules.GROUPS[grp]:
            item = dict(set=bool(getattr(cfg, k))) if k in rules.SECRET else dict(value=getattr(cfg, k))
            if k in rules.MASKED: item['masked'] = rules.mask(getattr(cfg, k))
            item.update(source=rules.source(k, fv, environ), env=env_name(k))
            out.setdefault(grp, {})[k] = item
    out['server'] = {k: bool(getattr(cfg, k)) for k in rules.ENV_ONLY}
    out['server']['import_buckets'] = cfg.import_buckets
    override = sorted(env_name(k) for g in rules.GROUPS.values() for k in g if rules.source(k, fv, environ) == 'environment')
    out['file'] = dict(path=env.path, exists=env.exists(), writable=env.writable(), environment_override=override,
                       pending=getattr(ctx, 'settings_pending', []))
    return out


def write(ctx, values):
    """{kolom: nilai | None}: tulis ke .env (None = baris dinonaktifkan -> bawaan) lalu terapkan ke server. Hanya kolom
    yang nilainya berubah yang ditulis. -> daftar nama variabel yang berubah."""
    cfg = ctx.cfg
    values = rules.changed_only(cfg, values)
    if not values: return []
    if not ctx.env.writable():
        raise SettingsFail(f'File {ctx.env.path} tidak bisa ditulis oleh server. Beri izin tulis (lihat docs/06-docker.md) atau ubah file itu langsung.', 'env_not_writable')
    changed = ctx.env.write({env_name(k): v for k, v in values.items()})
    for k, v in values.items(): setattr(cfg, k, getattr(rules.BASE, k) if v is None else v)
    return changed


def update(ctx, body):
    """PUT /api/admin/config. -> kelompok yang berubah (mis. 'kafka': konsumen perlu dimulai ulang)."""
    return rules.groups_of(write(ctx, rules.screen_values(ctx.cfg, body)))


def write_alerts(ctx, d):
    """Setelan notifikasi (sudah diperiksa alerts.merge) -> .env."""
    return write(ctx, alerts.to_fields(d))


def write_watch(ctx, url, minutes, enabled): return write(ctx, rules.watch_values(url, minutes, enabled))


def migrate(ctx):
    """Setelan lama di app_setting -> .env. Bila .env tidak bisa ditulis: tetap dipakai dari memori (tanpa hilang) dan
    layar menampilkan peringatan; baris di basis data baru dihapus sesudah berhasil ditulis."""
    auth, cfg = ctx.auth, ctx.cfg
    try: old = {k: auth.setting_get(k) for k in rules.OLD_KEYS}
    except Exception: return   # noqa: BLE001  basis data akun belum siap
    old = {k: v['value'] for k, v in old.items() if v}
    if not old: return
    values = rules.from_old(cfg, old)
    try:
        write(ctx, values)
        for k in old: auth.setting_delete(k)
        ctx.settings_pending = []
    except SettingsFail:
        for k, v in values.items(): setattr(cfg, k, v)
        ctx.settings_pending = sorted(env_name(k) for k in values)


# ------------------------------------------------------------------ uji koneksi (memakai setelan TERSIMPAN)
def test_aws(ctx):
    """Daftar 1 objek di S3: folder induk S3 otomatis bila ada, selain itu awalan pertama daftar izin."""
    cfg, s3 = ctx.cfg, ctx.s3
    s3.ready()
    w = ctx.imports.watch_config()
    try: targets = s3_import.parse_watch(cfg, w['url']) if w['url'] else []
    except s3_import.ImportFail: targets = []
    targets = targets or [(b, p) for b, ps in sorted(cfg.import_buckets.items()) for p in ps][:1]
    if not targets: raise Fail('import_disabled', 'Impor S3 tidak diaktifkan: daftar izin S4_IMPORT_BUCKETS di .env kosong.', 400)
    bucket, prefix = targets[0]
    s3.probe(bucket, prefix)
    return dict(ok=True, kind='aws', target=f's3://{bucket}/{prefix}', source=s3.creds.get()[1])


def test_maxmind(ctx):
    """Minta tautan unduhan GeoLite2 (hanya otorisasi, tanpa mengunduh)."""
    cfg = ctx.cfg
    if not (cfg.maxmind_account_id and cfg.maxmind_license_key):
        raise Fail('maxmind_missing', 'Account ID dan License key MaxMind belum diisi.', 400)
    if cfg.offline: raise Fail('offline', 'Server dalam mode luring (S4_OFFLINE); uji koneksi tidak dijalankan.', 400)
    ctx.maxmind(cfg)
    return dict(ok=True, kind='maxmind')


TESTS = dict(aws=test_aws, maxmind=test_maxmind)


def test_connection(ctx, kind):
    fn = TESTS.get(kind)
    if not fn: raise Fail('invalid_parameter', 'Jenis uji tidak dikenal.', 400)
    return fn(ctx)
