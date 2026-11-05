// Collectors page helpers (docs/12-collector.md, step 6): the rules the server checks (monishield/domain/collectors.py and
// collector_config.py) so a mistake shows while typing, the options a platform offers, and the commands an admin runs.
// Pure: no DOM, no stores. The server checks everything again.

export const PLATFORMS = ['linux', 'windows', 'docker', 'kubernetes'];
export const CHANNELS = ['application', 'system', 'security'];
export const NAME = /^[a-z0-9][a-z0-9-]{0,62}$/;
export const SERVICE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,252}$/;
export const UNIT = /^[A-Za-z0-9:_.@\\-]{1,200}$/;
export const MAX_FILES = 30, MAX_UNITS = 30, MAX_PATH = 500;
export const STATUSES = ['online', 'late', 'offline', 'waiting', 'revoked'];

/** What a new collector sends when nothing is changed (same as the server's defaults). */
export function defaults(platform) {
  if (platform === 'linux') return { files: [], journald: true, units: [] };
  if (platform === 'docker') return { files: [], journald: false, units: [], containers: true };
  if (platform === 'windows') return { files: [], channels: ['application', 'system'] };
  return {};
}

/** A copy of options that can be edited without touching the original; missing parts take the platform's empty form. */
export function editable(platform, options) {
  const o = options ? JSON.parse(JSON.stringify(options)) : defaults(platform);
  if (platform === 'kubernetes') return {};
  o.files = o.files || [];
  if (platform === 'windows') o.channels = o.channels || [];
  else { o.journald = !!o.journald; o.units = o.units || []; if (platform === 'docker') o.containers = !!o.containers; }
  return o;
}

export function checkName(name) {
  if (!name) return 'empty';
  return NAME.test(name) ? '' : 'invalid';
}

/** -> '' or an error key for one file path of a platform. */
export function checkPath(path, platform) {
  const p = String(path ?? '').trim();
  if (!p) return 'empty';
  if (p.length > MAX_PATH) return 'long';
  if (/[\u0000-\u001f\u007f"'`]/.test(p) || p.includes('${')) return 'chars';
  if (platform === 'windows' ? !/^([A-Za-z]:[\\/]|\\\\)/.test(p) : !p.startsWith('/')) return platform === 'windows' ? 'windows' : 'absolute';
  if (/[\\/]$/.test(p)) return 'dir';
  return '';
}

export const checkService = (s) => (!String(s ?? '') ? 'empty' : SERVICE.test(s) ? '' : 'invalid');

/** "ssh.service, cron.service" -> ['ssh.service', 'cron.service'] (spaces, commas and new lines separate). */
export const parseUnits = (text) => [...new Set(String(text || '').split(/[\s,]+/).filter(Boolean))];

/**
 * Errors of an options object: {files: [{path, service}], units, channels, none}; empty object = fine.
 * Values are error keys (collector.err.*), not texts.
 */
export function checkOptions(platform, o) {
  const err = {};
  if (platform === 'kubernetes') return err;
  const files = (o.files || []).map((f) => ({ path: checkPath(f.path, platform), service: checkService(f.service) }));
  if (files.some((f) => f.path || f.service)) err.files = files;
  if ((o.files || []).length > MAX_FILES) err.toomany = 'too_many_files';
  if (platform !== 'windows') {
    if (o.units?.length > MAX_UNITS) err.units = 'too_many_units';
    else if ((o.units || []).some((u) => !UNIT.test(u))) err.units = 'invalid_unit';
  }
  const any = platform === 'windows' ? o.channels?.length : o.journald || (platform === 'docker' && o.containers);
  if (!any && !(o.files || []).length) err.none = 'no_inputs';
  return err;
}

/** The body of POST /api/admin/collectors (options part): only what the platform has, trimmed. */
export function payload(platform, o) {
  if (platform === 'kubernetes') return {};
  const files = (o.files || []).map((f) => ({ path: f.path.trim(), service: f.service.trim() }));
  if (platform === 'windows') return { files, channels: CHANNELS.filter((c) => o.channels.includes(c)) };
  const out = { files, journald: !!o.journald, units: o.journald ? o.units : [] };
  if (platform === 'docker') out.containers = !!o.containers;
  return out;
}

/** Short labels of what a collector sends, as [{key, n?}] for the chips; the page turns each into text. */
export function sends(platform, o) {
  if (platform === 'kubernetes') return [{ key: 'pods' }];
  const out = [];
  if (platform === 'windows') for (const c of o?.channels || []) out.push({ key: c });
  else {
    if (o?.journald) out.push({ key: 'journald' });
    if (platform === 'docker' && o?.containers) out.push({ key: 'containers' });
  }
  if (o?.files?.length) out.push({ key: 'files', n: o.files.length });
  return out;
}

// Commands (the page shows them with copy buttons). `base` is the receiver address without a trailing slash.
const q = (s) => `'${String(s).replace(/'/g, `'\\''`)}'`;   // POSIX single quotes

/** Steps to install: [{id, lines: [..]}]; each step is one copy block. */
export function installSteps(platform, base, name, token) {
  if (platform === 'windows') return [
    { id: 'download', lines: [`Invoke-WebRequest -UseBasicParsing -OutFile install.ps1 ${base}/collector/install.ps1`] },
    { id: 'run', lines: [`powershell -ExecutionPolicy Bypass -File .\\install.ps1 -Name ${name} -Token ${token}`] },
  ];
  if (platform === 'kubernetes') return [
    { id: 'repo', lines: ['helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts', 'helm repo update'] },
    { id: 'enroll', lines: [
      `KEY=$(curl -fsS -D - -o /dev/null -X POST -H 'Content-Type: application/json' -H 'X-Requested-With: monishield-collector' \\`,
      `  -d '{"token":"${token}"}' '${base}/api/collector/enroll?format=install' \\`,
      `  | awk 'tolower($1)=="x-collector-key:" {print $2}' | tr -d '\\r')`] },
    { id: 'secret', lines: ['kubectl create namespace monishield', 'kubectl -n monishield create secret generic monishield-collector --from-literal=key="$KEY"'] },
    { id: 'helm', lines: ['helm upgrade --install monishield-collector open-telemetry/opentelemetry-collector -n monishield -f values.yaml'] },
  ];
  return [
    { id: 'download', lines: [`curl -fsSLo install.sh ${base}/collector/install.sh`] },
    { id: 'run', lines: [`sudo sh install.sh --name ${name} --token ${token}`] },
  ];
}

/** Where the new key goes after "Replace key": [{id, lines}] and the file or object it belongs to. */
export function keySteps(platform, key) {
  if (platform === 'windows') return [{ id: 'set', lines: [
    `$reg = 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\otelcol-contrib'`,
    `New-ItemProperty -Path $reg -Name Environment -PropertyType MultiString -Value @('MONISHIELD_COLLECTOR_KEY=${key}') -Force`,
    'Restart-Service otelcol-contrib'] }];
  if (platform === 'kubernetes') return [{ id: 'set', lines: [
    `kubectl -n monishield create secret generic monishield-collector --from-literal=key=${q(key)} --dry-run=client -o yaml | kubectl apply -f -`,
    'kubectl -n monishield rollout restart daemonset/monishield-collector'] }];
  return [{ id: 'set', lines: [
    `echo 'MONISHIELD_COLLECTOR_KEY=${key}' | sudo tee /etc/otelcol-contrib/monishield.env > /dev/null`,
    'sudo chmod 600 /etc/otelcol-contrib/monishield.env',
    'sudo systemctl restart otelcol-contrib'] }];
}

/** After "Change inputs": how the collector gets its new configuration. Kubernetes: download values.yaml, then helm. */
export function updateSteps(platform, base) {
  if (platform === 'windows') return [{ id: 'update', lines: [
    `$key = ((Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\otelcol-contrib').Environment | Where-Object { $_ -like 'MONISHIELD_COLLECTOR_KEY=*' }).Split('=', 2)[1]`,
    `Invoke-WebRequest -UseBasicParsing -Headers @{ Authorization = "Bearer $key" } -Uri ${base}/api/collector/config -OutFile "$env:ProgramFiles\\OpenTelemetry Collector\\config.yaml"`,
    'Restart-Service otelcol-contrib'] }];
  if (platform === 'kubernetes') return [{ id: 'update', lines: ['helm upgrade --install monishield-collector open-telemetry/opentelemetry-collector -n monishield -f values.yaml'] }];
  return [{ id: 'update', lines: [
    `sudo sh -c '. /etc/otelcol-contrib/monishield.env && curl -fsS -H "Authorization: Bearer $MONISHIELD_COLLECTOR_KEY" ${base}/api/collector/config -o /etc/otelcol-contrib/config.yaml && systemctl restart otelcol-contrib'`] }];
}

/** Seconds -> the unit and number for "5 min ago": [value, 'second' | 'minute' | 'hour' | 'day']. */
export function ago(seconds) {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return [s, 'second'];
  if (s < 3600) return [Math.floor(s / 60), 'minute'];
  if (s < 86400) return [Math.floor(s / 3600), 'hour'];
  return [Math.floor(s / 86400), 'day'];
}

/** Count collectors by status for the row of tiles. */
export function counts(rows) {
  const c = { online: 0, late: 0, offline: 0, waiting: 0, revoked: 0 };
  for (const r of rows) if (r.status in c) c[r.status]++;
  return c;
}
