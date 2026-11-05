#!/bin/sh
# MoniShield collector installer for Linux with systemd (Debian/Ubuntu: .deb, RHEL/Fedora/SUSE: .rpm).
#
# It installs the OpenTelemetry Collector (otelcol-contrib), enrolls it with the one-time token from the MoniShield
# Collectors page, writes the configuration MoniShield made for this collector and starts the service.
# The script holds no secret. Download it to a file, read it, then run it as root:
#
#   curl -fsSLo install.sh https://<your-MoniShield>/collector/install.sh
#   sudo sh install.sh --name <collector name> --token <enrollment token>
#
# Options:  --name NAME   the collector's name as on the page (checked against the server's answer)
#           --token TOKEN the enrollment token (works once, for 24 hours)
#           --url URL     MoniShield's address (default: the one this script was served from)
#           --upgrade     no token: refresh an installed collector (its key stays; new configuration, Docker name helper)
#           --dry-run     print the steps and change nothing
set -eu

VERSION='@@VERSION@@'
URL='@@URL@@'
RELEASE="https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v${VERSION}"
SERVICE='otelcol-contrib'
CONF_DIR='/etc/otelcol-contrib'
STATE_DIR='/var/lib/otelcol-contrib'
HELPER_DIR='/usr/local/lib/monishield'
HELPER="${HELPER_DIR}/docker-names.sh"
NAME=''
TOKEN=''
DRY=0
UPGRADE=0

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
say() { printf '==> %s\n' "$*"; }
usage() { sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --name) [ $# -ge 2 ] || die '--name needs a value'; NAME="$2"; shift 2 ;;
    --token) [ $# -ge 2 ] || die '--token needs a value'; TOKEN="$2"; shift 2 ;;
    --url) [ $# -ge 2 ] || die '--url needs a value'; URL="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    --upgrade) UPGRADE=1; shift ;;
    --conf-dir) [ $# -ge 2 ] || die '--conf-dir needs a value'; CONF_DIR="$2"; shift 2 ;;   # where the installed key is (for tests)
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
done

# Docker names its log files by container id. This helper keeps <container name>.log links to them, so the services are named
# after the containers; a timer refreshes the links every 15 seconds and the collector service runs it once before it starts.
install_helper() {
  say "Installing ${HELPER} and its systemd timer"
  install -d -m 0755 "$HELPER_DIR"
  cat >"${HELPER}.new" <<'MONISHIELD_DOCKER_NAMES'
@@DOCKER_NAMES_SH@@
MONISHIELD_DOCKER_NAMES
  chmod 0755 "${HELPER}.new"; mv -f "${HELPER}.new" "$HELPER"
  cat >/etc/systemd/system/monishield-docker-names.service <<EOF
[Unit]
Description=MoniShield: name-based links to the Docker container logs
After=docker.service

[Service]
Type=oneshot
User=root
ExecStart=${HELPER}
RestrictAddressFamilies=AF_UNIX
NoNewPrivileges=yes
PrivateTmp=yes
EOF
  cat >/etc/systemd/system/monishield-docker-names.timer <<'EOF'
[Unit]
Description=MoniShield: refresh the Docker container log links

[Timer]
OnBootSec=5s
OnUnitActiveSec=15s
AccuracySec=1s

[Install]
WantedBy=timers.target
EOF
  chmod 0644 /etc/systemd/system/monishield-docker-names.service /etc/systemd/system/monishield-docker-names.timer
}

# Check what was typed before anything is installed: these values end up in commands and files.
if [ "$UPGRADE" = 1 ]; then
  [ -z "$NAME$TOKEN" ] || die '--upgrade takes no --name and no --token: it uses the key that is installed'
else
  [ -n "$NAME" ] || die '--name is required'
  case "$NAME" in *[!a-z0-9-]*|-*) die '--name may only hold lowercase letters, digits and hyphen' ;; esac
  [ -n "$TOKEN" ] || die '--token is required'
  case "$TOKEN" in mse_*) ;; *) die '--token does not look like an enrollment token (mse_...)' ;; esac
  case "$TOKEN" in *[!A-Za-z0-9_-]*) die '--token holds characters an enrollment token never has' ;; esac
fi
URL="${URL%/}"
case "$URL" in https://*|http://*) ;; *) die '--url must start with https://' ;; esac
case "$URL" in *[!A-Za-z0-9./:_~-]*) die '--url holds characters that are not allowed in an address' ;; esac

if [ "$DRY" = 0 ]; then
  [ "$(id -u)" = 0 ] || die 'run this script as root (for example with sudo)'
fi

# --upgrade: an installed collector keeps its key; it gets the current configuration (and, for Docker, the name helper)
if [ "$UPGRADE" = 1 ]; then
  ENVF="${CONF_DIR}/monishield.env"
  [ -r "$ENVF" ] || die "no collector key is installed (${ENVF} is missing or not readable). Install the collector first: sh install.sh --name <name> --token <token>"
  KEY="$(sed -n 's/^MONISHIELD_COLLECTOR_KEY=//p' "$ENVF" | head -n 1)"
  case "$KEY" in msk_*) ;; *) die "${ENVF} holds no collector key (MONISHIELD_COLLECTOR_KEY=msk_...). Replace the key on the Collectors page first." ;; esac
  case "$KEY" in *[!A-Za-z0-9_-]*) die "the collector key in ${ENVF} has unexpected characters" ;; esac
  say "Upgrading the collector in place: receiver ${URL}, key from ${ENVF}"
  if [ "$DRY" = 1 ]; then
    say "[dry-run] would GET ${URL}/api/collector/config with the installed key as a Bearer token"
    say "[dry-run] would check it with otelcol-contrib validate, then write ${CONF_DIR}/config.yaml (mode 0640)"
    say "[dry-run] for a Docker collector: would install ${HELPER} and the systemd units monishield-docker-names.service and .timer (every 15 s), and run the collector as root with the helper before it starts"
    say "[dry-run] would restart ${SERVICE} and show its status"
    exit 0
  fi
  command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ] || die 'systemd is required (the collector runs as a systemd service)'
  command -v curl >/dev/null 2>&1 || die 'curl is required'
  command -v otelcol-contrib >/dev/null 2>&1 || die 'otelcol-contrib is not installed: install the collector first'
  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK"' EXIT INT TERM
  say 'Fetching the current configuration'
  printf 'header = "Authorization: Bearer %s"\n' "$KEY" | curl -sS --proto '=https,http' -K - -o "${WORK}/config.yaml" -w '%{http_code}' \
    "${URL}/api/collector/config" >"${WORK}/status" || die "could not reach ${URL}"
  [ "$(cat "${WORK}/status")" = 200 ] || die "the server refused the key (HTTP $(cat "${WORK}/status")): it may be revoked or replaced. Replace the key on the Collectors page. ($(head -c 200 "${WORK}/config.yaml"))"
  if grep -qE 'otelcol-contrib/containers/|docker_stats:' "${WORK}/config.yaml"; then PLATFORM=docker; else PLATFORM=linux; fi
  RUN_USER="$(id -un otelcol-contrib 2>/dev/null || echo root)"
  RUN_GROUP="$(id -gn "$RUN_USER" 2>/dev/null || echo root)"
  if [ "$PLATFORM" = docker ]; then RUN_USER=root; RUN_GROUP=root; fi
  say 'Checking the configuration'
  MONISHIELD_COLLECTOR_KEY="$KEY" otelcol-contrib validate --config="${WORK}/config.yaml" || die 'the new configuration did not pass otelcol-contrib validate; nothing was changed'
  say "Writing ${CONF_DIR}/config.yaml"
  install -m 0640 -o root -g "$RUN_GROUP" "${WORK}/config.yaml" "${CONF_DIR}/config.yaml"
  if [ "$PLATFORM" = docker ]; then
    install_helper
    DROPIN_DIR="/etc/systemd/system/${SERVICE}.service.d"
    mkdir -p "$DROPIN_DIR"
    printf '[Unit]\nAfter=docker.service\n\n[Service]\nEnvironmentFile=%s/monishield.env\nUser=root\nGroup=root\nExecStartPre=-%s\n' "$CONF_DIR" "$HELPER" >"${DROPIN_DIR}/monishield.conf"
    chmod 0644 "${DROPIN_DIR}/monishield.conf"
    install -d -m 0750 -o root -g root "$STATE_DIR" "${STATE_DIR}/queue"
  fi
  say "Restarting ${SERVICE}"
  systemctl daemon-reload
  if [ "$PLATFORM" = docker ]; then systemctl enable --now monishield-docker-names.timer >/dev/null 2>&1; fi
  systemctl restart "$SERVICE"
  sleep 3
  systemctl status --no-pager "$SERVICE" || true
  if ! systemctl is-active --quiet "$SERVICE"; then
    journalctl -u "$SERVICE" -n 30 --no-pager || true
    die "${SERVICE} is not running; see the log above"
  fi
  say 'Done. The collector now runs the current configuration.'
  exit 0
fi

case "$(uname -m)" in
  x86_64|amd64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) die "unsupported machine type: $(uname -m) (amd64 and arm64 are supported)" ;;
esac
if command -v dpkg >/dev/null 2>&1; then PKG=deb
elif command -v rpm >/dev/null 2>&1; then PKG=rpm
else die 'neither dpkg nor rpm found: this script supports Debian-like and RPM-based systems'; fi
if [ "$DRY" = 0 ]; then
  command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ] || die 'systemd is required (the collector runs as a systemd service)'
  command -v curl >/dev/null 2>&1 || die 'curl is required'
  command -v sha256sum >/dev/null 2>&1 || die 'sha256sum is required'
fi
ASSET="otelcol-contrib_${VERSION}_linux_${ARCH}.${PKG}"

say "MoniShield collector '${NAME}': otelcol-contrib ${VERSION} (${ARCH}, ${PKG}), receiver ${URL}"
if [ "$DRY" = 1 ]; then
  say "[dry-run] would download ${RELEASE}/${ASSET}"
  say "[dry-run] would download ${RELEASE}/${ASSET}.sha256 and stop if the SHA-256 differs"
  say "[dry-run] would install the package (${PKG})"
  say "[dry-run] would POST the token to ${URL}/api/collector/enroll with X-Requested-With: monishield-collector"
  say "[dry-run] would write ${CONF_DIR}/config.yaml (mode 0640) from the answer"
  say "[dry-run] would write the key to ${CONF_DIR}/monishield.env (mode 0600) and reference it from a systemd drop-in"
  say "[dry-run] for a Docker collector: would install ${HELPER} and the systemd units monishield-docker-names.service and .timer (every 15 s), which keep name-based links to the container logs in ${STATE_DIR}/containers"
  say "[dry-run] would create ${STATE_DIR}/queue, validate the configuration, enable and restart ${SERVICE}, and show its status"
  exit 0
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT INT TERM

say "Downloading ${ASSET}"
curl -fsSL --proto '=https' --tlsv1.2 -o "${WORK}/${ASSET}" "${RELEASE}/${ASSET}" || die "could not download ${RELEASE}/${ASSET}"
curl -fsSL --proto '=https' --tlsv1.2 -o "${WORK}/${ASSET}.sha256" "${RELEASE}/${ASSET}.sha256" || die 'could not download the checksum file'
WANT="$(awk 'NR == 1 { print tolower($1) }' "${WORK}/${ASSET}.sha256")"
case "$WANT" in *[!0-9a-f]*|'') die 'the checksum file does not hold a SHA-256' ;; esac
[ "${#WANT}" = 64 ] || die 'the checksum file does not hold a SHA-256'
HAVE="$(sha256sum "${WORK}/${ASSET}" | awk '{ print $1 }')"
[ "$HAVE" = "$WANT" ] || die "checksum mismatch for ${ASSET}: expected ${WANT}, got ${HAVE}; nothing was installed"
say 'Checksum matches'

say "Installing the ${PKG} package"
if [ "$PKG" = deb ]; then dpkg -i --force-confold "${WORK}/${ASSET}" >/dev/null
else rpm -U --replacepkgs "${WORK}/${ASSET}" >/dev/null; fi
command -v otelcol-contrib >/dev/null 2>&1 || die 'the package did not install otelcol-contrib'

say 'Enrolling this collector'
printf '{"token":"%s"}' "$TOKEN" | curl -sS --proto '=https,http' -o "${WORK}/config.yaml" -D "${WORK}/headers" -w '%{http_code}' \
  -H 'Content-Type: application/json' -H 'X-Requested-With: monishield-collector' --data-binary @- \
  "${URL}/api/collector/enroll?format=install" >"${WORK}/status" || die "could not reach ${URL}"
if [ "$(cat "${WORK}/status")" != 200 ]; then
  die "enrollment was refused (HTTP $(cat "${WORK}/status")): the token is wrong, used or expired. Make a new one on the Collectors page. ($(head -c 300 "${WORK}/config.yaml"))"
fi
header() { awk -v h="$1" 'tolower($1) == tolower(h) ":" { sub(/\r$/, "", $2); print $2; exit }' "${WORK}/headers"; }
KEY="$(header X-Collector-Key)"
PLATFORM="$(header X-Collector-Platform)"
GOT="$(header X-Collector-Name)"
[ "$GOT" = "$NAME" ] || die "the token belongs to the collector '${GOT}', not '${NAME}'. Its key was issued: replace the key on the Collectors page."
case "$PLATFORM" in linux|docker) ;; *) die "this collector is registered for ${PLATFORM}, not for a Linux server. Replace its key on the Collectors page and follow the steps for ${PLATFORM}." ;; esac
case "$KEY" in msk_*) ;; *) die 'the server did not answer with a collector key' ;; esac
case "$KEY" in *[!A-Za-z0-9_-]*) die 'the collector key has unexpected characters' ;; esac

# The service user: the package's own user, except for Docker where the log files belong to root.
RUN_USER="$(id -un otelcol-contrib 2>/dev/null || echo root)"
RUN_GROUP="$(id -gn "$RUN_USER" 2>/dev/null || echo root)"
DROPIN_DIR="/etc/systemd/system/${SERVICE}.service.d"
mkdir -p "$DROPIN_DIR" "$CONF_DIR"
if [ "$PLATFORM" = docker ]; then RUN_USER=root; RUN_GROUP=root; fi

if [ "$PLATFORM" = docker ]; then install_helper; fi

say "Writing ${CONF_DIR}/config.yaml and ${CONF_DIR}/monishield.env"
install -m 0640 -o root -g "$RUN_GROUP" "${WORK}/config.yaml" "${CONF_DIR}/config.yaml"
( umask 077; printf 'MONISHIELD_COLLECTOR_KEY=%s\n' "$KEY" >"${CONF_DIR}/monishield.env" )
chmod 0600 "${CONF_DIR}/monishield.env"; chown root:root "${CONF_DIR}/monishield.env"
{
  if [ "$PLATFORM" = docker ]; then printf '[Unit]\nAfter=docker.service\n\n'; fi   # After= belongs to [Unit], not [Service]
  printf '[Service]\nEnvironmentFile=%s/monishield.env\n' "$CONF_DIR"
  if [ "$PLATFORM" = docker ]; then printf 'User=root\nGroup=root\nExecStartPre=-%s\n' "$HELPER"; fi
} >"${DROPIN_DIR}/monishield.conf"
chmod 0644 "${DROPIN_DIR}/monishield.conf"

install -d -m 0750 -o "$RUN_USER" -g "$RUN_GROUP" "$STATE_DIR" "${STATE_DIR}/queue"
if [ "$PLATFORM" = linux ]; then   # let the service read the system logs
  for g in adm systemd-journal; do
    if getent group "$g" >/dev/null 2>&1 && [ "$RUN_USER" != root ]; then usermod -aG "$g" "$RUN_USER"; fi
  done
fi

say 'Checking the configuration'
MONISHIELD_COLLECTOR_KEY="$KEY" otelcol-contrib validate --config="${CONF_DIR}/config.yaml" || die 'the configuration did not pass otelcol-contrib validate'

say "Starting ${SERVICE}"
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null 2>&1
if [ "$PLATFORM" = docker ]; then systemctl enable --now monishield-docker-names.timer >/dev/null 2>&1; fi
systemctl restart "$SERVICE"
sleep 3
systemctl status --no-pager "$SERVICE" || true
if ! systemctl is-active --quiet "$SERVICE"; then
  journalctl -u "$SERVICE" -n 30 --no-pager || true
  die "${SERVICE} is not running; see the log above"
fi
say 'Done. The collector sends its first lines within a minute; check the Collectors page.'
