#!/usr/bin/env python3
"""Print the equivalence report v2 vs the old system (E1, E3, E4). Exits with code 1 on any unexpected difference.

  python3 tools/laporan_kesetaraan.py [output-file.md]
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kesetaraan

if __name__ == '__main__':
    hasil = kesetaraan.jalankan()
    ok = kesetaraan.cetak(*hasil)
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'w', encoding='utf-8') as fh: kesetaraan.cetak(*hasil, keluar=fh)
        print('->', sys.argv[1], file=sys.stderr)
    sys.exit(0 if ok else 1)
