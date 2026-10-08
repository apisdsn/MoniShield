"""DuckDB data warehouse (Warehouse port adapter for the application layer). ONE connection owned by the server process (TRD K1);
each operation opens its own cursor. Page queries (read side) live in monishield/infrastructure/queries/."""
import contextlib, datetime, json

from monishield.domain.errors import Busy
from monishield.infrastructure import db, ingest
from monishield.infrastructure.queries import command


class DuckWarehouse:
    def __init__(self, ctx):
        self.ctx = ctx   # the connection (ctx.con) is only opened when the server starts

    @contextlib.contextmanager
    def _cur(self):
        cur = self.ctx.con.cursor()
        try: yield cur
        finally: cur.close()

    # -------------------------------------------------------------- ingest
    def ingest(self, folder=None, force=False, progress=None):
        """-> ingest summary. Another ingest running -> Busy."""
        with self._cur() as cur:
            try: return ingest.run(self.ctx.cfg, cur, folder=folder, force=force, progress=progress)
            except ingest.Busy: raise Busy('Another ingest is running.') from None

    def snapshot_wanted(self, missing_only=False):
        cfg = self.ctx.cfg
        if not cfg.duckdb_snapshot: return False
        if missing_only:
            import os
            return not os.path.exists(db.snapshot_path(cfg))
        return True

    def snapshot(self):
        """Read-only copy for DbGate (S4_DUCKDB_SNAPSHOT). Errors are raised to the caller."""
        with self._cur() as cur: db.snapshot(cur, self.ctx.cfg)

    @contextlib.contextmanager
    def exclusive(self):
        """Ingest lock for derive/folder deletion: must not run concurrently with an ingest."""
        if not ingest._lock.acquire(blocking=False): raise Busy('An ingest is running; try again after it finishes.')
        try: yield self
        finally: ingest._lock.release()

    def derive_all(self, folder=None):
        with self._cur() as cur: return ingest.derive_all(cur, folder)

    def forget(self, folder):
        with self._cur() as cur: return ingest.forget(cur, folder)

    # -------------------------------------------------------------- folder
    def last_run(self):
        with self._cur() as cur:
            r = cur.execute("""SELECT started_at, finished_at, status, files_seen, files_changed, message FROM ingest_run
                              WHERE finished_at IS NOT NULL ORDER BY run_id DESC LIMIT 1""").fetchone()
        return r and dict(started_at=str(r[0].replace(microsecond=0)), finished_at=str(r[1].replace(microsecond=0)), status=r[2], files_seen=r[3],
                          files_changed=r[4], warnings=json.loads(r[5]) if r[5] else [])

    def known_folders(self):
        with self._cur() as cur: return {str(r[0]) for r in cur.execute('SELECT folder FROM folder_state').fetchall()}

    def ignored(self):
        with self._cur() as cur: return ingest.ignored(cur)

    def newest_folder(self):
        with self._cur() as cur: r = cur.execute('SELECT max(folder) FROM folder_state').fetchone()[0]
        return None if r is None else str(r)

    def folder_table(self):
        """-> ({folder: dict(lines, files, files_corrupt)}, {ignored folder: dict(by, at)})."""
        with self._cur() as cur:
            rows = {str(f): dict(lines=l, files=n, files_corrupt=c) for f, l, n, c in cur.execute('SELECT folder, lines, files, files_corrupt FROM folder_state').fetchall()}
            ign = {f: dict(by=b, at=str(a.replace(microsecond=0)) if a else None) for f, b, a in cur.execute('SELECT ignored_folder, by_user, at_utc FROM folder_ignored').fetchall()}
        return rows, ign

    def ignore(self, folder, by):
        with self._cur() as cur:
            cur.execute('INSERT OR REPLACE INTO folder_ignored VALUES (?, ?, ?)', [folder, by, datetime.datetime.now(datetime.UTC).replace(tzinfo=None)])

    def unignore(self, folder):
        """-> False when the folder is not currently ignored."""
        with self._cur() as cur:
            if not cur.execute('SELECT 1 FROM folder_ignored WHERE ignored_folder = ?', [folder]).fetchone(): return False
            cur.execute('DELETE FROM folder_ignored WHERE ignored_folder = ?', [folder])
        return True

    # -------------------------------------------------------------- notifications and realtime map (no IPs)
    def folder_facts(self, folder, crs):
        """One folder's aggregate numbers for notification evaluation (monishield/domain/alerts.py)."""
        with self._cur() as cur:
            a = command._kpi(cur, folder, crs)
            b = command.baseline(cur, folder, crs, a)
            cats = [r[0] for r in cur.execute("""SELECT category, sum(hits) h FROM agg_crs_url WHERE folder = ? AND severity = 3
                                                 GROUP BY 1 ORDER BY h DESC LIMIT 3""", [folder]).fetchall()] if crs and a['crit_req'] else []
        return dict(kpi=a, base=b, ngx_keys=command.NGX_KEYS, crit_cats=cats)

    def ip_locations(self):
        """{public ip: (lat, lon)} from the offline location database (ip_info). Used in memory only, never sent."""
        with self._cur() as cur:
            return {ip: (round(la, 3), round(lo, 3)) for ip, la, lo in
                    cur.execute('SELECT ip, lat, lon FROM ip_info WHERE lat IS NOT NULL AND NOT coalesce(is_private, false)').fetchall()}
