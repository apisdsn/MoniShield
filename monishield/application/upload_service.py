"""Upload log folders from the browser (owner request 2026-10-07): plan (rules in monishield/domain/uploads.py) ->
files one by one to temporary storage (ctx.uploads) -> move to the inbox -> ingest in the background."""
import threading

from monishield.domain import uploads
from monishield.domain.s3_import import ImportFail


def plan(ctx, files, folder, by):
    ok, skip = uploads.plan(ctx.cfg, files, folder.strip(), in_log_dir=ctx.logfolders.in_log_dir)
    if not ok:
        raise ImportFail('nothing_to_upload', 'No log files in this folder can be uploaded.' + (f' Example: {skip[0]["path"][:120]} — {skip[0]["reason"]}.' if skip else ''))
    uid = ctx.uploads.create(by, ok)
    return dict(upload_id=uid, files=[dict(i=f['i'], rel=f['rel'], size=f['size']) for f in ok], skipped=skip[:200], skipped_count=len(skip),
                folders=sorted({f['folder'] for f in ok}), bytes=sum(f['size'] for f in ok))


def finish(ctx, uid, by):
    """Move to the inbox, then ingest those folders in the background (waiting for other ingests to finish); the result
    shows in the ingest status as usual."""
    r = ctx.uploads.finish(uid, by)

    def kerja():
        for f in r['folders']:
            try: ctx.ingest.run_blocking(f, f'upload by {by}')
            except Exception: pass   # noqa: BLE001  ingest errors are recorded in the ingest status and the ingest_run table
    threading.Thread(target=kerja, name='upload-ingest', daemon=True).start()
    return r


def cancel(ctx, uid, by):
    ctx.uploads.get(uid, by)
    ctx.uploads.drop(uid)
    return dict(cancelled=True)
