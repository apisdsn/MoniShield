#!/usr/bin/env python3
"""Cetak laporan kesetaraan v2 vs sistem lama (E1, E3, E4). Keluar dengan kode 1 bila ada selisih tak terduga.

  python3 tools/laporan_kesetaraan.py [berkas-keluaran.md]
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
