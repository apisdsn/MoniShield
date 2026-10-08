# Page checklist (Stages 13–20)

Built from inventory §2 and DRD §3, §6, §8. Every page is checked in **8 combinations**: {ID, EN} × {dark,
light} × {wide 1440 px, narrow 390 px}. Whatever can be automated is checked by a Playwright script (column "Method");
whatever can only be judged by eye is marked **look**, with screenshots as evidence.

General items for **every** page and every combination:

| # | Item | Method |
|--:|---|---|
| U1 | No horizontal page scroll; KPIs in 2 columns at 390 px; tables with > 4 columns become row cards | script |
| U2 | `lang` attribute and theme match the selection; no card title left behind in the other language | script |
| U3 | No page/console errors | script |
| U4 | System names (services, pods, upstreams) in lowercase as-is (DRD U33) | script + look |
| U5 | Numbers formatted per language (`1.234` / `1,234`), times in WIB, durations `dtk` / `s` | look |
| U6 | Loading: grey skeleton after 200 ms; folder change: old content dimmed until the new one arrives | look |
| U7 | Chart labels not clipped at the edges; time axis without repeated dates when it covers one day | look |

## Overview (inv. §2.1, DRD §3.1) — Stage 13 ☑

| Item | Reference | Method | Result |
|---|---|---|:-:|
| Log period: first hour – last hour | inv. §2.1 | look | ☑ |
| KPIs equal to the old ones: lines, errors, warning/4xx app, HTTP requests, 4xx rate (1 decimal), 5xx rate (2 decimals), services, log files, empty files | 06 Oct: 191,898 · 2,810 · 856 · 124,822 · 3.6 % · 0.04 % · 7 · 18 · 1 | `tools/uji_tahap13.cjs` (vs `dashboard.html`) | ☑ |
| New KPI "Corrupt files" only when > 0 (B05) | DRD §3.1 | look | ☑ |
| ▲/▼ change vs the previous folder only over comparable services; equal to the old one | 06 Oct: lines ▼ 36 %, errors ▼ 37 %, warning unchanged | script | ☑ |
| `(i)` on Error (5xx + error log lines) and Warning / 4xx app | DRD §4.1 U8 | look | ☑ |
| Errors per hour per service (stacked bars, wide) | inv. §2.1; changed: includes error log lines (U32) | look | ☑ |
| Errors & warnings per service; Log lines per service | inv. §2.1 | script (card titles) | ☑ |
| Service summary; Log files | inv. §2.1 | script | ☑ |
| Top error messages across services: the top 25 equal in content and count order; "Show next" | inv. §2.1, B04 | script | ☑ |
| Section "System-wide HTTP traffic" + source note + nginx cards without the map and without the message card | inv. §2.1 | script (20 cards = old) | ☑ |
| Without ingress nginx: HTTP KPIs and the traffic section are not shown | DRD §6.6 | script (folder 27 Sep) | ☑ |
| Practically empty folder: yellow band "contains only N lines; M corrupt files" + link to Pods | DRD §6.6 | script (01 Oct) | ☑ |
| 8 combinations of language × theme × width | U1–U3 | script | ☑ |

## Service page (inv. §2.10, DRD §3.10) — Stage 13 ☑ (except the map, Stage 20)

| Item | Reference | Method | Result |
|---|---|---|:-:|
| KPIs: lines, errors, warnings; HTTP + 4xx/5xx rate when there are requests; first 4 level entries | inv. §2.10 | script, 5 services (nginx, simpel-loop, appsmanager, coredns, frontend) | ☑ |
| The cards shown equal the old ones (checkmark table inv. §2.10) | nginx 16, simpel-loop 16, frontend 10, appsmanager 4, coredns 4 cards | script | ☑ |
| coredns: "Top 10 domains failing to resolve", table "Domains failing to resolve" | inv. §2.10 no. 6, 10 | script | ☑ |
| simpel-loop: per-hour title "from X % of requests traced in nginx" | inv. §2.10 no. 2 | script | ☑ |
| nginx: the Errors-per-hour line includes error log lines (Σ = Error KPI 125) | TRD §4.4 item 2 | script | ☑ |
| simpel-loop 29 Sep: level donut WARN 9,614, no ERROR; `(i)` explains | TRD §4.4 item 4 | script | ☑ |
| Status codes: logarithmic axis, color per class, code always written | inv. §2.10 no. 3, DRD §9.2 | look | ☑ |
| Endpoint performance: P95 ≥ 1 s yellow, P99 ≥ 5 s red; error rate red when there are 5xx | inv. §2.10 no. 14 | look | ☑ |
| Message table: expanded row → original log line (UTC) + copy button; filter "JWT" only matching rows + "N matching rows" | DRD §4.3 | script | ☑ |
| 0 lines: "No logs for this service …"; only corrupt: + tag "Corrupt" | DRD §6.6 | script (01 Oct) | ☑ |
| Map of this module, collapsed by default (U6) | DRD §3.10 no. 1 | — | Stage 20 |
| 8 combinations of language × theme × width | U1–U3 | script | ☑ |

## Trends (inv. §2.3, DRD §3.3) — Stage 14 ☑

| Item | Reference | Method | Result |
|---|---|---|:-:|
| Note "Daily data is not always complete …" | inv. §2.3 | look | ☑ |
| 6 charts: errors, warnings, log lines per day per service (stacked); HTTP requests (Total, 4xx, 5xx); security (attacks, wrong passwords, resets); business (5 metrics) — series and numbers equal to the old ones | inv. §2.3 | `tools/uji_tahap14.cjs` | ☑ |
| Table "Errors per service & change": numbers and ▲/▼ % equal to the old ones | inv. §2.3 | script | ☑ |
| Table "Data completeness": numbers / Empty / None equal; new marker "Corrupt" (B05) | inv. §2.3, DRD §3.3 | script | ☑ |
| simpel-loop 30 Sep "None"; 1 Oct "Corrupt"/"Empty" | plan Stage 14 | script | ☑ |
| Folder picker in the header disabled with an explanation | DRD §3.3 | script | ☑ |
| Range picker 14 / 30 / 90 / all (default 30, remembered per browser): the number of columns changes | DRD §3.3 U4 | script, simulated database of 40 folders | ☑ |
| Table scrolls horizontally, Service column pinned, newest folder on the right; also at 390 px (not cards) | DRD §3.3, §8.2 | script | ☑ |
| 8 combinations of language × theme × width | U1–U3 | script | ☑ |

## Security (inv. §2.4, DRD §3.4) — Stage 15 ☑

| Item | Reference | Method | Result |
|---|---|---|:-:|
| 8 KPIs laid out 4 + 4 (U5), numbers equal to the old ones | 06 Oct: 88 · 14 · 5 · 62 · 9 · 1 · 0 · 4 | `tools/uji_tahap15.cjs` (06 Oct, 29 Sep, 28 Sep) | ☑ |
| "Key findings": 9 rules, sentences equal to the old ones in 2 languages; built from components + dictionary, not HTML in strings | inv. §2.4 | script (6 items 06 Oct, 11 items 29 Sep) | ☑ |
| 6 charts: categories (severity colors), hourly timeline, top 10 IPs, per network owner, wrong passwords per hour, top 10 IPs with wrong passwords | inv. §2.4 | script (card titles) | ☑ |
| 5 tables: attack endpoints (full URL + base host + UA, "2xx – verify"), source IPs, account analysis (same ISP), failed logins (Multi-account), 4xx IPs | inv. §2.4 | script (core columns of every row) | ☑ |
| Without nginx: note "per-URL attack detection is unavailable"; the login section remains | DRD §6.6 | script (28 Sep) | ☑ |
| URLs containing `<script>` / `onerror` / `${jndi:` are shown as text, not executed; no `@html` | plan Stage 15 | script (29 Sep) + `grep` | ☑ |
| Attack categories and account flags translated (labels, DRD §6.3) | DRD §6.3 | look | ☑ |
| 8 combinations of language × theme × width | U1–U3 | script | ☑ |

## Root Causes (inv. §2.5, DRD §3.5) — Stage 16 ☑

| Item | Reference | Method | Result |
|---|---|---|:-:|
| "Root cause summary" up to 5 items, sentences equal to the old ones (both languages, codes as `<code>`); empty → "No root cause patterns …" | inv. §2.5 | `tools/uji_tahap16.cjs` (29 Sep, 06 Oct, 30 Sep, 27 Sep) | ☑ |
| The connection error item uses the full count (30 Sep 200 → 1,200) | TRD §4.4 item 1 | script | ☑ |
| 4 charts: repeated 401s, JWT age (stacked per service), PDF per template, connection errors by type | inv. §2.5 | script (chart data vs old) | ☑ |
| New: "Expired refresh tokens: N" below the JWT chart | DRD §3.5 B07 | script (29 Sep: 237) | ☑ |
| 401 table: the first 30 rows equal (ties may differ in order) + "Showing 30 of N"; PDF; DNS + impact | inv. §2.5, B04 | script | ☑ |
| DNS upstream from configuration (`S4_DNS_UPSTREAM`), not hard-coded | inv. §2.5 | look | ☑ |

## Availability (inv. §2.6, DRD §3.6) — Stage 16 ☑

| Item | Reference | Method | Result |
|---|---|---|:-:|
| 7 KPIs (4 + 3) equal to the old ones except pod connection errors (30 Sep 200 → 1,200); retry 825; 10 incidents | inv. §2.6, TRD §4.4 item 1 | script (30 Sep, 06 Oct) | ☑ |
| 3 charts: 5xx per hour, 5xx per upstream, Uptime-Kuma per hour (success/failure) — same data | inv. §2.6 | script | ☑ |
| Tables per upstream, incidents (duration in minutes), Uptime-Kuma targets — equal; first 200 connection errors + continuation | inv. §2.6 | script | ☑ |
| Without nginx: note "Availability analysis uses the ingress nginx log …" | DRD §6.6 | script (28 Sep) | ☑ |
| 8 combinations of language × theme × width (both pages) | U1–U3 | script | ☑ |

## Pods (inv. §2.7, DRD §3.7) — Stage 17 ☑

| Item | Reference | Method | Result |
|---|---|---|:-:|
| 5 KPIs equal to the old ones; label "Pods with retries" (not "… retry 502") + (i) explanation | inv. §2.7, B10 | `tools/uji_tahap17.cjs` (06 Oct, 29 Sep, 28 Sep) | ☑ |
| Note "Pod names come from the log file names …" | inv. §2.7 | look | ☑ |
| 2 charts: errors per pod (15), request distribution per pod (IP) (15) — same data | inv. §2.7 | script | ☑ |
| Health per pod: lines, errors, warnings, size equal; status "Corrupt" for corrupt files (06 Oct: 3; old "Ada Log"), other statuses equal | inv. §2.7, B05 | script | ☑ |
| Traffic distribution per backend pod (share, 5xx, retry) and restarts — equal | inv. §2.7 | script | ☑ |

## Business (inv. §2.8, DRD §3.8) — Stage 17 ☑

| Item | Reference | Method | Result |
|---|---|---|:-:|
| 11 KPIs + change vs the previous folder equal to the old ones; 29 Sep: 12 / 108 / 35 / 12 / 314 / 18 / 55 / 813 / 32 / 389 | inv. §2.8 | script (29 Sep, 06 Oct, 28 Sep) | ☑ |
| simpel-loop / report / appsmanager log absent → KPI "–" + "No … log in this folder", not 0 | DRD U16 | script (30 Sep: 9 KPIs "–") | ☑ |
| 5 charts (summary, email, top activities, logins per hour, PDF per template) — same data; metric labels from the dictionary | inv. §2.8, DRD §6.3 | script | ☑ |
| Activity table (top 20; ties at the cut-off may be chosen differently, rule E2) and PDF per template equal | inv. §2.8 | script | ☑ |

## Request Tracing (inv. §2.9, DRD §3.9) — Stage 17 ☑

| Item | Reference | Method | Result |
|---|---|---|:-:|
| KPIs 1–3 equal to the old ones; 29 Sep: 60,665 / 22,638 / 37.3 % | inv. §2.9 | script (29 Sep, 06 Oct) | ☑ |
| Failed / IP / slow KPIs from ALL traces (29 Sep: 3,245 → 3,479, 150 → 176, slow 15 → 24) | TRD §4.4 items 1, 9 | script (= API) | ☑ |
| Note "… X % of events do not match …" equal to the old one | inv. §2.9 | script | ☑ |
| Trace table: first 300 + "Showing 300 of 550"; after loading everything, every old row is present | inv. §2.9, B04 | script | ☑ |
| Trace URLs shown as text (not executed), truncated at 200, UA below them | inv. §2.9 | script + look | ☑ |
| No matches (27 Sep) or no simpel-loop (30 Sep): note "Tracing needs om-be-simpel-loop and ingress nginx logs …" (ASSUMPTION; the old one showed zero KPIs on 27 Sep) | DRD §6.6 | script | ☑ |
| 8 combinations of language × theme × width (all three pages) | U1–U3 | script | ☑ |

## Manage users (DRD §3.11, TRD §8.4) — Stage 18 ☑

| Item | Reference | Method | Result |
|---|---|---|:-:|
| User table: name, display name, role (admin tag), status (active = ok tag, inactive = dimmed, locked), last sign-in (WIB), ⋯ actions menu | DRD §3.11 | `tools/uji_tahap18.cjs` | ☑ |
| Add user in a dialog: rules written before typing, per-field errors (`aria-describedby`), "Generate"; focus on the first field; Esc closes, focus returns to the trigger | DRD §3.11 | script | ☑ |
| New user: must change password, then the whole dashboard without the admin menu | TRD §8.2 | script (two windows) | ☑ |
| Role promotion/demotion takes effect on the next request (tab switch / reload) | plan 18 | script | ☑ |
| Reset password: confirmation names the user; temporary password shown once + Copy + "will not be shown again"; the user's sessions end immediately | DRD §3.11 | script | ☑ |
| Deactivate / Delete: confirmation names the user; sessions end; sign-in refused with a generic message; reactivate | DRD §3.11 | script | ☑ |
| Last admin / own account: item not offered (disabled + reason); role locked; stale list → refusal message in the dialog; API 409 | DRD §3.11 | script | ☑ |
| Regular user at the admin address: "No access"; API 403 | TRD §8.4 | script | ☑ |
| Phone: row cards, "+ Add user" sticky at the bottom, full-screen dialog | DRD §3.11 | script + look | ☑ |

## Ingest & import (DRD §3.11, TRD §8.4) — Stage 18 ☑, import card Stage 19 ☑ (tested with a fake S3)

| Item | Reference | Method | Result |
|---|---|---|:-:|
| Last ingest from the database (survives a server restart): time in WIB, success/failure, N files changed of M | DRD §3.11 | script + `test_api.py` | ☑ |
| "Ingest now": disabled while running; progress every 2 s (polite `aria-live`, `progressbar`); done → notification "0 files changed"; the dashboard stays open | DRD §3.11 | script | ☑ |
| Ingest warnings can be expanded (`details`); errors are shown | DRD §3.11 | look | ☑ |
| Audit log: newest on top, first 50 + continuation, filter; time, user, action, details, IP; no passwords/tokens | DRD §3.11 | script | ☑ |
| Import: credential status (available/not + source, without values); accepted link forms; import disabled → note on how to enable it | DRD §3.11 | `tools/uji_tahap19.cjs` | ☑ |
| "Dry run": summary + fetch/skip details with reasons, 0 bytes downloaded; links refused with a reason (bucket, prefix, date) | DRD §3.11 | script | ☑ |
| "Import": confirmation names the link, progress (`progressbar`, `aria-live`), done → ingest + folder appears; repeat → 0 objects; import history | DRD §3.11 | script | ☑ |
| Temporary credentials: three password fields without autocomplete, note "server memory only", wrong format refused, delete; values never shown | DRD §3.11 | script | ☑ |
| 8 combinations of language × theme × width (both screens) | U1–U3 | script | ☑ |

## Additional presentation (suggestions 1–9) — Stage 24 ☑

| Item | Method | Result |
|---|---|:-:|
| Command Center: ▲/▼ vs the previous folder (only when comparable), hourly charts (requests; 5xx & attacks) | API test + look at 30 Sep (▼ 81 % requests, ▲ 731 % 5xx) | ☑ |
| New attention items: uptime failures, service error spike, restarts, failed PDFs, JWT spike; links to the related page/service | API test + look (30 Sep: "nginx-ingress-controller errors spiked") | ☑ |
| IP profile from any IP cell and from search; trail across all folders; requests + category + CRS rules | look at 34.19.127.176 (51 requests, 6 attacks, 2 folders) | ☑ |
| Download the attack IP list (CSV), safe to open in a spreadsheet | download `ip-serangan-2026-10-06.csv` 4 rows; `_safe` test | ☑ |
| "CRS rules" column with rule descriptions | look (944150 · Potential Remote Command Execution: Log4j / Log4shell) | ☑ |
| Global search (Ctrl+K / 🔍): IP, account, requestId, URL → page + filter filled in | API test + look | ☑ |
| Trends: data completeness (missing dates, corrupt files, last ingest) + hour × date heatmap (Requests/Errors, table) | look | ☑ |
| One-page A4 PDF summary (light theme, map, KPIs, attention items) | Chromium PDF | ☑ |
| 390 px without horizontal scroll (Command Center, Trends, IP profile); both languages | look + `cek_i18n` | ☑ |

## Command Center (DRD §12, TRD §12) — Stage 22 ☑

Absorbs the IP Map tab (ASSUMPTION DRD §12) at the same address (`#/peta?modul=`); the "IP Map" section below still
applies to the map and its flow table.

| Item | Reference | Method | Result |
|---|---|---|:-:|
| 6 main KPIs (HTTP requests, 5xx, errors of all services, upstream connection errors, attack source IPs, failed-login IPs) = numbers on their source pages | TRD §12 | `pytest tests/test_api.py -k command` | ☑ |
| Numbered "What needs your attention" card: attacks, upstream connection errors, 5xx, failed logins, corrupt files; red first; "Open …" links to the related page | DRD §12 | API test + look (06 Oct: 5 items) | ☑ |
| Map as wide and as tall as the screen (owner request), attention card below the map; module picker + 6 map figures above it | owner request 2026-10-06 | look (1440 px: map 1106 × 600 px) | ☑ |
| Without nginx (28 Sep): request/5xx KPIs "–" + "No nginx ingress log"; attention card remains; map note | DRD §6.6 | look | ☑ |
| Both languages, no horizontal scroll at 390 px | U1–U3 | look + `uji_tahap20.cjs` | ☑ |

## Security: OWASP CRS + CAPEC detection (TRD §4.6) — Stage 21 ☑

Default view (`S4_ATTACK_RULES=crs`). The "Security" section above still applies to the old-rules view
(`S4_ATTACK_RULES=lama`), which is re-tested with `tools/uji_tahap15.cjs` so that parity is not lost.

| Item | Reference | Method | Result |
|---|---|---|:-:|
| 8 KPIs = API; critical KPI = requests of the highest severity (CRITICAL), label "Critical attacks (highest severity)" | TRD §4.6 | `tools/uji_tahap21.cjs` (06 Oct: 50 · 4 · 50 · 46 · 9 · 1 · 0 · 4) | ☑ |
| Number of attacker IPs in the folder summary (Overview, banner) = Security KPI, same scheme | TRD §4.6 | script | ☑ |
| Categories named by CAPEC in both languages (+ CRS family when the CAPEC is generic) and a small "CAPEC-n" line; the category chart uses the same names | plan Stage 21 | script (49 URL rows, 4 IP rows, ID and EN) | ☑ |
| "CRS rules" column: IDs of the matched rules per row, equal to the API | plan Stage 21 | script | ☑ |
| Key findings: Log4Shell from the CRS Log4j rule; critical categories = the 3 categories of highest severity | TRD §4.6 | script | ☑ |
| Footnote: CRS + version + license + paranoia level + number of rules + threshold; only URL, arguments, User-Agent are inspected; not a WAF replacement | plan Stage 21 | script (ID and EN) | ☑ |
| Attack URL/UA content still shown as text | plan Stage 15 | script | ☑ |
| 8 combinations of language × theme × width | U1–U3 | script | ☑ |

## IP Map (inv. §2.2, DRD §3.2, §7) — Stage 20 ☑

| Item | Reference | Method | Result |
|---|---|---|:-:|
| 6 KPIs; source IPs, modules, pods, total requests equal to the old ones; location/country/"from outside Indonesia" differ because of MaxMind vs DB-IP (plan Stage 7) | inv. §2.2 | `tools/uji_tahap20.cjs` (06 Oct) | ☑ |
| Module picker (in the address `?modul=`): KPIs, points, table change; map position and zoom stay | DRD §3.2 | script | ☑ |
| 13 layers §7.3; server point in Jakarta labeled; label of the largest locations name + "N IP · N req"; clusters < 40 px without numbers (owner decision) | DRD §7.3, §7.5 | script + look | ☑ |
| Labels country → province (zoom ≥ 4) → regency (zoom ≥ 7) without overlapping; clusters split at zoom 8 | DRD §7.3, §7.5 | script | ☑ |
| Mouse wheel scrolls the page + hint "Hold Ctrl…"; Ctrl + wheel zooms; keyboard arrows/+/−/0/Esc | DRD §7.6 | script | ☑ |
| 390 px touch: screen-tall map in the Command Center (Stage 22; previously 4:3), 44 px buttons, one finger does not pan the map, two fingers pan; full-screen button | DRD §7.6, §8.2 | script (CDP touch) | ☑ |
| Tooltip (location, IP, requests, module) → "Show in table" fills the flow table filter; Esc closes | DRD §7.7 | script | ☑ |
| All requests go to the same origin; internet cut off → map, labels, points still shown; MaxMind · GeoNames · Natural Earth attribution always visible | DRD §7.2, §7.8 | script | ☑ |
| Theme/language switch: colors and country names change without losing the position | DRD §7.1 | script | ☑ |
| Flow table first 100 + continuation (rows equal to the old ones); note names MaxMind; without nginx → note | inv. §2.2, X6 | script | ☑ |
| Service page: map collapsed; when opened → flows of that module only | DRD §3.10, Q5 | script | ☑ |
| 8 combinations of language × theme × width | U1–U3 | script | ☑ |

## Next pages

| Page | Reference | Stage |
|---|---|:-:|
| Command Center realtime stream (Kafka, postponed) | TRD §12 | 23 |

Each stage adds its section here in the same form, plus a `tools/uji_tahapNN.cjs` script when the page
has a counterpart in the old dashboard.
