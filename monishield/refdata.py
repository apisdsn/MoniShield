"""Data acuan offline: pemilik IP, lokasi IP, dan berkas peta (TRD §3.6, §5.7).

Semua pencocokan dilakukan di server sendiri atas berkas yang diunduh utuh; **tidak ada alamat IP pengguna
yang dikirim ke pihak mana pun** (PRD §5.4). Yang keluar hanya permintaan unduh ke lima alamat tetap.

- Pemilik jaringan (ASN, organisasi, negara): ip2asn (public domain), lewat `rules.ip_owner()` apa adanya.
- Lokasi (kota, provinsi, negara, koordinat): **MaxMind GeoLite2 City** varian CSV, butuh akun gratis
  (`MAXMIND_ACCOUNT_ID` + `MAXMIND_LICENSE_KEY` di .env). Keputusan pemilik 2026-10-06, menggantikan DB-IP.
- Berkas peta: daratan + batas negara + batas provinsi Indonesia (Natural Earth, public domain) dan label
  wilayah (Natural Earth + GeoNames, CC BY 4.0) lewat `rules.map_labels()`.

Tanpa kunci atau tanpa internet: semuanya dilewati dengan keterangan; ingest tetap selesai dan dicoba lagi
pada ingest berikutnya. Tidak pernah diam-diam jatuh ke sumber lain.
"""
import base64, csv, datetime, io, ipaddress, json, os, urllib.request, zipfile

from . import rules

# Atribusi yang wajib tampil di setiap peta (lisensi GeoLite2 dan CC BY 4.0).
ATTRIBUTION = ['Produk ini memuat data GeoLite2 buatan MaxMind, tersedia dari https://www.maxmind.com',
               'IP ownership data from iptoasn.com', 'Nama wilayah: GeoNames (CC BY 4.0)', 'Peta dasar: Natural Earth']
MAXMIND_URL = 'https://download.maxmind.com/geoip/databases/{}/download?suffix=zip'
BORDERS_URL = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_boundary_lines_land.geojson'
PROVINCES_URL = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson'
GEO_MAX_AGE_DAYS = 7   # lisensi GeoLite2 melarang memakai basis data usang; berkas lama dihapus saat yang baru masuk
ASN_MAX_AGE_DAYS = 7   # sama dengan sistem lama
MAP_MAX_AGE_DAYS = 3650


class _StripAuth(urllib.request.HTTPRedirectHandler):
    """Unduhan MaxMind mengalihkan ke URL bertanda tangan yang MENOLAK header Authorization (400)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None: new.headers = {k: v for k, v in new.headers.items() if k.lower() != 'authorization'}
        return new


def fetch_maxmind(cfg, edition, path, max_age_days=GEO_MAX_AGE_DAYS, log=print):
    """Unduh satu edisi GeoLite2 (zip) bila belum ada / sudah lama. False = tidak tersedia."""
    fresh = os.path.exists(path) and os.path.getmtime(path) > (datetime.datetime.now() - datetime.timedelta(days=max_age_days)).timestamp()
    if fresh: return True
    if not (cfg.maxmind_account_id and cfg.maxmind_license_key):
        log(f'{edition}: kunci MaxMind belum diisi (layar Konfigurasi atau MAXMIND_ACCOUNT_ID/MAXMIND_LICENSE_KEY di .env); lokasi IP dilewati')
        return os.path.exists(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    auth = base64.b64encode(f'{cfg.maxmind_account_id}:{cfg.maxmind_license_key}'.encode()).decode()
    req = urllib.request.Request(MAXMIND_URL.format(edition), headers={'Authorization': 'Basic ' + auth, 'User-Agent': 'monishield/2.0'})
    try:
        with urllib.request.build_opener(_StripAuth).open(req, timeout=600) as r, open(path + '.tmp', 'wb') as fh:
            while chunk := r.read(1 << 20): fh.write(chunk)
        os.replace(path + '.tmp', path)  # berkas lama diganti, bukan ditumpuk
        return True
    except OSError as e:
        log(f'{edition}: gagal diunduh ({e}); memakai berkas lama bila ada')
        if os.path.exists(path + '.tmp'): os.remove(path + '.tmp')
    return os.path.exists(path)


def _zip_member(zf, suffix):
    for n in zf.namelist():
        if n.endswith(suffix): return n
    raise ValueError(f'{suffix} tidak ada di dalam arsip')


def geolite_locations(zip_path):
    """{geoname_id: [kota, provinsi, kode negara]} dari Locations-en (bahasa Inggris, seperti DB-IP lama)."""
    out = {}
    with zipfile.ZipFile(zip_path) as zf, zf.open(_zip_member(zf, 'Locations-en.csv')) as fh:
        rd = csv.reader(io.TextIOWrapper(fh, 'utf-8'))
        next(rd, None)
        for r in rd: out[r[0]] = [r[10], r[7], r[4]]  # city_name, subdivision_1_name, country_iso_code
    return out


def geolite_ranges(zip_path, locations):
    """Blok CIDR -> (awal, akhir, [kota, provinsi, negara, lintang, bujur]) terurut naik.

    Blok tanpa geoname_id memakai negara terdaftar (nama kota kosong); blok tanpa koordinat tetap
    menghasilkan negara, tetapi tidak digambar di peta.
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
    """need = [(int ip, ip)] terurut; ranges = (awal, akhir, lokasi) terurut -> {ip: lokasi | None}.

    Sapuan yang sama dengan rules.geo_scan() lama (diuji di test_refdata), hanya rentangnya sudah berupa int.
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
    """Lengkapi ip_info untuk IP yang belum punya data. Mengembalikan ringkasan.

    IP yang sudah ada tidak dihitung ulang walau basis data diperbarui (ASUMSI T3); kolom tanggal basis
    data dicatat supaya pembaruan massal bisa ditambahkan kelak.
    """
    res = dict(ip_baru=0, pemilik=0, lokasi=0, lewat=[])
    baru = [r[0] for r in con.execute(f'SELECT ip FROM ({IP_SOURCES}) EXCEPT SELECT ip FROM ip_info', ).fetchall()]
    if cfg.server_ip and not con.execute('SELECT count(*) FROM ip_info WHERE ip = ?', [cfg.server_ip]).fetchone()[0]:
        baru.append(cfg.server_ip)  # titik tujuan peta
    res['ip_baru'] = len(baru)
    if not baru: return res

    rows = {ip: dict(asn=None, cc=None, org=None, is_private=None, city=None, region=None, country=None, lat=None, lon=None,
                     geo_checked=False, asn_db_date=None, geo_db_date=None) for ip in baru}

    asn_path = os.path.join(cfg.cache_dir, 'ip2asn-v4.tsv.gz')
    if offline and not os.path.exists(asn_path):
        res['lewat'].append('pemilik: ip2asn belum diunduh dan mode luring')
    else:
        db = rules.load_ip2asn(asn_path, max_age_days=10**6 if offline else ASN_MAX_AGE_DAYS)
        if db is None:
            res['lewat'].append('pemilik: ip2asn tidak tersedia')
        else:
            date = _db_date(asn_path)
            for ip in baru:
                o = rules.ip_owner(ip, db)
                if o:
                    rows[ip].update(asn=o['asn'], cc=o['cc'], org=o['org'], is_private=o['cc'] == '-', asn_db_date=date)
                    res['pemilik'] += 1

    need = []
    for ip in baru:
        try: a = ipaddress.ip_address(ip)
        except ValueError: continue
        if a.version == 4 and a.is_global: need.append((int(a), ip))
    geo_path = os.path.join(cfg.cache_dir, 'geolite2-city-csv.zip')
    if not need:
        pass
    elif offline and not os.path.exists(geo_path):
        res['lewat'].append('lokasi: GeoLite2 belum diunduh dan mode luring')
    elif not (offline or fetch_maxmind(cfg, 'GeoLite2-City-CSV', geo_path, log=log)):
        res['lewat'].append('lokasi: GeoLite2 tidak tersedia (kunci MaxMind kosong atau unduhan gagal)')
    else:
        date = _db_date(geo_path)
        locs = geolite_locations(geo_path)
        for ip, loc in sweep(sorted(need), geolite_ranges(geo_path, locs)).items():
            rows[ip]['geo_checked'] = True
            rows[ip]['geo_db_date'] = date
            if loc:
                rows[ip].update(city=loc[0] or None, region=loc[1] or None, country=loc[2] or None, lat=loc[3], lon=loc[4])
                res['lokasi'] += 1

    cols = ['asn', 'cc', 'org', 'is_private', 'city', 'region', 'country', 'lat', 'lon', 'geo_checked', 'asn_db_date', 'geo_db_date']
    con.executemany(f"INSERT INTO ip_info VALUES ({', '.join('?' * (len(cols) + 1))})", [[ip, *(rows[ip][c] for c in cols)] for ip in baru])
    return res


def _have(urls, path, age, offline, nama, log):
    """True bila berkas sumber siap dipakai. Dalam mode luring tidak pernah mengunduh."""
    if offline:
        if os.path.exists(path): return True
        log(f'{nama}: belum diunduh dan mode luring; dilewati')
        return False
    if rules.fetch(urls, path, age): return True
    log(f'{nama}: tidak tersedia')
    return False


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.tmp', 'w', encoding='utf-8') as fh: json.dump(obj, fh, ensure_ascii=False, separators=(',', ':'))
    os.replace(path + '.tmp', path)


def _round_geom(g, nd=2):
    """Bulatkan koordinat ke 2 desimal (≈ 1 km, sama dengan peta lama) agar berkasnya kecil."""
    if isinstance(g, (int, float)): return round(g, nd)
    return [_round_geom(x, nd) for x in g]


def build_map_files(cfg, offline=False, log=print):
    """Buat berkas statis peta di <data_dir>/map. Mengembalikan ringkasan per berkas."""
    out_dir = os.path.join(cfg.data_dir, 'map')
    os.makedirs(out_dir, exist_ok=True)
    res, cache = {}, cfg.cache_dir
    age = 10**6 if offline else MAP_MAX_AGE_DAYS

    land_src = os.path.join(cache, 'ne_50m_land.geojson')
    if _have([rules.LAND_URL], land_src, age, offline, 'daratan', log):
        g = json.load(open(land_src, encoding='utf-8'))
        g['features'] = [dict(type='Feature', properties={}, geometry=_round_geom_feature(f['geometry'])) for f in g['features']]
        _write_json(os.path.join(out_dir, 'land.geojson'), g)
        res['land.geojson'] = len(g['features'])

    b_src = os.path.join(cache, 'ne_50m_boundary_lines.geojson')
    if _have([BORDERS_URL], b_src, age, offline, 'batas negara', log):
        g = json.load(open(b_src, encoding='utf-8'))
        g['features'] = [dict(type='Feature', properties={}, geometry=_round_geom_feature(f['geometry'])) for f in g['features']]
        _write_json(os.path.join(out_dir, 'borders-country.geojson'), g)
        res['borders-country.geojson'] = len(g['features'])

    p_src = os.path.join(cache, 'ne_10m_admin_1_states_provinces.geojson')
    if _have([PROVINCES_URL], p_src, age, offline, 'batas provinsi', log):
        g = json.load(open(p_src, encoding='utf-8'))
        feats = [f for f in g['features'] if (f['properties'].get('adm0_a3') or f['properties'].get('iso_a2')) in ('IDN', 'ID')]
        _write_json(os.path.join(out_dir, 'borders-province-id.geojson'),
                    dict(type='FeatureCollection', features=[dict(type='Feature', properties={'name': f['properties'].get('name')},
                                                                  geometry=_round_geom_feature(f['geometry'])) for f in feats]))
        res['borders-province-id.geojson'] = len(feats)

    countries = os.path.join(cache, 'ne_110m_countries.geojson')
    geonames = os.path.join(cache, 'geonames-ID.zip')
    if _have([rules.COUNTRIES_URL], countries, age, offline, 'label negara', log) & _have([rules.GEONAMES_URL], geonames, age, offline, 'label wilayah Indonesia', log):
        labels = rules.map_labels(countries, geonames)   # dipakai apa adanya dari sistem lama
        if any(labels.values()):
            _write_json(os.path.join(out_dir, 'labels.json'), labels)
            res['labels.json'] = {k: len(v) for k, v in labels.items()}
    return res


def _round_geom_feature(geom): return dict(type=geom['type'], coordinates=_round_geom(geom['coordinates']))


def run(cfg, con, offline=False, force_map=False, log=print):
    """Dipanggil di akhir ingest (force_map=False: berkas peta yang sudah ada tidak dibuat ulang)."""
    ip = fill_ip_info(cfg, con, offline=offline, log=log)
    peta = {}
    if force_map or not map_ready(cfg):
        try: peta = build_map_files(cfg, offline=offline, log=log)
        except Exception as e:  # noqa: BLE001  berkas peta gagal tidak boleh membuang hasil ip_info
            log(f'berkas peta gagal dibuat: {type(e).__name__}: {e}')
    return dict(ip=ip, peta=peta)


MAP_FILES = ('land.geojson', 'borders-country.geojson', 'borders-province-id.geojson', 'labels.json')


def map_ready(cfg):
    return all(os.path.exists(os.path.join(cfg.data_dir, 'map', f)) for f in MAP_FILES)
