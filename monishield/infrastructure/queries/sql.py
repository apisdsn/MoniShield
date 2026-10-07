"""Pembantu kueri sisi baca: format sel, jam WIB, eksekusi singkat, penolakan (galat domain -> HTTP di antarmuka)."""
import datetime

from monishield.domain.errors import Fail


def reject(status, code, message):
    """Penolakan dari kueri (parameter tidak sah, tidak ditemukan): lapisan antarmuka menerjemahkannya ke HTTP."""
    return Fail(code, message, status)


# ------------------------------------------------------------------ format
def wib(ts, n=16):
    """TIMESTAMP UTC -> teks WIB 'YYYY-MM-DD HH:MM' (n=13: sampai jam), format yang sama dengan data sistem lama."""
    return None if ts is None else (ts + datetime.timedelta(hours=7)).strftime('%Y-%m-%d %H:%M')[:n]


def ip_cell(ip, asn=None, cc=None, org=None):
    """Sel IP + pemilik jaringan (TRD §5.1): hanya {'ip'} bila pemilik tidak diketahui."""
    return dict(ip=ip) if org is None else dict(ip=ip, asn=asn, cc=cc, org=org)


# ------------------------------------------------------------------ dipakai modul halaman (TRD §5.3)
# Semua angka halaman dibaca dari tabel agregat lengkap (TRD K4), bukan dari daftar yang sudah dipotong.
# Bila log yang dibutuhkan tidak ada: 200 dengan available=false + reason, bukan galat.
SL, AM, RP = 'om-be-simpel-loop', 'om-be-appsmanager', 'om-be-report'
H = "strftime({}, '%Y-%m-%d %H')"   # jam WIB, format lama


def _all(cur, sql, *p): return [list(r) for r in cur.execute(sql, list(p)).fetchall()]
def _one(cur, sql, *p): return cur.execute(sql, list(p)).fetchone()[0]
def _no(reason): return dict(available=False, reason=reason)
def _has(svc, name): return bool(svc.get(name))   # layanan ada DAN punya baris
