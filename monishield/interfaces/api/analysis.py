"""Analysis Settings page (admin): which log is the access log, which are the application logs, the request ID field and the
business metrics of each source. The work is in monishield/application/analysis_service.py (saving) and
monishield/infrastructure/queries/analysis.py (what Auto picks, counting the rules).
  POST /api/v1/admin/analysis/view      the settings of the three sources + what Auto picks for the newest folder of each (service names: a POST)
  PUT  /api/v1/admin/analysis           {source, settings}: validate, write analysis.toml, use it at once
  POST /api/v1/admin/analysis/test      {source, business: [...], folder?}: how many each rule counts in a folder (newest by default); nothing is saved
  POST /api/v1/admin/analysis/suggest   {source, folder?}: the successful POST endpoints of the source's access log, as rules to add
Service names are site data, so every read is a POST (the web UI sends an encrypted body)."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from monishield.application import analysis_service as svc, sources
from monishield.domain import analysis
from monishield.domain.errors import Fail
from monishield.infrastructure.queries import analysis as q_analysis
from .admin import _audit
from .common import client_ip, require_admin

router = APIRouter(prefix='/api/v1/admin/analysis')


def _read(request, source, fn):
    """Run a read-side function with a cursor on the database of one source."""
    con = request.app.state.sources[source].con
    cur = con.cursor()
    try: return fn(cur)
    finally: cur.close()


def _view_of(request):
    out = {}
    for s in sources.SOURCES:
        st = analysis.current(s)
        out[s] = dict(settings=st.public(), **_read(request, s, lambda cur: q_analysis.overview(cur, st)))
    return dict(file=dict(exists=request.app.state.analysisfile.exists(), path=request.app.state.analysisfile.path),
                id_fields=list(analysis.ID_FIELDS), max_rules=analysis.MAX_METRICS, sources=out)


@router.post('/view')
def view(request: Request, admin=Depends(require_admin)): return _view_of(request)


class SaveBody(BaseModel):
    source: str = 's3'
    settings: dict


@router.put('')
def put_settings(body: SaveBody, request: Request, admin=Depends(require_admin)):
    svc.save(request.app.state, body.source, body.settings, admin, client_ip(request))
    return _view_of(request)


class TestBody(BaseModel):
    source: str = 's3'
    business: list[dict] = []
    folder: str | None = None


def _folder(cur, folder):
    if folder is None: return q_analysis.newest_folder(cur)
    if not cur.execute('SELECT 1 FROM folder_state WHERE folder = ?', [folder]).fetchone(): raise Fail('not_found', 'Folder not found.', 404)
    return folder


@router.post('/test')
def test(body: TestBody, request: Request, admin=Depends(require_admin)):
    source = svc.source_name(body.source)
    metrics = svc.metrics_of(source, body.business)

    def run(cur):
        folder = _folder(cur, body.folder)
        return dict(folder=folder, counts=q_analysis.count_rules(cur, folder, metrics))
    r = _read(request, source, run)
    _audit(request, admin, 'analysis.test', f'source={source} rules={len(metrics)}')
    return r


class SuggestBody(BaseModel):
    source: str = 's3'
    folder: str | None = None


@router.post('/suggest')
def suggest(body: SuggestBody, request: Request, admin=Depends(require_admin)):
    source = svc.source_name(body.source)

    def run(cur):
        folder = _folder(cur, body.folder)
        return dict(folder=folder, suggestions=q_analysis.suggestions(cur, folder, analysis.current(source)) if folder else [])
    return _read(request, source, run)
