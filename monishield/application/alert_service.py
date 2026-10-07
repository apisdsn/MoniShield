"""Notifikasi: kapan dikirim dan ke mana (aturan + teks di monishield/domain/alerts.py, saluran di
monishield/infrastructure/notify_channels.py). Dipanggil layanan ingest / impor sesudah pekerjaan selesai, dan penjadwal
tiap jam (folder belum datang). Semua pengiriman di thread latar: ingest dan layar tidak pernah menunggu Telegram/SMTP.

ATURAN PROYEK: alamat IP pengguna tidak boleh dikirim ke layanan pihak ketiga — teks dibersihkan `alerts.scrub` di sini,
tepat sebelum diserahkan ke saluran.
"""
import datetime, threading, time

from monishield.application import settings_service
from monishield.domain import alerts
from monishield.domain.alerts import AlertFail
from monishield.domain.errors import Fail


def deliver(ctx, cfg, key, event, title, text, channels=None, force=False):
    """Kirim ke semua saluran aktif (atau `channels`). Sudah pernah berhasil untuk `key` -> dilewati (kecuali force).
    -> {saluran: None (berhasil) | pesan galat}. Galat tidak pernah memuat kredensial."""
    auth = ctx.auth
    if not force and auth.alert_seen(key): return {}
    title, text = alerts.scrub(title), alerts.scrub(text)
    out = {}
    for name, ch in cfg['channels'].items():
        if (channels and name not in channels) or (not channels and not ch['enabled']): continue
        try: ctx.channels.send(name, ch, title, text); out[name] = None
        except AlertFail as e: out[name] = str(e)
        except Exception as e: out[name] = type(e).__name__   # noqa: BLE001
        auth.alert_add(key, event, name, out[name] is None, summary=title, error=out[name])
    return out


# ------------------------------------------------------------------ layar (admin)
def view(ctx):
    return dict(alerts.public(alerts.load(ctx.cfg)), events_all=list(alerts.EVENTS), history=ctx.auth.alert_list(30))


def update(ctx, body):
    """Gabungkan isian layar (kredensial kosong = tetap, `clear` = hapus), periksa, tulis ke .env. -> setelan baru."""
    try: cfg = alerts.merge(alerts.load(ctx.cfg), body)
    except (TypeError, ValueError): raise Fail('invalid_parameter', 'Isian notifikasi tidak sah.', 400) from None
    settings_service.write_alerts(ctx, cfg)
    return cfg


def send_test(ctx, channel):
    """Pesan uji ke satu saluran memakai setelan TERSIMPAN. Gagal kirim -> Fail 502."""
    if channel not in ctx.channels.names: raise Fail('invalid_parameter', 'Saluran tidak dikenal.', 400)
    cfg = alerts.load(ctx.cfg)
    alerts.validate(cfg)
    ch = cfg['channels'][channel]
    if not all(ch[k] for k in alerts.TEST_NEEDS[channel]): raise Fail('alert_not_configured', 'Lengkapi dan simpan isian saluran ini dulu.', 400)
    r = deliver(ctx, cfg, f'test:{channel}:{time.time()}', 'test', alerts._t(cfg, 'test'), alerts._t(cfg, 'test_text'), channels=[channel], force=True)
    if r.get(channel): raise Fail('alert_send_failed', f'Gagal mengirim ke {channel}: {r[channel]}.', 502)
    return dict(sent=True, channel=channel)


# ------------------------------------------------------------------ otomatis
class Notifier:
    def __init__(self, ctx):
        self.ctx, self._lock = ctx, threading.Lock()

    def _cfg(self): return alerts.load(self.ctx.cfg)

    def _bg(self, fn, *a):
        threading.Thread(target=self._safe, args=(fn, *a), name='alerts', daemon=True).start()

    def _safe(self, fn, *a):
        with self._lock:
            try: fn(*a)
            except Exception: pass   # noqa: BLE001  notifikasi tidak boleh menjatuhkan server; galat kirim tercatat di alert_log

    def after_ingest(self, result, error=None): self._bg(self._after_ingest, result, error)

    def _after_ingest(self, result, error):
        cfg = self._cfg()
        if not alerts.active(cfg): return
        if ev := alerts.ingest_failed(cfg, result, error): deliver(self.ctx, cfg, ev[0], 'ingest_failed', ev[1], ev[2])
        if error or not result: return
        changed = sorted(result.get('folders_changed') or [])
        if not changed: return
        w = self.ctx.warehouse
        newest = w.newest_folder()
        floor = (datetime.date.fromisoformat(newest) - datetime.timedelta(days=2)).isoformat()
        crs = self.ctx.cfg.attack_rules == 'crs'
        for f in (x for x in changed if x >= floor):   # folder lama yang di-ingest ulang tidak memicu notifikasi
            for ev, key, title, text in alerts.folder_events(cfg, f, w.folder_facts(f, crs)): deliver(self.ctx, cfg, key, ev, title, text)

    def after_sync(self, res): self._bg(self._after_sync, res)

    def _after_sync(self, res):
        cfg = self._cfg()
        if alerts.active(cfg) and (ev := alerts.sync_failed(cfg, res)): deliver(self.ctx, cfg, ev[0], 'sync_failed', ev[1], ev[2])

    def check_missing(self, now_utc=None):
        """Folder bertanggal hari ini (WIB) belum ada setelah `missing_hour` -> sekali per hari."""
        cfg = self._cfg()
        if not alerts.active(cfg) or not cfg['events']['folder_missing']: return None
        wib = (now_utc or datetime.datetime.now(datetime.timezone.utc)) + datetime.timedelta(hours=7)
        if wib.hour < int(cfg['missing_hour']): return None
        ev = alerts.folder_missing(cfg, wib, self.ctx.warehouse.newest_folder())
        return ev and deliver(self.ctx, cfg, ev[0], 'folder_missing', ev[1], ev[2])

    def start(self):
        self._stop = threading.Event()
        def loop():
            while not self._stop.wait(3600):
                self._safe(self.check_missing)
        threading.Thread(target=loop, name='alerts-hourly', daemon=True).start()

    def stop(self):
        if getattr(self, '_stop', None): self._stop.set()
