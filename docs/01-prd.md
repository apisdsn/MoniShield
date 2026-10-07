# PRD — Migration of the SIMPEL4 log dashboard (v2)

Product requirements document for moving the SIMPEL4 log dashboard from a single built HTML file to a
small application (ingest once per day, data fetched per tab). Written for readers who have not seen the
code. Details of the old system are in [`00-inventaris.md`](00-inventaris.md); references such as "inv. §2.4"
point there. Technical decisions (schema, endpoints, code structure) are deliberately not made here; they belong to the TRD.

Items marked **ASSUMPTION** are decisions I made without confirmation from the product owner, choosing the
safest and most easily reversible option. All assumptions are summarized in [§9](#9-list-of-assumptions) and the questions
for the product owner in [§10](#10-open-questions-for-the-product-owner).

> **Revision 2026-10-06 (plan Stage 1).** The product owner has answered some of the questions. This document
> has been aligned with those answers and with [`03-trd.md`](03-trd.md). Changed items are marked
> **[Decided]**, **[Dropped]**, or **[New]**.

| Owner decision | Content |
|---|---|
| "Day" | Stays **per export folder** (P2). |
| Access | The dashboard is opened from **many computers** (P3), over HTTPS, **login required**. |
| Roles | Two roles for now: **admin** and **user**. A user sees the whole dashboard; an admin also adds and manages users. Per-module restriction is **deferred** (P1). |
| Accounts | **Local** in the application database; not SSO. |
| Odd definitions | **Fixed** according to good practice (P4); details in TRD §4.4. |
| Automatic import | From an S3 prefix, e.g. `s3://simpel4-backup/k8s-logs/2026-09-26/`, with a fixed read-only access key, Jakarta region. |
| Mobile view | Done **properly**. |

Terms:

| Term | Meaning |
|---|---|
| Log folder | One folder named after a date (e.g. `2026-10-06`) containing the log export of all services. It contains the logs of the **previous** day in WIB (inv. §8 item 1). |
| Service | A log source: ingress nginx, om-fe-inhouse, om-be-simpel-loop, om-be-appsmanager, om-be-referensi, om-be-report, coredns. |
| Ingest | The process of reading log files and storing them in a form ready for display. |
| Old system | `build_dashboard.py` + `dashboard_template.html` → `dashboard.html`. |
| Reference figures | Figures from the old system for each folder, in `00-acuan.json` (inv. §7). |

---

## 1. Background and problem

The SIMPEL4 team (Ombudsman RI) receives daily log exports from the cluster and reads them through a single
`dashboard.html` file. That dashboard is useful: in one place it shows service health, attack indications,
reporting activity, and where users come from. It is the way it is built that will not last.

### 1.1 Problems to solve

| # | Problem | Evidence from the old system |
|--:|---|---|
| M1 | **All logs are re-parsed on every build.** Build time grows with the number of folders. | 11 folders (774 thousand lines) = 14 seconds. At full-day volume (±360 thousand lines/day) a year = ±131 million lines, roughly 40 minutes per build. |
| M2 | **All data for all days is loaded into the browser at once.** | `dashboard.html` is 2.3 MB for 11 folders; one full folder adds ±200 KB. A year means tens of MB in one page. |
| M3 | **Detail is thrown away at build time.** To keep the file from bloating, almost every list is truncated (top 15–300). Some KPIs are then computed from the already-truncated list, so **the numbers are wrong**. | "Pod connection errors" shows 200, actually 1,200 (folder 09-30). The 401 client list is truncated to 30 of 653. The text filter only searches the remaining rows. (inv. §5.2, §8 item 6) |
| M4 | **The display code is one 1,900-line file.** Nine tabs, seven kinds of service page, two languages, and the map are mixed together; changing one tab risks breaking the others. | inv. §2 |
| M5 | **No cross-day view except in the Trends tab.** Account analysis, incidents, and tracing are cut at folder boundaries. | inv. §8 item 12 |
| M6 | **Not fully self-contained and no access control.** Needs a CDN for charts and fonts; the HTML file contains account emails and client IPs and can be copied anywhere. | inv. §8 items 18–19 |

### 1.2 Deliberately left untouched

- **How logs are exported from the cluster** and their folder structure. v2 reads the same folders as they are.
- **Application log formats.** Simpel-loop and coredns stay without timestamps (inv. §8 item 4); adding them
  is work for the application team, not for this migration.
- **Detection rules.** Attack signatures, account-analysis rules, incident grouping, message normalization,
  and the endpoint → business metric mapping are carried over as they are (inv. §4). Detection stays based on
  simple patterns, not a WAF replacement. **[Decided]** Exception: wrong or odd metric definitions
  are fixed; the list is closed, in TRD §4.4. The attack detection rules are replaced by OWASP CRS in the
  final stage (B15), after parity with the old rules has been proven.
- **Content and layout of the analysis tabs.** No new analysis tab and none removed. (The sign-in page
  and the admin page are additions outside the analysis tabs.)
- **The old system and the log folders.** They remain and can still be run, as a baseline for comparison.
- **Real-time alerts, notifications, and integrations** with other systems.

---

## 2. Goals

1. The dashboard content is the same as the old one for the same folder, and this can be proven with numbers;
   the only differences are the listed fixes.
2. Adding one new log folder does not redo work for older folders.
3. Opening the dashboard stays fast once there is a year of data.
4. One tab can be changed without touching other tabs.
5. Privacy does not regress: user IPs are still never sent to third parties.
6. **[New]** Can be opened safely from many computers: only people with an account see the data.
7. **[New]** A new log folder can be brought in without copying files by hand (import from S3).

Non-goals: adding new analyses, replacing monitoring tools (Uptime-Kuma, Rancher), or becoming a SIEM.

---

## 3. Users and their needs

The old system does not record who its users are. The three roles below are **inferred from the tab content**, so
this table of job roles has the status **ASSUMPTION**. What the owner has decided are the access roles, below the table.

| Role (ASSUMPTION) | Questions they want answered | Tabs used | What matters most to them |
|---|---|---|---|
| **Operations / DevOps** — keeping services alive | Was there an outage yesterday? Which service and pod? What caused it? Which endpoints are slow? Are today's logs complete? | Overview, Availability, Pods, Root Causes, Request Tracing, service pages, Trends | Correct error and 5xx counts; able to trace from symptom to the original log line; know when data is incomplete |
| **Security** — monitoring attack attempts and account abuse | Who is scanning us and from which network? Any "successful" (2xx) attacks? Any accounts likely compromised? | Security, IP Map, ingress nginx page | Complete, searchable lists (not just top-N); network owner and location of IPs; no IP leaking outside |
| **Product owner / service management** — monitoring SIMPEL4 usage | How many reports were created? Are OTP and email working? Where do users come from? Up or down compared with yesterday? | Business, Trends, IP Map, Overview | Concise numbers with comparisons; a view readable without understanding logs; Indonesian language |
| **Application developer** (secondary) — fixing bugs visible in the logs | Which errors are most frequent in my service? Which requests failed and from whom? | Service pages, Request Tracing, Root Causes | Grouped error messages with original line samples; full URLs |
| **Dashboard maintainer** (secondary) — whoever runs and changes this dashboard | How do I bring in a new folder? How do I add one card? | — | One command to run; ingest that is safe to repeat; code per tab |

**[Decided]** **Access** roles (distinct from the job roles above) are just two for now:

| Access role | Can |
|---|---|
| **user** | View the whole dashboard (all tabs, all services, all folders); change their own password |
| **admin** | All of that, plus: add, edit, deactivate, delete users; reset passwords; trigger ingest and import; view the audit log |

Anyone from the five job roles above can be given either access role. Restricting a user to particular
pages is deferred (T03).

Shared needs, visible in the old design and kept: two languages (ID/EN), two themes, all times
in WIB, readable on small screens, and direct links to a specific tab.

---

## 4. Features and priorities

- **P0 — parity required**: must exist when v2 is declared to replace the old one.
- **P1 — improvement**: made possible by the new architecture; done if it does not interfere with P0.
- **P2 — deferred**: recorded so it is not lost, not done in this migration.

### 4.1 P0 — parity with the old system required

| ID | Feature | Reference |
|---|---|---|
| F01 | **Ingest** of the seven services with the same parse rules, including ignored lines and `.log.gz` files that are only read when the `.log` is missing | inv. §1.1, §3 |
| F02 | **Shell**: two-group sidebar (Analysis, Services) with badges, folder picker (defaults to the latest folder), title and subtitle, direct links to tabs | inv. §2.0 |
| F03 | **Two languages** ID/EN for all interface text, including automatic finding sentences, number formats, dates, and country names; the choice is remembered | inv. §2.0 |
| F04 | **Two themes** dark/light, including chart and map colors; the choice is remembered | inv. §2.0 |
| F05 | Complete **Overview tab**, including the "System-wide HTTP traffic" section | inv. §2.1 |
| F06 | **IP Map tab**: module filter, 6 KPIs, map with location dots, arcs to the server, tiered region labels, Indonesia/World presets, zoom and pan, legend, flow table, attribution note | inv. §2.2 |
| F07 | Cross-folder **Trends tab**: 6 charts, change table, data completeness table | inv. §2.3 |
| F08 | **Security tab**: 8 KPIs, "Key findings" (9 rules), 6 charts, 5 tables, severity tags | inv. §2.4 |
| F09 | **Root Causes tab**: summary (5 rules), 4 charts, 3 tables | inv. §2.5 |
| F10 | **Availability tab**: 7 KPIs, 3 charts, 4 tables | inv. §2.6 |
| F11 | **Pods tab**: 5 KPIs, 2 charts, 3 tables | inv. §2.7 |
| F12 | **Business tab**: 11 KPIs with comparison, 5 charts, 2 tables | inv. §2.8 |
| F13 | **Request Tracing tab**: 6 KPIs, 2 charts, trace table | inv. §2.9 |
| F14 | **Service page** for each service: KPIs, module map, and 19 cards depending on the service type | inv. §2.10 |
| F15 | **Derived logic** with the same results: attack classification, account analysis, 5xx incidents, request id correlation, IP → pod flow, retries, endpoint percentiles, repeated 401s, business metrics, JWT, PDF report, restarts | inv. §4 |
| F16 | **IP owner and location offline** from downloaded databases; "Ombudsman network" tag; "Internal network" for private IPs | inv. §4.6 |
| F17 | **Comparison with the previous folder** (▲/▼, "incomplete, not compared") with the same comparability rule | inv. §2.0 |
| F18 | **Text filter** on the tables that have a filter today | inv. §2.0 |
| F19 | **Grouped error messages** with an original log line sample (UTC time) | inv. §2.10, §4.7 |
| F20 | **Empty states** that explain why (no nginx, no correlation, empty file) | inv. §2 |
| F21 | **Small-screen view**: navigation moves to the top, tables can scroll | inv. §2.0 |
| F22 | **Attribution** of the IP location source and GeoNames stays visible. **[Decided]** The location source is switched from DB-IP to **MaxMind GeoLite2** (still matched on our own server), so the attribution becomes MaxMind | inv. §6; TRD §3.6 |
| F23 | Same **display format** for numbers, WIB times, durations, and time ranges | inv. §2.0 |

**[New] P0 from owner decisions** (not in the old system; required at handover):

| ID | Feature | Details |
|---|---|---|
| N01 | **Login**: username + password; session expires by itself after inactivity; sign out | TRD §8.2 |
| N02 | **Two roles**, admin and user, enforced on the server | TRD §8.3 |
| N03 | **User management** by an admin: add, change role, reset password, deactivate, delete. No self-registration; the initial password must be changed | TRD §5.6, §8.4 |
| N04 | **Audit log**: sign-ins, user changes, ingest, import | TRD §8.2 |
| N05 | **Access from many computers** over HTTPS | TRD §7 |
| N06 | **A proper mobile view**: drawer navigation, wide tables become row cards, adequate touch targets | DRD §8 |

All user-visible thresholds are kept: slow ≥ 1 second and ≥ 5 seconds, error rate minimum 20
requests, performance minimum 5 requests, incident gap 5 minutes, login window 60 minutes, multi-account ≥ 3
(inv. §5.4).

### 4.2 P1 — improvements made possible by the new architecture

| ID | Improvement | Problem | Notes |
|---|---|---|---|
| B01 | **Incremental ingest**: folders already ingested and unchanged are skipped; changed folders are replaced entirely | M1 | Core of the migration; treated like P0 |
| B02 | **Data fetched per tab and per folder**, not all at once | M2 | Core of the migration; treated like P0 |
| B03 | **KPIs computed from complete data**, not from truncated lists | M3 | **[Decided]** (P4). Differences from the old system are recorded as "expected differences" (§6.2) |
| B04 | **Tables no longer silently truncated**: the initial view stays top-N as today, but the rest can be expanded, and the text filter searches all data | M3 | Initial view limit = old limit (inv. §5.2) |
| B05 | **Corrupt files are flagged** in the Pods tab, Overview, and the Data Completeness table, separately from "empty" | inv. §8 item 3 | Lines are still counted as before so the numbers match |
| B06 | **Honest folder labels**: show the actual log time range next to the folder name | inv. §8 items 1–2 | Does not change the grouping (see A1) |
| B07 | **"Expired refresh tokens" shown** in Root Causes | inv. §8 item 15 | Already computed, only needs displaying |
| B08 | **Attribution everywhere a location is shown**, including the map on service pages | inv. §8 item 17 | |
| B09 | **No CDN dependency**: charts, fonts, and the map work without internet | M6 | **ASSUMPTION A4** |
| B10 | **The "Pods with 502 retries" label** fixed to match its content | inv. §8 item 13 | Text only |
| B11 | **Hard-coded values become configuration**: server IP, host list, upstream DNS | inv. §8 item 20 | Default values = current values |
| B12 | **Display code separated per tab** | M4 | Not visible to users; a maintenance requirement |
| B13 | **[New] Odd definitions fixed**: the nginx/frontend errors-per-hour chart also includes error log lines; `crit` = error in both services; the simpel-loop level donut uses the effective level; "slow ≥ 5 s" includes 3xx | inv. §8 items 7–9, 14 | **[Decided]** (P4). Closed list in TRD §4.4; core figures do not change |
| B14 | **[New] Import log folders from S3**: an admin or the system sends a link `s3://simpel4-backup/k8s-logs/<date>/`; the dashboard downloads and then ingests it | goal 7 | **[Decided]**. Done after parity is proven. Only buckets and prefixes on the allow list (TRD §3.8) |
| B15 | **[New] Attack detection with OWASP CRS, categories named after CAPEC**: replaces the old system's seven hand-written patterns; each finding names the rule ID | inv. §5.1 (simple detection) | **[Decided]** owner request. Done last, after parity is proven, because it changes every number in the Security tab. Approach: match CRS patterns against the URL and User-Agent in the log; inspecting body/header/cookie needs CRS at the ingress (outside this project) |

### 4.3 P2 — deferred

| ID | Item | Why deferred |
|---|---|---|
| T01 | ~~View per WIB calendar date~~ | **[Dropped]** Decided per folder (P2); not planned |
| T02 | **Cross-folder** account analysis, incidents, and tracing | Same: changes the numbers |
| T03 | **Per-module restriction**: restricting a user to particular pages. Also SSO and two-factor authentication | **[Decided]** Two-role login is already in scope (N01–N04); per-module restriction is deferred by owner decision; adding it is localized (TRD §8.3) |
| T04 | Watching folders and ingesting automatically when files appear (replacement for `--watch`) | The automation need is met by S3 import (B14) and scheduled ingest; a file watcher is not needed |
| T05 | Remaining definitions **not** changed: `EXC` lines still do not add to Error (prevents double counting) | **[Decided]** Most of the old T05 is done now (B13); this item is left on purpose (TRD §4.4 item 5) |
| T06 | Table export (CSV), saving links with filters | Not requested yet |
| T07 | Location and owner for IPv6 | The old system does not have it either |
| T08 | Timestamps for simpel-loop and coredns | Needs a change in the source application |
| T09 | Automatic retention (delete data older than N months) | Not needed before there is a year of data. Note (TRD §3.2): a log folder that disappears from disk does **not** remove its data from the dashboard; deletion only through an admin command |

---

## 5. Non-functional requirements

Figures are measured on the same developer laptop as the reference measurement (old build 14.2 seconds for 11
folders), with a year of data simulated from the largest folder (`2026-09-29`: 359 thousand lines, 131 MB).

### 5.1 Display speed

| Measure | Target |
|---|---|
| Opening the dashboard until the Overview of the latest folder is readable | ≤ 2 seconds |
| Switching tab or folder until content is shown | ≤ 1 second (95th percentile) |
| Trends tab with 365 folders of data | ≤ 2 seconds |
| Typing in a table filter until the result changes | ≤ 0.5 seconds |
| Data downloaded to open one tab | ≤ 500 KB, **does not grow** with the number of folders (except Trends) |

### 5.2 Ingest

| Measure | Target |
|---|---|
| Ingesting one folder the size of `2026-09-29` | ≤ 60 seconds |
| Running ingest when there is no new folder | ≤ 5 seconds |
| Re-ingesting the same folder | Identical result, no duplicated data |
| One corrupt file | Logged and skipped; other files still go in; ingest does not stop |
| Initial ingest of all existing folders (11) | ≤ 3 minutes |

### 5.3 Data size

| Measure | Target |
|---|---|
| Planned volume | 365 folders × ±360 thousand lines = ±131 million lines/year; raw logs ±47 GB/year |
| Dashboard storage for one year | ≤ 10 GB (**ASSUMPTION A8**; the exact figure depends on the TRD decision about how much detail is stored) |
| IP location and owner database | ±100 MB, as now |
| Display speed §5.1 | Still met with a year of data |

Raw logs are not moved or deleted by v2.

### 5.4 Privacy

1. **User IPs are never sent to a third-party service**, neither during ingest nor when the dashboard
   is opened. Location and owner are matched from downloaded databases (inv. §6).
2. Downloading those databases only fetches whole files; no IP is included in the request.
3. The browser opening the dashboard does not call external domains (ASSUMPTION A4). This includes the map: it must not
   depend on an online map service.
4. **[Decided]** The dashboard contains personal data (account emails, client IPs, log line samples). It is opened from
   many computers, so **all access is over HTTPS and requires login**; without a session no data leaves.
   Passwords are stored as hashes; admin actions are logged.
5. Location is still treated as a city-level estimate and owner as network owner, not a person's
   identity; the explanatory text is kept.
6. **[New]** AWS credentials for import exist only in the server configuration; they are never sent to the browser,
   never written to logs or the database. The dashboard only reads from allowed buckets and prefixes.

### 5.5 How to run

- **Local: one command** from the project folder to: set up the requirements, ingest the folders not yet
  ingested, then open the dashboard in a local browser. On the first run that command asks for the name and password
  of the first admin.
- **[Decided] Server: one command** `docker compose up -d` (step 7); daily ingest via a scheduled
  task or S3 import.
- Running the same command the next day, after the new folder has been copied, is enough to update.
- Local run: no services to install separately (accounts use an SQLite file). **Server**: accounts are stored
  in PostgreSQL, which is started by the same `docker compose` (owner decision 2026-10-06; TRD K11).
- Still works without internet, provided the IP location/owner database has been downloaded once; if not,
  the dashboard still displays without location and owner, with a note.
- Run instructions fit on one README page.

### 5.6 Maintenance

- Adding or changing one card only touches that tab's code and the data it needs.
- Parse rules and derived logic have automated tests against original sample lines (inv. §3).
- The parity test (§6.2) can be re-run with one command whenever there is a new folder.

---

## 6. Success criteria

### 6.1 Completeness

- Every table row in inv. §2.1–§2.10 (KPIs, charts, tables, notes, filters, empty states) exists in v2,
  checked one by one. Target: **100 %**, with no unwritten exceptions.
- Every interface text has an ID and an EN version; no Indonesian text is left over when EN is selected.
- Both themes are readable in all tabs, including charts and the map.

### 6.2 Numeric parity with the old system

Compared per folder and per service against `00-acuan.json`, which is regenerated from the old system
on the same folder contents.

| Group | Figures | Condition |
|---|---|---|
| Core | lines, requests, 4xx, 5xx, errors, warnings, unique IPs, IP flows | **exactly equal** for all 11 folders × all services |
| Per feature | attack requests and per category, attack URLs, attacker IPs, IPs with 4xx, 401 clients, total 5xx per upstream, incidents, backend pods, retries, pod connection errors, Uptime-Kuma, simpel-loop events, correlation count, slow requests, business metrics, notification emails, activities, restarts, JWT groups, PDF success/failure, login failed/reset/success, accounts analyzed | **exactly equal** |
| List content | For each top-N table: the first N rows of v2 = the old system's rows (keys and values) | equal; order may differ only among rows with equal values |
| Percentiles | P50, P95, P99, maximum per endpoint | equal up to display rounding |
| IP location and owner | country, city, ASN for the same IP | equal when using the same database file |

**[Decided] Expected differences** (resulting from B03 and B13) are recorded in the parity report with the old
value, the new value, and the reason. The list is closed: items 1, 2, 3, 4, and 9 in TRD §4.4. A difference outside
that list = a failure. Core figures (first row of the table above) are not part of the difference list.

### 6.3 Performance and operations

- All targets in §5.1–§5.3 are met and measured, on the data of the 11 real folders and on the 365-folder simulation.
- Adding a 12th folder does not change the figures of folders 1–11 (except the request id correlation figures, which,
  as in the old system, can change when the same request appears in two folders; TRD §3.5) and finishes within
  the limits of §5.2.
- The dashboard opens and works fully with the network turned off.
- Network traffic inspection during ingest and while the dashboard is used: no IP from the logs leaves.
- Someone who has never seen this project can run it from the README in ≤ 10 minutes.
- **[New]** Without a session, every data address answers "not signed in"; an ordinary user cannot call admin
  functions; six wrong passwords lock further attempts; the last admin cannot be deleted.
- **[New]** On a real phone (width 360–390 px): signing in, switching folder, opening every page, and reading
  every table can be done without scrolling the page sideways.
- **[New]** S3 import: a link to a bucket or prefix outside the allow list is rejected before AWS is contacted;
  sending the same link twice does not duplicate data.

### 6.4 Handover

v2 is declared to replace the old system when §6.1–§6.3 are met and the product owner approves the list of
expected differences. The old system is not deleted.

---

## 7. Out of scope

- Changing the log export, application log formats, or cluster configuration.
- New analyses or tabs; changes to attack detection rules.
- Alerts, notifications, scheduled reports.
- **[Decided]** Per-module restriction, SSO, two-factor authentication, self-registration, and "forgot
  password" via email (T03). Two-role login and audit **are** in scope.
- Running on a Kubernetes cluster. Deployment on a single server via Docker Compose **is** in scope (step 7).
- The `recovery-file/` folder and `recovery-file.zip` (not part of the dashboard; inv. §8 item 22).
- Fixing problems found by the dashboard (repeated 401s, missing PDF template, DNS timeouts).

---

## 8. Risks

| # | Risk | Impact | Mitigation |
|--:|---|---|---|
| R1 | ~~The meaning of "day" changed midway~~ | — | **[Dropped]** Decided per folder (P2) |
| R2 | **Parity not reached because of hidden behavior** of the old system (text truncation, ordering of equal values, cross-folder correlation, rounding) | The migration cannot be proven | Inventory §4–§5 as the specification; per-rule tests with original lines; compare from the first stage, not at the end |
| R3 | **Stale reference figures** because log folders keep being added | Wrong comparison | Reference figures are always regenerated right before comparing |
| R4 | **Data grows faster than expected** (volume rises, or too much detail is stored) | Size and speed targets missed | Test with a one-year simulation before the display code is written; T09 as a fallback |
| R5 | **Map**: new map libraries usually use an online map service | Violates §5.4 item 3, or an empty map without internet | The "no online map service" requirement goes into the TRD; use the same land and label data as now |
| R6 | **License and attribution** of IP data not satisfied | Small legal risk, easy to prevent | B08; check the ip2asn license (P6) |
| R7 | **Personal data becomes easier to access** once the dashboard is a service opened from many computers | Leak of account emails and IPs | **[Decided]** HTTPS + login + two roles + audit (N01–N05); the application port is not exposed directly to the network |
| R8 | **Corrupt log files or format changes** without notice (already happened: 3 of 11 folders practically empty) | A day looks "quiet" when its data is actually missing | B05, B06; the Data Completeness table is kept |
| R9 | **Scope creep**: P1 and P2 improvements done before P0 parity is proven | The migration slips, hard to compare | Order: P0 + B01–B03 → parity test → remaining P1 |
| R10 | **Both systems run side by side for too long** | Confusion about which numbers are right | Clear handover criteria §6.4 |
| R11 | **[New] Accounts and passwords managed in-house** | Weak passwords, accounts of former employees stay active, a single admin forgets their password | Passwords at least 12 characters and must be changed at first sign-in; deactivate users; a server command to create a new admin; audit log |
| R12 | **[New] Broad AWS key for import**: read-only, but can see all buckets in the Jakarta region | If the server leaks, other buckets' content can be read too | Allow list of buckets and prefixes in the application, not changeable from the UI; recommendation: a dedicated key that can only read `simpel4-backup/k8s-logs/` |
| R13 | **[New] Server state not yet known** (proxy/HTTPS, outbound access, disk, memory) | Deployment delayed; S3 import or IP database download fails | Checked with commands during deployment; without outbound access the dashboard still runs from the mounted log folder |

---

## 9. List of assumptions

All can be reversed without throwing away major work; the last column explains the cost.

| # | ASSUMPTION | Reason for choosing this | If it turns out wrong |
|--:|---|---|---|
| A1 | **[Decided]** "Day" = **export folder**, as now. The original time of each line is still stored and its range is shown (B06). | Owner decision (P2) | — |
| A2 | **[Decided, changed]** Wrong or odd metric definitions are **fixed** (B03, B13); everything else is replicated exactly. The list of fixes is closed in TRD §4.4. | Owner decision (P4) | — |
| A3 | **[Dropped]** ~~Local only, no login.~~ Replaced by: opened from many computers over HTTPS with two-role login, local accounts. | Owner decision (P1, P3) | — |
| A4 | The dashboard **must work without internet** and does not call external domains from the browser. | Consistent with the privacy rules; removes a dependency that is currently unintended | Allowing a CDN again only relaxes the requirement |
| A5 | User **job** roles = the table in §3 (still an assumption). **Access** roles are decided: admin and user. | Inferred from tab content | P1 priorities rearranged; P0 does not change |
| A6 | Corrupt files **still have their lines counted** as before, and are flagged (B05). | Keeps parity of "Total log lines" | Excluding them changes the line count in 5 folders |
| A7 | The `--watch` mode is **not carried over**; replaced by incremental ingest triggered manually, on a schedule, or by S3 import (B14). | The migration goal says "once per day"; the owner plans automation via the bucket | T04 |
| A8 | Data is kept for **one year**, budget ≤ 10 GB. | The request mentions "data size for a year" | Budget and T09 adjusted |
| A9 | Folders **without a namespace** (09-26, 09-27) are still supported. | Present in the reference figures | Can be dropped at any time |
| A10 | Unknown service folders are still treated as now (Spring Boot parser), **with a warning** during ingest. | Parity with the old one without hiding problems | Change to rejected |
| A11 | `.log` and `.log.gz` are considered identical; the file selection rule is the same as before. | Parity | Rule replaced once P5 is answered |

---

## 10. Open questions for the product owner

Ordered by size of impact. **P1–P4 have been answered** (2026-10-06). New questions that came up
after the TRD are in TRD §11.2 (server, log folder on the server, backups).

| # | Question | Interim assumption | Why it matters |
|--:|---|---|---|
| P1 | ~~Who are the users of this dashboard?~~ | **Answered**: two-role login (admin, user); admin adds users; per-module restriction deferred | — |
| P2 | ~~"Day" per folder or per calendar date?~~ | **Answered**: per folder; new folders will arrive via S3 import | — |
| P3 | ~~Opened on one computer or many?~~ | **Answered**: many computers; login with local accounts | — |
| P4 | ~~Wrong KPIs and odd definitions: replicate or fix?~~ | **Answered**: fix according to good practice (TRD §4.4) | — |
| P5 | Are `.log` and `.log.gz` always identical, and which will continue to be available? | A11 | Ingest rules |
| P6 | ip2asn license: the code says "public domain", not yet checked at the source. Location attribution is now MaxMind GeoLite2 and is shown on every map (already decided). | B08 | License compliance |
| P7 | How long does data need to be kept, and how much disk space is available? | A8 | Size budget |
| P8 | Corrupt files (`unsupported log format`): just flag them, or report them to the team that exports the logs? Is the cause known? | A6 | 3 of 11 folders practically without data |
| P9 | Can simpel-loop and coredns be given timestamps at the source? | no (T08) | Today the simpel-loop per-hour chart covers only 4–70 % of events |
| P10 | Server IP, host list, and upstream DNS: is configuration with the current values enough? Who updates them when they change? | B11 | Map destination point and full URLs |
| P11 | Is automatic ingest needed when a new folder appears? | no (A7) | T04 |
| P12 | Folders without a namespace and unknown services: can they still appear? | A9, A10 | Ingest rules |
| P13 | After v2 is accepted, how long is the old system kept? | not deleted | Handover |
