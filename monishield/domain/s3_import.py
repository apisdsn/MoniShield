"""S3 import rules (TRD §3.8): link format, bucket/prefix allowlist (S4_IMPORT_BUCKETS), parent folder for
automatic sync, selection of new folders, and the plan of objects to fetch. Pure (no network/files); downloading is in
monishield/infrastructure/importer.py."""
import datetime, os, re

from monishield.domain import rules
from monishield.domain.errors import Fail

URL = re.compile(r's3://([a-z0-9][a-z0-9.-]{1,61}[a-z0-9])/(.*)')


CONTROL = re.compile(r'[\x00-\x1f\x7f]')


class ImportFail(Fail):
    """Import rejection or failure with a readable cause (code + message; contains no secrets)."""


# ------------------------------------------------------------------ link
def parse_url(cfg, url):
    """Check the link against the format and the allowlist. -> (bucket, full prefix ending in '/', folder). No network."""
    if not cfg.import_buckets:
        raise ImportFail('import_disabled', 'Import is not enabled on the server: set S4_IMPORT_BUCKETS (e.g. {"bucket-name": ["k8s-logs/"]}).')
    if not isinstance(url, str) or len(url) > 1024 or CONTROL.search(url):
        raise ImportFail('invalid_url', 'The link must look like s3://<bucket>/<prefix>/<YYYY-MM-DD>/.')
    m = URL.fullmatch(url.strip())
    if not m: raise ImportFail('invalid_url', 'The link must look like s3://<bucket>/<prefix>/<YYYY-MM-DD>/.')
    bucket, path = m.group(1), m.group(2).rstrip('/')
    parts = path.split('/')
    if not path or '' in parts or '..' in parts or '.' in parts:
        raise ImportFail('invalid_url', 'The link must look like s3://<bucket>/<prefix>/<YYYY-MM-DD>/ without "..", "." or double slashes.')
    folder = parts[-1]
    try:
        if not rules.DATE_DIR.fullmatch(folder): raise ValueError
        datetime.date.fromisoformat(folder)
    except ValueError:
        raise ImportFail('invalid_date', f'The last part of the link must be a valid YYYY-MM-DD date (the folder name), not "{folder[:40]}".') from None
    base = '/'.join(parts[:-1]) + '/' if len(parts) > 1 else ''
    allowed = cfg.import_buckets.get(bucket)
    if allowed is None:
        raise ImportFail('bucket_not_allowed', f'This bucket is not allowed. Allowed: {", ".join(sorted(cfg.import_buckets))}.')
    if not any(base.startswith(p) for p in allowed):
        raise ImportFail('prefix_not_allowed', f'This prefix is not allowed for bucket {bucket}. Allowed: '
                                               f'{", ".join(f"s3://{bucket}/{p}<date>/" for p in allowed)}.')
    return bucket, base + folder + '/', folder


def allowed_examples(cfg):
    """Examples of accepted link shapes (for the import page)."""
    return [f's3://{b}/{p}<YYYY-MM-DD>/' for b, ps in sorted(cfg.import_buckets.items()) for p in ps]


NO_CREDENTIALS = ('No AWS credentials. Set them on the Configuration page (account menu; written to .env) or directly as '
                  'AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in the server .env, or paste temporary credentials on the Ingest & import page.')


# ------------------------------------------------------------------ watch parent prefix (automatic sync, owner request 2026-10-07)
def parse_watch(cfg, text=None):
    """Watched parent folders (from the page, or S4_S3_WATCH; one or more s3://<bucket>/<prefix>/, comma-separated;
    the trailing slash is optional) -> [(bucket, prefix)]. Checked against the same S4_IMPORT_BUCKETS allowlist as
    manual import; no network."""
    out = []
    text = cfg.s3_watch if text is None else text
    for u in (x for x in re.split(r'[,\s]+', (text or '').strip()) if x):
        m = URL.fullmatch(u) if len(u) <= 1024 and not CONTROL.search(u) else None
        path = m.group(2).strip('/') if m else ''
        parts = path.split('/') if path else []
        if not m or '' in parts or '..' in parts or '.' in parts:
            raise ImportFail('invalid_watch', f'"{u[:100]}" must look like s3://<bucket>/<prefix>/ (a parent folder containing YYYY-MM-DD folders).')
        bucket, base = m.group(1), path + '/' if path else ''
        if parts and rules.DATE_DIR.fullmatch(parts[-1]):
            raise ImportFail('watch_is_date', f'Enter the PARENT folder without a date, e.g. s3://{bucket}/{"/".join(parts[:-1])}/ (not folder {parts[-1]}).')
        if not cfg.import_buckets:
            raise ImportFail('import_disabled', 'Import is not enabled on the server: set S4_IMPORT_BUCKETS (e.g. {"bucket-name": ["k8s-logs/"]}).')
        allowed = cfg.import_buckets.get(bucket)
        if allowed is None or not any(base.startswith(p) for p in allowed):
            raise ImportFail('watch_not_allowed', f's3://{bucket}/{base} is not on the server allowlist (S4_IMPORT_BUCKETS). Allowed: '
                                                  f'{", ".join(f"s3://{b}/{p}" for b, ps in sorted(cfg.import_buckets.items()) for p in ps)}.')
        if (bucket, base) not in out: out.append((bucket, base))
    return out


def pick(folders, known, from_s3, today, days, recheck_days, max_new):
    """Of the folders in S3: the NEW ones (not known at all) and the RE-CHECKED ones (recent S3 imports that may have
    gained files). Only folders within the last `days` days (0 = all). At most `max_new` new folders are taken per
    round, newest first; the rest follow in later rounds. -> (new, again, waiting)"""
    floor = (today - datetime.timedelta(days=days)).isoformat() if days else ''
    fresh = (today - datetime.timedelta(days=recheck_days)).isoformat()
    new = [f for f in folders if f >= floor and f not in known]
    take = sorted(new[-max_new:]) if max_new > 0 else []
    again = [f for f in folders if f >= fresh and f in from_s3 and f not in take]
    return take, again, len(new) - len(take)


# ------------------------------------------------------------------ select
def plan(cfg, objects, prefix, folder, before=None, have_stored=lambda stored, size: False):
    """Decide which objects are fetched / skipped. Unsafe key -> the whole import is rejected. Over the limits -> rejected.
    before = manifest of the previous download {rel: {key, size, etag[, stored, stored_size]}}; have_stored(stored_rel, size)
    = the file from the old download is still intact in the inbox (checked by the adapter, not here)."""
    before = before or {}
    rows, keys = [], set()
    for o in objects:
        rel = o['key'][len(prefix):] if o['key'].startswith(prefix) else None
        if rel is None or rel.startswith('/') or '//' in rel or CONTROL.search(rel) or any(p in ('..', '.') for p in rel.split('/')):
            raise ImportFail('unsafe_key', f'Unsafe object key, import cancelled: {o["key"][:200]!r}.')
        keys.add(rel)
        rows.append(dict(rel=rel, **o))
    n_log = 0
    for r in rows:
        rel, name = r['rel'], r['rel'].rsplit('/', 1)[-1]
        ok_name = name.endswith('.log') or name.endswith('.log.gz')
        if not ok_name or rel.endswith('/') or not rules.split_relpath(os.path.join(folder, *rel.split('/'))):
            r.update(action='skip', reason='not a log file'); continue
        n_log += 1
        if name.endswith('.gz') and rel[:-3] in keys:
            r.update(action='skip', reason='.gz paired with .log'); continue
        prev = before.get(rel)
        if prev and prev.get('etag') == r['etag'] and prev.get('size') == r['size']:
            if have_stored(prev.get('stored', rel), prev.get('stored_size', r['size'])):
                # old download is a not-yet-extracted .gz: extracted in place when the import runs (no re-download)
                r.update(action='skip', reason='same as the previous download',
                         extract_local=bool(cfg.import_extract and rel.endswith('.gz') and 'stored' not in prev))
                continue
        if r['size'] > cfg.import_max_object_mb * 2**20:
            raise ImportFail('object_too_large', f'Object {rel} {r["size"] / 2**20:.0f} MB exceeds the limit of {cfg.import_max_object_mb} MB per object.')
        r.update(action='fetch', reason='')
    if n_log > cfg.import_max_objects:
        raise ImportFail('too_many_objects', f'{n_log} log files under this prefix exceed the limit of {cfg.import_max_objects} objects.')
    total = sum(r['size'] for r in rows if r['action'] == 'fetch')
    if total > cfg.import_max_total_mb * 2**20:
        raise ImportFail('too_large', f'Total download {total / 2**20:.0f} MB exceeds the limit of {cfg.import_max_total_mb} MB.')
    return rows
