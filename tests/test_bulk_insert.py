"""Speed fixes of 2026-10-27 (ingest profile): the bulk insert gives the same rows as executemany, and the account analysis
gives the same result as the first (quadratic) version."""
import collections, datetime, os, random, tempfile, time

import pytest

from monishield.domain import rules
from monishield.infrastructure import db

WEIRD = ['x"y', 'a\\b', 'üñí☃', 'tab\there', 'new\nline', "'; DROP TABLE x; --", '<script>alert(1)</script>', '', ' ', '日本語', 'null', '{"a": 1}']
MAP = 'CAST(map(?, ?) AS MAP(VARCHAR, INTEGER))'


def same(con, a, b):
    return (con.execute(f'SELECT count(*) FROM (SELECT * FROM {a} EXCEPT SELECT * FROM {b})').fetchone()[0] == 0
            and con.execute(f'SELECT count(*) FROM (SELECT * FROM {b} EXCEPT SELECT * FROM {a})').fetchone()[0] == 0
            and con.execute(f'SELECT count(*) FROM {a}').fetchone() == con.execute(f'SELECT count(*) FROM {b}').fetchone())


def test_insert_rows_equals_executemany_for_maps_lists_dates_and_awkward_text():
    con = db.open(':memory:')
    for t in ('o', 'n'): con.execute(f'CREATE TABLE {t} AS SELECT * FROM agg_crs_url WHERE false')
    rows = []
    for i in range(300):
        w = WEIRD[i % len(WEIRD)]
        rows.append(['2026-10-10', f'cat{i % 4}', f'GET /p/{w}?q={i}', w, i % 4, [i, i + 1], i * 7, i % 9, f'10.1.{i % 250}.1',
                     {'200': i, '404': 1}, [i, 2 ** 31], [w, 'up'], w[:20], '2026-10-10 00:00:00', f'2026-10-10 23:{i % 60:02d}:00'])
    con.executemany(f'INSERT INTO o VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, {MAP}, ?, ?, ?, ?, ?)',
                    [r[:9] + [list(r[9]), list(r[9].values())] + r[10:] for r in rows])
    db.insert_rows(con, 'n', rows)
    assert same(con, 'o', 'n') and con.execute('SELECT count(*) FROM n').fetchone()[0] == 300
    assert con.execute("SELECT method_path FROM n WHERE method_path LIKE '%\n%' LIMIT 1").fetchone()                 # the newline survived


def test_insert_rows_handles_null_nan_dates_bool_and_temp_tables():
    con = db.open(':memory:')
    con.execute('CREATE TABLE ip AS SELECT * FROM ip_info WHERE false')
    cols = [c[0] for c in con.execute('DESCRIBE ip').fetchall()]
    row = lambda ip, **k: [ip] + [k.get(c) for c in cols[1:]]
    db.insert_rows(con, 'ip', [row('1.1.1.1', asn=13335, cc='AU', org='Cloudflare "1"', is_private=False, lat=-33.4, lon=151.2, geo_checked=True,
                                    asn_db_date=datetime.date(2026, 10, 1)),
                               row('10.0.0.1', is_private=True),                                  # nothing known: NULLs
                               row('2.2.2.2', lat=float('nan'), lon=float('inf'))])               # JSON has no NaN: NULL
    r = {x[0]: x for x in con.execute('SELECT ip, asn, cc, org, is_private, lat, lon, asn_db_date::VARCHAR FROM ip').fetchall()}
    assert r['1.1.1.1'] == ('1.1.1.1', 13335, 'AU', 'Cloudflare "1"', False, -33.4, 151.2, '2026-10-01')
    assert r['10.0.0.1'][1:4] == (None, None, None) and r['10.0.0.1'][4] is True
    assert r['2.2.2.2'][5] is None and r['2.2.2.2'][6] is None
    con.execute('CREATE TEMP TABLE _t (m VARCHAR, r INTEGER[], s SMALLINT)')
    db.insert_rows(con, '_t', [['a', [1, 2, 3], 5], ['b', [], None]])
    assert con.execute('SELECT m, r, s FROM _t ORDER BY m').fetchall() == [('a', [1, 2, 3], 5), ('b', [], None)]


def test_insert_rows_nothing_to_do_leaves_no_file_and_errors_clean_up():
    con = db.open(':memory:')
    before = set(os.listdir(tempfile.gettempdir()))
    db.insert_rows(con, 'agg_biz', [])
    con.execute('CREATE TABLE t (a BIGINT)')
    with pytest.raises(Exception): db.insert_rows(con, 't', [['not a number']])                         # the engine refuses the value
    assert not [f for f in set(os.listdir(tempfile.gettempdir())) - before if f.endswith('.jsonl')]       # the temp file is gone either way


def test_insert_rows_is_fast_where_executemany_is_slow():
    con = db.open(':memory:')
    rows = [['2026-10-10', f'10.{i // 65000}.{i // 250 % 250}.{i % 250}', i, {'a': i}, {'200': i}, 'ua', '2026-10-10 00:00:00', '2026-10-10 01:00:00'] for i in range(20000)]
    t = time.time(); db.insert_rows(con, 'agg_attack_ip', rows)
    assert time.time() - t < 5 and con.execute('SELECT count(*) FROM agg_attack_ip').fetchone()[0] == 20000      # executemany: ~60 s for the same rows


# ---------------------------------------------------------------- account analysis
def _accounts_reference(lev, window_min=60):
    """The first version (quadratic), kept here as the reference the fast one must agree with."""
    per = collections.defaultdict(list)
    for e in sorted(lev): per[e[1]].append(e)
    rows = []
    for user, ev in per.items():
        fails = [e for e in ev if e[3] == 'fail']; oks = [e for e in ev if e[3] == 'ok']
        if not fails: continue
        flags, hits = set(), []
        for ok in oks:
            recent = [f for f in fails if 0 <= (rules.dt(ok[0]) - rules.dt(f[0])).total_seconds() <= window_min * 60]
            if len(recent) >= 3:
                flags.add('Sukses Setelah ≥3 Gagal')
                if ok[2] not in {f[2] for f in recent}: flags.add('Sukses Dari IP Berbeda'); hits.append(f'{ok[0]} sukses dari {ok[2]}')
        if len({f[2] for f in fails}) >= 2: flags.add('Dicoba Dari ≥2 IP')
        rows.append([user, len(fails), sum(e[3] == 'lock' for e in ev), len(oks), sorted({f[2] for f in fails}), sorted({o[2] for o in oks}),
                     sorted(flags), ev[0][0], ev[-1][0], hits[:3]])
    return sorted(rows, key=lambda r: (-('Sukses Dari IP Berbeda' in r[6]), -len(r[6]), -r[1]))[:150]


def _events(rng, n, users, ips, minutes):
    base = datetime.datetime(2026, 10, 10, 0, 0)
    return [((base + datetime.timedelta(minutes=rng.randrange(minutes))).strftime('%Y-%m-%d %H:%M'), f'user{rng.randrange(users)}',
             f'10.0.0.{rng.randrange(ips)}', rng.choice(['fail', 'fail', 'fail', 'ok', 'lock'])) for _ in range(n)]


@pytest.mark.parametrize('seed', range(40))
def test_accounts_gives_the_same_result_as_the_first_version(seed):
    rng = random.Random(seed)
    lev = _events(rng, rng.choice([5, 30, 150, 400]), rng.choice([1, 3, 12]), rng.choice([1, 2, 5]), rng.choice([20, 90, 400, 1500]))
    assert rules.accounts(lev) == _accounts_reference(lev)
    assert rules.accounts(lev, 5) == _accounts_reference(lev, 5)


def test_accounts_window_edges_are_inclusive_and_a_later_failure_does_not_count():
    f = lambda m, ip='1.1.1.1': (f'2026-10-10 {m}', 'ann', ip, 'fail')
    lev = [f('09:00'), f('09:10'), f('09:20'), ('2026-10-10 10:00', 'ann', '2.2.2.2', 'ok')]        # the first failure is exactly 60 min before
    assert rules.accounts(lev)[0][6] == ['Sukses Dari IP Berbeda', 'Sukses Setelah ≥3 Gagal']
    lev = [f('08:59'), f('09:10'), f('09:20'), ('2026-10-10 10:00', 'ann', '2.2.2.2', 'ok')]        # one minute outside: only two failures remain
    assert rules.accounts(lev)[0][6] == [] and rules.accounts(lev) == _accounts_reference(lev)
    lev = [f('09:00'), f('09:10'), f('09:20'), ('2026-10-10 09:15', 'ann', '2.2.2.2', 'ok'), f('09:30')]   # failures after the success do not count
    assert rules.accounts(lev) == _accounts_reference(lev) and 'Sukses Setelah ≥3 Gagal' not in rules.accounts(lev)[0][6]


def test_accounts_stays_fast_under_a_password_guessing_attack():
    rng = random.Random(1)
    lev = _events(rng, 6000, 1, 40, 1200)                       # one account, thousands of events (the shape that took 33 s)
    t = time.time(); r = rules.accounts(lev)
    assert time.time() - t < 2 and r[0][1] > 3000
