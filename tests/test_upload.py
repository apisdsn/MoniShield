"""Upload a log folder from the browser (owner request 2026-10-07): plan -> files one by one -> inbox -> ingest."""
import dataclasses, gzip, os, time

import pytest
from fastapi.testclient import TestClient

import logs_mini
from monishield.domain import accounts, uploads as upload_rules
from monishield.infrastructure import config, db, importer, ingest, logfolders
from monishield.interfaces.api import app as appmod
from conftest import JWT_SECRET

X = {'X-Requested-With': 'uji'}
PW, PW2 = 'sandi-admin-pertama', 'sandi-admin-sesudah-diganti'
D = '2026-01-09'
APPS = logs_mini.lines('om-be-appsmanager').encode()
FE = logs_mini.lines('om-fe-inhouse').encode()


def f(path, data): return dict(path=path, size=len(data), data=data)


@pytest.fixture
def cfg(tmp_path):
    return dataclasses.replace(config.Config(), log_dir=logs_mini.build(tmp_path / 'logs'), data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'),
                               inbox_dir=str(tmp_path / 'inbox'), cache_dir=str(tmp_path / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False,
                               admin_user='admin', admin_password=PW, jwt_secret=JWT_SECRET)


def rencana(cfg, paths, folder=''):
    return upload_rules.plan(cfg, [dict(path=p, size=10) for p in paths], folder, in_log_dir=logfolders.LogFolders(cfg).in_log_dir)


def test_rencana_bentuk_jalur(cfg):
    ok, skip = rencana(cfg, [
        f'unduhan/{D}/ombudsman/om-be-appsmanager/a.log',     # parent of the date folders
        '2026-01-10/ombudsman/om-fe-inhouse/b.log.gz',        # several dates at once
        f'{D}/ombudsman/om-be-appsmanager/a.log.gz',          # paired with a .log: skipped
        f'{D}/.DS_Store', f'{D}/catatan.txt',                 # not a log
        f'{D}/lepas.log',                                     # missing components
        '2026-01-01/ombudsman/om-be-appsmanager/c.log',       # exists in the main log folder
        'ombudsman/om-be-report/d.log',                       # no date, date not filled in
    ])
    assert [o['rel'] for o in ok] == [f'{D}/ombudsman/om-be-appsmanager/a.log', '2026-01-10/ombudsman/om-fe-inhouse/b.log.gz']
    why = {s['path']: s['reason'] for s in skip}
    assert why[f'{D}/ombudsman/om-be-appsmanager/a.log.gz'] == '.gz paired with .log' and why[f'{D}/.DS_Store'] == 'not a log file'
    assert 'main log folder' in why['2026-01-01/ombudsman/om-be-appsmanager/c.log'] and 'fill in the folder date' in why['ombudsman/om-be-report/d.log']
    assert 'namespace' in why[f'{D}/lepas.log']
    # one date's contents without a date name: the chosen folder (first component) is replaced by the chosen date
    ok, _ = rencana(cfg, ['salinan-server/ombudsman/om-be-report/d.log'], folder=D)
    assert [o['rel'] for o in ok] == [f'{D}/ombudsman/om-be-report/d.log']


@pytest.mark.parametrize('paths,folder,code', [([f'{D}/../x/a/b.log'], '', 'unsafe_path'), ([f'{D}//a/b.log'], '', 'unsafe_path'),
                                                (['a\x00/b/c.log'], '', 'unsafe_path'), ([], '', 'nothing_to_upload'), (['x/y/z.log'], '2026-02-30', 'invalid_date')])
def test_rencana_ditolak(cfg, paths, folder, code):
    with pytest.raises(importer.ImportFail) as e: rencana(cfg, paths, folder)
    assert e.value.code == code


def test_rencana_batas(cfg):
    big = dataclasses.replace(cfg, import_max_object_mb=1)
    with pytest.raises(importer.ImportFail) as e: upload_rules.plan(big, [dict(path=f'{D}/ns/svc/a.log', size=2 * 2**20)])
    assert e.value.code == 'object_too_large'
    few = dataclasses.replace(cfg, import_max_objects=1)
    with pytest.raises(importer.ImportFail) as e: rencana(few, [f'{D}/ns/svc/a.log', f'{D}/ns/svc/b.log'])
    assert e.value.code == 'too_many_objects'


@pytest.fixture
def client(cfg, auth_url, monkeypatch):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    c = dataclasses.replace(cfg, auth_database_url=auth_url)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    with TestClient(appmod.create_app(c)) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        yield tc


def unggah(tc, files, folder=''):
    r = tc.post('/api/admin/upload', json=dict(files=[dict(path=x['path'], size=x['size']) for x in files], folder=folder), headers=X)
    assert r.status_code == 201, r.text
    p = r.json()
    for o in p['files']:
        assert tc.put(f"/api/admin/upload/{p['upload_id']}/{o['i']}", content=files[o['i']]['data'], headers=X).status_code == 200
    return p


def tunggu_ingest(tc):
    for _ in range(400):
        st = tc.get('/api/admin/ingest/status').json()
        if not st['running'] and not tc.app.state.uploads.sessions: break
        time.sleep(0.05)
    time.sleep(0.2)
    while tc.get('/api/admin/ingest/status').json()['running']: time.sleep(0.05)


def test_unggah_folder_lalu_ingest(client, cfg):
    files = [f(f'log-saya/{D}/ombudsman/om-be-appsmanager/log_om-be-appsmanager_pod-a_{D}-00-00.log', APPS),
             f(f'log-saya/{D}/ombudsman/om-fe-inhouse/log_om-fe-inhouse_pod-f_{D}-00-00.log.gz', gzip.compress(FE)),
             f(f'log-saya/{D}/catatan.txt', b'abaikan')]
    p = unggah(client, files)
    assert (p['folders'], len(p['files']), p['skipped_count']) == ([D], 2, 1)
    r = client.post(f"/api/admin/upload/{p['upload_id']}/finish", headers=X)
    assert r.status_code == 202 and r.json() == dict(folders=[D], files=2, bytes=len(APPS) + len(gzip.compress(FE)), extracted=1)
    base = os.path.join(cfg.inbox_dir, D, 'ombudsman')
    assert open(os.path.join(base, 'om-fe-inhouse', f'log_om-fe-inhouse_pod-f_{D}-00-00.log'), 'rb').read() == FE      # .gz extracted
    assert not os.path.exists(os.path.join(base, 'om-fe-inhouse', f'log_om-fe-inhouse_pod-f_{D}-00-00.log.gz'))
    assert not [d for d in os.listdir(os.path.join(cfg.data_dir, 'tmp')) if d.startswith('upload-')]
    tunggu_ingest(client)
    assert D in [x['folder'] for x in client.get('/api/meta').json()['folders']]
    assert client.get('/api/admin/ingest/status').json()['last_run']['status'] == 'ok'
    assert 'upload.finish' in {x['action'] for x in client.get('/api/admin/audit').json()['rows']}
    # re-upload of a changed file: replaces the old one, ingest refreshes only that file
    p = unggah(client, [f(f'{D}/ombudsman/om-be-appsmanager/log_om-be-appsmanager_pod-a_{D}-00-00.log', APPS + APPS)])
    assert client.post(f"/api/admin/upload/{p['upload_id']}/finish", headers=X).status_code == 202
    tunggu_ingest(client)
    con = client.app.state.con.cursor()
    try: assert con.execute("SELECT lines FROM ingest_file WHERE folder = ? AND service = 'om-be-appsmanager'", [D]).fetchone()[0] == 2 * len(APPS.splitlines())
    finally: con.close()


def test_unggah_ditolak_dan_dibatalkan(client, cfg):
    data = APPS
    r = client.post('/api/admin/upload', json=dict(files=[dict(path=f'{D}/ombudsman/om-be-appsmanager/a.log', size=len(data))]), headers=X)
    uid = r.json()['upload_id']
    put = lambda i, body, h=X: client.put(f'/api/admin/upload/{uid}/{i}', content=body, headers=h)
    assert put(0, data + b'x').status_code == 413                         # larger than planned
    assert put(0, data[:-1]).json()['error']['code'] == 'size_mismatch'   # smaller
    assert put(5, data).status_code == 404                                # not part of the plan
    assert put(0, data, {}).status_code == 403                            # without CSRF header
    fin = client.post(f'/api/admin/upload/{uid}/finish', headers=X)
    assert (fin.status_code, fin.json()['error']['code']) == (409, 'incomplete')
    assert client.put(f'/api/admin/upload/{"0" * 32}/0', content=data, headers=X).status_code == 404
    assert put(0, data).status_code == 200
    assert client.delete(f'/api/admin/upload/{uid}', headers=X).status_code == 200
    assert not os.path.exists(os.path.join(cfg.data_dir, 'tmp', f'upload-{uid}')) and not os.path.exists(os.path.join(cfg.inbox_dir, D))
    r = client.post('/api/admin/upload', json=dict(files=[dict(path='a/b.txt', size=1)]), headers=X)
    assert (r.status_code, r.json()['error']['code']) == (400, 'nothing_to_upload')


def test_user_biasa_tidak_boleh_unggah(client):
    assert client.post('/api/admin/users', json=dict(username='rina', display_name='Rina', role='user', password='sandi-awal-rina-123'), headers=X).status_code == 201
    u = TestClient(client.app)
    assert u.post('/api/auth/login', json=dict(username='rina', password='sandi-awal-rina-123'), headers=X).status_code == 200
    assert u.post('/api/me/password', json=dict(old_password='sandi-awal-rina-123', new_password='sandi-baru-rina-123'), headers=X).status_code == 200
    assert u.post('/api/admin/upload', json=dict(files=[dict(path=f'{D}/a/b/c.log', size=1)]), headers=X).status_code == 403
    assert u.post('/api/admin/import/sync', headers=X).status_code == 403
