"""Live map from collector access lines (Stage 57): one hub per source, lines of http rules become coordinates-only events."""
import json, threading, time

import httpx
import pytest

from monishield.application import live_map
from monishield.domain import log_formats
from monishield.infrastructure import geo_lookup
from test_collector_receiver import make, otlp, post   # noqa: F401  (fixture and helpers of the receiver tests)
from test_kafka import serve
from test_refdata import write_geolite
from test_api import X, cfg   # noqa: F401

CADDY = '{"level":"info","ts":1793786136.5,"logger":"http.log.access.log0","msg":"handled request","request":{"remote_ip":"172.71.1.1","client_ip":"%s","method":"GET","uri":"/api/v1/me","headers":{"User-Agent":["curl/8.5.0"]}},"duration":0.012,"size":512,"status":200}'
RULES = log_formats.rules_from({'service': [{'match': 'caddy', 'format': 'caddy-json'}, {'match': 'worker', 'format': 'json'}, {'match': '*', 'format': 'plain'}]})
JAKARTA, SYDNEY = '44.44.44.5', '66.66.66.9'


class FakeGeo:
    """Stands in for the offline lookup: two known visitors, and a count of how often it was asked."""
    known = {JAKARTA: (-6.2, 106.8, 'Jakarta', 'ID'), SYDNEY: (-33.87, 151.21, 'Sydney', 'AU')}
    def __init__(self): self.asked = []
    def locate(self, ip):
        self.asked.append(ip)
        return self.known.get(ip)


@pytest.fixture
def rules(monkeypatch):
    """rules() after make(): creating the app sets the rules of its configuration; the original is put back after the test."""
    monkeypatch.setattr(log_formats, '_current', None)
    return lambda: log_formats.use(RULES)


def totals(hub):
    hub._close()
    out = {}
    for _, ps, _ in hub.ring:
        for la, lo, n, mod in ps: out[la, lo, mod] = out.get((la, lo, mod), 0) + n
    return out


def test_one_hub_per_live_source(make):
    tc, key, root = make()
    st = tc.app.state
    assert st.collector_feed.live is not st.kafka.live
    assert st.collector_feed.live.ctx is st.sources['collector']   # the visitors of the collector database


def test_access_lines_of_http_rules_become_coordinates(make, rules):
    tc, key, root = make(); rules()
    tc.app.state.geo = FakeGeo()
    hub = tc.app.state.collector_feed.live
    lines = [CADDY % JAKARTA, CADDY % JAKARTA, CADDY % SYDNEY, CADDY % '203.0.113.77', 'not an access line', '{"msg":"certificate obtained"}']
    assert post(tc, key, otlp(lines, svc='caddy')).status_code == 200
    assert totals(hub) == {(-6.2, 106.8, 'caddy'): 2, (-33.87, 151.21, 'caddy'): 1}   # unknown address and unread lines: nothing
    assert hub.names[-6.2, 106.8] == ('Jakarta', 'ID')
    # a service whose rule is an app rule, or a plain one, draws nothing
    assert post(tc, key, otlp([CADDY % JAKARTA], svc='worker')).status_code == 200
    assert post(tc, key, otlp([CADDY % JAKARTA], svc='other')).status_code == 200
    assert totals(hub) == {(-6.2, 106.8, 'caddy'): 2, (-33.87, 151.21, 'caddy'): 1}


def test_module_is_the_upstream_when_the_line_has_one(rules):
    rule = log_formats.rules_from({'service': [{'match': 'web', 'format': 'nginx-combined', 'kind': 'http'}]})[0]
    got = live_map_reader(rule)('203.0.113.5 - - [04/Nov/2026:16:55:36 +0700] "GET /a HTTP/1.1" 200 5 "-" "curl"')
    assert got == ('203.0.113.5', None)
    ingress = live_map_reader(log_formats.Rule('*', 'ingress-nginx', 'http'), 'ns-')
    line = '66.66.66.9 - - [04/Nov/2026:16:55:36 +0700] "GET / HTTP/1.1" 200 5 "-" "curl" 80 0.012 [ns-orders-80] [] 10.0.0.1:80 5 0.012 200 x'
    assert ingress(line) == ('66.66.66.9', 'orders-80')
    assert live_map_reader(log_formats.Rule('x', 'json', 'app')) is None


def live_map_reader(rule, prefix=''):
    from monishield.domain import live_map as dom
    return dom.line_reader(rule, prefix)


def test_at_most_2000_lines_of_a_request_go_to_the_map(make, rules):
    tc, key, root = make(); rules()
    tc.app.state.geo = FakeGeo()
    hub = tc.app.state.collector_feed.live
    assert post(tc, key, otlp([CADDY % JAKARTA] * 2500, svc='caddy')).status_code == 200
    assert sum(totals(hub).values()) == live_map.MAX_PER_REQUEST == 2000
    assert len(open(next(p for p in __import__('glob').glob(root + '/**/*.log', recursive=True))).read().splitlines()) == 2500   # all lines are stored


def test_a_map_error_never_fails_a_receive(make, rules):
    tc, key, root = make(); rules()
    class Broken:
        def locate(self, ip): raise RuntimeError('lookup broke')
    tc.app.state.geo = Broken()
    r = post(tc, key, otlp([CADDY % JAKARTA], svc='caddy'))
    assert (r.status_code, r.json()) == (200, {})
    assert tc.app.state.collector_feed.status()['collectors']   # counted as usual


def test_unknown_visitors_are_found_by_the_offline_lookup_once_per_address(make, rules):
    tc, key, root = make(); rules()
    geo = tc.app.state.geo = FakeGeo()
    post(tc, key, otlp([CADDY % JAKARTA] * 3, svc='caddy'))
    assert totals(tc.app.state.collector_feed.live) == {(-6.2, 106.8, 'caddy'): 3}
    assert geo.asked == [JAKARTA] * 3   # the hub asks the lookup; its own LRU cache (geo_lookup) answers repeats


def test_stream_has_coordinates_and_no_address(make, rules):
    tc, key, root = make(); rules()
    tc.app.state.geo = FakeGeo()
    feed = tc.app.state.collector_feed
    feed.stop()   # the app started it
    assert tc.get('/api/live/map?source=collector', headers=X).status_code == 204   # no collector feed running
    assert tc.get('/api/live/map?source=kafka', headers=X).status_code == 204
    assert tc.get('/api/live/map?source=s3', headers=X).status_code == 204
    feed.start()
    srv, port = serve(tc.app)
    got = []
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', cookies={c.name: c.value for c in tc.cookies.jar}, trust_env=False, timeout=15) as h, \
                h.stream('GET', '/api/live/map?source=collector', headers=X) as r:
            assert r.status_code == 200 and r.headers['content-type'].startswith('text/event-stream')
            for raw in r.iter_lines():
                if raw.startswith('data: ') and '"live"' in raw:
                    got.append(json.loads(raw[6:]))
                    post(tc, key, otlp([CADDY % JAKARTA] * 3, svc='caddy'))
                elif raw.startswith('data: '):
                    got.append(json.loads(raw[6:])); break
        # the Kafka hub is a different stream: nothing was written to it
        assert tc.app.state.kafka.live.since(0)[1] == []
    finally: srv.should_exit = True
    assert got[0] == dict(live=True, folder=feed.live_folder())
    assert got[1]['p'] == [[-6.2, 106.8, 3, 'caddy']]
    text = json.dumps(got)
    assert JAKARTA not in text and '172.71.1.1' not in text


# The offline lookup
@pytest.fixture
def geo(tmp_path):
    class C: cache_dir = str(tmp_path)
    write_geolite(str(tmp_path / 'geolite2-city-csv.zip'),
                  blocks=[('1.0.0.0/24', '2077456', '2077456', '-27.5', '153.0'), ('8.8.8.0/24', '', '6252001', '', ''),
                          ('44.44.44.0/24', '1642911', '1642911', '-6.2', '106.8')],
                  locations=[('2077456', 'AU', 'Queensland', 'Brisbane'), ('6252001', 'US', '', ''), ('1642911', 'ID', 'Jakarta', 'Jakarta')])
    g = geo_lookup.GeoLookup(C)
    g.load_now()
    return g


def test_geo_lookup_reads_the_downloaded_file(geo):
    assert geo.ready()
    assert geo.locate('44.44.44.5') == (-6.2, 106.8, 'Jakarta', 'ID')
    assert geo.locate('1.0.0.200') == (-27.5, 153.0, 'Brisbane', 'AU')
    assert geo.locate('8.8.8.8') is None            # a block without coordinates is not drawn
    assert geo.locate('45.45.45.45') is None         # in no block
    assert geo.locate('10.0.0.1') is None and geo.locate('192.168.1.1') is None   # private
    assert geo.locate('2001:db8::1') is None and geo.locate('not an address') is None


def test_geo_lookup_sorts_blocks_that_come_unsorted(tmp_path):
    class C: cache_dir = str(tmp_path)
    write_geolite(str(tmp_path / 'geolite2-city-csv.zip'), blocks=[('66.66.66.0/24', '1', '1', '-6.2', '106.8'), ('1.0.0.0/24', '2', '2', '1.29', '103.85')],
                  locations=[('1', 'ID', 'Jakarta', 'Jakarta'), ('2', 'SG', '', 'Singapore')])
    g = geo_lookup.GeoLookup(C); g.load_now()
    assert g.locate('66.66.66.5')[2] == 'Jakarta' and g.locate('1.0.0.9')[2] == 'Singapore'


def test_geo_lookup_cache_is_bounded(geo, monkeypatch):
    monkeypatch.setattr(geo_lookup, 'CACHE_SIZE', 5)
    for i in range(20): geo.locate(f'44.44.44.{i}')
    assert len(geo._cache) == 5


def test_geo_lookup_without_a_file_answers_none(tmp_path):
    class C: cache_dir = str(tmp_path)
    g = geo_lookup.GeoLookup(C)
    assert g.locate('44.44.44.5') is None and not g.ready()
    (tmp_path / 'geolite2-city-csv.zip').write_bytes(b'not a zip')
    g.load_now()
    assert g.locate('44.44.44.5') is None


def test_geo_lookup_loads_in_the_background(geo, tmp_path):
    class C: cache_dir = str(tmp_path)
    g = geo_lookup.GeoLookup(C)
    assert g.locate('44.44.44.5') is None or g.ready()   # the first call only starts the load
    for _ in range(100):
        if g.ready(): break
        time.sleep(0.05)
    g._cache.clear()
    assert g.locate('44.44.44.5') == (-6.2, 106.8, 'Jakarta', 'ID')
