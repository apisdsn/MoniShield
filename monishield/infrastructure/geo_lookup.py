"""Offline location of one client address for the live map (Stage 57): the GeoLite2 City file that the ingest already downloads
(`geolite2-city-csv.zip` in the cache folder). It is read once, in a background thread, into compact arrays (about 12 bytes per
block) and searched with a binary search; nothing is downloaded here and no address ever leaves the process. Until the file is
loaded, or when there is none, `locate` answers None and the address is simply not drawn. A bounded LRU cache keeps busy visitors.
Implements the `GeoLocator` port (application/ports.py)."""
import array, bisect, collections, ipaddress, os, threading, time, zipfile

from monishield.infrastructure import refdata

CACHE_SIZE = 20_000
RECHECK_SECONDS = 600   # how often the file's date is looked at (the ingest replaces it about weekly)


class GeoLookup:
    def __init__(self, cfg):
        self.path = os.path.join(cfg.cache_dir, 'geolite2-city-csv.zip')
        self._lock, self._cache = threading.Lock(), collections.OrderedDict()
        self._index, self._stamp, self._checked, self._loading = None, None, 0.0, False

    # Index
    def _build(self):
        locs, ids, starts, ends, which = [], {}, array.array('I'), array.array('I'), array.array('I')
        for start, end, loc in refdata.geolite_ranges(self.path, refdata.geolite_locations(self.path)):
            if loc[3] is None or loc[4] is None: continue   # a block without coordinates is not drawn
            key = (round(loc[3], 3), round(loc[4], 3), loc[0] or None, loc[2] or None)
            starts.append(start); ends.append(end)
            which.append(ids.setdefault(key, len(locs)))
            if len(locs) < len(ids): locs.append(key)
        return starts, ends, which, locs

    def _load(self):
        try:
            stamp = os.path.getmtime(self.path)
            index = self._build()
        except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile): index, stamp = None, None   # no file, or one that cannot be read
        with self._lock:
            self._index, self._stamp, self._loading = index, stamp, False
            self._cache.clear()

    def _ensure(self):
        now = time.monotonic()
        if self._loading or (self._index is not None and now - self._checked < RECHECK_SECONDS): return
        if self._index is None and now - self._checked < 30: return   # no file yet: look again in a moment, not on every line
        self._checked = now
        try: stamp = os.path.getmtime(self.path)
        except OSError: return
        if self._index is not None and stamp == self._stamp: return
        self._loading = True
        threading.Thread(target=self._load, name='geo-lookup', daemon=True).start()

    def ready(self): return self._index is not None

    def load_now(self):
        """Read the file in the calling thread (tests, tools)."""
        self._loading = True
        self._load()

    # Lookup
    def locate(self, ip):
        """(lat, lon, city, country) of a public IPv4 address, or None."""
        with self._lock:
            if ip in self._cache:
                self._cache.move_to_end(ip)
                return self._cache[ip]
        self._ensure()
        index = self._index
        if index is None: return None
        found = self._search(index, ip)
        with self._lock:
            self._cache[ip] = found
            if len(self._cache) > CACHE_SIZE: self._cache.popitem(last=False)
        return found

    @staticmethod
    def _search(index, ip):
        starts, ends, which, locs = index
        try: a = ipaddress.ip_address(ip)
        except ValueError: return None
        if a.version != 4 or not a.is_global: return None
        n = int(a)
        i = bisect.bisect_right(starts, n) - 1
        return locs[which[i]] if i >= 0 and n <= ends[i] else None

