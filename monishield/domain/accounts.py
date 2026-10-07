"""Aturan akun (TRD §8.2–§8.3): peran, bentuk nama user dan sandi, hash scrypt bergaram, token mesin. Murni; penyimpanan
akun/sesi ada di monishield/infrastructure/auth.py."""
import hashlib, hmac, re, secrets

from monishield.domain.errors import Fail

ROLES = ('admin', 'user')


USERNAME = re.compile(r'[a-z0-9._-]{3,32}')


PASSWORD_MIN, PASSWORD_MAX = 12, 128


SCRYPT = (15, 8, 1)          # n = 2^15, r, p: ±76 ms di laptop pengembang (docs/04a-hasil-ukur.md); disimpan per akun


# ------------------------------------------------------------------ pembantu
class AuthError(Fail):
    """Galat yang boleh ditampilkan ke pengguna. code = kode galat API, status = status HTTP."""


def hash_password(password, salt=None, params=None):
    """(hash, garam). params dibaca saat dipanggil, sehingga yang disimpan di hash_params selalu yang benar-benar dipakai."""
    salt = salt or secrets.token_bytes(16)
    n, r, p = params or SCRYPT
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2 ** n, r=r, p=p, maxmem=2 ** 30, dklen=32), salt


def check_username(username):
    if not isinstance(username, str) or not USERNAME.fullmatch(username):
        raise AuthError('invalid_username', 'Nama user harus 3–32 karakter: huruf kecil, angka, titik, garis bawah, atau strip.')
    return username


def check_password(password, username=''):
    if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise AuthError('invalid_password', f'Sandi harus {PASSWORD_MIN}–{PASSWORD_MAX} karakter.')
    if username and password.lower() == username.lower():
        raise AuthError('invalid_password', 'Sandi tidak boleh sama dengan nama user.')
    return password


def job_token_ok(configured, presented):
    """Token mesin (tugas ingest, pengirim tautan S3): perbandingan waktu-konstan; kosong = fitur mati."""
    return bool(configured) and isinstance(presented, str) and hmac.compare_digest(configured.encode(), presented.encode())
