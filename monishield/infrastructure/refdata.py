"""Offline reference data: IP owner, IP location, and map files (TRD §3.6, §5.7).

All matching happens on our own server against fully downloaded files; **no user IP address is
sent to anyone** (PRD §5.4). The only outbound traffic is download requests to five fixed addresses.

- Network owner (ASN, organization, country): ip2asn (public domain), via `rules.ip_owner()` as is.
- Location (city, province, country, coordinates): **MaxMind GeoLite2 City** CSV variant, needs a free account
  (`MAXMIND_ACCOUNT_ID` + `MAXMIND_LICENSE_KEY` in .env). Owner decision 2026-10-06, replacing DB-IP.
- Map files: land + country borders + Indonesian province borders (Natural Earth, public domain) and region
  labels (Natural Earth + GeoNames, CC BY 4.0) via `map_labels()`.

Without a key or without internet: everything is skipped with a note; the ingest still finishes and it is retried
on the next ingest. Never silently falls back to another source.
"""
import base64, csv, datetime, gzip, io, ipaddress, json, os, sys, time, urllib.error, urllib.request, zipfile

from monishield.domain import rules
from monishield.domain.errors import Fail

# Attribution that must appear on every map (GeoLite2 and CC BY 4.0 licenses).
ATTRIBUTION = ['This product includes GeoLite2 data created by MaxMind, available from https://www.maxmind.com',
               'IP ownership data from iptoasn.com', 'Region names: GeoNames (CC BY 4.0)', 'Base map: Natural Earth']
# Download source addresses and maximum file ages are set in the configuration (.env: S4_URL_*, S4_GEO_MAX_AGE_DAYS,
# S4_ASN_MAX_AGE_DAYS, S4_MAP_MAX_AGE_DAYS); defaults are the official addresses. The GeoLite2 license forbids using stale databases.


# ------------------------------------------------------------------ download + reading of reference data (from the old system, old:353-466)
def load_ip2asn(path, max_age_days=7, url=rules.IP2ASN_URL):  # differs from old: file path and address became parameters
    if not fetch([url], path, max_age_days): return None
    starts, rows = [], []
    with gzip.open(path, 'rt', errors='replace') as fh:
        for line in fh:
            a, b, asn, cc, org = line.rstrip('\n').split('\t')
            if asn == '0': continue  # unrouted block
            starts.append(int(ipaddress.IPv4Address(a))); rows.append((int(ipaddress.IPv4Address(b)), int(asn), cc, org))
    return starts, rows


def fetch(urls, path, max_age_days):
    """Download to .cache if missing / stale. Download failure -> use the old file if any."""
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_days * 86400: return True
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as r, open(path + '.tmp', 'wb') as fh:
                while chunk := r.read(1 << 20): fh.write(chunk)
            os.replace(path + '.tmp', path); return True
        except OSError as e:
            print(f'Download failed: {url} ({e})', file=sys.stderr)
    return os.path.exists(path)


def map_labels(countries_file, geonames_file, countries_url=rules.COUNTRIES_URL, geonames_url=rules.GEONAMES_URL):  # differs from old: path & address became parameters
    """c = [ID name, EN name, longitude, latitude, rank]; p / k = [name, longitude, latitude] of province / regency-city."""
    out = dict(c=[], p=[], k=[])
    if fetch([countries_url], countries_file, 3650):
        for f in json.load(open(countries_file))['features']:
            p = f['properties']
            out['c'].append([p['NAME_ID'], p['NAME'], round(p['LABEL_X'], 2), round(p['LABEL_Y'], 2), p['LABELRANK']])
    if fetch([geonames_url], geonames_file, 3650):
        with zipfile.ZipFile(geonames_file).open('ID.txt') as fh:
            for line in io.TextIOWrapper(fh, 'utf-8'):
                if '\tADM' not in line: continue
                r = line.split('\t')
                if r[7] == 'ADM1' and r[10] in rules.PROV: out['p'].append([rules.PROV[r[10]], float(r[5]), float(r[4])])
                elif r[7] == 'ADM2': out['k'].append([rules.kab_name(r[1]), float(r[5]), float(r[4])])
    return out


class _StripAuth(urllib.request.HTTPRedirectHandler):
    """The MaxMind download redirects to a signed URL that REJECTS the Authorization header (400)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None: new.headers = {k: v for k, v in new.headers.items() if k.lower() != 'authorization'}
        return new


def fetch_maxmind(cfg, edition, path, max_age_days=None, log=print):
    """Download one GeoLite2 edition (zip) if missing / stale. False = not available."""
    max_age_days = cfg.geo_max_age_days if max_age_days is None else max_age_days
    fresh = os.path.exists(path) and os.path.getmtime(path) > (datetime.datetime.now() - datetime.timedelta(days=max_age_days)).timestamp()
    if fresh: return True
    if not (cfg.maxmind_account_id and cfg.maxmind_license_key):
        log(f'{edition}: MaxMind key not set (Configuration page or MAXMIND_ACCOUNT_ID/MAXMIND_LICENSE_KEY in .env); IP location skipped')
        return os.path.exists(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    auth = base64.b64encode(f'{cfg.maxmind_account_id}:{cfg.maxmind_license_key}'.encode()).decode()
    req = urllib.request.Request(cfg.url_maxmind.format(edition), headers={'Authorization': 'Basic ' + auth, 'User-Agent': 'monishield/2.0'})
    try:
        with urllib.request.build_opener(_StripAuth).open(req, timeout=600) as r, open(path + '.tmp', 'wb') as fh:
            while chunk := r.read(1 << 20): fh.write(chunk)
        os.replace(path + '.tmp', path)  # the old file is replaced, not piled up
        return True
    except OSError as e:
        log(f'{edition}: download failed ({e}); using the old file if any')
        if os.path.exists(path + '.tmp'): os.remove(path + '.tmp')
    return os.path.exists(path)


def _zip_member(zf, suffix):
    for n in zf.namelist():
        if n.endswith(suffix): return n
    raise ValueError(f'{suffix} not found in the archive')


def geolite_locations(zip_path):
    """{geoname_id: [city, province, country code]} from Locations-en (English, like the old DB-IP)."""
    out = {}
    with zipfile.ZipFile(zip_path) as zf, zf.open(_zip_member(zf, 'Locations-en.csv')) as fh:
        rd = csv.reader(io.TextIOWrapper(fh, 'utf-8'))
        next(rd, None)
        for r in rd: out[r[0]] = [r[10], r[7], r[4]]  # city_name, subdivision_1_name, country_iso_code
    return out


def geolite_ranges(zip_path, locations):
    """CIDR blocks -> (start, end, [city, province, country, latitude, longitude]) in ascending order.

    Blocks without geoname_id use the registered country (empty city name); blocks without coordinates still
    yield a country, but are not drawn on the map.
    """
    with zipfile.ZipFile(zip_path) as zf, zf.open(_zip_member(zf, 'Blocks-IPv4.csv')) as fh:
        rd = csv.reader(io.TextIOWrapper(fh, 'utf-8'))
        next(rd, None)
        for r in rd:
            net, _, bits = r[0].partition('/')
            start = rules.ip_int(net)
            loc = locations.get(r[1]) or locations.get(r[2])
            if not loc: continue
            lat, lon = r[7], r[8]
            yield start, start + (1 << (32 - int(bits))) - 1, [loc[0], loc[1], loc[2], float(lat) if lat else None, float(lon) if lon else None]


def sweep(need, ranges):
    """need = [(int ip, ip)] sorted; ranges = (start, end, location) sorted -> {ip: location | None}.

    The same sweep as the old rules.geo_scan() (tested in test_refdata), only the ranges are already ints.
    """
    found, i = {}, 0
    for start, end, loc in ranges:
        if i == len(need): break
        while i < len(need) and need[i][0] <= end:
            found[need[i][1]] = loc if need[i][0] >= start else None
            i += 1
    for _, ip in need[i:]: found[ip] = None
    return found


def _db_date(path):
    return datetime.date.fromtimestamp(os.path.getmtime(path)) if os.path.exists(path) else None


IP_SOURCES = """SELECT ip FROM nginx_access WHERE ip IS NOT NULL
                UNION SELECT ip FROM fe_access WHERE ip IS NOT NULL
                UNION SELECT ip FROM sl_event WHERE ip IS NOT NULL
                UNION SELECT login_ip FROM spring_line WHERE login_ip IS NOT NULL"""


def fill_ip_info(cfg, con, offline=False, log=print):
    """Fill ip_info for IPs that have no data yet. Returns a summary.

    Existing IPs are not recomputed even when the database is updated (ASSUMPTION T3); the database date
    columns are recorded so a bulk update can be added later.
    """
    res = dict(new_ips=0, owners=0, locations=0, skipped=[])
    baru = [r[0] for r in con.execute(f'SELECT ip FROM ({IP_SOURCES}) EXCEPT SELECT ip FROM ip_info', ).fetchall()]
    if cfg.server_ip and not con.execute('SELECT count(*) FROM ip_info WHERE ip = ?', [cfg.server_ip]).fetchone()[0]:
        baru.append(cfg.server_ip)  # map destination point
    res['new_ips'] = len(baru)
    if not baru: return res

    rows = {ip: dict(asn=None, cc=None, org=None, is_private=None, city=None, region=None, country=None, lat=None, lon=None,
                     geo_checked=False, asn_db_date=None, geo_db_date=None) for ip in baru}

    asn_path = os.path.join(cfg.cache_dir, 'ip2asn-v4.tsv.gz')
    if offline and not os.path.exists(asn_path):
        res['skipped'].append('IP owner: ip2asn not downloaded and offline mode')
    else:
        db = load_ip2asn(asn_path, max_age_days=10**6 if offline else cfg.asn_max_age_days, url=cfg.url_ip2asn)
        if db is None:
            res['skipped'].append('IP owner: ip2asn not available')
        else:
            date = _db_date(asn_path)
            for ip in baru:
                o = rules.ip_owner(ip, db)
                if o:
                    rows[ip].update(asn=o['asn'], cc=o['cc'], org=o['org'], is_private=o['cc'] == '-', asn_db_date=date)
                    res['owners'] += 1

    need = []
    for ip in baru:
        try: a = ipaddress.ip_address(ip)
        except ValueError: continue
        if a.version == 4 and a.is_global: need.append((int(a), ip))
    geo_path = os.path.join(cfg.cache_dir, 'geolite2-city-csv.zip')
    if not need:
        pass
    elif offline and not os.path.exists(geo_path):
        res['skipped'].append('IP location: GeoLite2 not downloaded and offline mode')
    elif not (offline or fetch_maxmind(cfg, 'GeoLite2-City-CSV', geo_path, log=log)):
        res['skipped'].append('IP location: GeoLite2 not available (MaxMind key empty or download failed)')
    else:
        date = _db_date(geo_path)
        locs = geolite_locations(geo_path)
        for ip, loc in sweep(sorted(need), geolite_ranges(geo_path, locs)).items():
            rows[ip]['geo_checked'] = True
            rows[ip]['geo_db_date'] = date
            if loc:
                rows[ip].update(city=loc[0] or None, region=loc[1] or None, country=loc[2] or None, lat=loc[3], lon=loc[4])
                res['locations'] += 1

    cols = ['asn', 'cc', 'org', 'is_private', 'city', 'region', 'country', 'lat', 'lon', 'geo_checked', 'asn_db_date', 'geo_db_date']
    con.executemany(f"INSERT INTO ip_info VALUES ({', '.join('?' * (len(cols) + 1))})", [[ip, *(rows[ip][c] for c in cols)] for ip in baru])
    return res


def _have(urls, path, age, offline, nama, log):
    """True when the source file is ready to use. Never downloads in offline mode."""
    if offline:
        if os.path.exists(path): return True
        log(f'{nama}: not downloaded and offline mode; skipped')
        return False
    if fetch(urls, path, age): return True
    log(f'{nama}: not available')
    return False


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.tmp', 'w', encoding='utf-8') as fh: json.dump(obj, fh, ensure_ascii=False, separators=(',', ':'))
    os.replace(path + '.tmp', path)


def _round_geom(g, nd=2):
    """Round coordinates to 2 decimals (≈ 1 km, same as the old map) to keep the files small."""
    if isinstance(g, (int, float)): return round(g, nd)
    return [_round_geom(x, nd) for x in g]


def build_map_files(cfg, offline=False, log=print):
    """Build the static map files in <data_dir>/map. Returns a summary per file."""
    out_dir = os.path.join(cfg.data_dir, 'map')
    os.makedirs(out_dir, exist_ok=True)
    res, cache = {}, cfg.cache_dir
    age = 10**6 if offline else cfg.map_max_age_days

    land_src = os.path.join(cache, 'ne_50m_land.geojson')
    if _have([cfg.url_land], land_src, age, offline, 'land', log):
        g = json.load(open(land_src, encoding='utf-8'))
        g['features'] = [dict(type='Feature', properties={}, geometry=_round_geom_feature(f['geometry'])) for f in g['features']]
        _write_json(os.path.join(out_dir, 'land.geojson'), g)
        res['land.geojson'] = len(g['features'])

    b_src = os.path.join(cache, 'ne_50m_boundary_lines.geojson')
    if _have([cfg.url_borders], b_src, age, offline, 'country borders', log):
        g = json.load(open(b_src, encoding='utf-8'))
        g['features'] = [dict(type='Feature', properties={}, geometry=_round_geom_feature(f['geometry'])) for f in g['features']]
        _write_json(os.path.join(out_dir, 'borders-country.geojson'), g)
        res['borders-country.geojson'] = len(g['features'])

    p_src = os.path.join(cache, 'ne_10m_admin_1_states_provinces.geojson')
    if _have([cfg.url_provinces], p_src, age, offline, 'province borders', log):
        g = json.load(open(p_src, encoding='utf-8'))
        feats = [f for f in g['features'] if (f['properties'].get('adm0_a3') or f['properties'].get('iso_a2')) in ('IDN', 'ID')]
        _write_json(os.path.join(out_dir, 'borders-province-id.geojson'),
                    dict(type='FeatureCollection', features=[dict(type='Feature', properties={'name': f['properties'].get('name')},
                                                                  geometry=_round_geom_feature(f['geometry'])) for f in feats]))
        res['borders-province-id.geojson'] = len(feats)

    countries = os.path.join(cache, 'ne_110m_countries.geojson')
    geonames = os.path.join(cache, 'geonames-ID.zip')
    if _have([cfg.url_countries], countries, age, offline, 'country labels', log) & _have([cfg.url_geonames], geonames, age, offline, 'Indonesian region labels', log):
        labels = map_labels(countries, geonames, cfg.url_countries, cfg.url_geonames)   # used as is from the old system
        if any(labels.values()):
            _write_json(os.path.join(out_dir, 'labels.json'), labels)
            res['labels.json'] = {k: len(v) for k, v in labels.items()}
    return res


def _round_geom_feature(geom): return dict(type=geom['type'], coordinates=_round_geom(geom['coordinates']))


def run(cfg, con, offline=False, force_map=False, log=print):
    """Called at the end of an ingest (force_map=False: existing map files are not rebuilt)."""
    ip = fill_ip_info(cfg, con, offline=offline, log=log)
    peta = {}
    if force_map or not map_ready(cfg):
        try: peta = build_map_files(cfg, offline=offline, log=log)
        except Exception as e:  # noqa: BLE001  failed map files must not discard the ip_info result
            log(f'map files could not be built: {type(e).__name__}: {e}')
    return dict(ip=ip, peta=peta)


MAP_FILES = ('land.geojson', 'borders-country.geojson', 'borders-province-id.geojson', 'labels.json')


def map_ready(cfg):
    return all(os.path.exists(os.path.join(cfg.data_dir, 'map', f)) for f in MAP_FILES)


# ------------------------------------------------------------------ MaxMind key test (Configuration page)
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None   # 302 = key accepted; the download link is not followed


def probe_maxmind(cfg):
    """HEAD the GeoLite2 download link with the stored key: authorization only, no download. Failure -> Fail (502)."""
    auth = base64.b64encode(f'{cfg.maxmind_account_id}:{cfg.maxmind_license_key}'.encode()).decode()
    req = urllib.request.Request(cfg.url_maxmind.format('GeoLite2-City-CSV'), method='HEAD',
                                 headers={'Authorization': 'Basic ' + auth, 'User-Agent': 'monishield/2.0'})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=20) as r: code = r.status
    except urllib.error.HTTPError as e: code = e.code
    except OSError as e: raise Fail('maxmind_unreachable', f'MaxMind is unreachable from the server ({type(e).__name__}).', 502) from None
    if code in (401, 403): raise Fail('maxmind_denied', f'MaxMind rejected the key ({code}): check the Account ID and License key.', 502)
    if code not in (200, 302, 303, 307): raise Fail('maxmind_error', f'MaxMind answered {code}.', 502)
