#!/bin/sh
# Entrypoint of the "https" service: checks the settings, generates the optional Caddy files, then runs caddy with the
# arguments of the service's command. Optional files (generated fresh at every start):
#   generated/ingest.caddy       when DOCKER_INGEST_DOMAIN is set (collector receiver host)
#   generated/main/guard.caddy   when DOCKER_MAIN_CLOUDFLARE_ONLY=1 (main site answers Cloudflare addresses only)
#   generated/main/access-log.caddy + generated/global/trusted-proxies.caddy   unless DOCKER_ACCESS_LOG=0 (JSON access log of the main site)
set -eu
[ -n "${DOCKER_DOMAIN:-}" ] && [ -n "${DOCKER_ACME_EMAIL:-}" ] || { echo 'set DOCKER_DOMAIN and DOCKER_ACME_EMAIL in .env' >&2; exit 1; }
SRC=${CADDY_SRC:-/etc/caddy/extra}
OUT=${CADDY_OUT:-/etc/caddy/generated}
rm -rf "$OUT"; mkdir -p "$OUT/main" "$OUT/global"

if [ -n "${DOCKER_INGEST_DOMAIN:-}" ]; then
  case $DOCKER_INGEST_DOMAIN in
    *[!A-Za-z0-9.-]*|.*|*.|*..*|-*|*-.*|*.-*) echo 'DOCKER_INGEST_DOMAIN must be a host name such as ingest.example.com' >&2; exit 1 ;;
    *.*) ;;
    *) echo 'DOCKER_INGEST_DOMAIN must be a host name such as ingest.example.com' >&2; exit 1 ;;
  esac
  [ "$DOCKER_INGEST_DOMAIN" != "$DOCKER_DOMAIN" ] || { echo 'DOCKER_INGEST_DOMAIN must differ from DOCKER_DOMAIN' >&2; exit 1; }
  cp "$SRC/ingest.caddy" "$OUT/ingest.caddy"
fi
if [ "${DOCKER_MAIN_CLOUDFLARE_ONLY:-}" = 1 ]; then
  cp "$SRC/cloudflare-only.caddy" "$OUT/main/guard.caddy"
fi
if [ "${DOCKER_ACCESS_LOG:-1}" != 0 ]; then
  cp "$SRC/access-log.caddy" "$OUT/main/access-log.caddy"
  cp "$SRC/trusted-proxies.caddy" "$OUT/global/trusted-proxies.caddy"
fi
exec caddy "$@"
