"""IP owner & location and map files (TRD §3.6, §5.7).

No test touches the network: every test installs a guard that fails any download.
Source files are built small inside the tests (fake GeoLite2 zip, fake ip2asn gz, fake GeoJSON).
"""
import csv, dataclasses, gzip, io, ipaddress, json, os, urllib.request, zipfile

import pytest

import logs_mini
from monishield.infrastructure import config, db, ingest, refdata
from monishield.domain import rules

IP = lambda s: int(ipaddress.IPv4Address(s))


@pytest.fixture(autouse=True)
def tanpa_jaringan(monkeypatch):
    """Any download in a test = a test failure, not a request to the internet."""
    def tolak(*a, **k): raise AssertionError('uji tidak boleh mengakses jaringan')
    monkeypatch.setattr(urllib.request, 'urlopen', tolak)
    monkeypatch.setattr(urllib.request, 'build_opener', tolak)


def tulis_geolite(path, blocks, locations):
    """blocks = [(cidr, geoname_id, registered_id, lat, lon)]; locations = [(id, cc, province, city)]."""
    with zipfile.ZipFile(path, 'w') as z:
        b = io.StringIO(); w = csv.writer(b)
        w.writerow(['network', 'geoname_id', 'registered_country_geoname_id', 'represented_country_geoname_id',
                    'is_anonymous_proxy', 'is_satellite_provider', 'postal_code', 'latitude', 'longitude', 'accuracy_radius', 'is_anycast'])
        for cidr, gid, rid, lat, lon in blocks: w.writerow([cidr, gid, rid, '', '0', '0', '', lat, lon, '100', ''])
        z.writestr('GeoLite2-City-CSV_20261002/GeoLite2-City-Blocks-IPv4.csv', b.getvalue())
        z.writestr('GeoLite2-City-CSV_20261002/GeoLite2-City-Blocks-IPv6.csv', 'network,geoname_id\n::/0,1\n')  # must be ignored
        loc = io.StringIO(); w = csv.writer(loc)
        w.writerow(['geoname_id', 'locale_code', 'continent_code', 'continent_name', 'country_iso_code', 'country_name',
                    'subdivision_1_iso_code', 'subdivision_1_name', 'subdivision_2_iso_code', 'subdivision_2_name', 'city_name', 'metro_code', 'time_zone', 'is_in_european_union'])
        for gid, cc, prov, kota in locations: w.writerow([gid, 'en', 'AS', 'Asia', cc, 'Negara', '31', prov, '', '', kota, '', 'Asia/Jakarta', '0'])
        z.writestr('GeoLite2-City-CSV_20261002/GeoLite2-City-Locations-en.csv', loc.getvalue())
        z.writestr('GeoLite2-City-CSV_20261002/GeoLite2-City-Locations-ja.csv', 'geoname_id\n1\n')  # other languages are not used
    return path


def tulis_ip2asn(path, rows):
    with gzip.open(path, 'wt') as fh:
        for a, b, asn, cc, org in rows: fh.write(f'{a}\t{b}\t{asn}\t{cc}\t{org}\n')
    return path


@pytest.fixture
def cfg(tmp_path):
    return dataclasses.replace(config.Config(), log_dir=str(tmp_path / 'logs'), data_dir=str(tmp_path / 'data'),
                               state_dir=str(tmp_path / 'data'), inbox_dir=str(tmp_path / 'inbox'), cache_dir=str(tmp_path / 'cache'),
                               maxmind_account_id='123', maxmind_license_key='kunci', offline=True)


@pytest.fixture
def siap(cfg):
    """Cache holds fake ip2asn and GeoLite2; empty database."""
    os.makedirs(cfg.cache_dir)
    tulis_ip2asn(os.path.join(cfg.cache_dir, 'ip2asn-v4.tsv.gz'), [
        ('1.0.0.0', '1.0.0.255', '13335', 'AU', 'CLOUDFLARENET'),
        ('103.170.104.0', '103.170.104.255', '132634', 'ID', 'IDNIC-EGOV-AS-ID'),
        ('45.33.0.0', '45.33.0.255', '0', 'ID', 'blok tidak ter-routing'),  # ASN 0: skipped, like the old system
    ])
    tulis_geolite(os.path.join(cfg.cache_dir, 'geolite2-city-csv.zip'),
                  blocks=[('1.0.0.0/24', '2077456', '2077456', '-27.5', '153.0'),
                          ('8.8.8.0/24', '', '6252001', '', ''),              # no city and no coordinates
                          ('103.170.104.0/24', '1642911', '1642911', '-6.2', '106.8')],
                  locations=[('2077456', 'AU', 'Queensland', 'Brisbane'), ('6252001', 'US', '', ''), ('1642911', 'ID', 'Jakarta', 'Jakarta')])
    return cfg


def con_for(cfg): return db.open(cfg.db_path)


def taruh_ip(con, **kolom):
    """Insert one nginx_access row with a given IP."""
    for i, ip in enumerate(kolom['ips'], 1):
        con.execute("""INSERT INTO nginx_access (file_id, line_no, folder, ts_utc, ip, method, path, path_key, status, bytes, ua, request_time,
                                                upstream, request_id, pod_final, up_addrs, up_statuses, attack_cat, is_uptime_kuma)
                       VALUES (1, ?, DATE '2026-01-02', TIMESTAMP '2026-01-02 00:00:00', ?, 'GET', '/', '/', 200, 1,
                       'UA', 0.1, '-', NULL, '-', NULL, NULL, NULL, false)""", [i, ip])


# ------------------------------------------------------------------ sweep
def test_sweep_sama_dengan_geo_scan_lama(old):
    """sweep() over int ranges must give results identical to rules.geo_scan() over DB-IP rows."""
    baris = [('1.0.0.0', '1.0.0.255', 'OC', 'AU', 'Queensland', 'Brisbane', '-27.5', '153.0'),
             ('1.0.2.0', '1.0.2.255', 'AS', 'ID', 'Jakarta', 'Jakarta', '-6.2', '106.8'),
             ('9.0.0.0', '9.0.0.255', 'NA', 'US', 'Texas', 'Austin', '30.3', '-97.7')]
    ips = ['0.0.0.1', '1.0.0.0', '1.0.0.7', '1.0.0.255', '1.0.1.9', '1.0.2.255', '9.0.0.1', '255.255.255.255']
    need = sorted((rules.ip_int(i), i) for i in ips)
    lama = old.geo_scan(need, [list(r) for r in baris])
    baru = refdata.sweep(need, [(IP(r[0]), IP(r[1]), [r[5], r[4], r[3], float(r[6]), float(r[7])]) for r in baris])
    assert baru == lama == rules.geo_scan(need, [list(r) for r in baris])
    assert baru['1.0.0.7'] == ['Brisbane', 'Queensland', 'AU', -27.5, 153.0] and baru['1.0.1.9'] is None and baru['255.255.255.255'] is None


def test_sweep_kosong():
    assert refdata.sweep([], [(1, 2, ['x', 'y', 'ID', 0.0, 0.0])]) == {}
    assert refdata.sweep([(IP('1.2.3.4'), '1.2.3.4')], []) == {'1.2.3.4': None}


# ------------------------------------------------------------------ GeoLite2 reading
def test_baca_geolite(siap):
    p = os.path.join(siap.cache_dir, 'geolite2-city-csv.zip')
    locs = refdata.geolite_locations(p)
    assert locs['2077456'] == ['Brisbane', 'Queensland', 'AU'] and locs['6252001'] == ['', '', 'US']
    r = list(refdata.geolite_ranges(p, locs))
    assert r[0] == (IP('1.0.0.0'), IP('1.0.0.255'), ['Brisbane', 'Queensland', 'AU', -27.5, 153.0])
    assert r[1] == (IP('8.8.8.0'), IP('8.8.8.255'), ['', '', 'US', None, None])   # registered country, no coordinates
    assert len(r) == 3 and r[2][2][0] == 'Jakarta'


# ------------------------------------------------------------------ filling ip_info
def test_isi_ip_info(siap):
    con = con_for(siap)
    taruh_ip(con, ips=['1.0.0.7', '8.8.8.8', '10.0.0.1', '45.33.0.9', '2a06:98c0::1', '${jndi:ldap://x}', '55.66.77.88'])
    r = refdata.fill_ip_info(siap, con)
    assert r['new_ips'] == 8 and r['skipped'] == []        # 7 IPs + server IP
    got = {x[0]: x[1:] for x in con.execute('SELECT ip, asn, cc, org, is_private, city, region, country, lat, lon, geo_checked FROM ip_info').fetchall()}
    assert got['1.0.0.7'] == (13335, 'AU', 'CLOUDFLARENET', False, 'Brisbane', 'Queensland', 'AU', -27.5, 153.0, True)
    assert got['10.0.0.1'] == (None, '-', 'Jaringan Internal (IP Privat)', True, None, None, None, None, None, False)  # private: location not looked up
    assert got['8.8.8.8'][4:] == (None, None, 'US', None, None, True)                 # country only, no coordinates
    assert got['45.33.0.9'][:3] == (None, None, None) and got['45.33.0.9'][9] is True  # ASN 0 skipped; location looked up, not found
    assert got['2a06:98c0::1'][:4] == (None, None, None, None) and got['2a06:98c0::1'][9] is False  # IPv6: out of range
    assert got['${jndi:ldap://x}'][:4] == (None, None, None, None)                    # fake 'IP' from an attack payload: does not cause a failure
    assert got[siap.server_ip][:4] == (132634, 'ID', 'IDNIC-EGOV-AS-ID', False) and got[siap.server_ip][6] == 'ID'
    assert r['owners'] == 3 and r['locations'] == 3


def test_ip_lama_tidak_dihitung_ulang(siap):
    con = con_for(siap)
    taruh_ip(con, ips=['1.0.0.7'])
    refdata.fill_ip_info(siap, con)
    con.execute("UPDATE ip_info SET city = 'DIUBAH TANGAN'")
    taruh_ip(con, ips=['103.170.104.5'])
    r = refdata.fill_ip_info(siap, con)
    assert r['new_ips'] == 1                                            # new IPs only
    assert con.execute("SELECT city FROM ip_info WHERE ip = '1.0.0.7'").fetchone()[0] == 'DIUBAH TANGAN'  # T3
    assert con.execute("SELECT city FROM ip_info WHERE ip = '103.170.104.5'").fetchone()[0] == 'Jakarta'
    assert refdata.fill_ip_info(siap, con)['new_ips'] == 0


def test_tanpa_kunci_maxmind_lokasi_dilewati(cfg):
    os.makedirs(cfg.cache_dir)
    tulis_ip2asn(os.path.join(cfg.cache_dir, 'ip2asn-v4.tsv.gz'), [('1.0.0.0', '1.0.0.255', '13335', 'AU', 'CLOUDFLARENET')])
    tanpa = dataclasses.replace(cfg, maxmind_account_id='', maxmind_license_key='')
    con = con_for(tanpa)
    taruh_ip(con, ips=['1.0.0.7'])
    pesan = []
    r = refdata.fill_ip_info(tanpa, con, log=pesan.append)
    assert r['owners'] == 1 and r['locations'] == 0 and any('MAXMIND' in m for m in pesan)
    assert any('IP location' in m for m in r['skipped'])
    row = con.execute('SELECT org, city, geo_checked FROM ip_info WHERE ip = ?', ['1.0.0.7']).fetchone()
    assert row == ('CLOUDFLARENET', None, False)   # geo_checked False: retried on the next ingest


def test_luring_tanpa_cache_tidak_mengunduh(cfg):
    con = con_for(cfg)
    taruh_ip(con, ips=['1.0.0.7'])
    r = refdata.fill_ip_info(cfg, con, offline=True)          # tanpa_jaringan fails the test if anything is downloaded
    assert r['owners'] == 0 and r['locations'] == 0 and len(r['skipped']) == 2
    assert con.execute('SELECT count(*) FROM ip_info').fetchone()[0] == 2  # the rows are still created, waiting for data


def test_ingest_tetap_selesai_tanpa_data_acuan(tmp_path, cfg):
    """Real ingest (logs_mini) in offline mode without cache: finishes, has a warning, log data still goes in."""
    cfg = dataclasses.replace(cfg, log_dir=logs_mini.build(tmp_path / 'logs'), offline=True)
    con = con_for(cfg)
    r = ingest.run(cfg, con, workers=0)
    assert r['status'] == 'ok' and r['files_parsed'] == 9
    assert any('IP location' in w for w in r['warnings']) and r['refdata']['ip']['new_ips'] > 5
    assert con.execute('SELECT count(*) FROM nginx_access').fetchone()[0] == 7


def test_ingest_mengisi_ip_info(tmp_path, siap):
    cfg = dataclasses.replace(siap, log_dir=logs_mini.build(tmp_path / 'logs'))
    con = con_for(cfg)
    r = ingest.run(cfg, con, workers=0)
    assert r['refdata']['ip']['new_ips'] > 5 and r['refdata']['ip']['owners'] >= 1
    assert con.execute("SELECT org FROM ip_info WHERE ip = ?", [cfg.server_ip]).fetchone()[0] == 'IDNIC-EGOV-AS-ID'
    assert ingest.run(cfg, con, workers=0)['refdata']['ip']['new_ips'] == 0   # second ingest: no new IPs


# ------------------------------------------------------------------ map files
def tulis_geojson(path, features):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(dict(type='FeatureCollection', features=features), open(path, 'w'))


def fitur(tipe, koordinat, **props): return dict(type='Feature', properties=props, geometry=dict(type=tipe, coordinates=koordinat))


def test_berkas_peta(cfg, tmp_path):
    c = cfg.cache_dir
    tulis_geojson(os.path.join(c, 'ne_50m_land.geojson'), [fitur('Polygon', [[[106.123456, -6.987654], [107.0, -6.0], [106.0, -7.0]]])])
    tulis_geojson(os.path.join(c, 'ne_50m_boundary_lines.geojson'), [fitur('LineString', [[95.111111, 5.222222], [96.0, 6.0]])])
    tulis_geojson(os.path.join(c, 'ne_10m_admin_1_states_provinces.geojson'), [
        fitur('Polygon', [[[106.5, -6.2], [107.0, -6.0]]], adm0_a3='IDN', name='Jawa Barat'),
        fitur('Polygon', [[[101.0, 3.1], [102.0, 3.2]]], adm0_a3='MYS', name='Selangor')])
    res = refdata.build_map_files(cfg, offline=True)
    assert res['land.geojson'] == 1 and res['borders-country.geojson'] == 1 and res['borders-province-id.geojson'] == 1
    land = json.load(open(os.path.join(cfg.data_dir, 'map', 'land.geojson')))
    assert land['features'][0]['geometry']['coordinates'] == [[[106.12, -6.99], [107.0, -6.0], [106.0, -7.0]]]  # 2 decimals ≈ 1 km
    prov = json.load(open(os.path.join(cfg.data_dir, 'map', 'borders-province-id.geojson')))
    assert [f['properties']['name'] for f in prov['features']] == ['Jawa Barat']     # Indonesia only
    assert 'labels.json' not in res and refdata.map_ready(cfg) is False              # labels need their source


def test_label_wilayah(cfg):
    """labels.json uses rules.map_labels() as is (its equality test is in test_rules)."""
    c = cfg.cache_dir; os.makedirs(c, exist_ok=True)
    tulis_geojson(os.path.join(c, 'ne_110m_countries.geojson'), [
        dict(type='Feature', properties=dict(NAME_ID='Indonesia', NAME='Indonesia', LABEL_X=117.123, LABEL_Y=-2.456, LABELRANK=2), geometry=None)])
    with zipfile.ZipFile(os.path.join(c, 'geonames-ID.zip'), 'w') as z:
        # GeoNames columns: id, name, ascii, aliases, latitude, longitude, class, feature code, country, cc2, admin1
        z.writestr('ID.txt', '\t'.join(['1', 'Jawa Barat', 'x', '', '-6.9', '107.6', 'P', 'ADM1', 'ID', '', '30'] + [''] * 8) + '\n' +
                             '\t'.join(['2', 'Gresik Regency', 'x', '', '-7.1', '112.6', 'P', 'ADM2', 'ID', '', '08'] + [''] * 8) + '\n')
    res = refdata.build_map_files(cfg, offline=True)
    assert res['labels.json'] == dict(c=1, p=1, k=1)
    labels = json.load(open(os.path.join(cfg.data_dir, 'map', 'labels.json')))
    assert labels['c'] == [['Indonesia', 'Indonesia', 117.12, -2.46, 2]] and labels['p'] == [['Jawa Barat', 107.6, -6.9]]
    assert labels['k'] == [['Kab. Gresik', 112.6, -7.1]]


def test_atribusi_menyebut_sumber():
    teks = ' '.join(refdata.ATTRIBUTION)
    assert 'MaxMind' in teks and 'GeoLite2' in teks and 'GeoNames' in teks and 'Natural Earth' in teks


def test_kredensial_tidak_bocor(siap):
    con = con_for(siap)
    taruh_ip(con, ips=['1.0.0.7'])
    pesan = []
    refdata.fill_ip_info(siap, con, log=pesan.append)
    isi = ' '.join(pesan) + json.dumps(siap.public()) + str(con.execute('SELECT * FROM ip_info').fetchall())
    assert siap.maxmind_license_key not in isi and siap.maxmind_account_id not in isi
