"""Public home page map (owner request 2026-10-28; rules in monishield/domain/public_map.py). Live when the Kafka feed has
traffic in the last minute, otherwise the request origins of the newest folder. One snapshot is shared by every visitor
for a few seconds, so many open home pages cost the same as one."""
import datetime, threading, time

from monishield.application import sources
from monishield.domain import public_map

LIVE_SECONDS, PULSE_SECONDS, TTL = 60, 6, 3
LOOKBACK = 7          # folders tried, newest first, when the newest one has no located nginx requests (empty, still arriving)
DAY_CACHE = 600       # seconds a folder's points are kept (the newest folder keeps growing during the day)


class PublicMap:
    def __init__(self, ctx):
        self.ctx, self._lock, self._snap, self._at, self._days = ctx, threading.Lock(), None, 0.0, {}

    def snapshot(self):
        if not self.ctx.cfg.public_map: return dict(enabled=False)
        with self._lock:
            if self._snap is None or time.monotonic() - self._at >= TTL:
                self._snap, self._at = self._build(), time.monotonic()
            return self._snap

    def _server(self):
        """Where the arcs end: the server's area from the configuration, rounded like the dots, without its IP address."""
        city, _region, cc, lat, lon = self.ctx.cfg.server_fallback
        return dict(lat=public_map.cell(lat), lon=public_map.cell(lon), city=city, cc=cc)

    def _build(self):
        base = dict(enabled=True, server=self._server())
        feed = getattr(self.ctx, 'kafka', None)
        try: live = feed is not None and feed.running()
        except Exception: live = False   # noqa: BLE001
        if live:
            pts = public_map.coarse(feed.live.window(LIVE_SECONDS))
            if pts:
                # pulses (the last seconds, for the animation) only in cells already shown: a cell under the minimum
                # must not appear through its animation either
                shown = {(p['lat'], p['lon']) for p in pts}
                pulses = [p for p in public_map.coarse(feed.live.window(PULSE_SECONDS), 1) if (p['lat'], p['lon']) in shown]
                return dict(base, mode='live', seconds=LIVE_SECONDS, points=pts, totals=public_map.totals(pts),
                            pulses=[dict(lat=p['lat'], lon=p['lon'], n=p['requests']) for p in pulses])
        folder, pts = self._latest()
        if not pts: return dict(base, mode='none', points=[], totals=public_map.totals([]))
        day = (datetime.date.fromisoformat(folder) - datetime.timedelta(days=1)).isoformat()   # folder D holds the logs of D-1
        return dict(base, mode='day', day=day, points=pts, totals=public_map.totals(pts))

    def _latest(self):
        """(folder, coarse points) of the newest folder with located nginx requests among the latest LOOKBACK folders
        that hold lines: S3 first, then Kafka. Points are cached per folder for DAY_CACHE seconds."""
        for src in (self.ctx, (getattr(self.ctx, 'sources', None) or {}).get(sources.KAFKA)):
            if src is None: continue
            try:
                rows, ignored = src.warehouse.folder_table()
                folders = sorted((f for f, r in rows.items() if r.get('lines') and f not in ignored and _is_day(f)), reverse=True)
                for folder in folders[:LOOKBACK]:
                    pts = self._points(src, folder)
                    if pts: return folder, pts
            except Exception: continue   # noqa: BLE001  database not open / busy: try the other source, or no map this time
        return None, []

    def _points(self, src, folder):
        key, now = (src.source, folder), time.monotonic()
        hit = self._days.get(key)
        if hit is None or now - hit[0] >= DAY_CACHE:
            if len(self._days) > 4 * LOOKBACK: self._days.clear()
            hit = self._days[key] = (now, public_map.coarse(src.warehouse.request_origins(folder)))
        return hit[1]


def _is_day(folder):
    try: datetime.date.fromisoformat(folder); return True
    except ValueError: return False
