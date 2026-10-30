"""Import from an S3 prefix (TRD §3.8, §9.6) against a local FAKE S3: no AWS, no internet."""
import dataclasses, gzip, json, os, time

import pytest
from fastapi.testclient import TestClient

import logs_mini
from fake_s3 import KEY_OK, FakeS3
from monishield.domain import accounts, s3_import
from monishield.infrastructure import config, db, envfile, importer, ingest
from monishield.interfaces.api import app as appmod
from conftest import JWT_SECRET

D = '2026-01-05'
PRE = f'k8s-logs/{D}/'
SECRET = 'fakeTestSecretThatMustNeverLeak0001'
URL = f's3://example-log-bucket/{PRE}'
X = {'X-Requested-With': 'test'}
TOKEN = 'machine-token-for-import-tests'
PW, PW2 = 'first-admin-password', 'admin-password-after-change'


def obj(service, pod, ns='tenant', ext='.log', folder=D):
    return f'k8s-logs/{folder}/{ns}/{service}/log_{service}_{pod}_{folder}-00-00{ext}'


APPS = logs_mini.lines('auth-service').encode()
CONTENTS = {
    obj('auth-service', 'pod-a'): APPS,
    obj('auth-service', 'pod-a', ext='.log.gz'): gzip.compress(APPS),          # paired: only the .log is fetched
    obj('web-frontend', 'pod-f', ns='tenant', ext='.log.gz'): gzip.compress(logs_mini.lines('web-frontend').encode()),   # .gz only: fetched
    f'{PRE}.DS_Store': b'x',                                                          # not a log file
    f'{PRE}notes.txt': b'not a log',
    f'{PRE}loose.log': b'fewer than 3 path parts',
}


@pytest.fixture
def s3(monkeypatch):
    t = FakeS3({'example-log-bucket': dict(CONTENTS), 'other-bucket': dict(CONTENTS)})
    monkeypatch.setattr(importer, 'ENDPOINT', t.url)
    yield t
    t.close()


@pytest.fixture
def cfg(tmp_path):
    return dataclasses.replace(config.Config(), log_dir=logs_mini.build(tmp_path / 'logs'), data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'),
                               inbox_dir=str(tmp_path / 'inbox'), cache_dir=str(tmp_path / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False,
                               admin_user='admin', admin_password=PW, job_token=TOKEN, jwt_secret=JWT_SECRET,
                               import_buckets={'example-log-bucket': ['k8s-logs/']}, aws_access_key_id=KEY_OK, aws_secret_access_key=SECRET)


def blank(cfg): return not os.path.exists(cfg.inbox_dir) or not os.listdir(cfg.inbox_dir)


def failed(cfg, url, code, **kw):
    with pytest.raises(importer.ImportFail) as e: importer.run(cfg, url, importer.Credentials(cfg), **kw)
    assert e.value.code == code, (e.value.code, e.value.message)
    assert e.value.message and SECRET not in e.value.message
    return e.value


# ------------------------------------------------------------------ links: rejected before contacting S3
@pytest.mark.parametrize('url, code', [
    ('https://example-log-bucket.s3.amazonaws.com/k8s-logs/2026-01-05/', 'invalid_url'),
    ('s3://other-bucket/k8s-logs/2026-01-05/', 'bucket_not_allowed'),
    ('s3://example-log-bucket/other/2026-01-05/', 'prefix_not_allowed'),
    ('s3://example-log-bucket/k8s-logs/not-a-date/', 'invalid_date'),
    ('s3://example-log-bucket/k8s-logs/2026-02-30/', 'invalid_date'),
    ('s3://example-log-bucket/k8s-logs/../2026-01-05/', 'invalid_url'),
    ('s3://example-log-bucket/k8s-logs//2026-01-05/', 'invalid_url'),
    ('s3://example-log-bucket/k8s-logs/\x00/2026-01-05/', 'invalid_url'),
    ('s3://EXAMPLE-LOG-BUCKET/k8s-logs/2026-01-05/', 'invalid_url'),
])
def test_link_rejected_without_contacting_s3(cfg, s3, url, code):
    failed(cfg, url, code)
    assert s3.log == [] and blank(cfg)


def test_import_off_without_an_allow_list(cfg, s3):
    e = failed(dataclasses.replace(cfg, import_buckets={}), URL, 'import_disabled')
    assert 'not enabled' in e.message and s3.log == []


def test_without_credentials_the_message_says_how_to_add_them(cfg, s3):
    e = failed(dataclasses.replace(cfg, aws_access_key_id='', aws_secret_access_key=''), URL, 'no_credentials')
    assert 'AWS_ACCESS_KEY_ID' in e.message and 'paste' in e.message and s3.log == [] and blank(cfg)


def test_credentials_rejected_by_s3(cfg, s3):
    c = dataclasses.replace(cfg, aws_access_key_id='AKIASALAHSALAHSALAH1')
    failed(c, URL, 's3_denied')
    assert blank(cfg)


def test_empty_prefix(cfg, s3):
    failed(cfg, 's3://example-log-bucket/k8s-logs/2026-01-09/', 'empty_prefix')


# ------------------------------------------------------------------ objects
def test_key_with_dot_dot_cancels_the_import(cfg, s3):
    s3.buckets['example-log-bucket'][f'{PRE}tenant/../../x/log_a_b_{D}.log'] = b'x'
    failed(cfg, URL, 'unsafe_key')
    assert blank(cfg) and s3.gets() == []


@pytest.mark.parametrize('change, code', [(dict(import_max_objects=1), 'too_many_objects'), (dict(import_max_object_mb=0), 'object_too_large'),
                                        (dict(import_max_total_mb=0), 'too_large')])
def test_over_the_limits(cfg, s3, change, code):
    failed(dataclasses.replace(cfg, **change), URL, code)
    assert blank(cfg) and s3.gets() == []


def test_dry_run_writes_nothing(cfg, s3):
    r = importer.run(cfg, URL, importer.Credentials(cfg), dry_run=True)
    actions = {o['rel']: (o['action'], o['reason']) for o in r['objects']}
    assert actions[obj('auth-service', 'pod-a')[len(PRE):]] == ('fetch', '')
    assert actions[obj('auth-service', 'pod-a', ext='.log.gz')[len(PRE):]] == ('skip', '.gz paired with .log')
    assert actions[obj('web-frontend', 'pod-f', ext='.log.gz')[len(PRE):]] == ('fetch', '')
    assert actions['.DS_Store'] == actions['notes.txt'] == actions['loose.log'] == ('skip', 'not a log file')
    assert (r['take'], r['skipped'], r['downloaded'], r['credentials']) == (2, 4, 0, 'environment')
    assert blank(cfg) and s3.gets() == [] and not os.path.exists(os.path.join(cfg.data_dir, 'tmp'))


def test_import_then_ingest_and_repeat_without_download(cfg, s3):
    r = importer.run(cfg, URL, importer.Credentials(cfg))
    assert (r['take'], r['downloaded'], r['downloaded_bytes']) == (2, 2, len(APPS) + len(CONTENTS[obj('web-frontend', 'pod-f', ext='.log.gz')]))
    got = sorted(p.split('/', 2)[2] for p in s3.gets())
    assert got == sorted([obj('auth-service', 'pod-a'), obj('web-frontend', 'pod-f', ext='.log.gz')])      # paired .gz is not downloaded
    folder = os.path.join(cfg.inbox_dir, D)
    assert open(os.path.join(folder, 'tenant', 'auth-service', f'log_auth-service_pod-a_{D}-00-00.log'), 'rb').read() == APPS
    assert os.path.isfile(os.path.join(folder, importer.MANIFEST)) and os.listdir(os.path.join(cfg.data_dir, 'tmp')) == []
    con = db.open(cfg.db_path)
    try:
        g = ingest.run(cfg, con, folder=D, workers=0)
        assert g['files_failed'] == 0 and g['files_changed'] == 2
        rows = con.execute('SELECT service, lines FROM ingest_file WHERE folder = ? ORDER BY service', [D]).fetchall()
        assert [x[0] for x in rows] == ['auth-service', 'web-frontend'] and all(n > 0 for _, n in rows)
        # same link again: 0 objects downloaded, ingest unchanged, no duplicate data
        n0 = len(s3.gets())
        r2 = importer.run(cfg, URL, importer.Credentials(cfg))
        assert (r2['take'], r2['downloaded']) == (0, 0) and len(s3.gets()) == n0
        assert {o['reason'] for o in r2['objects'] if o['action'] == 'skip'} >= {'same as the previous download'}
        assert ingest.run(cfg, con, folder=D, workers=0)['files_changed'] == 0
        assert con.execute('SELECT count(*) FROM ingest_file WHERE folder = ?', [D]).fetchone()[0] == 2
        # object in S3 changed: only that object is downloaded again
        s3.buckets['example-log-bucket'][obj('auth-service', 'pod-a')] = APPS + APPS
        r3 = importer.run(cfg, URL, importer.Credentials(cfg))
        assert (r3['take'], r3['downloaded']) == (1, 1)
    finally:
        con.close()


def test_same_folder_in_the_local_log_folder_gets_a_warning(cfg, s3):
    s3.buckets['example-log-bucket'][obj('auth-service', 'pod-z', folder='2026-01-01')] = APPS
    r = importer.run(cfg, 's3://example-log-bucket/k8s-logs/2026-01-01/', importer.Credentials(cfg), dry_run=True)
    assert any('local log folder' in w for w in r['warnings'])


# ------------------------------------------------------------------ credentials
def test_temporary_credentials_in_memory(cfg):
    c = importer.Credentials(dataclasses.replace(cfg, aws_access_key_id='', aws_secret_access_key=''))
    assert c.get() == (None, None) and c.status()['available'] is False
    with pytest.raises(importer.ImportFail): c.set('not a key', 'x')
    c.set('AKIAPASTEDTEST000002', SECRET, 'session-token')
    kw, src = c.get()
    assert src == 'pasted' and kw['aws_session_token'] == 'session-token'
    assert SECRET not in repr(c) and SECRET not in str(c.status()) and c.status()['pasted_at']
    c.clear()
    assert c.get() == (None, None)
    # order: pasted then environment
    c2 = importer.Credentials(cfg)
    assert c2.get()[1] == 'environment'
    c2.set('AKIAPASTEDTEST000002', SECRET)
    assert c2.get()[1] == 'pasted'


# ------------------------------------------------------------------ API
@pytest.fixture
def client(cfg, auth_url, monkeypatch, s3):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    c = dataclasses.replace(cfg, auth_database_url=auth_url)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    with TestClient(appmod.create_app(c)) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        yield tc


def wait_job(tc, job, h=X):
    for _ in range(300):
        j = tc.get(f'/api/admin/imports/{job}', headers=h).json()
        if not j['running'] and j['status'] != 'running' and (j['result'] or j['status'] == 'failed'): return j
        time.sleep(0.05)
    raise AssertionError('import did not finish')


def test_api_dry_run_then_import_with_the_machine_token(client, cfg):
    r = client.post('/api/admin/imports', json=dict(url=URL, dry_run=True), headers=X)
    assert r.status_code == 202
    j = wait_job(client, r.json()['job_id'])
    assert (j['status'], j['files'], j['skipped'], j['result']['downloaded']) == ('dry_run', 2, 4, 0) and blank(cfg)
    machine = TestClient(client.app)
    h = {**X, 'Authorization': f'Bearer {TOKEN}'}
    r = machine.post('/api/admin/imports', json=dict(url=URL), headers=h)
    assert r.status_code == 202
    j = wait_job(machine, r.json()['job_id'], h)
    assert (j['status'], j['files'], j['folder'], j['requested_by']) == ('done', 2, D, '(machine token)'), j
    assert j['result']['ingest']['files_changed'] == 2 and 'ingest #' in j['message']
    assert D in [f['folder'] for f in client.get('/api/meta').json()['folders']]               # folder appears in the dashboard
    ov = client.get('/api/admin/imports').json()
    assert [x['status'] for x in ov['jobs']][:2] == ['done', 'dry_run'] and ov['enabled'] and ov['allowed'] == ['s3://example-log-bucket/k8s-logs/<YYYY-MM-DD>/']
    assert {'import.start'} <= {x['action'] for x in client.get('/api/admin/audit').json()['rows']}


@pytest.mark.parametrize('url, code', [('s3://other-bucket/k8s-logs/2026-01-05/', 'bucket_not_allowed'), ('s3://example-log-bucket/k8s-logs/x/', 'invalid_date'), ('', 'invalid_url')])
def test_api_rejected_link_400(client, s3, url, code):
    r = client.post('/api/admin/imports', json=dict(url=url), headers=X)
    assert (r.status_code, r.json()['error']['code']) == (400, code) and s3.log == []
    assert client.get('/api/admin/imports').json()['jobs'] == []


def test_api_temporary_credentials(client, cfg, auth_url, s3):
    h = {**X, 'Authorization': f'Bearer {TOKEN}'}
    machine = TestClient(client.app)
    assert machine.post('/api/admin/imports/credentials', json=dict(access_key_id=KEY_OK, secret_access_key=SECRET), headers=h).status_code == 401
    assert machine.delete('/api/admin/imports/credentials', headers=h).status_code == 401
    r = client.post('/api/admin/imports/credentials', json=dict(access_key_id='AKIAPASTEDTEST000002', secret_access_key=SECRET), headers=X)
    assert r.status_code == 200 and r.json()['credentials']['source'] == 'pasted' and SECRET not in r.text and 'AKIAPASTED' not in r.text
    meta = client.get('/api/meta').json()['imports']
    assert meta == dict(enabled=True, credentials=dict(available=True, source='pasted'))
    # pasted key unknown to the fake S3 -> import fails with a cause; inbox stays empty
    j = wait_job(client, client.post('/api/admin/imports', json=dict(url=URL), headers=X).json()['job_id'])
    assert j['status'] == 'failed' and 'S3 denied' in j['message'] and blank(cfg)
    assert client.delete('/api/admin/imports/credentials', headers=X).json()['credentials']['source'] == 'environment'
    # secrets are not in the response, the audit, or the account database
    everything = client.get('/api/admin/audit?limit=500').text + client.get('/api/admin/imports').text + client.get(f'/api/admin/imports/{j["job_id"]}').text
    assert SECRET not in everything and KEY_OK not in everything and 'AKIAPASTED' not in everything
    assert {'import.credentials.set', 'import.credentials.clear'} <= {x['action'] for x in client.get('/api/admin/audit?limit=500').json()['rows']}
    if auth_url.startswith('sqlite:///'):
        fill = open(auth_url[len('sqlite:///'):], 'rb').read()
        assert SECRET.encode() not in fill and b'AKIAPASTED' not in fill


def test_pasted_credentials_are_gone_after_a_restart(cfg, auth_url, monkeypatch, s3):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    c = dataclasses.replace(cfg, auth_database_url=auth_url, aws_access_key_id='', aws_secret_access_key='')
    con = db.open(c.db_path); con.close()
    for i in range(2):
        with TestClient(appmod.create_app(c)) as tc:
            assert tc.post('/api/auth/login', json=dict(username='admin', password=PW if i == 0 else PW2), headers=X).status_code == 200
            if i == 0:
                assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
                assert tc.post('/api/admin/imports/credentials', json=dict(access_key_id=KEY_OK, secret_access_key=SECRET), headers=X).status_code == 200
                assert tc.get('/api/admin/imports').json()['credentials']['available'] is True
            else:
                assert tc.get('/api/admin/imports').json()['credentials']['available'] is False
                r = tc.post('/api/admin/imports', json=dict(url=URL), headers=X)
                assert (r.status_code, r.json()['error']['code']) == (400, 'no_credentials')


def test_plain_user_403(client):
    assert client.post('/api/admin/users', json=dict(username='rina', display_name='Rina', role='user', password='rina-initial-password-123'), headers=X).status_code == 201
    tc = TestClient(client.app)
    assert tc.post('/api/auth/login', json=dict(username='rina', password='rina-initial-password-123'), headers=X).status_code == 200
    assert tc.post('/api/me/password', json=dict(old_password='rina-initial-password-123', new_password='rina-new-password-456'), headers=X).status_code == 200
    for m, p in (('get', '/api/admin/imports'), ('post', '/api/admin/imports'), ('get', '/api/admin/imports/1'), ('post', '/api/admin/imports/credentials'),
                 ('delete', '/api/admin/imports/credentials')):
        r = getattr(tc, m)(p, headers=X) if m in ('get', 'delete') else getattr(tc, m)(p, json={}, headers=X)
        assert r.status_code == 403, p


def test_without_boto3_refused_with_how_to_install(client, monkeypatch):
    """Owner report 2026-10-07: import failed with "No module named 'botocore'" (s3 package not installed). Now rejected
    up front with a message on how to install it, without creating a failed job; the UI reads `library` to disable import."""
    monkeypatch.setattr(importer, 'library_ok', lambda *a: False)
    before = len(client.get('/api/admin/imports').json()['jobs'])
    r = client.post('/api/admin/imports', json=dict(url=URL), headers=X)
    assert r.status_code == 400 and r.json()['error']['code'] == 'no_s3_library' and 'pip install' in r.json()['error']['message']
    ov = client.get('/api/admin/imports').json()
    assert ov['library'] is False and len(ov['jobs']) == before
    monkeypatch.undo()
    assert importer.library_ok() is True and client.get('/api/admin/imports').json()['library'] is True


# ------------------------------------------------------------------ extract .log.gz -> .log (owner request 2026-10-07)
FE_GZ = obj('web-frontend', 'pod-f', ext='.log.gz')
FE_LOG = os.path.join('tenant', 'web-frontend', f'log_web-frontend_pod-f_{D}-00-00.log')


def test_gz_is_extracted_to_log(cfg, s3):
    r = importer.run(cfg, URL, importer.Credentials(cfg))
    folder = os.path.join(cfg.inbox_dir, D)
    assert r['extracted'] == 1 and not os.path.exists(os.path.join(folder, FE_LOG + '.gz'))
    assert open(os.path.join(folder, FE_LOG), 'rb').read() == gzip.decompress(CONTENTS[FE_GZ])
    man = json.load(open(os.path.join(folder, importer.MANIFEST)))
    assert man[FE_GZ[len(PRE):]]['stored'] == FE_GZ[len(PRE):-3] and man[FE_GZ[len(PRE):]]['size'] == len(CONTENTS[FE_GZ])
    r2 = importer.run(cfg, URL, importer.Credentials(cfg))                  # again: no re-download and no re-extract
    assert (r2['downloaded'], r2['extracted']) == (0, 0)
    con = db.open(cfg.db_path)
    try: assert ingest.run(cfg, con, folder=D, workers=0)['files_failed'] == 0
    finally: con.close()


def test_without_extraction_gz_is_kept_as_is(cfg, s3):
    c = dataclasses.replace(cfg, import_extract=False)
    r = importer.run(c, URL, importer.Credentials(c))
    folder = os.path.join(cfg.inbox_dir, D)
    assert r['extracted'] == 0 and os.path.isfile(os.path.join(folder, FE_LOG + '.gz')) and not os.path.exists(os.path.join(folder, FE_LOG))


def test_gz_from_an_earlier_import_is_extracted_without_downloading_again(cfg, s3):
    importer.run(dataclasses.replace(cfg, import_extract=False), URL, importer.Credentials(cfg))   # like the owner's 2026-10-07 folder
    n0 = len(s3.gets())
    r = importer.run(cfg, URL, importer.Credentials(cfg))
    folder = os.path.join(cfg.inbox_dir, D)
    assert (r['downloaded'], r['extracted']) == (0, 1) and len(s3.gets()) == n0
    assert os.path.isfile(os.path.join(folder, FE_LOG)) and not os.path.exists(os.path.join(folder, FE_LOG + '.gz'))
    assert importer.run(cfg, URL, importer.Credentials(cfg))['extracted'] == 0
    assert importer.run(cfg, URL, importer.Credentials(cfg), dry_run=True)['extracted'] == 0


def test_corrupt_gz_cancels_the_import(cfg, s3):
    s3.buckets['example-log-bucket'][FE_GZ] = gzip.compress(b'log line\n' * 100)[:-12]     # truncated
    failed(cfg, URL, 'bad_gzip')
    assert blank(cfg) and os.listdir(os.path.join(cfg.data_dir, 'tmp')) == []


def test_too_large_extraction_is_cancelled(cfg, s3, monkeypatch):
    monkeypatch.setattr(importer, 'EXTRACT_RATIO', 1e-8)        # ±10-byte limit: a fake "gzip bomb"
    failed(cfg, URL, 'extract_too_large')
    assert blank(cfg)


# ------------------------------------------------------------------ automatic sync from the parent prefix (S4_S3_WATCH)
WATCH = 's3://example-log-bucket/k8s-logs/'


def test_pick_new_folders_and_recheck():
    import datetime as dt
    today = dt.date(2026, 10, 7)
    fs = ['2026-08-01', '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-05', '2026-10-06', '2026-10-07']
    known = {'2026-10-02', '2026-10-06', '2026-10-07'}
    take, again, wait = s3_import.pick(fs, known, {'2026-10-06', '2026-10-07'}, today, days=30, recheck_days=1, max_new=2)
    assert (take, again, wait) == (['2026-10-03', '2026-10-05'], ['2026-10-06', '2026-10-07'], 1)   # 08-01 outside 30 days; 10-01 follows later
    assert s3_import.pick(fs, known, set(), today, days=0, recheck_days=1, max_new=10)[0] == ['2026-08-01', '2026-10-01', '2026-10-03', '2026-10-05']


@pytest.mark.parametrize('watch, code', [('s3://example-log-bucket/k8s-logs/', None), ('s3://other-bucket/k8s-logs/', 'watch_not_allowed'),
                                        ('s3://example-log-bucket/other/', 'watch_not_allowed'), ('https://x/y', 'invalid_watch'),
                                        ('s3://example-log-bucket/k8s-logs/../x/', 'invalid_watch')])
def test_watch_prefix_is_checked_against_the_allow_list(cfg, watch, code):
    c = dataclasses.replace(cfg, s3_watch=watch)
    if code is None: assert s3_import.parse_watch(c) == [('example-log-bucket', 'k8s-logs/')]
    else:
        with pytest.raises(importer.ImportFail) as e: s3_import.parse_watch(c)
        assert e.value.code == code


@pytest.fixture
def wclient(cfg, auth_url, monkeypatch, s3):
    """S3 holds folders 2026-01-02 (already in the local log folder), 01-05, 01-06, 01-07, and a non-date prefix."""
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    b = s3.buckets['example-log-bucket']
    for f in ('2026-01-02', '2026-01-06', '2026-01-07'): b[obj('auth-service', 'pod-a', folder=f)] = APPS
    b['k8s-logs/old-archive/x.log'] = b'x'
    c = dataclasses.replace(cfg, auth_database_url=auth_url, s3_watch=WATCH, s3_watch_days=0, s3_watch_max_folders=2, s3_watch_recheck_days=400, s3_watch_minutes=0)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    with TestClient(appmod.create_app(c)) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        yield tc


def sync(tc, h=X, read_back=None):
    assert tc.post('/api/admin/imports/sync', headers=h).status_code == 202
    tc.app.state.imports.wait(60)
    return (read_back or tc).get('/api/admin/imports', headers=X).json()['watch']['last']


def test_automatic_sync_fetches_new_folders_without_a_link(wclient, cfg, s3):
    w = wclient.get('/api/admin/imports').json()['watch']
    assert w['enabled'] and w['sources'] == [WATCH] and w['problem'] is None and w['last'] is None
    r = sync(wclient)
    assert (r['imported'], r['waiting'], r['errors'], r['failed']) == (['2026-01-06', '2026-01-07'], 1, [], []), r   # newest first, max. 2
    assert r['sources'] == [dict(source=WATCH, folders=4, new=3)]                    # 01-02 is in the local log folder: not fetched
    folders = [f['folder'] for f in wclient.get('/api/meta').json()['folders']]
    assert {'2026-01-06', '2026-01-07'} <= set(folders) and D not in folders
    jobs = wclient.get('/api/admin/imports').json()['jobs']
    assert [(j['folder'], j['status']) for j in jobs[:2]] == [('2026-01-07', 'done'), ('2026-01-06', 'done')] and jobs[0]['requested_by'] == 'admin'
    # next round via machine token (cron): pending folders follow; existing ones are not downloaded again
    n0 = len(s3.gets())
    r = sync(TestClient(wclient.app), {**X, 'Authorization': f'Bearer {TOKEN}'}, wclient)
    assert (r['imported'], r['rechecked'], r['waiting']) == ([D], [], 0) and r['by'] == '(machine token)'
    assert len(s3.gets()) - n0 == 2                                                   # only the two objects of folder D
    # file arriving later in an already-synced folder: rechecked, only new objects are downloaded
    s3.buckets['example-log-bucket'][obj('web-frontend', 'pod-f', folder='2026-01-07')] = logs_mini.lines('web-frontend').encode()
    n0 = len(s3.gets())
    r = sync(wclient)
    assert (r['imported'], r['rechecked']) == ([], ['2026-01-07']) and len(s3.gets()) - n0 == 1
    assert {'import.sync'} <= {x['action'] for x in wclient.get('/api/admin/audit').json()['rows']}


def test_folder_deleted_by_an_admin_is_not_synced_again(wclient, cfg):
    sync(wclient)
    assert wclient.delete('/api/admin/folders/2026-01-07?delete_inbox=true', headers=X).status_code == 200
    r = sync(wclient)
    assert '2026-01-07' not in r['imported'] + r['rechecked'] and r['imported'] == [D]
    assert not os.path.exists(os.path.join(cfg.inbox_dir, '2026-01-07'))


def test_sync_not_set_up_and_without_credentials(client, cfg):
    r = client.post('/api/admin/imports/sync', headers=X)
    assert (r.status_code, r.json()['error']['code']) == (400, 'watch_disabled')
    assert client.get('/api/admin/imports').json()['watch']['enabled'] is False


def test_scheduler_checks_by_itself(wclient):
    """Settings saved from the UI -> the scheduler is woken and checks ±5 seconds later, without a button."""
    m = wclient.app.state.imports
    r = wclient.put('/api/admin/imports/watch', json=dict(url=WATCH, minutes=5, enabled=True), headers=X)
    assert r.status_code == 200 and r.json()['minutes'] == 5
    assert config.read_dotenv(os.path.join(wclient.app.state.cfg.state_dir, '.env'))['S4_S3_WATCH_MINUTES'] == '5'   # written to .env
    for _ in range(400):
        if m.watch['last'] and not m.state['running']: break
        time.sleep(0.05)
    assert m.watch['last']['by'] == '(automatic S3 sync)' and m.watch['last']['imported'] == ['2026-01-06', '2026-01-07']
    assert wclient.get('/api/admin/imports').json()['watch']['next_check']


@pytest.fixture
def plain(cfg, auth_url, monkeypatch, s3):
    """Without S4_S3_WATCH in .env: sync only via the address the admin fills in on the UI."""
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    b = s3.buckets['example-log-bucket']
    b[obj('auth-service', 'pod-a', folder='2026-01-06')] = APPS
    c = dataclasses.replace(cfg, auth_database_url=auth_url, s3_watch_days=0)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    return c


def sign_in_admin(tc):
    assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
    assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200


@pytest.mark.parametrize('url, code', [('s3://example-log-bucket/k8s-logs/2026-01-06/', 'watch_is_date'), ('s3://other-bucket/x/', 'watch_not_allowed'),
                                      ('example-log-bucket/k8s-logs', 'invalid_watch'), ('', 'invalid_watch')])
def test_address_from_the_page_is_validated(plain, url, code):
    with TestClient(appmod.create_app(plain)) as tc:
        sign_in_admin(tc)
        r = tc.put('/api/admin/imports/watch', json=dict(url=url, minutes=60, enabled=True), headers=X)
        assert (r.status_code, r.json()['error']['code']) == (400, code)


def test_address_from_the_page_is_saved_and_used(plain, s3):
    with TestClient(appmod.create_app(plain)) as tc:
        sign_in_admin(tc)
        w = tc.get('/api/admin/imports').json()['watch']
        assert (w['enabled'], w['source'], w['url']) == (False, None, '')
        assert tc.post('/api/admin/imports/sync', headers=X).json()['error']['code'] == 'watch_disabled'
        r = tc.put('/api/admin/imports/watch', json=dict(url='s3://example-log-bucket/k8s-logs', minutes=60, enabled=True), headers=X)   # without trailing "/"
        assert r.status_code == 200, r.text
        w = r.json()
        assert (w['enabled'], w['sources'], w['source'], w['minutes']) == (True, [WATCH], 'file', 60)
        env = config.read_dotenv(os.path.join(plain.state_dir, '.env'))
        assert env == {'S4_S3_WATCH': 's3://example-log-bucket/k8s-logs'}   # only values that differ from the current ones are written
        assert 'import.watch' in {x['action'] for x in tc.get('/api/admin/audit').json()['rows']}
        assert tc.put('/api/admin/imports/watch', json=dict(url=WATCH, minutes=7, enabled=True), headers=X).status_code == 400   # interval outside the choices
    # settings persist after a server restart (read again from .env), then the check uses that address
    with TestClient(appmod.create_app(reload_with(plain))) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW2), headers=X).status_code == 200   # password already changed above
        assert tc.get('/api/admin/imports').json()['watch']['sources'] == [WATCH]
        assert tc.post('/api/admin/imports/sync', headers=X).status_code == 202
        tc.app.state.imports.wait(60)
        assert tc.get('/api/admin/imports').json()['watch']['last']['imported'] == [D, '2026-01-06']
        # turned off from the UI: S4_S3_WATCH_ENABLED=false, address kept; button rejected
        assert tc.put('/api/admin/imports/watch', json=dict(url=WATCH, minutes=60, enabled=False), headers=X).json()['enabled'] is False
        assert tc.post('/api/admin/imports/sync', headers=X).json()['error']['code'] == 'watch_disabled'
        assert tc.app.state.cfg.s3_watch == WATCH
        assert config.read_dotenv(os.path.join(plain.state_dir, '.env'))['S4_S3_WATCH_ENABLED'] == 'false'


def reload_with(c):
    """Like a server restart: all test values as environment, EXCEPT those in .env (read by config.load)."""
    path = os.path.join(c.state_dir, '.env')
    fv = config.read_dotenv(path)
    env = {config.env_name(f.name): envfile.fmt(getattr(c, f.name)) for f in dataclasses.fields(c)}
    return config.load(env={k: v for k, v in env.items() if k not in fv}, dotenv=path)


def test_plain_user_may_not_set_up_sync(plain):
    with TestClient(appmod.create_app(plain)) as tc:
        sign_in_admin(tc)
        assert tc.post('/api/admin/users', json=dict(username='rina', display_name='Rina', role='user', password='rina-initial-password-123'), headers=X).status_code == 201
        u = TestClient(tc.app)
        u.post('/api/auth/login', json=dict(username='rina', password='rina-initial-password-123'), headers=X)
        u.post('/api/me/password', json=dict(old_password='rina-initial-password-123', new_password='rina-new-password-123'), headers=X)
        assert u.put('/api/admin/imports/watch', json=dict(url=WATCH, minutes=60, enabled=True), headers=X).status_code == 403


@pytest.fixture
def kclient(cfg, auth_url, monkeypatch, s3):
    """Kafka filled ITS OWN inbox with 2026-01-06 (auth-service, the same lines S3 has, and report-service, which only
    Kafka has); S3 has 2026-01-06 too. Two sources, two databases: nothing is shared."""
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    s3.buckets['example-log-bucket'][obj('auth-service', 'pod-a', folder='2026-01-06')] = APPS
    k = os.path.join(cfg.kafka_inbox, '2026-01-06', 'tenant')
    for svc, pod in (('auth-service', 'pod-a'), ('report-service', 'pod-r')):
        os.makedirs(os.path.join(k, svc), exist_ok=True)
        with open(os.path.join(k, svc, f'log_{svc}_{pod}_2026-01-06-00-00.log'), 'w', encoding='utf-8') as fh: fh.write(logs_mini.lines(svc))
    c = dataclasses.replace(cfg, auth_database_url=auth_url, s3_watch=WATCH, s3_watch_days=0, s3_watch_max_folders=5, s3_watch_recheck_days=0, s3_watch_minutes=0)
    with TestClient(appmod.create_app(c)) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        tc.app.state.sources['kafka'].ingest.start(by='test'); tc.app.state.sources['kafka'].ingest.wait(60)
        yield tc


def meta_of(tc, source):
    return {f['folder']: f for f in tc.get(f'/api/meta?source={source}').json()['folders']}


def test_s3_and_kafka_are_two_sources_that_never_mix(kclient, cfg):
    """Owner rule 2026-10-23: a day has an S3 version and a Kafka version, each complete, each from one source."""
    k = meta_of(kclient, 'kafka')['2026-01-06']
    assert k['source'] == 'kafka' and k['services'] == 2                         # both Kafka services
    assert '2026-01-06' not in meta_of(kclient, 's3')                            # S3 has not synced it yet
    r = sync(kclient)
    assert '2026-01-06' in r['imported'] and r['errors'] == [] and r['failed'] == [], r
    s = meta_of(kclient, 's3')['2026-01-06']
    assert s['source'] == 's3' and s['services'] == 1                            # S3's service only: no Kafka-only report-service
    k = meta_of(kclient, 'kafka')['2026-01-06']
    assert k['source'] == 'kafka' and k['services'] == 2                         # Kafka's day is untouched by the S3 import
    assert not os.path.exists(os.path.join(cfg.inbox_dir, '2026-01-06', 'tenant', 'report-service'))
    assert os.listdir(os.path.join(cfg.kafka_inbox, '2026-01-06', 'tenant', 'report-service'))
    assert kclient.get('/api/meta?source=nope').status_code == 400
    r = sync(kclient)
    assert '2026-01-06' not in r['imported']                                     # synced once


def test_kafka_lines_for_a_date_with_an_s3_copy_are_still_kept(tmp_path):
    """Kafka no longer yields to S3: its lines are written whatever S3 has."""
    from monishield.infrastructure import inbox
    import datetime
    t = datetime.datetime(2026, 1, 5, 3, 0, tzinfo=datetime.timezone.utc)
    rec = dict(ns='tenant', svc='report-service', pod='pod-r', line='x', t=t)
    sp = inbox.Spool(str(tmp_path))
    f = sp.add(rec)
    os.makedirs(tmp_path / f); (tmp_path / f / importer.MANIFEST).write_text('{}')
    assert sp.flush() == {f: 1} and (tmp_path / f / 'tenant' / 'report-service').exists()


def test_migrate_moves_kafka_files_out_of_the_s3_inbox(tmp_path):
    """Production case (2026-10-23): before the two-sources layout Kafka's files lived in the S3 inbox (mark file), mixed with
    the S3 copy, plus an 'aside' folder. They move to the Kafka inbox; S3 files stay."""
    from monishield.infrastructure import inbox
    root, kroot = tmp_path / 'inbox', tmp_path / 'inbox' / 'kafka'
    for f in ('2026-10-14', '2026-10-15'):
        (root / f / 'ns' / 'only-kafka').mkdir(parents=True); (root / f / 'ns' / 'only-kafka' / 'k.log').write_text('k')
        (root / f / inbox.MARK).write_text('{}')
    (root / '2026-10-14' / 'ns' / 's3svc').mkdir(); (root / '2026-10-14' / 'ns' / 's3svc' / 's.log').write_text('s')
    (root / '2026-10-14' / importer.MANIFEST).write_text(json.dumps({'ns/s3svc/s.log': dict(key='k', size=1, etag='e')}))
    (root / inbox.SUPERSEDED / '2026-10-13' / 'ns' / 'aside').mkdir(parents=True); (root / inbox.SUPERSEDED / '2026-10-13' / 'ns' / 'aside' / 'a.log').write_text('a')
    (root / '2026-10-16').mkdir(); (root / '2026-10-16' / 'plain.log').write_text('s3 only, no mark')
    kafka_only, split = inbox.migrate(str(root), str(kroot))
    assert (kafka_only, split) == (['2026-10-15'], ['2026-10-14'])
    assert (root / '2026-10-14' / 'ns' / 's3svc' / 's.log').exists() and not (root / '2026-10-14' / 'ns' / 'only-kafka').exists()
    assert not (root / '2026-10-14' / inbox.MARK).exists() and not (root / '2026-10-15').exists()
    assert (kroot / '2026-10-14' / 'ns' / 'only-kafka' / 'k.log').read_text() == 'k' and (kroot / '2026-10-15' / 'ns' / 'only-kafka' / 'k.log').exists()
    assert (kroot / '2026-10-13' / 'ns' / 'aside' / 'a.log').read_text() == 'a' and not (root / inbox.SUPERSEDED).exists()
    assert (root / '2026-10-16' / 'plain.log').exists()                                                      # S3-only folders untouched
    assert inbox.migrate(str(root), str(kroot)) == ([], [])                                                 # nothing left to do


def test_server_start_migrates_the_old_layout_and_the_s3_database_forgets_kafka_days(cfg, auth_url, monkeypatch):
    """A Kafka-only day was ingested into the S3 database by the old version: after the move the S3 database no longer has it."""
    from monishield.infrastructure import inbox
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    d = os.path.join(cfg.inbox_dir, '2026-01-06', 'tenant', 'report-service')
    os.makedirs(d)
    with open(os.path.join(d, 'log_report-service_pod-r_2026-01-06-00-00.log'), 'w', encoding='utf-8') as fh: fh.write(logs_mini.lines('report-service'))
    with open(os.path.join(cfg.inbox_dir, '2026-01-06', inbox.MARK), 'w') as fh: fh.write('{}')
    c = dataclasses.replace(cfg, auth_database_url=auth_url)
    con = db.open(c.db_path); ingest.run(c, con, workers=0)                         # the old version put it in the S3 database
    assert con.execute("SELECT count(*) FROM folder_state WHERE folder = '2026-01-06'").fetchone()[0] == 1
    con.close()
    with TestClient(appmod.create_app(c)) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        assert '2026-01-06' not in meta_of(tc, 's3')
        tc.app.state.sources['kafka'].ingest.start(by='test'); tc.app.state.sources['kafka'].ingest.wait(60)
        assert meta_of(tc, 'kafka')['2026-01-06']['services'] == 1
    assert os.path.exists(os.path.join(cfg.kafka_inbox, '2026-01-06', 'tenant', 'report-service'))


def test_cli_sync_runs_through_the_server(wclient, cfg, monkeypatch, capsys):
    """`python -m monishield sync` (for cron): the server checks the parent folder; no API path to remember."""
    from monishield.interfaces import cli
    tc = TestClient(wclient.app)

    def api(c, method, path, body=None):
        r = tc.request(method, path, json=body, headers={**X, 'Authorization': f'Bearer {TOKEN}'})
        return r.status_code, r.json()
    monkeypatch.setattr(cli, '_api', api)
    assert cli.cmd_sync(cfg, None) == 0
    out = capsys.readouterr().out
    assert out.startswith('sync: 2 folders imported or rechecked') and '2026-01-07' in out and '0 errors' in out
    monkeypatch.setattr(cli, '_api', lambda *a, **k: None)
    assert cli.cmd_sync(cfg, None) == 2                                            # server down: says so, exit code 2
