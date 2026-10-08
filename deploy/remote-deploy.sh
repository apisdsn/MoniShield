#!/usr/bin/env bash
# Deploys MoniShield on the server. Run by the "Deploy" job of .github/workflows/ci.yml over SSH (stdin), or by hand:
#   DEPLOY_PROFILES=https,kafka bash deploy/remote-deploy.sh
# Idempotent. The first run also migrates an older checkout (DEPLOY_MIGRATE_FROM): it clones the repo and copies the
# old .env. Data stays in the Docker volumes: both checkouts use the compose project name "monishield", so the same
# volumes and containers are reused. Secrets never come from GitHub: the server's .env is the only source.
set -euo pipefail

DIR=${DEPLOY_DIR:-/srv/MoniShield}
REPO=${DEPLOY_REPO:-https://github.com/apisdsn/MoniShield.git}
BRANCH=${DEPLOY_BRANCH:-prd}
SHA=${DEPLOY_SHA:-}                        # exact commit tested by CI; empty = tip of $BRANCH
MIGRATE_FROM=${DEPLOY_MIGRATE_FROM:-}      # old checkout (e.g. /srv/dashboard-logging/v2) whose .env is copied once
export COMPOSE_PROFILES=${DEPLOY_PROFILES:-https}   # comma-separated, e.g. https,kafka
HEALTH_WAIT=${DEPLOY_HEALTH_WAIT:-180}     # seconds to wait for the app healthcheck

say() { printf '==> %s\n' "$*"; }

# ---------------------------------------------------------------- code
if [ ! -d "$DIR/.git" ]; then
  say "cloning $REPO ($BRANCH) into $DIR"
  git clone -q -b "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"
git fetch -q origin "$BRANCH"
git checkout -q "$BRANCH"
# the server checkout has no local edits: .env, logs/ and data live outside git (ignored files are not touched)
git reset -q --hard "${SHA:-origin/$BRANCH}"
say "code at $(git log -1 --format='%h %s')"

# ---------------------------------------------------------------- .env (secrets stay on the server)
if [ ! -f .env ]; then
  if [ -n "$MIGRATE_FROM" ] && [ -f "$MIGRATE_FROM/.env" ]; then
    say "first deploy: copying .env from $MIGRATE_FROM"
    # via Docker: the old .env belongs to root/10001 with mode 660, the deploy user may not read it directly
    docker run --rm -v "$MIGRATE_FROM/.env:/src/.env:ro" -v "$DIR:/dst" busybox cp /src/.env /dst/.env
  else
    echo "error: $DIR/.env is missing. Create it on the server from .env.example (docs/07-deploy-vps.md §5)." >&2
    exit 1
  fi
fi
# the app container runs as uid/gid 10001 and the Configuration page writes .env in place
docker run --rm -v "$DIR/.env:/e" busybox sh -c 'chgrp 10001 /e && chmod 660 /e'

# ---------------------------------------------------------------- containers
say "building and starting (profiles: ${COMPOSE_PROFILES:-none})"
docker compose build --pull
docker compose up -d --remove-orphans

app=$(docker compose ps -q app)
for _ in $(seq 1 "$HEALTH_WAIT"); do
  status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$app")
  [ "$status" = healthy ] && break
  sleep 1
done
if [ "$status" != healthy ]; then
  echo "error: app is '$status' after ${HEALTH_WAIT}s; last log lines:" >&2
  docker compose logs --tail 40 app >&2
  exit 1
fi
docker image prune -f >/dev/null
say "deployed $(git rev-parse --short HEAD): app is healthy"
