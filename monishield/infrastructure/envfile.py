"""Menulis nilai ke file .env (layar Konfigurasi; permintaan pemilik 2026-10-07: "semua configuration … ke dalam .env").

Hanya baris kunci yang diubah yang disentuh; komentar, urutan, dan baris lain tetap. Kunci yang belum aktif dicari dulu
sebagai baris contoh berkomentar (`# KUNCI=…`, seperti di .env.example) dan diaktifkan di tempatnya; bila tidak ada,
ditambahkan di bagian akhir. Menghapus (nilai None) = baris dinonaktifkan menjadi `# KUNCI=` tanpa nilai lama (agar
rahasia tidak tertinggal di komentar), sehingga nilai bawaan berlaku lagi.

File ditulis DI TEMPAT (bukan ganti-nama), karena di Docker .env dipasang sebagai satu file (bind mount): ganti-nama
akan memutus pasangannya. Hasilnya dibaca ulang dengan pembaca yang sama dengan server (config.read_dotenv); bila tidak
sama, isi lama dikembalikan.
"""
import os, re, threading

from monishield.domain.settings import SettingsFail
from monishield.infrastructure import config

_LOCK = threading.Lock()
MARK = '# --- diisi dari layar Konfigurasi MoniShield ---'


class EnvFileFail(Exception):
    pass


def writable(path):
    if os.path.exists(path): return os.access(path, os.W_OK)
    return os.access(os.path.dirname(path) or '.', os.W_OK)


def fmt(value):
    """Nilai Python -> teks .env (tanpa kutip bila aman)."""
    if isinstance(value, bool): return 'true' if value else 'false'
    if isinstance(value, (list, dict)):
        import json
        value = json.dumps(value, ensure_ascii=False)
    return str(value)


def _quote(v):
    if re.search(r'[\x00-\x1f\x7f]', v): raise EnvFileFail('Nilai tidak boleh memuat baris baru atau karakter kendali.')
    if v == '' or (not re.search(r'[\s#]', v) and v[:1] not in ('"', "'")): return v
    if '"' not in v: return f'"{v}"'
    if "'" not in v: return f"'{v}'"
    raise EnvFileFail('Nilai tidak boleh memuat tanda kutip tunggal dan ganda sekaligus.')


def _key_re(name, active):
    return re.compile(rf'^\s*(export\s+)?{re.escape(name)}\s*=' if active else rf'^\s*#\s*(export\s+)?{re.escape(name)}\s*=')


def update(path, changes):
    """changes: {NAMA_VARIABEL: teks | None}. -> daftar nama yang berubah."""
    lines_new = {k: (None if v is None else f'{k}={_quote(v)}') for k, v in changes.items()}
    with _LOCK:
        old = open(path, encoding='utf-8').read() if os.path.exists(path) else ''
        lines = old.split('\n')
        if lines and lines[-1] == '': lines.pop()
        for name, line in lines_new.items():
            act = [i for i, l in enumerate(lines) if _key_re(name, True).match(l)]
            if line is None:
                for i in act: lines[i] = f'# {name}='
                continue
            if act:
                lines[act[0]] = line
                for i in act[1:]: lines[i] = f'# {name}='   # duplikat: yang pertama yang dipakai
                continue
            com = [i for i, l in enumerate(lines) if _key_re(name, False).match(l)]
            if com: lines[com[0]] = line
            else:
                if MARK not in lines: lines += ['', MARK]
                lines.append(line)
        text = '\n'.join(lines) + '\n'
        if text == old: return []
        new_file = not os.path.exists(path)
        with open(path, 'r+' if not new_file else 'w', encoding='utf-8') as fh:
            fh.seek(0); fh.write(text); fh.truncate()
        if new_file: os.chmod(path, 0o600)
        try:
            back = config.read_dotenv(path)
            ok = all((back.get(k) is None and v is None) or (v is not None and back.get(k) == v) for k, v in changes.items())
        except SystemExit: ok = False
        if not ok:
            with open(path, 'r+', encoding='utf-8') as fh: fh.seek(0); fh.write(old); fh.truncate()
            raise EnvFileFail('Isi .env hasil tulis tidak terbaca sama; perubahan dibatalkan.')
        return sorted(changes)


class EnvStore:
    """Port EnvStore untuk layar Konfigurasi: membaca/menulis satu file .env + melihat variabel lingkungan proses.
    Nilai ditulis dengan nama variabelnya (S4_…, AWS_…); pemanggil tidak tahu format file."""

    def __init__(self, path): self.path = path

    def values(self):
        try: return config.read_dotenv(self.path)
        except SystemExit: return {}

    def environ(self): return os.environ

    def exists(self): return os.path.exists(self.path)

    def writable(self): return writable(self.path)   # dicari saat dipanggil (bisa diganti di uji)

    def write(self, changes):
        """{NAMA: nilai Python | None (baris dinonaktifkan)} -> daftar nama yang berubah. Gagal -> SettingsFail."""
        try: return update(self.path, {k: None if v is None else fmt(v) for k, v in changes.items()})
        except EnvFileFail as e: raise SettingsFail(str(e)) from None
