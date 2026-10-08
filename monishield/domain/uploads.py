"""Rules for uploading log folders from the browser (owner request 2026-10-07): accepted paths, date folders, the same
size limits as S3 import. Pure; temporary files and the move to the inbox are in
monishield/infrastructure/uploads.py.

Accepted path shapes (webkitRelativePath from the browser):
  …/<YYYY-MM-DD>/<namespace>/<service>/<file>.log[.gz]   date folder (or its parent, containing several dates)
  <any folder>/<namespace>/<service>/<file>               contents of ONE date: the date is chosen on screen (`folder`)
"""
import datetime, os

from monishield.domain import rules
from monishield.domain.s3_import import CONTROL, ImportFail

def _date_ok(s):
    if not rules.DATE_DIR.fullmatch(s or ''): return False
    try: datetime.date.fromisoformat(s); return True
    except ValueError: return False


def plan(cfg, files, folder='', in_log_dir=lambda folder: False):
    """files: [{path, size}] from the browser -> (accepted [{i, rel, folder, size}], skipped [{path, reason}]).
    Unsafe path / over the limits -> ImportFail for the whole upload; non-log files are just skipped.
    in_log_dir(folder): that date folder already exists in the main log folder (checked on disk by the caller)."""
    if folder and not _date_ok(folder): raise ImportFail('invalid_date', 'Folder date must be a valid YYYY-MM-DD.')
    if not isinstance(files, list) or not files: raise ImportFail('nothing_to_upload', 'No files selected.')
    if len(files) > cfg.import_max_objects * 4:
        raise ImportFail('too_many_objects', f'More than {cfg.import_max_objects * 4} files selected; limit is {cfg.import_max_objects} log files per upload.')
    ok, skip, seen = [], [], {}
    for i, f in enumerate(files):
        path, size = str((f or {}).get('path') or '')[:1024], (f or {}).get('size')
        parts = path.replace('\\', '/').split('/')
        if CONTROL.search(path) or any(p in ('', '.', '..') for p in parts) or not isinstance(size, int) or size < 0:
            raise ImportFail('unsafe_path', f'Invalid file name, upload cancelled: {path[:200]!r}.')
        if not parts[-1].endswith(('.log', '.log.gz')): skip.append(dict(path=path, reason='not a log file')); continue
        k = next((j for j, p in enumerate(parts[:-1]) if _date_ok(p)), None)
        if k is not None: rel = parts[k:]
        elif folder: rel = [folder] + parts[1:]          # the selected folder holds one date: its name is replaced by that date
        else: skip.append(dict(path=path, reason='no date folder (YYYY-MM-DD) in its path; fill in the folder date')); continue
        if not rules.split_relpath(os.path.join(*rel)):
            skip.append(dict(path=path, reason='not <date>/<namespace>/<service>/<file>')); continue
        if in_log_dir(rel[0]):
            skip.append(dict(path=path, reason=f'folder {rel[0]} already exists in the main log folder (that one is used)')); continue
        r = '/'.join(rel)
        if r in seen: skip.append(dict(path=path, reason='duplicate')); continue
        if size > cfg.import_max_object_mb * 2**20:
            raise ImportFail('object_too_large', f'{path[:200]} {size / 2**20:.0f} MB exceeds the limit of {cfg.import_max_object_mb} MB per file.')
        seen[r] = len(ok)
        ok.append(dict(i=i, rel=r, folder=rel[0], size=size, path=path))
    keep = []
    for o in ok:   # ingest rule: .log.gz only when its paired .log is absent
        if o['rel'].endswith('.gz') and o['rel'][:-3] in seen: skip.append(dict(path=o['path'], reason='.gz paired with .log'))
        else: keep.append(o)
    if len(keep) > cfg.import_max_objects:
        raise ImportFail('too_many_objects', f'{len(keep)} log files exceed the limit of {cfg.import_max_objects} files per upload.')
    total = sum(o['size'] for o in keep)
    if total > cfg.import_max_total_mb * 2**20:
        raise ImportFail('too_large', f'Total {total / 2**20:.0f} MB exceeds the limit of {cfg.import_max_total_mb} MB per upload.')
    return keep, skip
