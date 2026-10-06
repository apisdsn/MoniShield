#!/bin/sh
# Jalankan SIMPeL4 Dashboard (v2) secara lokal: ./run.sh
# Konfigurasi dan rahasia dibaca aplikasi dari v2/.env (lihat .env.example); skrip ini tidak membacanya.
set -eu
cd "$(dirname "$0")"

[ -f .env ] || { echo "v2/.env belum ada: salin .env.example ke .env, isi, lalu chmod 600 .env" >&2; exit 1; }
[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip install -q -e .; }

# Tampilan dibangun hanya bila sumbernya ada dan lebih baru dari hasil bangun terakhir.
if [ -f web/package.json ] && { [ ! -d web/dist ] || [ -n "$(find web/src web/package.json -newer web/dist -print -quit 2>/dev/null)" ]; }; then
  (cd web && { [ -d node_modules ] || npm ci; } && npm run build)
fi

# Admin pertama dibuat server dari S4_ADMIN_USER / S4_ADMIN_PASSWORD bila belum ada user sama sekali.
exec .venv/bin/python -m simpel4 serve
