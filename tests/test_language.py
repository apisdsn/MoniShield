"""Code is English (CLAUDE.md, "Language"): names, comments, messages and test data. Indonesian belongs only in the UI
dictionaries and in the files below, which hold Indonesian UI copy, old Indonesian values kept for conversion, or tests
of the Indonesian output. A new Indonesian word anywhere else fails this test."""
import glob, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORDS = re.compile(r'\b(yang|dengan|tidak|contoh|uji|tiruan|kunci|sudah|belum|untuk|harus|sandi|galat|berkas|layanan|bukan|rahasia|salah|sebagai|kosong|tanggal|'
                   r'selesai|gagal|sukses|diisi|sebelum|sesudah|lihat|tampilkan|pesan|jumlah|baris)\b', re.I)
ALLOWED = {
    # Indonesian UI copy next to the English one
    'monishield/domain/letters.py', 'monishield/domain/alerts.py', 'monishield/interfaces/api/home_meta.py', 'tools/og_image.cjs',
    'web/src/srv.js', 'web/src/format.js', 'web/src/lib/MapView.svelte', 'monishield/infrastructure/queries/ips.py',
    # old Indonesian values read and converted (stored data, .env written by earlier versions)
    'monishield/infrastructure/auth.py', 'monishield/infrastructure/db.py', 'monishield/infrastructure/config.py',
    'monishield/infrastructure/envfile.py', 'monishield/domain/config_model.py', 'monishield/domain/rules.py',
    'web/src/pages/Security.svelte', 'web/src/lib/ImportCard.svelte',
    'monishield/infrastructure/queries/tables.py', 'monishield/infrastructure/queries/security.py',   # login flags stored by derive
    # tests of the Indonesian output or of the old values
    'tests/test_alerts.py', 'tests/test_password_reset.py', 'tests/test_format.mjs', 'tests/test_status_migration.py',
    'tests/test_derive_features.py', 'tests/test_bulk_insert.py', 'tests/test_home_meta.py', 'tests/test_language.py',
}
PATTERNS = ('monishield/**/*.py', 'tests/*.py', 'tests/*.mjs', 'tools/*.py', 'tools/*.mjs', 'tools/*.cjs', 'web/src/**/*.js', 'web/src/**/*.svelte')


def test_no_indonesian_outside_the_ui_copy():
    found = []
    for pattern in PATTERNS:
        for path in glob.glob(os.path.join(ROOT, pattern), recursive=True):
            rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
            if rel in ALLOWED: continue
            for n, line in enumerate(open(path, encoding='utf-8'), 1):
                if m := WORDS.search(line): found.append(f'{rel}:{n}: {m[0]}')
    assert not found, 'Indonesian in code (write it in English, or add UI copy to the dictionaries):\n' + '\n'.join(found[:40])
