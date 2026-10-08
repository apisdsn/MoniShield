#!/bin/sh
# Run the SIMPeL4 Dashboard (v2) locally: ./run.sh
# Configuration and secrets are read by the app from .env (see .env.example); this script does not read them.
set -eu
cd "$(dirname "$0")"

[ -f .env ] || { echo ".env is missing: copy .env.example to .env, fill it in, then chmod 600 .env" >&2; exit 1; }
[ -x .venv/bin/python ] || python3 -m venv .venv
# Python packages (including boto3 for S3 import and kafka-python for Kafka logs) are installed when .venv is new AND whenever pyproject.toml changes,
# so dependencies added later get installed too (previously: only when .venv did not exist yet).
if [ ! -f .venv/.deps-ok ] || [ pyproject.toml -nt .venv/.deps-ok ]; then
  .venv/bin/pip install -q -e ".[s3,kafka]" && touch .venv/.deps-ok
fi

# The UI is built only when its sources exist and are newer than the last build.
if [ -f web/package.json ] && { [ ! -d web/dist ] || [ -n "$(find web/src web/package.json -newer web/dist -print -quit 2>/dev/null)" ]; }; then
  (cd web && { [ -d node_modules ] || npm ci; } && npm run build)
fi

# The server creates the first admin from S4_ADMIN_USER / S4_ADMIN_PASSWORD when there are no users at all.
exec .venv/bin/python -m monishield serve
