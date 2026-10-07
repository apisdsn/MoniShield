"""Unggah folder log dari browser (permintaan pemilik 2026-10-07): rencana (aturan monishield/domain/uploads.py) ->
file satu per satu ke penyimpanan sementara (ctx.uploads) -> pindah ke kotak masuk -> ingest di latar."""
import threading

from monishield.domain import uploads
from monishield.domain.s3_import import ImportFail


def plan(ctx, files, folder, by):
    ok, skip = uploads.plan(ctx.cfg, files, folder.strip(), in_log_dir=ctx.logfolders.in_log_dir)
    if not ok:
        raise ImportFail('nothing_to_upload', 'Tidak ada file log yang bisa diunggah dari folder ini.' + (f' Contoh: {skip[0]["path"][:120]} — {skip[0]["reason"]}.' if skip else ''))
    uid = ctx.uploads.create(by, ok)
    return dict(upload_id=uid, files=[dict(i=f['i'], rel=f['rel'], size=f['size']) for f in ok], skipped=skip[:200], skipped_count=len(skip),
                folders=sorted({f['folder'] for f in ok}), bytes=sum(f['size'] for f in ok))


def finish(ctx, uid, by):
    """Pindah ke kotak masuk, lalu ingest folder-folder itu di latar (menunggu ingest lain selesai); hasilnya terlihat di
    status ingest seperti biasa."""
    r = ctx.uploads.finish(uid, by)

    def kerja():
        for f in r['folders']:
            try: ctx.ingest.run_blocking(f, f'unggah oleh {by}')
            except Exception: pass   # noqa: BLE001  galat ingest tercatat di status ingest dan tabel ingest_run
    threading.Thread(target=kerja, name='upload-ingest', daemon=True).start()
    return r


def cancel(ctx, uid, by):
    ctx.uploads.get(uid, by)
    ctx.uploads.drop(uid)
    return dict(cancelled=True)
