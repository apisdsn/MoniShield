# Old system inventory — SIMPEL4 log dashboard

A "nothing gets lost" checklist for the migration. Sources: `build_dashboard.py` (583 lines) and
`dashboard_template.html` (1,913 lines), read in full, plus one build on 2026-10-06
against 11 log folders (2026-09-26 … 2026-10-06).

This document only records what exists now. There are no design proposals; things that need deciding
are collected in [§9 Open questions](#9-open-questions).

Notation: `S.<field>` = `D.days[<folder>][<service>].<field>`, i.e. the output of `summarize()` embedded in the
HTML. `s['x']` = raw statistic in Python before summarizing. Index `r[i]` = column position in an array row.

Contents: [1 Overview](#1-overview-of-the-old-system) · [2 Tabs](#2-tabs-and-service-pages) · [3 Log formats](#3-parsed-log-formats) ·
[4 Derived logic](#4-derived-logic) · [5 Limits](#5-intentional-limits-and-simplifications) ·
[6 External sources](#6-external-data-sources-licenses-attribution) · [7 Reference figures](#7-reference-figures) ·
[8 Findings](#8-findings-behavior-not-evident-from-the-ui) · [9 Questions](#9-open-questions)

---

## 1. Overview of the old system

### 1.1 Build flow

1. `build()` looks for `*/**/*.log`, plus `*.log.gz` **only when** its `.log` counterpart does not exist.
2. From the relative path: `date` = top-level folder (must match `\d{4}-\d\d-\d\d`, at least 3 path components),
   `service` = the file's parent folder, `ns` = the component in between (or `-`), `pod` = file name without the prefix
   `log_<service>_` and the suffix `_YYYY-…`.
3. Each line is passed to `parse(service, line, s)`; `s` = one statistics bag per (date, service),
   combining all pods. Files are read with `errors='replace'`.
4. `correlate()` joins simpel-loop events with nginx requests (see §4.4).
5. `summarize()` truncates each statistic to top-N (§5) → `D.days`.
6. IP owner (`ipinfo`), location (`geo`), land (`land`), region labels (`labels`) are computed offline (§4.6, §6).
7. The JSON replaces `/*DATA*/ null` in the template (must occur exactly once; `</` is escaped) → `dashboard.html`.

Command-line modes: no arguments = build once; `--watch` = poll every 5 seconds on size+mtime of all
`*.log*` and the template, then rebuild **all** days; `--selftest` = `demo()` (tests `geo_scan`,
`kab_name`, and IP flow with retries).

### 1.2 Shape of the embedded data (`D`)

| Key | Content | Current size |
|---|---|--:|
| `days` | `{folder: {service: summary}}`, 45 fields per service (§1.3) | 1,081 KB |
| `land` | one SVG path string of the world's land | 755 KB |
| `ipinfo` | `{ip: {asn, cc, org}}` for displayed IPs | 148 KB (1,734 IPs) |
| `geo` | `{ip: [city, province, country, lat, lon]}` for flow IPs + server | 106 KB (1,676 IPs) |
| `files` | `[{date, ns, svc, pod, size, lines, err, warn}]` | 28 KB (195 files) |
| `labels` | `{c: country, p: province, k: regency/city}` | 27 KB (177 / 38 / 514) |
| `hosts` | upstream → production base URL (constant `HOSTS`) | 6 entries |
| `server` | `[ip, city, province, country, lat, lon]` map destination point | 1 |

`dashboard.html` = 2,267,447 bytes. Largest fields in `days`: `flow` 437 KB, `trace` 195 KB, `msgs` 86 KB,
`ep` 73 KB, `uperr` 72 KB, `atk` 47 KB.

### 1.3 Summary fields per service

| Field | Shape | Filled by |
|---|---|---|
| `lines`, `err`, `warn` | number | all |
| `hour` | `[[WIB hour 'YYYY-MM-DD HH', n]]` | nginx, FE, Spring; simpel-loop only via correlation |
| `herr` | `{hour: n}` | nginx & FE (5xx), Spring (ERROR), simpel-loop (correlated failed events) |
| `status` | `[[code, n]]` | nginx, FE, simpel-loop |
| `paths` | top 20 `[key, n]` | nginx/FE/simpel-loop: `METHOD path_key`; coredns: domain |
| `perr` | top 20 `['<status> <key>', n]` | nginx, FE (4xx/5xx), simpel-loop (failed events only) |
| `ips` | top 15 `[ip, n]` | nginx, FE, simpel-loop |
| `up`, `ua` | top 12 | nginx |
| `extra` | `[[level/type, n]]` | simpel-loop (`OM-<level>`), Spring (level + `Hibernate SQL`) |
| `dur` | top 15 averages `{k,n,avg,max}` | nginx, simpel-loop — **not used by the template** |
| `ep` | top 150 `[key, requests, 4xx, 5xx, p50, p95, p99, max]` (seconds) | nginx, simpel-loop |
| `slow` | top 15 `[ms, key, status]` | simpel-loop |
| `msgs` | top 40 `['LEVEL \| normalized message', n, original line]` | all |
| `atk`, `atk_ip`, `atk_h`, `atk_cat`, `ip4` | §4.1 | nginx |
| `login`, `login_h`, `acct`, `login_ok`, `users_ok`, `login_okh` | §4.2 | Spring (in practice appsmanager) |
| `incidents`, `up5` | §4.3 | nginx |
| `corr`, `trace` | §4.4 | simpel-loop |
| `flow`, `pod`, `retry`, `uperr` | §4.5 | nginx |
| `c401` | top 30 `[ip, key, n, peak/minute, first, last]` | nginx |
| `uk`, `ukf`, `uk_t` | Uptime-Kuma per hour, failures per hour, top 5 targets | nginx |
| `biz`, `mail`, `act` | §4.8 | simpel-loop |
| `restart`, `jwt`, `rep` | §4.9 | Spring |

---

## 2. Tabs and service pages

Tab, KPI, chart and table names below are the old dashboard's English labels (from its `EN` dictionary); the
dashboard itself shows them in Indonesian by default.

### 2.0 Shell that applies to all tabs

- **Sidebar**: logo "S4 SIMPEL4 Log"; group *Analysis* (9 tabs, fixed order: Overview, IP Map, Trends, Security,
  Root Causes, Availability, Pods, Business, Request Tracing); group *Services* = the services present in the selected
  folder, in file order. Badges: Security tab `N IP` (`atk_ip.length`), each service = `S.err`.
  Footer "All times in WIB (UTC+7)". On screens ≤ 900 px the sidebar becomes a scrollable top bar.
- **Header**: tab title; subtitle `Log folder <date> · N services · All times in WIB (UTC+7)`;
  folder picker (default = latest folder); ID/EN language button; ☀/☾ theme button.
- **Remembered state**: tab in `location.hash`; language and theme in `localStorage` (`lang`, `theme`; defaults
  `id` and `dark`). Map module choice, map view, and zoom box are kept in memory only.
- **Two languages**: an `EN` dictionary (±240 entries, key = lowercase Indonesian text, exact match), 10 regex `RULES`
  for text containing numbers/dates, `L(id, en)` for long sentences; `translateDom()` sweeps all text nodes
  after rendering; some dictionary keys are text coming from Python (account flags, business metrics,
  JWT age groups, attack categories). Chart labels and legends go through `tr()`. Country names via `Intl.DisplayNames`.
- **Two themes**: CSS variables in `:root` and `:root[data-theme="light"]`; chart colors are read from the variables at
  render time, so switching theme = re-render.
- **Format**: numbers `toLocaleString` (`id-ID` / `en-US`); times `28 Sep 2026 06.03 WIB` (EN uses `:`), hours
  `28 Sep 06.00`; durations `850 ms` / `2,35 dtk` / `1 mnt 52 dtk` (ID; EN `s` / `min`); time ranges are merged when the date is the same.
  Interface text is *Capitalize Each Word* via CSS; data (URLs, IPs, messages, UAs) is not.
- **Components**: KPI (label, value, color, delta line); chart cards 280 px tall; tables with sticky headers,
  max height 440–600 px, right-aligned numeric columns; the first column of a simple table gets a proportion bar when
  the second column is titled "Count"; status codes colored (2xx green, 4xx yellow, 5xx red); severity tags.
- **IP owner note** (`ipTag`): under every IP that has `ipinfo` the text `AS<asn> · <cc> · <org>` is shown,
  plus an "Ombudsman network" tag when `org` contains `OMBUDSMAN`. IP chart tooltips also show `org`.
- **Text filter**: an input in the card title hides table rows that do not contain the text (substring,
  case-insensitive, on the browser side over the rows already truncated to top-N).
- **Charts**: Chart.js 4.4.1; lines = gradient areas; bars with rounded corners; donuts with percentages and the label of
  the largest slice in the middle; horizontal top-N bars truncate labels at 48 characters (full text in the tooltip).
- **Delta vs previous folder** (`dlt`): only for *comparable* services (log lines of the previous folder ≥ 50 % of
  this folder, and this folder not empty). Output: `▲/▼ N% Vs <tgl>` (red when worsening),
  `≈ Sama Dengan <tgl>` when |change| < 0.5 %, `Baru (<tgl>: 0)`, or
  `Log <tgl> Tidak Lengkap, Tidak Dibandingkan` (ID strings; EN: `▲/▼ N% vs <date>`, `≈ Same as <date>`,
  `New (<date>: 0)`, `<date> log incomplete, not compared`).

### 2.1 Overview (per folder)

| Element | Content | Source |
|---|---|---|
| Text | Log period: first hour – last hour | min/max `S.hour` of all services |
| KPI | Total log lines (+delta, up = good) | Σ `S.lines` |
| KPI | Error (+delta) | Σ `S.err` |
| KPI | Warning / app 4xx (+delta) | Σ `S.warn` |
| KPI | HTTP requests, 4xx rate (1 decimal), 5xx rate (2 decimals) — only when nginx has lines | `nginx.status` |
| KPI | Services, Log files, Empty files (size 0 bytes) | `D.days`, `D.files` |
| Chart | Errors per hour per service (stacked bars, wide) — only services that have `herr` | `S.herr` |
| Chart | Errors & warnings per service; Log lines per service (horizontal bars) | `S.err`, `S.warn`, `S.lines` |
| Table | Service summary: Service, Lines, Error, Warn, Pods (= number of files) | `S.*`, `D.files` |
| Table | Log files: Service / pod, Lines, Size (MB) | `D.files` |
| Table | Top errors across services (top 25, wide, with bars) | combined `S.msgs` of all services |
| Section | "System-wide HTTP traffic" + source note, then **all cards of the nginx service page** except the map and the message card (§2.10) | `nginx.*` |

### 2.2 IP Map (per folder)

| Element | Content | Source |
|---|---|---|
| Filter | Module picker: "All modules" + each upstream without its port suffix | `nginx.flow[*][1]` |
| KPI | Unique source IPs; Source locations (unique lat,lon pairs); Source countries; Destination modules; Unique destination IPs (pods); Total requests | `nginx.flow`, `D.geo` |
| Map | Land; curved arcs from each location to the server (width 1–4 by requests); a dot per location (IPs merged per lat,lon) with tooltip `city, province, country · N source IPs · N requests → module (n)`; the 6 largest locations get a label; server dot "Server SIMPEL4 + IP" | `D.land`, `nginx.flow`, `D.geo`, `D.server` |
| Map | Region labels: countries always (rank > 2 hidden when the view width > 100°); provinces at ≤ 100°; regencies/cities at ≤ 6° | `D.labels` |
| Interaction | Presets Indonesia `[94,-8,48,20]` / World `[-168,-80,336,140]`; +/− buttons; mouse wheel (zoom toward the cursor); drag to pan; width 1°–360°, ratio 2.4 | — |
| Legend | Source IP location; Destination server; `N requests from outside Indonesia · M requests from internal IPs / without location (not drawn)` | `D.geo` |
| Table | Source IP → destination IP flows: Source IP (+owner), Location, Destination module, Destination IP (pod) max. 3 with ×count, Requests; filterable | `nginx.flow` |
| Note | Location = city-level estimate; **DB-IP and GeoNames attribution**; destination IP = pod IP so it is drawn at the server location; "At most 3,000 top flows per day" | — |
| Empty | "The map needs ingress nginx logs; this folder does not have them." The map card also disappears when `D.land` is empty. | — |

Location in the table: place from `geo`; "Internal network" when `ipinfo.cc == '-'`; otherwise "Unknown".

### 2.3 Trends (all folders, independent of the folder picker)

| Element | Content | Source |
|---|---|---|
| Note | Daily data is not always complete | — |
| Chart | Errors per day per service; Warnings per day per service; Log lines per day per service (stacked) | `S.err`, `S.warn`, `S.lines` |
| Chart | HTTP requests per day (ingress nginx): Total, 4xx, 5xx | `nginx.status` |
| Chart | Security per day: Attack requests, Wrong passwords, Password resets | Σ `nginx.atk_cat`; Σ `appsmanager.login[*][1]` and `[2]` |
| Chart | Business activity per day: Reports created, Report registrations, Files uploaded, Emails sent, OTPs requested | `simpel-loop.biz` |
| Table | Errors per service & change vs previous day (▲/▼ % when yesterday's errors > 0 and yesterday's lines ≥ 50 % of today) | `S.err`, `S.lines` |
| Table | Data completeness: line count; "Empty" when 0; "None" when the service is not in the folder | `S.lines` |

### 2.4 Security (per folder)

| Element | Content | Source |
|---|---|---|
| KPI | Suspected attack requests | Σ `nginx.atk_cat` |
| KPI | Unique source IPs | `nginx.atk_ip.length` |
| KPI | Critical attacks (SQLi/XSS/LFI/RCE) | Σ hits of `nginx.atk` rows with severity 3 |
| KPI | Attack endpoints with 2xx response | number of `atk` rows with severity ≥ 2 whose status contains 2xx |
| KPI | IPs with failed logins | `appsmanager.login.length` |
| KPI | Accounts succeeding after ≥3 failures; Success from a different IP | `appsmanager.acct[*][6]` |
| KPI | Password resets (3× failed) | Σ `login[*][2]` |
| Warning | "Key findings": up to 9 automatic sentences (below) | `atk`, `atk_ip`, `login`, `acct`, `ipinfo` |
| Chart | Requests per attack category (color by severity); Suspected attacks timeline per hour | `atk_cat`, `atk_h` |
| Chart | Top 10 attack source IPs; Attack sources by network owner (ASN), top 10 | `atk_ip`, `ipinfo.org` |
| Chart | Wrong passwords per hour; Top 10 IPs with wrong passwords | `login_h`, `login` |
| Table | Endpoints with suspected attacks: Category, Full URL (upstream base URL + decoded path, + UA), Hits, IP (top IP `+N` others, owner), Status (`code×n`, "2xx – verify" marker), Response size (max. 5 values), Target upstream, Time; sorted by severity then hits; filterable | `atk`, `D.hosts` |
| Table | Attack source IPs: IP, Hits, Category (+count), Status, Most frequent User-Agent, Time; filterable | `atk_ip` |
| Table | Account analysis: Account, Failed, Resets, Success, Failed IPs, Success IPs, Flags (+up to 3 occurrences), Time; filterable | `acct` |
| Table | Failed logins / brute force: IP (+"Multi-account" tag when ≥ 3 different accounts), Wrong passwords, Resets, Successful logins, Accounts tried, Time; filterable | `login` |
| Table | IPs with most 4xx responses (nginx): IP, 4xx count, User-Agent | `ip4` |
| Note | Without nginx: "per-URL attack detection is not available". Page footer: signature-based detection, POST bodies are not inspected, 2xx is usually the SPA fallback | — |

Severity: 3 = Log4Shell / RCE, SQL Injection, Path Traversal / LFI, XSS; 2 = Sensitive file probe,
CMS / WordPress scan, PHP / CGI probe; 1 = Automated tool/scanner UA.

"Key findings" rules:

1. A Log4Shell / RCE category exists → count, IPs, upstream, recommend log4j-core ≥ 2.17.
2. For each of SQL Injection, XSS, Path Traversal / LFI → count, IPs, status.
3. A row with severity ≥ 2 whose upstream contains `rancher` exists → "Rancher panel is reachable from the internet".
4. An attack endpoint with a 2xx response exists → ask to verify the response size.
5. The attacker IP owner (severity ≥ 2) matches `CLOUD|OCEAN|AMAZON|AWS|AZURE|MICROSOFT|HETZNER|OVH|LINODE|VULTR|ALIBABA|TENCENT|HOSTING|DATACENTER`.
6. A failed-login IP belongs to the Ombudsman network → probably office NAT.
7. An IP tries ≥ 3 different accounts (the part before `@`) → indication of credential stuffing.
8. An account flagged "Success from a different IP" → verify with the account owner.
9. Automatic password resets exist → their count.

In the Account analysis table, the flag "Success from a different IP" changes to "… (same ISP)" when all success IPs
have the same ASN as one of the failed IPs.

### 2.5 Root Causes (per folder)

| Element | Content | Source |
|---|---|---|
| Warning | "Root cause summary", up to 5 items: repeated 401s (top client, peak/minute); expired JWT tokens (total + % > 1 hour); PDF report failed because the template is null; DNS timeouts (the text names the upstream DNS `10.88.1.100`, hard-coded); nginx → pod connection errors (most frequent type). Empty → "No root cause pattern…" | `nginx.c401`, `*.jwt`, `report.rep`, `coredns.paths`, `nginx.uperr` |
| Chart | Clients with repeated 401 (IP + endpoint), top 10 | `c401` |
| Chart | JWT age when rejected: 5 age groups, stacked per service (appsmanager, referensi, report) | `jwt` |
| Chart | PDF report generation per template (success vs failed), top 12 | `rep` |
| Chart | Nginx → pod connection errors by type | `uperr[*][1]` |
| Table | Clients with repeated 401: IP, Endpoint, 401 count, Peak / minute, Time; filterable | `c401` |
| Table | PDF report generation status per template: Template, Success, Failed (template null) | `rep` |
| Table | DNS timeouts per domain: Domain, Count, Impact | `coredns.paths` |

DNS impact: `backup|s3.` → "Backups to S3 may fail"; `pg-|postgres|.local` → "Database / internal service
connection"; `rancher|longhorn` → "Rancher / Longhorn update check"; otherwise → "External domain resolution".

### 2.6 Availability (per folder; needs nginx)

| Element | Content | Source |
|---|---|---|
| KPI | Availability (non-5xx), 3 decimals | (Σ `status` − Σ `up5`) / Σ `status` |
| KPI | Total 5xx responses; 5xx incidents | Σ `up5`; `incidents.length` |
| KPI | Retries to another pod; Pod connection errors | Σ `retry[*][3]`; `uperr.length` |
| KPI | Uptime-Kuma checks; Failed uptime checks | Σ `uk`; Σ `ukf` |
| Chart | 5xx responses per hour (wide); 5xx responses per upstream; Uptime-Kuma health checks per hour (succeeded/failed) | `herr`, `up5`, `uk`, `ukf` |
| Table | Availability per upstream: Upstream, Requests, 5xx, Availability | `up`, `up5` |
| Table | 5xx incident list: Start – end, Duration (minutes, difference + 1), 5xx count, Upstream ×n, Status ×n | `incidents` |
| Table | Nginx → pod connection errors: Time, Type, Pod (IP), Request; filterable | `uperr` |
| Table | Uptime-Kuma health check targets: Target (`METHOD path → upstream`), Checks | `uk_t` |
| Empty | "Availability analysis uses ingress nginx logs…" | — |

### 2.7 Pods (per folder)

| Element | Content | Source |
|---|---|---|
| KPI | Pods (log files); Pods without logs (0 lines) | `D.files` |
| KPI | Backend pods seen in nginx; Pods with 502 retries | `nginx.pod.length`; unique upstream+pod combinations in `nginx.retry` |
| KPI | App restarts / starts | Σ `S.restart` of all services |
| Note | Pod names come from file names; nginx only records the pod IP, there is no IP → pod name mapping | — |
| Chart | Errors per pod (top 15 files); Request distribution per pod (IP) from nginx (top 15) | `D.files[*].err`, `nginx.pod` |
| Table | Health per pod: Service / pod, Lines, Error, Warning, Size, Status (Has logs / No logs); filterable | `D.files` |
| Table | Traffic distribution per backend pod: Upstream, Pod (IP), Requests, Share within upstream, 5xx, Retries (this pod failed) | `nginx.pod`, `nginx.retry` |
| Table | App restarts / starts (Spring Boot): Time, Pod, Application, Startup time | `S.restart` |

### 2.8 Business (per folder)

| Element | Content | Source |
|---|---|---|
| KPI (+delta, up = good) | Reports created, Report registrations, OTPs requested, OTPs verified, Files uploaded, Emails sent | `simpel-loop.biz` |
| KPI | Uploads rejected = too large + file type | `biz` |
| KPI | PDF reports generated, PDF reports failed | Σ `report.rep[*][1]`, `[2]` |
| KPI | Successful logins, Unique users logged in | `appsmanager.login_ok`, `users_ok` |
| Note | Counted from 2xx events; only pods whose logs exist | — |
| Chart | Public service activity summary (all `biz` keys) | `biz` |
| Chart | Notification emails by type; Top report process activities (top 12) | `mail`, `act` |
| Chart | Successful logins per hour; PDF reports per template (top 12 by total) | `login_okh`, `rep` |
| Table | Report process activities (Endpoint, Count); PDF reports per template (Template, Success, Failed) | `act`, `rep` |

"OTPs failed", "Attachments added", and "Emails failed" only appear in the summary chart, not as KPIs.

### 2.9 Request Tracing (per folder; needs correlated simpel-loop)

| Element | Content | Source |
|---|---|---|
| KPI | Simpel-loop requestIds; Matched with nginx; Match rate | `corr = [matched, total]` |
| KPI | Traced failed requests; Unique IPs (failed) | `trace` rows with status 4xx/5xx |
| KPI | Slow requests ≥ 5 s | Σ `trace` rows with status 2xx |
| Note | Explanation of `requestId` + percentage of unmatched events | `corr` |
| Chart | Top 10 IPs with failed requests; Failed requests per error type (`status + error`) | `trace` |
| Table | Failed / slow request trace: IP, Status, Error, Full URL (truncated to 200 characters, UA below it), Count, Max duration, Time; filterable | `trace`, `D.hosts` |
| Empty | "Tracing needs om-be-simpel-loop and ingress nginx logs covering the same time range…" | — |

### 2.10 Service page (per service × folder)

One function for all services; cards with empty data are not rendered. Order:

| # | Element | Source | nginx | FE | simpel-loop | Spring ×3 | coredns |
|--:|---|---|:-:|:-:|:-:|:-:|:-:|
| – | KPI: Log lines, Error, Warning | `lines`, `err`, `warn` | ✓ | ✓ | ✓ | ✓ | ✓ |
| – | KPI: HTTP requests, 4xx rate, 5xx rate | `status` | ✓ | ✓ | ✓ | | |
| – | KPI: first 4 entries of the level distribution | `extra` | | | ✓ | ✓ | |
| 1 | Map + flow table for this module (nginx: all flows) | `nginx.flow` | ✓ | ✓ | ✓ | ✓ | |
| 2 | Chart Activity per hour: Total & Error (simpel-loop: title extended with "from X % of requests traced in nginx") | `hour`, `herr`, `corr` | ✓ | ✓ | ✓* | ✓ | |
| 3 | Chart HTTP status codes (logarithmic axis) | `status` | ✓ | ✓ | ✓ | | |
| 4 | Donut chart Traffic per upstream service | `up` | ✓ | | | | |
| 5 | Donut chart Log level / type distribution | `extra` | | | ✓ | ✓ | |
| 6 | Chart Top 10 endpoints (coredns: Top 10 domains failing to resolve) | `paths` | ✓ | ✓ | ✓ | | ✓ |
| 7 | Chart Top 10 endpoints with 4xx/5xx | `perr` | ✓ | ✓ | ✓ | | |
| 8 | Chart Top 10 client IPs | `ips` | ✓ | ✓ | ✓ | | |
| 9 | Chart Top 10 error / warning messages | `msgs` | ✓ | ✓ | ✓ | ✓ | ✓ |
| 10 | Table Top endpoints (coredns: Domains failing to resolve) | `paths` | ✓ | ✓ | ✓ | | ✓ |
| 11 | Table Endpoints with 4xx/5xx | `perr` | ✓ | ✓ | ✓ | | |
| 12 | Chart P95 response time – 10 slowest endpoints | `ep` | ✓ | | ✓ | | |
| 13 | Chart Highest error rate (min. 20 requests), top 10 | `ep` | ✓ | | ✓ | | |
| 14 | Table Endpoint performance (top 25 by P95): Endpoint, Requests, P50, P95, P99, Max, Error rate; P95 ≥ 1 s yellow, P99 ≥ 5 s red | `ep` | ✓ | | ✓ | | |
| 15 | Table Endpoints with the highest error rate (top 20): Endpoint, Requests, 4xx, 5xx, Error rate | `ep` | ✓ | | ✓ | | |
| 16 | Table Slow requests (≥ 1 second) | `slow` | | | ✓ | | |
| 17 | Table Top client IPs (+owner) | `ips` | ✓ | ✓ | ✓ | | |
| 18 | Table Top user agents | `ua` | ✓ | | | | |
| 19 | Table Error / warning messages (grouped): Level, Message (click → original log line, UTC time), Count; filterable | `msgs` | ✓ | ✓ | ✓ | ✓ | ✓ |

\* only when there is correlation with nginx. When `lines == 0`, the KPIs are replaced by the text "No logs for this
service on this date (empty file)."

---

## 3. Parsed log formats

The service is determined by the **parent folder name**; unknown folders fall through to the Spring Boot parser.
All log timestamps are UTC; `wib()` adds 7 hours and truncates to the minute. The examples below are original
lines; only the account names in the login examples are masked.

### 3.1 Ingress nginx — access log (`nginx-ingress-controller`)

```
(\S+) - \S+ \[(\d+)/(\w+)/(\d+):(\d+:\d+):\d+ [^\]]+\] "(\S+) (\S+)[^"]*" (\d{3}) (\d+) "[^"]*" "([^"]*)" \d+ ([\d.]+) \[([^\]]*)\]
```

Fields: client IP, day, month, year, `HH:MM`, method, path+query, status, response size, User-Agent,
`request_time` (seconds), upstream name. The prefix `ombudsman-ombudsman-` is stripped from the upstream; empty → `-`.
Referer, request length, and seconds are not captured.

Line tail, matched separately: `\] \[[^\]]*\] (.+) ([0-9a-f]{32})$` → the block
`upstream_addr length time status` (each part can hold a list `a, b` when there was a retry) and the request id.

```
103.160.147.100 - - [27/Sep/2026:17:02:58 +0000] "GET / HTTP/1.1" 200 6599 "-" "Uptime-Kuma/2.0.2" 355 0.001 [ombudsman-ombudsman-om-fe-inhouse-3000] [] 10.42.233.139:3000 6599 0.004 200 bbc49c2ed69b931599dd60d93314128c
```

Without an upstream (rejected at the ingress): `… 503 592 "-" "Mozilla/5.0 …" 313 0.000 [ombudsman-minio-web] [] - - - - ed48a8f22c074106a1eea58e5c038af9`.

Computed from each line: `hour`, `status`, `ips`, `up`, `ua` (90 characters), `paths`, `dur` (except
status 101), 4xx/5xx per endpoint, `err`+`herr`+`perr` for 5xx, `perr` for 4xx, `ip4`, `c401`,
Uptime-Kuma (UA contains `Uptime-Kuma`; failed = status not 2xx/3xx), attacks (§4.1), incidents (§4.3),
flow/pod/retry (§4.5), and the request id table (§4.4).

### 3.2 Ingress nginx — error log

```
\d{4}/\d\d/\d\d \d\d:\d\d:\d\d \[(\w+)\] \d+#\d+: \*\d+ (.*?)(?:, client:|$)
```

Fields: level, message up to `, client:`. `error` and `crit` → `err`; other levels → `warn`. Goes into `msgs`
(normalized). When the line contains `upstream: "http(s)://<host>`, it is recorded in `uperr`: WIB time, message without
the errno number (`(104: ` → `(`) truncated to 100 characters, pod address, `METHOD path` from `request: "…"` truncated to 120.

```
2026/09/27 18:45:30 [error] 41#41: *90237038 recv() failed (104: Connection reset by peer) while reading response header from upstream, client: 103.170.104.160, server: _, request: "GET / HTTP/1.1", upstream: "http://10.42.245.132:8080/", host: "*.ombudsman.go.id"
```

Not parsed (only add to `lines`): ingress controller logs (`I1005 … status.go`, `W… controller.go`),
separator lines, and lines without a connection number `*N`.

### 3.3 Frontend (`om-fe-inhouse`) — nginx access log

```
\S+ - \S+ \[(\d+)/(\w+)/(\d+):(\d+:\d+):\d+ [^\]]+\] "(\S+) (\S+)[^"]*" (\d{3}) \d+ "[^"]*" "[^"]*" "([^",]*)
```

Fields: day, month, year, `HH:MM`, method, path, status, **IP = first entry of `X-Forwarded-For`** (the third
quoted column). The IP at the start of the line (node IP) is ignored. No response time.

```
10.88.1.102 - - [25/Sep/2026:16:46:08 +0000] "GET /js/chunk-vendors.60f38547.js HTTP/1.1" 200 1110667 "https://simpel4.ombudsman.go.id/lapor-ombudsman" "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Mobile Safari/537.36" "114.4.82.221, 10.88.1.100"
```

The error log uses the §3.2 regex: only `error` → `err`, other levels → `warn`; goes into `msgs`.

```
2026/10/05 07:31:51 [error] 22#22: *26370 open() "/app/apple-touch-icon-precomposed.png" failed (2: No such file or directory), client: 10.42.233.128, server: localhost, request: "GET /apple-touch-icon-precomposed.png HTTP/1.1", host: "simpel4.ombudsman.go.id"
```

### 3.4 Simpel-loop (`om-be-simpel-loop`, Node.js)

Lines must match `\[OM-(\w+)\] (.*)`; anything else is treated as a multi-line continuation and ignored.
**There is no timestamp in these log lines.** The level goes into `extra`.

HTTP event = content that is JSON with a `statusCode`:

```
[OM-INFO] {"requestId":"cbd8b650fbf2ff78ef03826371defaad","event":"http.request.completed","method":"GET","path":"/tx-file-upload","statusCode":200,"ipAddress":"103.138.53.20","durationMs":59}
[OM-ERROR] {"event":"http.request.failed","requestId":"69dda3958192b7ac11f28e3e2dc2f10c","method":"GET","path":"/tx-laporan/count","statusCode":401,"durationMs":1,"error":{"name":"UnauthorizedError","message":"Unauthorized"}}
```

Fields: `requestId`, `event`, `method`, `path`, `statusCode`, `ipAddress` (absent on failed events),
`durationMs`, `error.name`, `error.message`. Computed: `status`, `paths`, `ips`, `dur` (seconds), `slow`
(≥ 1,000 ms), 4xx/5xx per endpoint, the event list for correlation, business metrics (§4.8). Event
`http.request.failed` → `perr`, `msgs` (`<status> <name>: <message>`, level `ERROR` when 5xx, otherwise
`WARN`), and `err` (5xx) or `warn` (others).

Text lines:

| Pattern | Effect |
|---|---|
| starts with `Email sent successfully` | `biz['Email Terkirim']` |
| `Notification email sent successfully (\w+)` | `mail[<type>]` |
| level `ERROR` and contains `mail` | `biz['Email Gagal']` |
| level `ERROR` / `WARN` | `err` / `warn` + `msgs` |

```
[OM-INFO] Notification email sent successfully sendNotificationMailToKepalaKeasistenanRiksa {
[OM-PERFORMANCE] GET /v-monitoring { totalMs: 95 }
```

### 3.5 Spring Boot (`om-be-appsmanager`, `om-be-referensi`, `om-be-report`)

```
(\d{4}-\d\d-\d\d \d\d:\d\d):\d\d\.\d+ +(\w+) \d+ --- \[([^\]]+)\] (\S+) *: (.*)
```

Fields: time (minute), level, thread, logger, message. Computed: `hour`, `extra[level]`, `err`+`herr` (ERROR),
`warn` (WARN), `msgs` for ERROR/WARN with the key `<last logger class>: <message>`.

| Pattern in the message | Effect | Original example |
|---|---|---|
| `Started (\w+) in ([\d.]+) seconds` | `restart` (time, pod, application, seconds) | `2026-09-25 16:04:28.984  INFO 1 --- [           main] i.c.appsmanager.AppsmanagerApplication   : Started AppsmanagerApplication in 17.163 seconds (JVM running for 19.336)` |
| `JWT token is expired: .* a difference of (\d+) milliseconds` | `jwt[<age group>]` | `2026-09-25 16:23:24.776 ERROR 1 --- [nio-3000-exec-6] id.com.appsmanager.config.jwt.JwtUtils   : JWT token is expired: JWT expired at 2026-09-25T23:22:35Z. Current time: 2026-09-25T23:23:24Z, a difference of 49775 milliseconds.  Allowed clock skew: 0 milliseconds.` |
| contains `Refresh token expired` | `jwt['Refresh Token Kedaluwarsa']` | `2026-09-27 23:31:53.899  WARN 1 --- [nio-3000-exec-5] i.c.a.controller.UserController          : SECURITY ALERT: Refresh token expired from IP: 125.164.203.65. Error: JWT expired at 2026-09-27T02:59:54Z. …` |
| `(\S+) pdf path` | remember the template per thread | `2026-09-27 19:14:19.466  INFO 1 --- [nio-3000-exec-3] i.c.jasper.service.JasperReportService   : cover_map_kuning pdf path : /tmp/cover_map_kuning7643129013998660935.pdf` |
| starts with `Jasper template path : ` | `rep[template][success \| failed]`; failed when it ends with `: null` | `… JasperReportService   : Jasper template path : /jasper/cover_map_kuning.jrxml` and `… : Jasper template path : null` |
| `Invalid password for user/email: '([^']*)' from IP: ([\d.]+)` | failed login | `2026-09-27 23:39:32.545  WARN 1 --- [nio-3000-exec-6] i.c.a.controller.UserController          : SECURITY EVENT: Invalid password for user/email: '<akun>@ombudsman.go.id' from IP: 39.194.3.114 (Attempt 1/3)` |
| `due to 3 failed login attempts for user/email: '([^']*)' from IP: ([\d.]+)` | password reset | `… SECURITY ALERT: Password reset and notification email sent due to 3 failed login attempts for user/email: '<akun>@ombudsman.go.id' from IP: 36.83.211.41` |
| `User '([^']*)' successfully logged in from IP: ([\d.]+)` | successful login | `2026-09-25 16:55:52.965  INFO 1 --- [nio-3000-exec-4] i.c.a.controller.UserController          : SECURITY EVENT: User '<akun>' successfully logged in from IP: 103.247.21.209` |

(`<akun>` = masked account name.)

Lines that do not match the main regex:

- match `[\w.$]+(Exception|Error)\b` at the start → `msgs` with level `EXC` (does not add to `err`):
  `org.springframework.security.web.firewall.RequestRejectedException: The request was rejected because the URL contained a potentially malicious String "//"`
- start with `Hibernate:` → `extra['Hibernate SQL']`
- anything else (banners, stack traces) is ignored.

JWT age groups (verbatim labels): `< 5 Menit`, `5–60 Menit`, `1–24 Jam`, `1–7 Hari`, `> 7 Hari` (< 5 min, 5–60 min,
1–24 h, 1–7 days, > 7 days).

### 3.6 CoreDNS (`coredns`)

```
\[(\w+)\] plugin/errors: \d+ (\S+) (\w+): (.*)
```

Fields: level, domain, record type, message. Every matching line: `err`, `paths[domain]`, `msgs`
(`<domain> <type>: <message>` with every `ip:port` replaced by `X`). **No timestamp.**

```
[ERROR] plugin/errors: 2 backup-simpel4-volume.s3.ap-southeast-3.amazonaws.com. AAAA: read udp 10.42.191.189:58401->10.88.1.100:53: i/o timeout
```

### 3.7 Lines that are not logs

Files that failed to export contain a single giant line
`failed to get parse function: unsupported log format: "\x00\x00…"` (can be 30 MB). This line only adds to
`lines`. See §8.

---

## 4. Derived logic

### 4.1 Attack classification (nginx)

The path is *URL-decoded* twice (`unquote_plus` ×2), then matched in order; **the first match wins**
(all case-insensitive):

| # | Category | Pattern |
|--:|---|---|
| 1 | SQL Injection | `union\s+(all\s+)?select\|select\s.{1,60}\sfrom\|information_schema\|sleep\(\d\|benchmark\(\|waitfor\s+delay\|'\s*or\s*'?\d\|\bor\s+1=1\|;\s*drop\s` |
| 2 | XSS | `<script\|javascript:\|on(error\|load)\s*=\|alert\(\|<svg\|<iframe` |
| 3 | Path Traversal / LFI | `\.\./\|\.\.\\\|/etc/(passwd\|shadow\|hosts)\|win\.ini\|/proc/self` |
| 4 | Log4Shell / RCE | `\$\{jndi:\|\$\{.*\}\|;\s*(cat\|wget\|curl\|id\|uname\|sh)\b\|\|\s*(cat\|id\|sh)\b\|/bin/(ba)?sh\|cmd\.exe\|base64_decode\|eval\(\|system\(` |
| 5 | Sensitive file probe (`Probe file sensitif`) | `/\.(env\|git\|svn\|aws\|ssh\|htaccess\|htpasswd\|ds_store\|npmrc\|docker)\|/config\.(json\|php\|ya?ml)\|\.(sql\|bak\|old\|swp)$\|/id_rsa\|/actuator\|/server-status\|/_profiler\|/debug/` |
| 6 | CMS / WordPress scan (`Scan CMS / WordPress`) | `wp-(admin\|content\|includes\|login\|json)\|wordpress\|xmlrpc\|joomla\|drupal\|phpmyadmin\|/pma/` |
| 7 | PHP / CGI probe (`Probe PHP / CGI`) | `\.(php\d?\|asp\|aspx\|jsp\|cgi)\b\|cgi-bin` |

When the path is clean: a User-Agent (after decoding) containing `${` → Log4Shell / RCE; then a UA matching
`sqlmap|nikto|nmap|masscan|zgrab|nuclei|gobuster|dirbuster|dirb|wpscan|acunetix|nessus|openvas|-scanner|python-requests|go-http-client|curl/|wget|libwww|httpx|fuzz`
→ "Automated tool/scanner UA" (`UA tool/scanner otomatis`). The `;id` pattern is deliberately not applied to the UA (the Instagram UA contains `; id;`).

Example classified as "Sensitive file probe":
`34.19.127.176 - - [05/Oct/2026:14:30:46 +0000] "GET /.git HTTP/1.1" 200 5642 "-" "Mozilla/5.0 …" 289 0.001 [cattle-system-rancher-80] [] 10.42.233.150:80 5642 0.000 200 6fca94688c3a10d03c80b31af70877af`

Aggregation:

- `atk`: key = category + `METHOD path` (decoded once, 200 characters). Row:
  `[category, 'METHOD path', hits, IP count, top IP, 'code×n …', 5 smallest response sizes, upstream list, first UA (100), first, last]`; sorted by hits, top 300.
- `atk_ip`: per IP `[ip, hits, {category: n}, 'code×n …', most frequent UA, first, last]`; top 100.
- `atk_h`: per WIB hour. `atk_cat`: per category (not truncated).
- `ip4`: the 20 IPs with the most 4xx + their first UA.

### 4.2 Login and account analysis (Spring; the data only exists in appsmanager)

- `login`: per IP `[ip, failed, reset, success, accounts tried (only from failed/reset), first, last]`;
  only IPs that have a failure or reset; sorted by reset then failed; top 100.
- `login_h`: wrong passwords per hour. `login_okh`: successes per hour. `login_ok`: number of successes.
  `users_ok`: number of unique accounts that succeeded.
- Account name for analysis = the part before `@`, lowercase.

`accounts()` — per account that has ≥ 1 wrong password:

1. For each successful login, take the wrong passwords in the **preceding 60 minutes** (minute precision).
2. If ≥ 3 → flag "Success after ≥3 failures" (`Sukses Setelah ≥3 Gagal`). If the success IP is not among those failed IPs → flag
   "Success from a different IP" (`Sukses Dari IP Berbeda`) + note `<time> sukses dari <ip>` (max. 3).
3. Wrong passwords from ≥ 2 IPs → flag "Tried from ≥2 IPs" (`Dicoba Dari ≥2 IP`).

Row: `[account, failed, reset, success, failed IPs, success IPs, flags, first, last, notes]`; sorted
"different IP" first, then number of flags, then failures; top 150. The "same ISP" distinction is computed in the browser from the ASN.

### 4.3 5xx incidents (nginx)

Each 5xx response is recorded per (WIB minute, upstream, status). Minutes with 5xx are merged into one
incident when the gap is ≤ 5 minutes, **across upstreams**. Row: `[start, end, count, {upstream: n}, {status: n}]`.
`up5` = total 5xx per upstream.

### 4.4 Request id correlation nginx ↔ simpel-loop

- Every nginx access line whose tail matches fills `REQ[request id] = (WIB time, ip, method, path, status, upstream, UA 120)`.
  `REQ` is a single dictionary **global across all folders** (308,157 ids in the reference build).
- For each simpel-loop event: if the `requestId` is in `REQ` → counted as matched, adds to simpel-loop's `hour[hour]`
  (and `herr` when failed). This is the only time source for simpel-loop.
- Goes into `trace` when the event failed **or** `durationMs ≥ 5000`. Key = (IP, status, error or
  `Lambat X dtk` (slow X s), endpoint). Row: `[ip, status, error, endpoint, count, decoded full URL (300), upstream, UA, first, last, max duration ms]`; sorted by count, top 300.
- `corr = [matched, total events]`.

### 4.5 Source IP → pod flow, pod distribution, retries (nginx)

The tail block is split into 4 parts (`address length time status`), each a comma-separated list.

- `flow[(client IP, upstream)][pod]`: pod = **last address** (the one that answered); `-` when the tail does not match
  or there is no upstream. Row: `[ip, upstream, total, top 3 pods [address, n]]`; top 3,000 per folder.
- `pod[(upstream, address)]`: count per attempt (including failed ones); `pod5` = attempts with status 5xx.
  Row: `[upstream, address, requests, 5xx]`, not truncated.
- `retry[(upstream, first address, first status)]`: counted when there is more than one address; top 30.
- In the browser, "module" = upstream without the `-<port>` suffix.

### 4.6 IP owner and location (offline)

**Owner (`ipinfo`)** — only for displayed IPs (`shown_ips`: top IPs, attack sources, logins, 4xx, traces,
401, flows, account analysis):

- Private/loopback IP → `{asn: null, cc: '-', org: 'Jaringan Internal (IP Privat)'}` (internal network, private IP).
- Public IPv4 → binary search over the ranges of `ip2asn-v4.tsv` (ASN 0 rows skipped) → `{asn, cc, org}`.
- IPv6 or out of range → no entry.

**Location (`geo`)** — only for IPs in `flow` + the server IP:

- Global IPv4 only. The result per IP is stored in `.cache/geo.json` (including "not found"); the 86 MB database
  is only read when there are new IPs, with a single sweep over the sorted IP list (`geo_scan`).
- DB-IP columns: start, end, continent, country, province, city, lat, lon → `[city, province, country, lat, lon]`.
- Destination point = `SERVER_IP = '103.170.104.228'` (resolved from `api-simpel4.ombudsman.go.id`, hard-coded);
  if it is not in the database, `['Jakarta', 'Jakarta', 'ID', -6.2, 106.82]` is used.

**Land (`land`)**: Natural Earth 50m; rings whose starting point is south of −60° are dropped; coordinates to 2 decimals;
consecutive identical points are merged; rings with ≤ 3 points are dropped; x = longitude, y = −latitude.

**Labels (`labels`)**: countries `[ID name, EN name, longitude, latitude, rank]` from Natural Earth 110m;
provinces from GeoNames `ADM1` whose code is in the `PROV` table (38 provinces, Indonesian names hard-coded);
regencies/cities from `ADM2`, normalized by `kab_name()` (`… Regency` → `Kab. …`, `… City` → `Kota …`).

### 4.7 Message and path normalization

`norm(message)`, in order, then truncated to 220 characters:

1. `'…@…'` → `'<email>'`
2. `YYYY-MM-DDTHH:MM:SSZ` → `<ts>`
3. hexadecimal ≥ 16 characters → `<id>`
4. numbers (including decimals) → `#`

`msgs` key = `LEVEL | normalized message`; the stored sample = the **first** original line, 600 characters.

`path_key(path)`: drop the query; `/[0-9a-f-]{16,}` → `/:id`; `/<number>` → `/:n`; truncate to 120 characters.

### 4.8 Business metrics (simpel-loop)

2xx responses only, key = `METHOD path_key`:

| Endpoint | Metric |
|---|---|
| `POST /tx-laporan` | Laporan Dibuat (reports created) |
| `POST /tx-laporan/registrasi` | Registrasi Laporan (report registrations) |
| `POST /tx-laporan/request-otp` | OTP Diminta (OTPs requested) |
| `POST /tx-laporan/verify-otp` | OTP Terverifikasi (OTPs verified) |
| `POST /tx-file-upload`, `POST /files` | File Diunggah (files uploaded) |
| `POST /tx-lampiran` | Lampiran Ditambahkan (attachments added) |

Additionally: non-2xx `verify-otp` → OTP Gagal (OTPs failed); `error.name == MulterError` → Upload Ditolak (Terlalu Besar)
(uploads rejected, too large); `UnsupportedMediaTypeError` → Upload Ditolak (Tipe File) (uploads rejected, file type);
Email Terkirim / Email Gagal (emails sent / failed) from text lines (§3.4).
`act` = 2xx POST/PATCH/PUT/DELETE that are not one of the endpoints above (top 20). `mail` = notification emails per type.

### 4.9 Miscellaneous

- **Endpoint percentiles** (`ep`): durations sorted, index `min(n−1, int(q·n))`; only endpoints with ≥ 5 durations.
  The "Requests" column = number of requests for that endpoint (including status 101, which has no duration).
- **Repeated 401s** (`c401`): per (IP, endpoint): count, peak per minute, first, last.
- **Base URL** (`HOSTS`): 6 upstreams → production host; other upstreams are shown as "[Host not logged]", `-` is shown as
  "[Rejected at ingress, host not logged]".
- **`D.files`**: `err`/`warn` per file = difference of the service counters before and after that file.

---

## 5. Intentional limits and simplifications

### 5.1 `ponytail:` comments (3)

| Location | Content |
|---|---|
| `build_dashboard.py:33` | Simple regex signatures, can give false positives/negatives; use a WAF for serious detection |
| `build_dashboard.py:319` | Top 3,000 flows per day; raise when unique IPs per day are in the thousands |
| `build_dashboard.py:547` | `--watch` polls every 5 seconds; switch to watchdog when folders are very large |

### 5.2 Top-N in Python

| Field | Limit | Reached on current data? |
|---|--:|---|
| `paths`, `perr` | 20 | yes (nginx 825 unique endpoints in folder 10-06) |
| `ips` | 15 | yes (723 unique IPs on 09-29) |
| `up`, `ua` | 12 | `ua` yes |
| `dur` | 15, min. 5 durations | yes (not used) |
| `slow` | 15 | yes (553 on 09-29) |
| `msgs` | 40 | yes (appsmanager 43 on 09-29) |
| `atk` / `atk_ip` | 300 / 100 | no (max. 77 / 14) |
| `ip4` | 20 | yes (233 on 09-29) |
| `login` / `acct` | 100 / 150 | no |
| `ep` | 150, min. 5 durations | yes |
| `c401` | 30 | yes (653 on 09-29) |
| `uk_t` | 5 | — |
| `retry` | 30 keys | — |
| `uperr` | 200 **most recent** | yes (1,200 on 09-30) |
| `trace` | 300 | yes (09-29) |
| `act` | 20 | yes |
| `flow` | 3,000, 3 pods per flow | no (max. 1,762) |
| account notes | 3 | — |

### 5.3 Text truncation

UA 90 (`ua`), 100 (attacks, `ip4`), 120 (correlation); attack path 200; `path_key` 120; message 220; sample
line 600; connection error type 100; connection error request 120; trace URL 300 (200 in the table).

### 5.4 Thresholds and limits in the browser

- Charts top 10; cross-service messages 25; performance table 25; error rate 20 (table) / 10 (chart), min. 20 requests;
  errors per pod and requests per pod 15; PDF/activities 12; map location labels 6.
- Slow ≥ 1 s (table), ≥ 5 s (trace); P95 ≥ 1 s yellow; P99 ≥ 5 s red.
- Comparable when yesterday's lines ≥ 50 %; change < 0.5 % = "same".
- Multi-account ≥ 3 accounts; login window 60 minutes, ≥ 3 failures; incident gap 5 minutes.
- Map label detail levels: width > 100° / > 6° / ≤ 6°.

### 5.5 Other simplifications

- All times are truncated to the minute; aggregation per hour.
- `.log.gz` is skipped when the `.log` exists (assumed identical).
- Multi-line continuations (stack traces, objects) are ignored.
- Request bodies are not in the logs, so attacks via POST are not detected.
- Location IPv4 only; owner IPv4 only.
- Cache lifetime: ip2asn 7 days; DB-IP 30 days (tries this month, then last month); land, countries, GeoNames
  3,650 days; `geo.json` never expires. Failed download → use the old file if there is one.
- `lru_cache` on `wib()` and `path_attack()` (200,000 entries).
- The watcher swallows all build exceptions so it does not die because of one corrupt file.

---

## 6. External data sources, licenses, attribution

Used at build time (downloaded to `.cache/`, matched offline; user IPs are not sent out):

| Data | URL | Cache file | License according to the code | Obligation | Used for |
|---|---|---|---|---|---|
| ip2asn v4 | `https://iptoasn.com/data/ip2asn-v4.tsv.gz` | `ip2asn-v4.tsv.gz` (7.0 MB) | "public domain" | none | IP owner |
| DB-IP City Lite | `https://download.db-ip.com/free/dbip-city-lite-YYYY-MM.csv.gz` | `dbip-city-lite.csv.gz` (85.8 MB) | CC BY 4.0 | **attribution "IP Geolocation by DB-IP"** with a link to db-ip.com | IP location |
| Natural Earth 50m land | `raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson` | `ne_50m_land.geojson` (1.6 MB) | public domain | none | map land |
| Natural Earth 110m countries | `…/geojson/ne_110m_admin_0_countries.geojson` | `ne_110m_countries.geojson` (0.8 MB) | public domain | none | country labels |
| GeoNames ID | `https://download.geonames.org/export/dump/ID.zip` | `geonames-ID.zip` (10.4 MB) | CC BY 4.0 | **GeoNames attribution** | province & regency/city labels |

Attribution is currently only written in the footnote of the **IP Map** tab (DB-IP and GeoNames links).

Loaded by the browser when the dashboard is opened (not log data, but still third-party calls):

| Source | License | Notes |
|---|---|---|
| Chart.js 4.4.1 from `cdnjs.cloudflare.com` | MIT | without internet charts are not shown |
| Outfit font from `fonts.googleapis.com` | SIL OFL 1.1 | without internet falls back to the system font |

---

## 7. Reference figures

Produced by `python3 v2/tools/acuan_lama.py` (wraps the old build; `dashboard.html` is rewritten as well) →
`v2/docs/00-acuan.json`. Conditions: 2026-10-06 17:51, Python 3.13.1, build 14.2 seconds, 195 log files,
`--selftest` passed. Figures are taken from the **raw** statistics, before top-N.

**These figures only hold for the log folder contents at that time.** Log folders grow every day; re-run the
script before the parity test.

Column definitions: *Lines* = all lines of the files including unparsed ones; *Requests* = Σ `status`;
*Error* / *Warning* = `err` / `warn` (§3); *Unique IPs* = number of `ips` keys; *IP flows* = unique
(source IP, upstream) pairs.

| Folder | Files (0 lines) | Service | Lines | Requests | 4xx | 5xx | Error | Warning | Unique IPs | IP flows |
|---|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| 2026-09-26 | 19 (0) | om-fe-inhouse | 515 | 405 | 0 | 0 | 0 | 0 | 5 | 0 |
|  |  | om-be-simpel-loop | 75 | 54 | 1 | 0 | 0 | 0 | 3 | 0 |
|  |  | om-be-appsmanager | 206 | 0 | 0 | 0 | 5 | 4 | 0 | 0 |
|  |  | om-be-referensi | 286 | 0 | 0 | 0 | 1 | 4 | 0 | 0 |
|  |  | om-be-report | 121 | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| | | **total** | **1,203** | | | | **6** | **11** | | |
| 2026-09-27 | 19 (0) | om-fe-inhouse | 18,254 | 18,229 | 371 | 0 | 25 | 0 | 384 | 0 |
|  |  | om-be-simpel-loop | 3,620 | 2,988 | 552 | 0 | 0 | 552 | 162 | 0 |
|  |  | om-be-appsmanager | 2,001 | 0 | 0 | 0 | 190 | 17 | 0 | 0 |
|  |  | om-be-referensi | 1,301 | 0 | 0 | 0 | 46 | 0 | 0 | 0 |
|  |  | om-be-report | 193 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| | | **total** | **25,369** | | | | **262** | **569** | | |
| 2026-09-28 | 24 (16) | nginx-ingress-controller | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-fe-inhouse | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-simpel-loop | 9,014 | 7,642 | 1,273 | 0 | 0 | 1,273 | 156 | 0 |
|  |  | om-be-appsmanager | 1,949 | 0 | 0 | 0 | 117 | 12 | 0 | 0 |
|  |  | om-be-referensi | 781 | 0 | 0 | 0 | 41 | 0 | 0 | 0 |
|  |  | om-be-report | 708 | 0 | 0 | 0 | 7 | 0 | 0 | 0 |
|  |  | coredns | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| | | **total** | **12,452** | | | | **165** | **1,285** | | |
| 2026-09-29 | 25 (1) | nginx-ingress-controller | 132,402 | 132,203 | 4,635 | 59 | 94 | 164 | 723 | 1,762 |
|  |  | om-fe-inhouse | 86,089 | 86,064 | 26 | 0 | 25 | 0 | 662 | 0 |
|  |  | om-be-simpel-loop | 69,133 | 60,665 | 9,599 | 0 | 0 | 9,614 | 440 | 0 |
|  |  | om-be-appsmanager | 37,373 | 0 | 0 | 0 | 3,266 | 349 | 0 | 0 |
|  |  | om-be-referensi | 25,283 | 0 | 0 | 0 | 609 | 1 | 0 | 0 |
|  |  | om-be-report | 8,612 | 0 | 0 | 0 | 47 | 0 | 0 | 0 |
|  |  | coredns | 117 | 0 | 0 | 0 | 117 | 0 | 0 | 0 |
| | | **total** | **359,009** | | | | **4,158** | **10,128** | | |
| 2026-09-30 | 10 (1) | nginx-ingress-controller | 26,192 | 24,506 | 1,639 | 490 | 1,690 | 17 | 288 | 677 |
|  |  | om-be-appsmanager | 19,150 | 0 | 0 | 0 | 852 | 32 | 0 | 0 |
|  |  | om-be-referensi | 20,131 | 0 | 0 | 0 | 516 | 0 | 0 | 0 |
|  |  | coredns | 51 | 0 | 0 | 0 | 51 | 0 | 0 | 0 |
| | | **total** | **65,524** | | | | **3,109** | **49** | | |
| 2026-10-01 | 16 (12) | nginx-ingress-controller | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-fe-inhouse | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-simpel-loop | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-appsmanager | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-referensi | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | coredns | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| | | **total** | **4** | | | | **0** | **0** | | |
| 2026-10-02 | 16 (12) | nginx-ingress-controller | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-fe-inhouse | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-simpel-loop | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-appsmanager | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-referensi | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | coredns | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| | | **total** | **4** | | | | **0** | **0** | | |
| 2026-10-03 | 16 (1) | nginx-ingress-controller | 9,586 | 9,314 | 244 | 17 | 18 | 15 | 125 | 245 |
|  |  | om-fe-inhouse | 16,713 | 16,711 | 6 | 0 | 2 | 0 | 268 | 0 |
|  |  | om-be-simpel-loop | 42,994 | 37,244 | 5,084 | 0 | 0 | 5,081 | 501 | 0 |
|  |  | om-be-appsmanager | 19,821 | 0 | 0 | 0 | 1,820 | 91 | 0 | 0 |
|  |  | om-be-referensi | 7,598 | 0 | 0 | 0 | 100 | 1 | 0 | 0 |
|  |  | om-be-report | 3,327 | 0 | 0 | 0 | 9 | 7 | 0 | 0 |
|  |  | coredns | 142 | 0 | 0 | 0 | 142 | 0 | 0 | 0 |
| | | **total** | **100,181** | | | | **2,091** | **5,195** | | |
| 2026-10-04 | 16 (7) | nginx-ingress-controller | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-fe-inhouse | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-simpel-loop | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-appsmanager | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-referensi | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-report | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | coredns | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| | | **total** | **9** | | | | **0** | **0** | | |
| 2026-10-05 | 16 (1) | nginx-ingress-controller | 17,751 | 17,313 | 544 | 0 | 2 | 25 | 147 | 384 |
|  |  | om-fe-inhouse | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-simpel-loop | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-appsmanager | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-referensi | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-report | 545 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
|  |  | coredns | 305 | 0 | 0 | 0 | 305 | 0 | 0 | 0 |
| | | **total** | **18,611** | | | | **309** | **25** | | |
| 2026-10-06 | 18 (1) | nginx-ingress-controller | 125,097 | 124,822 | 4,533 | 51 | 125 | 136 | 516 | 1,242 |
|  |  | om-fe-inhouse | 26,682 | 26,640 | 49 | 0 | 42 | 0 | 286 | 0 |
|  |  | om-be-simpel-loop | 6,398 | 5,981 | 648 | 0 | 0 | 649 | 87 | 0 |
|  |  | om-be-appsmanager | 24,544 | 0 | 0 | 0 | 2,419 | 71 | 0 | 0 |
|  |  | om-be-referensi | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
|  |  | om-be-report | 8,979 | 0 | 0 | 0 | 33 | 0 | 0 | 0 |
|  |  | coredns | 195 | 0 | 0 | 0 | 191 | 0 | 0 | 0 |
| | | **total** | **191,898** | | | | **2,810** | **856** | | |

### 7.1 Figures per feature

**Ingress nginx**

| Folder | Source IPs (flows) | Attack requests | Attack URLs | Attacker IPs | IPs with 4xx | 401 clients (IP+endpoint) | 5xx incidents | Backend pods | Retries | Pod connection errors | Uptime-Kuma checks (failed) | Endpoints ≥5 durations |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 2026-09-29 | 723 | 155 | 77 | 12 | 233 | 653 | 7 | 21 | 30 | 35 | 699 (0) | 309 |
| 2026-09-30 | 288 | 32 | 19 | 9 | 142 | 151 | 10 | 22 | 825 | 1,200 | 270 (27) | 256 |
| 2026-10-03 | 125 | 10 | 10 | 4 | 50 | 70 | 1 | 14 | 0 | 1 | 364 (0) | 194 |
| 2026-10-05 | 147 | 30 | 15 | 3 | 58 | 139 | 0 | 14 | 1 | 2 | 669 (0) | 200 |
| 2026-10-06 | 516 | 88 | 71 | 14 | 216 | 555 | 1 | 14 | 71 | 74 | 859 (2) | 313 |

**Simpel-loop**

| Folder | HTTP events | Matched nginx | Trace rows | Slow ≥1 s | Reports created | Report registrations | OTPs requested | OTPs verified | Files uploaded | Attachments added | Emails sent | Uploads rejected | Notification emails | Activities |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 2026-09-26 | 54 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| 2026-09-27 | 2,988 | 0 | 0 | 1 | 1 | 5 | 1 | 1 | 13 | 0 | 6 | 0 | 9 | 29 |
| 2026-09-28 | 7,642 | 0 | 0 | 27 | 6 | 1 | 18 | 7 | 56 | 17 | 9 | 0 | 9 | 336 |
| 2026-09-29 | 60,665 | 22,638 | 300 | 553 | 12 | 108 | 35 | 12 | 314 | 116 | 55 | 18 | 74 | 1,571 |
| 2026-10-03 | 37,244 | 1,580 | 53 | 235 | 10 | 36 | 12 | 10 | 233 | 58 | 25 | 0 | 37 | 1,126 |
| 2026-10-06 | 5,981 | 4,161 | 111 | 27 | 7 | 1 | 7 | 10 | 27 | 2 | 1 | 0 | 2 | 99 |

**Appsmanager**

| Folder | Login IPs | Wrong passwords | Resets | Successful logins | Accounts analyzed | Restarts | JWT < 5 min | JWT 5–60 min | JWT 1–24 h | JWT 1–7 days | JWT > 7 days | Expired refresh tokens |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 2026-09-26 | 2 | 0 | 0 | 2 | 0 | 4 | 1 | 0 | 0 | 0 | 0 | 0 |
| 2026-09-27 | 21 | 0 | 0 | 23 | 0 | 0 | 85 | 20 | 38 | 15 | 2 | 17 |
| 2026-09-28 | 6 | 1 | 0 | 6 | 1 | 0 | 59 | 17 | 11 | 8 | 4 | 11 |
| 2026-09-29 | 117 | 86 | 24 | 389 | 39 | 0 | 2,057 | 559 | 283 | 226 | 40 | 237 |
| 2026-09-30 | 57 | 14 | 1 | 110 | 9 | 0 | 505 | 158 | 124 | 14 | 5 | 16 |
| 2026-10-03 | 115 | 19 | 0 | 142 | 14 | 0 | 1,108 | 265 | 288 | 57 | 15 | 68 |
| 2026-10-06 | 52 | 19 | 4 | 135 | 10 | 0 | 1,621 | 319 | 263 | 44 | 8 | 48 |

**Report**

| Folder | PDF success | PDF failed | Report JWT | Restarts |
|---|--:|--:|--:|--:|
| 2026-09-26 | 0 | 0 | 0 | 3 |
| 2026-09-27 | 28 | 0 | 1 | 0 |
| 2026-09-28 | 92 | 1 | 6 | 0 |
| 2026-09-29 | 813 | 32 | 14 | 0 |
| 2026-10-03 | 519 | 2 | 7 | 0 |
| 2026-10-05 | 91 | 0 | 2 | 0 |
| 2026-10-06 | 1,182 | 15 | 15 | 0 |

**Referensi**

| Folder | Expired JWT | Restarts |
|---|--:|--:|
| 2026-09-26 | 1 | 4 |
| 2026-09-27 | 46 | 0 |
| 2026-09-28 | 41 | 0 |
| 2026-09-29 | 608 | 0 |
| 2026-09-30 | 516 | 0 |
| 2026-10-03 | 99 | 0 |

Other figures (level distribution, attack categories, all business and JWT keys, hours with data, unique endpoints,
unique messages) are in `00-acuan.json`.

---

## 8. Findings: behavior not evident from the UI

These affect what "parity" means. Recorded as they are.

**Data**

1. **The folder name is not the log date.** Folder `2026-09-29` contains logs for 28 Sep 00:00–23:59 WIB; folder
   `2026-10-06` contains 5 Oct. All "per day" tabs are really "per export folder", and the hours in the charts
   are dated D−1.
2. **The time range of each service within one folder differs.** Example folder `2026-10-06`: nginx 5 Oct
   09–24 WIB, appsmanager 11–24, report 00–23, FE 13–23.
3. **Corrupt files.** 52 of 195 files contain 0 lines; folders 10-01, 10-02, 10-04 contain only the line
   `failed to get parse function: unsupported log format` (4–9 lines in total per folder), as do some
   services in 10-05 and 10-06. That line is counted in "Total log lines".
4. **Simpel-loop and coredns have no timestamps.** The simpel-loop per-hour chart covers only events that are
   correlated (37 % on 09-29, 4 % on 10-03, 70 % on 10-06; 0 % when the folder has no nginx). Coredns has
   no time chart at all.
5. **Two kinds of folder structure**: `2026-09-26` and `-27` without a namespace; the rest with a namespace.
   `D.files[*].ns` is computed but never displayed.

**Counting**

6. **KPIs computed from truncated lists.** "Pod connection errors" = length of `uperr` (max. 200; the actual
   value is 1,200 on 09-30). The same applies to "Retries to another pod" (30 keys), "Unique source IPs"
   (100), "IPs with failed logins" (100), "Critical attacks" (300 rows), "Total requests" and "Unique destination IPs"
   in the IP Map (3,000 flows, 3 pods per flow), and the connection error type chart.
7. **nginx `err` mixes two things**: 5xx responses and error log lines; `herr` (per-hour chart) is 5xx only.
8. **Level `crit`** is counted as an error in ingress nginx but as a warning in the frontend.
9. **Simpel-loop**: failed 4xx events are written by the application with `[OM-ERROR]`, so the level donut shows ERROR
   9,614 while KPI Error = 0 and Warning = 9,614 (09-29).
10. **`EXC` lines** (Spring exceptions without a timestamp) go into the message table but do not add to the Error KPI.
11. **Cross-folder correlation.** `REQ` is global, so a simpel-loop event can match an nginx request from
    another folder, and its hour goes into the folder where the event is.
12. **Account analysis and incidents are computed per folder**; sequences that cross a folder boundary are cut.
13. **The "Pods with 502 retries" label** counts retries with any initial status.
14. **"Slow requests ≥ 5 s"** only sums trace rows with status 2xx; 3xx ones are not in any KPI.

**Computed but not displayed**

15. `jwt['Refresh Token Kedaluwarsa']` (expired refresh tokens; e.g. 237 on 09-29) is in neither a chart nor the summary.
16. `S.dur` (average and maximum per endpoint) is not used by the template.

**Miscellaneous**

17. **DB-IP attribution only exists in the IP Map tab**, even though the map and location column also appear on service
    pages.
18. **"Self-contained" is not entirely true**: it needs Chart.js from a CDN and Google fonts.
19. **Personal data embedded in the HTML**: email addresses/account names (login and account analysis tables), client IPs, and
    up to 40 original log line samples per service.
20. **Hard-coded values**: `SERVER_IP`, `SERVER_FALLBACK`, `HOSTS` (6 hosts), `PROV` (38 provinces),
    `BIZ_EP`, upstream DNS `10.88.1.100` in the Root Causes text, the prefix `ombudsman-ombudsman-`.
21. **`--watch` rebuilds all folders** on every change (14 seconds now).
22. The `recovery-file/` folder and `recovery-file.zip` are not touched by `build_dashboard.py` (not a dated
    folder).

---

## 9. Open questions

Cannot be inferred from the code; need answers before the PRD/DRD.

1. **What is a "day"?** The export folder (as now) or the WIB calendar date of each line? The answer
   determines whether the §7 figures can be compared directly.
2. **Parity to what level?** Must the behavior in §8 items 6–14 be replicated exactly (so the numbers match)
   or may it be fixed, with the differences recorded?
3. **Which top-N limits are kept as display limits**, and which exist only because of the HTML file size?
4. **Corrupt files** (`unsupported log format`): counted as lines as now, or flagged as corrupt?
5. **`.log` vs `.log.gz`**: are they really always identical, and which will be available going forward?
6. **Simpel-loop and coredns without timestamps**: can the log format at the source get a time added, or
   will it keep depending on nginx correlation?
7. **ip2asn license**: the code says "public domain"; the iptoasn.com page needs checking for other
   terms. Does the DB-IP attribution need to appear on every page that shows a location?
8. **Must the dashboard open without internet?** (Chart.js and the font currently come from a CDN.)
9. **Who may open the dashboard?** It contains account emails and client IPs.
10. **Hard-coded values** (server IP, hosts, upstream DNS): keep as constants or make them configuration?
11. **`--watch` mode** still needed, or is "parse once per day" enough?
12. **Folders without a namespace** (09-26, 09-27) still need to be supported?
13. **New services**: today an unknown folder is silently treated as Spring Boot. Is that intentional?
