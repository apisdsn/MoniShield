"""Configuration page -> .env file (owner request 2026-10-07: "ubah semua yang berbau configuration … ke dalam .env"
(move everything configuration-related … into .env)).

All settings that can be changed from the page (AWS credentials + region, MaxMind, blocklist exclusions, Kafka, automatic
S3 parent folder, notifications) are SAVED TO THE .env FILE (ctx.env) — a single source of truth also read by the CLI and Docker.
Once written, the values are applied right away to the running server's configuration object, so no restart is needed.

Process environment variables that DIFFER from .env override .env when the server starts; the page flags them (source
'environment') so the admin knows the page value will not survive a restart. Field rules and input validation:
monishield/domain/settings.py.

Old settings formerly stored in the account database (app_setting 'config' / 'alerts' / 's3_watch') are moved once to .env
at server start (`migrate`).
"""
from monishield.domain import alerts, s3_import, settings as rules
from monishield.domain.config_model import env_name
from monishield.domain.errors import Fail
from monishield.domain.settings import SettingsFail


def source(ctx, field):
    return rules.source(field, ctx.env.values(), ctx.env.environ())


def view(ctx):
    """For the browser: non-secret values as is; secrets only as {set, source[, masked]}."""
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
    """{field: value | None}: write to .env (None = line disabled -> default) then apply to the server. Only fields
    whose value changed are written. -> list of changed variable names."""
    cfg = ctx.cfg
    values = rules.changed_only(cfg, values)
    if not values: return []
    if not ctx.env.writable():
        raise SettingsFail(f'File {ctx.env.path} is not writable by the server. Grant write permission (see docs/06-docker.md) or edit that file directly.', 'env_not_writable')
    changed = ctx.env.write({env_name(k): v for k, v in values.items()})
    for k, v in values.items(): setattr(cfg, k, getattr(rules.BASE, k) if v is None else v)
    return changed


def update(ctx, body):
    """PUT /api/admin/config. -> changed groups (e.g. 'kafka': the consumer needs a restart)."""
    return rules.groups_of(write(ctx, rules.screen_values(ctx.cfg, body)))


def write_alerts(ctx, d):
    """Notification settings (already validated by alerts.merge) -> .env."""
    return write(ctx, alerts.to_fields(d))


def write_watch(ctx, url, minutes, enabled): return write(ctx, rules.watch_values(url, minutes, enabled))


def migrate(ctx):
    """Old settings in app_setting -> .env. If .env is not writable: still used from memory (nothing lost) and
    the page shows a warning; the database rows are deleted only after a successful write."""
    auth, cfg = ctx.auth, ctx.cfg
    try: old = {k: auth.setting_get(k) for k in rules.OLD_KEYS}
    except Exception: return   # noqa: BLE001  account database not ready yet
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


# ------------------------------------------------------------------ connection test (uses the SAVED settings)
def test_aws(ctx):
    """List 1 object in S3: the automatic S3 parent folder if set, otherwise the first allowlist prefix."""
    cfg, s3 = ctx.cfg, ctx.s3
    s3.ready()
    w = ctx.imports.watch_config()
    try: targets = s3_import.parse_watch(cfg, w['url']) if w['url'] else []
    except s3_import.ImportFail: targets = []
    targets = targets or [(b, p) for b, ps in sorted(cfg.import_buckets.items()) for p in ps][:1]
    if not targets: raise Fail('import_disabled', 'S3 import is not enabled: the S4_IMPORT_BUCKETS allowlist in .env is empty.', 400)
    bucket, prefix = targets[0]
    s3.probe(bucket, prefix)
    return dict(ok=True, kind='aws', target=f's3://{bucket}/{prefix}', source=s3.creds.get()[1])


def test_maxmind(ctx):
    """Request a GeoLite2 download link (authorization only, no download)."""
    cfg = ctx.cfg
    if not (cfg.maxmind_account_id and cfg.maxmind_license_key):
        raise Fail('maxmind_missing', 'MaxMind Account ID and License key are not set.', 400)
    if cfg.offline: raise Fail('offline', 'Server is in offline mode (S4_OFFLINE); connection test not run.', 400)
    ctx.maxmind(cfg)
    return dict(ok=True, kind='maxmind')


TESTS = dict(aws=test_aws, maxmind=test_maxmind)


def test_connection(ctx, kind):
    fn = TESTS.get(kind)
    if not fn: raise Fail('invalid_parameter', 'Unknown test type.', 400)
    return fn(ctx)
