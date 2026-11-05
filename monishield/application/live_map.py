"""Live map events (owner request 2026-10-07, collector lines 2026-11-05, Stage 57): one `LiveHub` per live source (Kafka, collector).
A hub collects what the browser's realtime map shows: per second the request locations and the module (service or upstream). Only
coordinates, counts and the module leave the hub (SSE /api/v1/live/map); an IP address is looked up in memory and forgotten.

Locations come from `ip_info` of the source's database (known visitors) and, for an address not ingested yet, from the offline
lookup of `ctx.geo` (infrastructure/geo_lookup.py, GeoLite2 files on disk): a new visitor shows on the map at once and no address is
sent to any outside service."""
import collections, threading, time

from monishield.domain import live_map, log_formats

MAX_PER_REQUEST = 2000   # lines of one receiver request that go to the map: a big batch (history after an outage) must not cost much


class LiveHub:
    """Events collected per second: {(lat, lon, module): n}. Readers (SSE) take what is newer than their last sequence number."""

    def __init__(self, ctx):
        self.ctx, self._lock, self.seq, self.ring = ctx, threading.Lock(), 0, collections.deque(maxlen=120)
        self.geo, self.geo_at, self.cur, self.cur_sec = {}, 0, collections.Counter(), None
        self.names = {}   # (lat, lon) -> (city, country): names the cells of the public home page map

    def _geo(self):
        if time.time() - self.geo_at > 300:
            self.geo_at = time.time()
            try: self.geo = self.ctx.warehouse.ip_locations()
            except Exception: pass   # noqa: BLE001  database in use by ingest: try again later
        return self.geo

    def refresh(self): self.geo_at = 0

    def locate(self, ip):
        """(lat, lon, city, country) of a client address, or None: the known visitors first, then the offline lookup."""
        g = self._geo().get(ip)
        if g: return g
        lookup = getattr(self.ctx, 'geo', None)
        return lookup.locate(ip) if lookup is not None else None

    def add(self, ip, module):
        """One request of `ip` for `module`. Nothing happens for an address without a location."""
        g = self.locate(ip)
        if not g: return False
        sec = int(time.time())
        with self._lock:
            if self.cur_sec is not None and sec != self.cur_sec: self._close()
            self.cur_sec = sec
            self.cur[(g[0], g[1], module or '-')] += 1
            self.names[g[0], g[1]] = g[2:4]
        return True

    def nginx_line(self, line, prefix):
        """A line of the nginx ingress controller (Kafka)."""
        got = live_map.line_reader(log_formats.Rule('*', 'ingress-nginx', 'http'), prefix)(line)
        if got: self.add(got[0], got[1])

    def _close(self):
        if self.cur:
            self.seq += 1
            self.ring.append((self.seq, [[la, lo, n, mod] for (la, lo, mod), n in self.cur.items()], self.cur_sec))
        self.cur = collections.Counter()

    def since(self, seq):
        """-> (latest sequence number, [[lat, lon, n, module], …]) for events after `seq`."""
        with self._lock:
            if self.cur_sec is not None and int(time.time()) != self.cur_sec: self._close(); self.cur_sec = None
            pts = [p for s, ps, _ in self.ring if s > seq for p in ps]
            return self.seq, pts

    def window(self, seconds=60):
        """[(lat, lon, requests, city, country)] of the last `seconds`, every module together (public home page map)."""
        now = int(time.time())
        with self._lock:
            if self.cur_sec is not None and now != self.cur_sec: self._close(); self.cur_sec = None
            agg = collections.Counter()
            for _, ps, sec in self.ring:
                if sec is not None and sec > now - seconds:
                    for la, lo, n, _m in ps: agg[la, lo] += n
            return [(la, lo, n, *self.names.get((la, lo), (None, None))) for (la, lo), n in agg.items()]


class AccessLines:
    """Collector records -> live map events: the lines of services whose rule is an http rule are read with that rule's reader."""

    def __init__(self, hub, prefix=''):
        self.hub, self.prefix, self._readers, self._rules = hub, prefix, {}, None

    def _reader(self, rules, ns, svc):
        key = (ns, svc)
        if key not in self._readers:
            if len(self._readers) > 500: self._readers.clear()
            rule = log_formats.match(rules, ns, svc)
            self._readers[key] = live_map.line_reader(rule, self.prefix)
        return self._readers[key]

    def feed(self, records):
        """records: dicts with ns, svc and line (domain/otlp_logs.py). -> the number of events added. Never raises: the map is
        a view, a receive must not fail because of it."""
        added = 0
        try:
            rules = log_formats.current() or ()
            if not rules: return 0
            if rules is not self._rules: self._readers.clear(); self._rules = rules   # the rules file changed
            for rec in records[:MAX_PER_REQUEST]:
                read = self._reader(rules, rec['ns'], rec['svc'])
                if read is None: continue
                try: got = read(rec['line'])
                except Exception: continue   # noqa: BLE001  a line the reader chokes on is just not drawn
                if got and self.hub.add(got[0], got[1] or rec['svc']): added += 1
        except Exception: pass   # noqa: BLE001
        return added
