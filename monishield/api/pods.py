"""Halaman Pod (TRD §5.3)."""
from fastapi import APIRouter, Depends

from .common import cursor, folder_param, require_user_ready, _one
from .tables import first

router = APIRouter(prefix='/api', dependencies=[Depends(require_user_ready)])


@router.get('/folders/{folder}/pods')
def pods(folder: str = Depends(folder_param), cur=Depends(cursor)):
    files, empty = cur.execute('SELECT count(*), count(*) FILTER (WHERE lines = 0) FROM ingest_file WHERE folder = ?', [folder]).fetchone()
    return dict(
        available=True,
        kpi=dict(files=files, files_without_log=empty, backend_pods=_one(cur, 'SELECT count(*) FROM agg_pod WHERE folder = ?', folder),
                 pods_with_retry=_one(cur, 'SELECT count(*) FROM (SELECT DISTINCT upstream, addr_first FROM agg_retry WHERE folder = ?)', folder),
                 restarts=_one(cur, 'SELECT count(*) FROM v_restart WHERE folder = ?', folder)),
        tables={t: first(cur, t, folder) for t in ('backend-pods', 'restarts')})
