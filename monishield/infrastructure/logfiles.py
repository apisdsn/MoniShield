"""Berkas log -> CSV per tabel (adapter parser domain monishield/domain/parse.py). Dipakai subproses ingest.

  python -m monishield.infrastructure.logfiles <file.log[.gz]> --out <dir> [--service <nama>]
"""
import argparse, csv, gzip, hashlib, json, os, sys

from monishield.domain import parse
from monishield.domain.parse import TABLES


class CsvOut(parse.Out):
    """Out yang menulis tiap tabel ke <out_dir>/<tabel>.csv (dibuat saat baris pertama)."""

    def __init__(self, out_dir, service, upstream_prefix='ombudsman-ombudsman-'):
        super().__init__(service, upstream_prefix)
        self.dir, self._w, self._fh = out_dir, {}, []

    def _emit(self, table, values):
        if table not in self._w:
            fh = open(os.path.join(self.dir, table + '.csv'), 'w', newline='', encoding='utf-8')
            self._fh.append(fh)
            # QUOTE_NOTNULL: None -> kosong tanpa kutip (NULL), '' -> "" (teks kosong); DuckDB membedakannya.
            self._w[table] = csv.writer(fh, quoting=csv.QUOTE_NOTNULL, lineterminator='\n')
            self._w[table].writerow(TABLES[table])
        self._w[table].writerow(values)

    def close(self):
        for fh in self._fh: fh.close()


def parse_file(path, service, out_dir, upstream_prefix='ombudsman-ombudsman-'):
    """Parse satu file log -> CSV di out_dir; mengembalikan ringkasan (lines, err, warn, corrupt_lines, counters, rows)."""
    os.makedirs(out_dir, exist_ok=True)
    o = CsvOut(out_dir, service, upstream_prefix)
    try:
        with (gzip.open(path, 'rt', encoding='utf-8', errors='replace') if path.endswith('.gz')
              else open(path, encoding='utf-8', errors='replace')) as fh:
            return parse.parse_lines(fh, o)
    finally:
        o.close()


def hash_file(path):
    """SHA-256 isi SETELAH didekompresi: pasangan x.log / x.log.gz yang identik bersidik jari sama."""
    h = hashlib.sha256()
    with (gzip.open(path, 'rb') if path.endswith('.gz') else open(path, 'rb')) as fh:
        while chunk := fh.read(1 << 20): h.update(chunk)
    return h.hexdigest()


def work(path, service, out_dir, upstream_prefix, known_sha, pair_path):
    """Satu file, dijalankan di subproses ingest: sidik jari, lalu parse hanya bila isinya berbeda dari known_sha.

    Tidak menyentuh DuckDB (TRD K1/K2). Galat parse dikembalikan, bukan dilempar, agar file lain tetap masuk.
    pair_path = pasangan .log.gz dari sebuah .log (bila ada): ikut di-hash untuk memeriksa apakah keduanya identik.
    """
    out = dict(sha256=None, pair_sha256=None, summary=None, error=None)
    try:
        out['sha256'] = hash_file(path)
        if pair_path: out['pair_sha256'] = hash_file(pair_path)
        if out['sha256'] != known_sha: out['summary'] = parse_file(path, service, out_dir, upstream_prefix)
    except Exception as e:  # noqa: BLE001  (dilaporkan sebagai status 'gagal')
        out['error'] = f'{type(e).__name__}: {e}'
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog='monishield.infrastructure.logfiles', description='Parse satu file log menjadi CSV per tabel')
    ap.add_argument('file'); ap.add_argument('--out', required=True)
    ap.add_argument('--service', help='bawaan: nama folder induk file')
    a = ap.parse_args(argv)
    s = parse_file(a.file, a.service or os.path.basename(os.path.dirname(os.path.abspath(a.file))), a.out)
    json.dump(s, sys.stdout, ensure_ascii=False); print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
