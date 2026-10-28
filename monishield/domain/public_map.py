"""Live map of the public home page (owner request 2026-10-28). Anyone can open the home page, so the request origins
are made coarse before they leave the server: one dot per CELL degrees (about 55 km, a region, never a street), cells with
fewer than MIN_REQUESTS requests left out, and no IP address anywhere (project rule: the live map gets coordinates only)."""

CELL = 0.5
MIN_REQUESTS = 3


def cell(v): return round(round(v / CELL) * CELL, 2)


def coarse(rows, min_requests=MIN_REQUESTS):
    """[(lat, lon, requests, city, country)] -> [dict(lat, lon, requests, city, cc)] per cell, ascending (largest drawn last).
    The cell is named after its busiest named location."""
    cells = {}
    for lat, lon, n, city, cc in rows:
        if lat is None or lon is None or not n: continue
        k = (cell(lat), cell(lon))
        c = cells.setdefault(k, dict(lat=k[0], lon=k[1], requests=0, city=None, cc=cc, top=0))
        c['requests'] += int(n)
        if city and n > c['top']: c['city'], c['cc'], c['top'] = city, cc, n
    out = [dict(lat=c['lat'], lon=c['lon'], requests=c['requests'], city=c['city'], cc=c['cc'])
           for c in cells.values() if c['requests'] >= min_requests]
    return sorted(out, key=lambda c: (c['requests'], c['lat'], c['lon']))


def totals(points):
    """Numbers under the map: requests, places (cells) and countries of the dots shown."""
    return dict(requests=sum(p['requests'] for p in points), places=len(points), countries=len({p['cc'] for p in points if p['cc']}))
