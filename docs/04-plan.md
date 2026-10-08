# Implementation plan — SIMPEL4 log dashboard (v2)

A staged plan for building v2 according to [`03-trd.md`](03-trd.md) (technical), [`02-drd.md`](02-drd.md)
(design), [`01-prd.md`](01-prd.md) (requirements), and [`00-inventory.md`](00-inventory.md) (reference).
When documents conflict, the order of precedence is: **owner decisions in the TRD (P1–P4) → TRD → DRD → PRD**;
TRD §10 lists the PRD/DRD items that have been dropped.

Originally driven by `migrate/06-eksekusi.md` in the old `dashboard-logging` repo (one stage per session). Since the move
to `apisdsn/MoniShield` the plan is kept here: after each stage, the status table below is updated and deviations are
recorded in that stage's section and in the deviation notes. The current state of the project, open items and how
to continue are in [`09-status.md`](09-status.md).

## How to read this

- **21 stages** (+ 12a, 22, 23 at the owner's request 2026-10-06, 24–31 added later), ordered along the data flow: rules and schema → ingest → aggregates → parity tests → API →
  UI shell → pages one by one → admin screens → import → map, then one improvement
  requested by the owner: attack detection based on the OWASP CRS (Stage 21).
- Each stage can be run and checked on its own. The next stage does not start before this stage's
  verification passes.
- **Verification commands** are run from the repository root (formerly the `v2/` folder) unless stated otherwise. `py` = `.venv/bin/python`,
  `pytest` = `.venv/bin/pytest`.
- The marker **⚠ depends** = the stage uses an ASSUMPTION about a question not yet answered; the stage can still
  be done, but a different answer means rework of the size stated.
- The expected figures apply to the **11 log folders as of 2026-10-06** (`00-reference.json`). Log folders
  grow every day; once they have grown, run `python3 tools/acuan_lama.py` first and compare
  against the new reference. The figures for the 11 old folders must not change.

State of the machine when the plan was written: Python 3.13.1, Node 22.13, npm 10.9, Docker 29.6 present; the `duckdb`
package is not yet installed (installed in Stage 2); **only 17 GB of free disk** (affects Stage 9).

## Status

| # | Stage | Depends on | Open questions | Status |
|--:|---|---|---|:-:|
| 1 | Align the PRD and DRD with the owner decisions | — | — | ☑ 2026-10-06 |
| 2 | Project skeleton and rules module | — | — | ☑ 2026-10-06 |
| 3 | Schema and parser | 2 | — | ☑ 2026-10-06 |
| 4 | Raw table ingest | 3 | X4, X5 | ☑ 2026-10-06 |
| 5 | Core aggregates | 4 | — | ☑ 2026-10-06 |
| 6 | Feature aggregates: attacks, login, correlation, business | 5 | — | ☑ 2026-10-06 |
| 7 | IP data and map files | 4 | P6 | ☑ 2026-10-06 |
| 8 | Parity tests E1, E3, E4 | 5, 6, 7 | — | ☑ 2026-10-06 |
| 9 | Size and performance gate | 8 | P7 | ☑ 2026-10-06 |
| 10 | API: skeleton, login, roles, in-process ingest | 8 | — | ☑ 2026-10-06 |
| 11 | Data API for all pages + parity test E2 | 10 | X6 | ☑ 2026-10-06 |
| 12 | UI shell and shared components | 1, 11 | Q6, Q7, Q8 | ☑ 2026-10-08 (real phone test done by the owner) |
| 12a | Styling following the owner's design reference (tokens, icons, attention cards) for the whole dashboard | 12 | — (R6 answered) | ☑ 2026-10-06 |
| 13 | Service and Overview pages | 12 | — | ☑ 2026-10-06 (service page map: Stage 20) |
| 14 | Trends page | 12 | Q4 | ☑ 2026-10-06 |
| 15 | Security page | 12 | — | ☑ 2026-10-06 |
| 16 | Root Causes and Availability pages | 12 | — | ☑ 2026-10-06 |
| 17 | Pods, Business, Request Tracing pages | 12 | — | ☑ 2026-10-06 |
| 18 | Admin screens: manage users, ingest, audit | 12 | — | ☑ 2026-10-06 |
| 19 | Import from an S3 prefix | 10, 18 | X2, X3 | ☑ 2026-10-07 (real S3 credentials tested through the automatic sync: 12 folders) |
| 20 | IP map | 7, 13 | Q3, Q5, X7 | ☑ 2026-10-06 |
| 21 | Attack detection: OWASP CRS rules, CAPEC categories | 8, 15 | **S1** | ☑ 2026-10-06 |
| 22 | Command Center: world map screen + KPIs + what needs attention (absorbs the IP Map tab) | 12a, 13, 15, 16, 20 | — (R5 answered; ASSUMPTION about merging the IP Map) | ☑ 2026-10-06 |
| 23 | Realtime stream from Kafka to the Command Center | 22 | R1, R2, R4 | ☑ 2026-10-07 reopened by the owner; built as a consumer that writes S3-style folders (deviation 25 (r)) |
| 24 | Additional presentation: change & per hour in the Command Center, new attention items, IP profile + CSV, CRS rule descriptions, global search, data completeness + heatmap in Trends, PDF summary | 21, 22 | — (owner request 2026-10-07, suggestions 1–9) | ☑ 2026-10-07 |
| 25 | Sync data button (new log folders) + application name MoniShield | 18, 24 | — (owner request 2026-10-07) | ☑ 2026-10-07 |
| L7 | Docker Compose (step 7) + VPS deployment guide with automatic HTTPS | 21 | X2, X3, X8 | ☑ 2026-10-07 (`06-docker.md`, `07-deploy-vps.md`) |
| 26 | Standalone repository `apisdsn/MoniShield`, branches dev → stg → prd, Conventional Commits | 25 | — | ☑ 2026-10-07 |
| 27 | Clean architecture: domain / application / infrastructure / interfaces | 26 | — | ☑ 2026-10-07 |
| 28 | English for code, docs, server messages, API values and CLI output; UI stays bilingual | 27 | — | ☑ 2026-10-08 |
| 29 | Kafka folders labelled "(Kafka)" | 23 | — | ☑ 2026-10-08 |
| 30 | GitHub Actions CI + automatic deployment of `prd` | 26 | — | ◐ 2026-10-08 built and green on `dev`; the first real deploy waits for the promotion to `prd` |
| 31 | Documentation in English (file names too) + hand-over for local work | 28 | — | ☑ 2026-10-08 |
| 32 | Encrypted request/response bodies for the web UI | 27 | — | ☑ 2026-10-08 |
| 33 | Data retention (database, inbox) | 27 | — | ☑ 2026-10-08 |
| 34 | Notification thresholds per number and per service | 27 | — | ☑ 2026-10-08 |

After Stage 21 the old repo's `migrate/07-docker-compose.md` was done as step **L7** (`06-docker.md`); the equivalence
report (`migrate/08-kesetaraan.md` there) is produced by `tools/laporan_kesetaraan.py` here.

### The most decisive questions

| Question | Assumption used | If the answer is different |
|---|---|---|


| **Command Center** (TRD §11.2, §12) — **decided 2026-10-06**: the log folder remains the main source, Kafka postponed (R3); Overview stays, Command Center = world map screen (R5); reference styling for the whole dashboard (R6). Still an ASSUMPTION: the "IP Map" tab is merged into the Command Center | A single map page; the "IP Map" sidebar entry becomes "Command Center" in the same position | Stages 20 and 22: if the IP Map stays separate, the Command Center reuses the same map component (small addition) |
| **S1** attack detection: (a) the "in the script" way or also "in the ingress"? (b) old view replaced or side by side? (c) CRS paranoia level? | (a) in the script only; the ingress way is proposed to the cluster administrators. (b) CAPEC categories **replace** the old categories in the view; the old classification is still stored for tests. (c) Paranoia level 1 (fewest false positives) | Stage 21 only. If the ingress later runs CRS, the dashboard needs a parser for the ModSecurity/Coraza audit log: a new stage |

All other questions only change a default value or a single component.

**Already decided by the owner** (no longer assumptions): IP location uses MaxMind GeoLite2 (the account and license
key are already in `.env`, already tested as accepted by MaxMind); for now only the admin and user roles, users
see the whole dashboard, admins can add users; per-module restrictions postponed (X10); import from an S3 prefix with fixed access keys, region
Jakarta, so it can be automatic (X9); local accounts in the application database, no SSO (X1);
the definition fixes in TRD §4.4 approved (X11); the phone layout is done seriously (Q1), so DRD §8
applies in full, including wide tables becoming row cards.

---

## Stage 1 — Align the PRD and DRD with the owner decisions

**Goal.** The PRD and DRD were written before P1–P4 were answered. This stage updates them according to TRD §10 and
designs the new screens in TRD §8.4, so that the UI stages do not read assumptions that have been dropped.
Documents only; no code.

**Files changed**

- `docs/01-prd.md`: A1, A2, A3, A5 become decisions; T01 withdrawn; T03 and part of T05 move into scope;
  new features (two-role login, manage users, audit, S3 import) go into §4, per-module access rights go into the
  postponed list; §5.4, §5.5, §6.2, §7, R7 according to
  TRD §10; P1–P4 marked answered.
- `docs/02-drd.md`: §1 and §2 (user menu in the header; admin items only for admins); new section
  "Sign-in and admin" with sketches of the Sign in, Change password, Manage users, Ingest & import screens; §6.6–§6.7
  gain "no access" and "session expired"; U8 (Error explanation, `EXC`, simpel-loop level); flow
  table 100 rows; §6.5 loads per page; D7 and Q2 marked dropped; Q1 marked answered (phone done seriously).

**Verification**

| Command (from the project folder) | Expected result |
|---|---|
| `grep -c "hanya dibuka di komputer" docs/01-prd.md` | `0` |
| `grep -n "Kelola user\|Tidak punya akses\|Sesi habis" docs/02-drd.md` | all three found |
| Read TRD §10 line by line | every line has a counterpart in the PRD/DRD |


---

## Stage 2 — Project skeleton and rules module

**Goal.** The Python environment runs, the configuration is read, and the old system's rules are copied as-is with
proof that the copy is identical (TRD §4.1, §9.2).

**Files created**

- `pyproject.toml` (dependencies: `duckdb`, `fastapi`, `uvicorn`; tests: `pytest`, `httpx`), `.gitignore`
  (`data/`, `.venv/`, `web/node_modules/`, `web/dist/`).
- `monishield/__init__.py`, `monishield/__main__.py`, `monishield/cli.py` (only the `status` subcommand so far).
- `monishield/config.py` (TRD §6.3; defaults = the old constants), `config.example.toml`.
- `monishield/rules.py`: a copy of the regexes and functions in TRD §4.1, each block annotated with its original line number.
- `tests/test_rules.py`: (a) the contents of the old `demo()`; (b) comparison with `build_dashboard.py` for
  `classify`, `path_key`, `norm`, `jwt_bucket`, `accounts`, `incidents`, `ip_owner`, `geo_scan` on real
  input taken from the logs (at least 5,000 paths, 500 UAs, 500 messages); skipped when the old module is absent.
- `tests/conftest.py` (log folder location, old module).

**Verification**

| Command | Expected result |
|---|---|
| `python3 -m venv .venv && .venv/bin/pip install -e ".[test]"` | finishes without errors |
| `pytest tests/test_rules.py -q` | all pass, 0 skipped (old module present) |
| `py -m monishield status` | prints the effective configuration: log folder, data directory, cache; "no database yet" |
| `ls -la ../build_dashboard.py ../dashboard_template.html` | the modification dates of both old files are unchanged (not touched) |

---

## Stage 3 — Schema and parser

**Goal.** The DuckDB tables are defined (TRD §2.1–§2.3) and the parser turns log lines into table rows
with per-file counters equal to the old `parse()` (TRD §4.2), except for the `crit` fix (TRD §4.4
item 3).

**Files created**

- `monishield/schema.sql`: control, raw, and aggregate tables; views.
- `monishield/db.py`: opens the database, applies the schema (safe to repeat), memory limit.
- `monishield/parse.py`: one function per service type; output is a CSV per table + a file summary (`lines`,
  `err`, `warn`, `corrupt_lines`, `file_counter`); can be run on its own for a single file.
- `tests/fixtures/lines/*.txt`: real lines per format from inventory §3 and §4.1 (account names masked).
- `tests/test_parse.py`: (a) per sample line → the expected output row and counter changes;
  (b) for each real log file in three folders (`2026-09-27`, `2026-09-29`, `2026-10-06`): `lines`, `err`,
  `warn`, and the count per level equal the old `parse()` on the same file.

**Verification**

| Command | Expected result |
|---|---|
| `pytest tests/test_parse.py -q` | all pass |
| `py -m monishield.parse ../2026-10-06/ingress-nginx/nginx-ingress-controller/*5v8j4*.log --out /tmp/s4parse` | summary: `lines=111301`; files `nginx_access.csv`, `nginx_error.csv`, `log_message.csv` created |
| `py -c "from monishield import db; db.open(':memory:')"` then list the tables | all TRD §2 tables exist; running it twice gives no error |

Note: the frontend `crit` level fix (TRD §4.4 item 3) does not change any figure on the current data,
because there are no `crit` lines.

---

## Stage 4 — Raw table ingest

**Goal.** `monishield ingest` fills the raw tables and control tables from the log folder, incrementally and safe
to repeat (TRD §3.1–§3.3). No aggregates yet.

**Files created**

- `monishield/ingest.py`: scans two roots (log folder, inbox), fingerprint (size + mtime, then
  SHA-256 of the decompressed content), parse in a subprocess, load CSV, one transaction per folder, `ingest_run`.
- `monishield/cli.py`: subcommands `ingest [--folder] [--force]`, `forget <folder>`, full `status`.
- `tests/fixtures/logs_mini/`: a small synthetic log folder (two dates, all service types, one corrupt file,
  one `.log`/`.log.gz` pair, one folder without a namespace).
- `tests/test_ingest.py`: all items of TRD §9.4.

**Verification**

| Command | Expected result |
|---|---|
| `pytest tests/test_ingest.py -q` | all pass |
| `time py -m monishield ingest` (empty database) | finishes in ≤ 3 minutes; 11 folders, 195 files, 0 failed |
| `py -m monishield status` | total lines 774,264; `nginx_access` 308,158; `fe_access` 148,049; `sl_event` 114,574; files with 0 lines: 52 |
| `time py -m monishield ingest` (second time) | ≤ 5 seconds; "0 files changed" |
| `py -m monishield status --checksum` before and after the second ingest | checksum of every table is the same |
| `ls -la ../2026-10-06 ../.cache` | no new or changed files in the log folder |

Lines per folder (Σ `ingest_file.lines`) must equal the "total" column of inventory §7, e.g. `2026-09-29`
= 359,009 and `2026-10-06` = 191,898.

⚠ **Depends on X4** (folder disappears → data kept, T2) and **X5** (`.log` wins over `.gz`):
both are one small branch in `ingest.py`.

---

## Stage 5 — Core aggregates

**Goal.** The aggregates underlying the core figures and the service page are derived with SQL per folder
(TRD §3.4, §4.3): `agg_service`, `agg_hour` (except simpel-loop), `agg_status`, `agg_endpoint`,
`agg_endpoint_error`, `agg_ip`, `agg_upstream`, `agg_ua`, `agg_level`, `agg_message`, `agg_slow`,
`agg_flow`, `agg_pod`, `agg_retry`, `agg_c401`, `agg_uk_hour`, `agg_uk_target`, `folder_state`, and the views
`v_upstream_error`, `v_restart`, `v_dns`.

**Files created**

- `monishield/derive/__init__.py` (runs the SQL files in order for one folder, inside the ingest
  transaction) and one `monishield/derive/NN_<tabel>.sql` per aggregate above.
- `monishield/cli.py`: subcommand `derive [--folder | --all]`.
- `tests/test_derive_core.py`: on `logs_mini`, the value of each aggregate computed by hand; percentiles use the
  old index rule; "the first" follows the order (`relpath`, `line_no`).

**Verification**

| Command | Expected result |
|---|---|
| `pytest tests/test_derive_core.py -q` | all pass |
| `py -m monishield derive --all` | 11 folders derived without errors |
| `py -m monishield status --folder 2026-09-29` | nginx: requests 132,203, 4xx 4,635, 5xx 59, errors 94, warnings 164, unique IPs 723, flows 1,762; simpel-loop: requests 60,665, warnings 9,614 |
| `py -m monishield status --folder 2026-09-30` | nginx: errors 1,690; pod connection errors 1,200; retries 825 |
| Run `derive --all` twice, compare `status --checksum` | the same |

Includes the TRD §4.4 fixes, items 2 and 4 (the hourly chart includes error log lines; effective simpel-loop level).

---

## Stage 6 — Feature aggregates: attacks, login, correlation, business

**Goal.** The remaining aggregates: `agg_attack_url`, `agg_attack_ip`, `agg_attack_hour`, `v_attack_cat`,
`agg_login_ip`, `agg_login_hour`, `agg_account` (the old `accounts()` function), `agg_incident` (the old
`incidents()` function), `agg_corr`, `agg_trace`, simpel-loop `agg_hour` (cross-folder correlation, TRD §3.5),
`agg_biz`, `agg_mail`, `agg_activity`, `agg_jwt`, `agg_report`.

**Files created**

- `monishield/derive/NN_<tabel>.sql` for each aggregate above; `monishield/derive/accounts.py`,
  `monishield/derive/incidents.py` (call the functions in `rules.py` on the results of small queries).
- Re-derivation of the correlation aggregates for other affected folders (TRD §3.5), in `ingest.py`.
- `tests/test_derive_features.py`: values computed by hand on `logs_mini`, including one request id that
  matches across folders and one duplicate request id.

**Verification**

| Command | Expected result |
|---|---|
| `pytest tests/test_derive_features.py -q` | all pass |
| `py -m monishield derive --all && py -m monishield status --folder 2026-09-29` | attacks 155 requests / 77 URLs / 12 IPs; correlation 22,638 of 60,665; trace 300+ rows (not truncated); failed logins 86, resets 24, successes 389; accounts analysed 39; incidents 7; PDF 813 succeeded / 32 failed |
| `py -m monishield status --folder 2026-10-06` | attacks 88; correlation 4,161 of 5,981; "Laporan Dibuat" 7 |
| `time py -m monishield ingest --folder 2026-09-29 --force` | ≤ 60 seconds (parse + load + derive) |

Includes the TRD §4.4 fix, item 9 ("slow ≥ 5 s" includes 3xx); accounts and incidents stay per folder (item 7).

---

## Stage 7 — IP data and map files

**Goal.** `ip_info` is filled offline for all IPs (TRD §3.6) and five static map files are available (TRD
§5.7). No IP is sent outside.

**Files created**

- `monishield/refdata.py`: downloads into the cache (old age rule), owner (`ip_owner`), location (`geo_scan`),
  generation of `data/map/land.geojson`, `borders-country.geojson`, `borders-province-id.geojson`,
  `labels.json`.
- Called at the end of ingest; subcommand `refdata [--offline]`.
- `tests/test_refdata.py`: with a synthetic mini database file: private IPs, IPs outside the ranges, IPv6, a new
  IP after the second ingest; failed download → ingest still finishes.

**Verification**

| Command | Expected result |
|---|---|
| `pytest tests/test_refdata.py -q` | all pass |
| `py -m monishield refdata` (old cache `../.cache` used) | no new download; `ip_info` filled |
| `py -m monishield status` | IPs with an owner ≥ 1,734; IPs with a location ≥ 1,676; server in Jakarta (−6.17494; 106.822) |
| `ls -la data/map/` | 4 files; `labels.json` contains 177 countries / 38 provinces / 514 regencies-cities |
| `py -m monishield refdata --offline` with the network turned off | finishes, without errors |

**Decided by the owner (2026-10-06): IP location from MaxMind GeoLite2** (TRD §3.6), not DB-IP. Consequences for
this stage:

- `refdata.py` downloads `GeoLite2-City-CSV` with `MAXMIND_ACCOUNT_ID`/`MAXMIND_LICENSE_KEY` from `.env`,
  turns the CIDR blocks into sorted ranges, and uses the same `geo_scan()` sweep. `config.py`
  gets those two keys (secret: not printed).
- The verification in the table above changes: `py -m monishield refdata` **downloads** GeoLite2 (±49 MB) on the first
  run; "IPs with a location ≥ 1,676" is replaced by "≥ 95 % of public IPs have a location" (the old figure came from
  DB-IP); the server point stays in Jakarta but its coordinates may differ.
- Additional verification: without a key → ingest finishes, locations empty, with an explanation; the key does not appear in
  the `status` output, the logs, or the database; 20 sample IPs compared with the old DB-IP, city differences
  recorded (not a failure).
- The network owner stays ip2asn (ASSUMPTION T15), so the figure "IPs with an owner ≥ 1,734" still applies.

⚠ **Depends on P6** (the ip2asn license has not been checked; only affects the attribution text, not the code).
The province boundary source (Natural Earth 10m) is a new download, public domain; the match with the 38 provinces
is recorded for Q3 and used in Stage 20.

---

## Stage 8 — Parity tests E1, E3, E4

**Goal.** Prove that the v2 figures equal the old system's before there is an API and UI (PRD §6.2, R2, R9;
TRD §9.3).

**Files created**

- `tools/ekstrak_dashboard.py`: extracts the `D` object from `../dashboard.html` → JSON.
- `tools/acuan_lama.py` (already exists): extended with the "should be" values for items 2, 4, 9 of TRD §4.4, computed
  from the old system's raw statistics.
- `tests/test_equivalence.py`:
  - **E1** every figure of `00-reference.json` × (folder, service) vs the aggregate query → exactly equal.
  - **E3** `D.ipinfo` and `D.geo` vs `ip_info`.
  - **E4** closed list of differences (TRD §4.4 items 1, 2, 3, 4, 9): old value, new value, should-be value.
- `tools/laporan_kesetaraan.py`: prints a table of equal / different / expected differences.

**Verification**

| Command | Expected result |
|---|---|
| `python3 tools/acuan_lama.py` | `docs/00-reference.json` updated; the figures of the 11 old folders do not change |
| `pytest tests/test_equivalence.py -q` | all pass |
| `py tools/laporan_kesetaraan.py` | E1: 0 different out of all figures; E3: 0 different; E4: only the listed items, e.g. pod connection errors `2026-09-30` old 200 → new 1,200 |

If there is a difference outside the list: **stop**, find its cause in Stages 3–6; the list of differences must not be
extended without the owner's approval.


---

## Stage 9 — Size and performance gate

**Goal.** Confirm or reject ASSUMPTION T1 (one year of data ≤ 10 GB) and the query speed targets,
before the API and UI are built on top of this schema (PRD §5.1–§5.3, R4; TRD §9.7).

**Files created**

- `tools/simulasi_setahun.py`: duplicates the raw rows of folder `2026-09-29` into N folder dates in a
  **separate** database (`data/sim.duckdb`), then derives the aggregates.
- `tools/ukur.py`: file size per table; time of the queries each page will use (from aggregates); time to
  ingest one additional folder; time of an ingest without changes.
- `docs/04a-measurements.md`: measurement results and the decision.

**Verification**

| Command | Expected result |
|---|---|
| `df -h .` | enough space; **if free < 15 GB, use `--folders 90`** and extrapolate ×4.06 |
| `py tools/simulasi_setahun.py --folders 365` (or 90) | finishes; simulation database created |
| `py tools/ukur.py data/sim.duckdb` | one-year size ≤ 10 GB; query per page ≤ 200 ms; Trends over 365 folders ≤ 500 ms; ingest of one folder ≤ 60 seconds; without changes ≤ 5 seconds |
| `rm data/sim.duckdb` | space reclaimed |

**Gate.** If the size is > 10 GB: apply the T1 fallback (dictionary tables for `ua`/`path`), repeat Stages 4–8,
measure again. If it still misses: stop and ask for a decision (P7).

⚠ **Depends on P7** (how long data is kept, how much disk is available).

---

## Stage 10 — API: skeleton, login, roles, in-process ingest

**Goal.** The server runs as a single process that owns DuckDB (TRD K1), with login, sessions, two
roles (admin, user), audit, and an ingest trigger (TRD §5.2, §5.5, §5.6, §8.1–§8.3). No page endpoints yet.

**Files created**

- `monishield/auth.py`: ORM model of accounts in PostgreSQL/SQLite (TRD §2.6, K11), scrypt hash, JWT session in a cookie, lockout, CSRF, audit, machine token,
  "requires session" and "requires admin" dependencies.
- `monishield/api/app.py`: FastAPI application, one DuckDB connection, error format, security headers (CSP),
  static file serving, a startup check that "every router declares a role".
- `monishield/api/common.py`: parameter validation (TRD §8.1), IP cell + owner, table endpoint skeleton.
- `monishield/api/session.py` (`/api/auth/*`, `/api/me`), `users.py` (`/api/admin/users`, `audit`),
  `admin.py` (`/api/admin/ingest`, `status`, `derive`, `forget`), endpoints `/api/health`, `/api/meta`,
  `/api/folders/{folder}`.
- `monishield/cli.py`: `serve`; `user create --admin`; `ingest`/`derive`/`forget` try the API first (machine
  token), and only open DuckDB themselves when the server is down.
- `run.sh`: environment, first admin, build the frontend if present, `serve`.
- `tests/test_auth.py`, `tests/test_api.py` (skeleton part): items of TRD §9.6 except import.

**Verification**

| Command | Expected result |
|---|---|
| `pytest tests/test_auth.py tests/test_api.py -q` | all pass |
| `S4_ADMIN_USER=admin S4_ADMIN_PASSWORD='<password 12+>' S4_COOKIE_SECURE=false py -m monishield serve &` | listens on `127.0.0.1:8000`; initial ingest "0 files changed" |
| `curl -s -o /dev/null -w "%{http_code}" localhost:8000/api/meta` | `401` |
| `curl -s -c /tmp/c -H 'Content-Type: application/json' -d '{"username":"admin","password":"…"}' localhost:8000/api/auth/login`, change the first password (`POST /api/me/password`), then `curl -s -b /tmp/c localhost:8000/api/meta` | list of 11 folders with time ranges; `ingest.running: false` |
| `curl -s -b /tmp/c localhost:8000/api/folders/2026-10-06` | 7 services; nginx `err` 125; `attack_ip_count` 14 |
| The admin creates user `uji` (role user); signed in as `uji`: `GET /api/folders/2026-10-06`, then `GET /api/admin/users` | the first 200 with 7 services (same as admin); the second `403` |
| `py -m monishield ingest` while the server is running | goes through the API; "0 files changed"; no file lock error |
| `curl -sI -b /tmp/c localhost:8000/api/meta` | headers `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy` present |
| Six logins with a wrong password | the 6th attempt → `429` |

Local accounts (X1) and two roles without per-module restrictions (X10) are already decided; there are no open
questions for this stage.

---

## Stage 11 — Data API for all pages + parity test E2

**Goal.** Ten page endpoints and the table endpoint (TRD §5.3–§5.4), open to both roles
(TRD §8.3), and the list contents proven equal to the old system (E2).

**Files created**

- `monishield/api/overview.py`, `map.py`, `trends.py`, `security.py`, `rootcause.py`, `availability.py`,
  `pods.py`, `business.py`, `tracing.py`, `service.py`: one module per page.
- `monishield/api/common.py`: definitions of 25 tables (columns, sortable columns, text columns for `q`, default
  limit).
- `tests/test_api.py` (continued): response shape, `available: false`, validation and injection attempts on
  each parameter, response size ≤ 500 KB, a **role matrix** built from the TRD §8.3 table.
- `tests/test_equivalence.py` (continued) **E2**: each list in `D` vs the API response with `limit` = the old
  limit.

**Verification**

| Command | Expected result |
|---|---|
| `pytest tests/test_api.py -q` | all pass; the role matrix covers all endpoints |
| `pytest tests/test_equivalence.py -q` | E1–E4 pass; E2: each list is equal (order may differ only among equal values) |
| `curl -s -b /tmp/c localhost:8000/api/folders/2026-10-06/security \| py -m json.tool \| head -20` | `kpi.attack_requests` 88, `attack_ips` 14 |
| `curl -s -b /tmp/c "localhost:8000/api/folders/2026-09-30/availability"` | KPI pod connection errors 1,200 |
| `curl -s -b /tmp/c "localhost:8000/api/folders/2026-09-28/map"` | `available: false`, `reason: "no_nginx"` |
| `curl -s -b /tmp/c "localhost:8000/api/folders/2026-09-29/tables/c401?limit=5&q=count"` | `total` 653; ≤ 5 rows; `matched` ≤ 653 |
| `curl -s -o /dev/null -w "%{http_code}" -b /tmp/c "localhost:8000/api/folders/2026-09-29/tables/c401?sort=1;drop"` | `400` |
| `py tools/ukur.py --api localhost:8000` | each page endpoint ≤ 300 ms and ≤ 500 KB on folder `2026-09-29` |

⚠ **Depends on X6** (flow table of the first 100 rows; one figure).

---

## Stage 12 — UI shell and shared components

**Goal.** A Svelte application with the shell, login, two languages, two themes, loading/empty/failed states, and
all shared components (DRD §2, §4, §5, §6, §8, §9), tested with one sample page. No data pages
yet.

**Files created**

- `web/package.json`, `vite.config.js`, `index.html`; dependencies per TRD §6.4.
- `web/src/theme.css` (tokens per DRD §5.1–§5.5), fonts bundled.
- `web/src/i18n/id.json`, `en.json`, `i18n.js`; `tools/cek_i18n.mjs` (the keys of both files must be the same).
- `web/src/state.js` (tab, folder, module ↔ URL), `api.js` (401 → Sign in screen; 403 → "no access"),
  `format.js` (WIB time, durations, numbers, ranges; equivalents of the old formatters).
- `web/src/App.svelte`; `web/src/lib/`: `Sidebar`, `Header`, `FolderPicker`, `UserMenu`, `Kpi`,
  `ChartCard`, `HBar`, `DataTable`, `IpCell`, `SeverityTag`, `StatusCode`, `Alert`, `Note`, `Skeleton`,
  `EmptyState`, `ErrorState`.
- `web/src/pages/Login.svelte`, `ChangePassword.svelte`, `Placeholder.svelte`.
- `tests/test_format.mjs`: formatters vs the examples in inventory §2.0.

**Verification**

| Command | Expected result |
|---|---|
| `cd web && npm ci && npm run build` | `web/dist/` created without error warnings |
| `node tools/cek_i18n.mjs` | "keys match: N" |
| `node --test tests/test_format.mjs` | passes (`28 Sep 2026 06.03 WIB`, `2,35 dtk`, `1 mnt 52 dtk`, EN `06:03`) |
| `grep -rEoh "https?://[^\"' )]+" web/dist \| sort -u` | only attribution links (maxmind.com, geonames.org, naturalearthdata.com) and XML schemas |
| `./run.sh` then open `http://127.0.0.1:8000` | Sign in screen → after signing in: sidebar with two groups and badges (Security `14 IP`), folder picker with 11 folders, subtitle includes the log time range |
| In the browser: change language, theme, folder; reload the page | language/theme choice remembered; folder and tab are in the address |
| Sign in as a regular user | sidebar same as admin; user menu without "Manage users" and "Ingest & import"; admin screen address → "no access" |
| Window width 390 px and 360 px | navigation drawer; KPIs in 2 columns; tables with > 4 columns shown as row cards; touch targets ≥ 44 px; no horizontal page scroll |
| A real phone (not only emulation), via the local network address | sign in, change folder, open the drawer, scroll a table: all comfortable with one hand |
| Keyboard Tab from the top | "Skip to content" → navigation → header; focus always visible |
| Stop the server while the app is open | "Not connected" band; recovers on its own when the server is back |

Serious phone layout (Q1, decided): the table-to-cards mode in `DataTable` and the navigation drawer are **required**
in this stage. ⚠ **Depends on Q6** ("–" vs 0 in `Kpi`), **Q7** (column sorting,
copy, `(i)`, "view as table", shortcuts: may be postponed without changing other stages), **Q8** (logo).
Needs Stage 1 for the Sign in screen sketch.

---

## Stage 13 — Service and Overview pages

**Goal.** The service page template (DRD §3.10, inventory §2.10) and Overview (DRD §3.1, inventory §2.1),
which uses the nginx service cards. The map on the service page follows in Stage 20.

**Files created**

- `web/src/pages/Service.svelte`, `web/src/lib/ServiceCards.svelte` (cards 2–19, also used by Overview),
  `MessagesTable.svelte` (expanded row + original log sample), `web/src/pages/Overview.svelte`.
- New dictionary keys in `id.json`/`en.json`.
- `docs/04b-page-checklist.md`: checklist of pages × {ID, EN} × {dark, light} × {wide, narrow},
  built from inventory §2; used by Stages 13–20.

**Verification**

| Command | Expected result |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | passes |
| Open the Overview of folder `2026-10-06` in v2 and `../dashboard.html` side by side | same KPIs: lines 191,898, errors 2,810, warnings 856, HTTP requests 124,822, 4xx rate 3.6 %, 5xx rate 0.04 %, services 7, files 18; same delta ▼ vs 5 Oct; same tables and top 25 messages |
| Open the pages `nginx-ingress-controller`, `om-be-simpel-loop`, `om-be-appsmanager`, `coredns` | the cards shown match the checkbox table of inventory §2.10; coredns titled "domains failing to resolve" |
| The nginx "Activity per hour" chart | the Error line includes error log lines (expected difference, TRD §4.4 item 2) |
| The simpel-loop level donut of folder `2026-09-29` | WARN 9,614, no ERROR (item 4) |
| Folder `2026-10-01` | band "this folder contains only 4 lines; corrupt file"; the service page shows the empty state |
| Message table filter: type `JWT` | only matching rows; "N matching rows" |
| Checklist `04b` for these two pages | all items ticked in 2 languages × 2 themes × 2 widths |

---

## Stage 14 — Trends page

**Goal.** DRD §3.3, inventory §2.3.

**Files created.** `web/src/pages/Trends.svelte`; dictionary keys.

**Verification**

| Command | Expected result |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | passes |
| Open Trends side by side with the old dashboard | 6 charts and 2 tables equal for 11 folders; column `2026-09-30` simpel-loop "None"; `2026-10-01` "Corrupt"/"Empty" |
| Folder picker in the header | disabled with an explanation |
| Range picker 14 / 30 / 90 / all | number of columns changes; the table scrolls horizontally, the Service column is pinned |
| Checklist `04b` | complete |

⚠ **Depends on Q4** (default range 30; one value).

---

## Stage 15 — Security page

**Goal.** DRD §3.4, inventory §2.4, including the 9 "Key findings" rules composed from components (not HTML
in a string).

**Files created.** `web/src/pages/Security.svelte`, `web/src/lib/Findings.svelte`, `AttackUrl.svelte` (full
URL with the base host); dictionary keys (finding sentences in two languages).

**Verification**

| Command | Expected result |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | passes |
| Folder `2026-10-06` side by side with the old one | 8 KPIs: 88, 14, 5, 62, 9, 1, 0, 4; the same six finding items (Log4Shell, Rancher, 62 2xx endpoints, cloud, Ombudsman network, 4 resets); 6 charts; 5 tables |
| Folder `2026-09-28` (no nginx) | note "per-URL attack detection not available"; the login section remains |
| Table "Endpoints with suspected attacks": URL containing `<script>` or `${jndi:` | shown as text; not executed (check the browser console is clean) |
| `grep -rn "@html" web/src` | no use on log data |
| Checklist `04b` | complete |

---

## Stage 16 — Root Causes and Availability pages

**Goal.** DRD §3.5–§3.6, inventory §2.5–§2.6.

**Files created.** `web/src/pages/RootCause.svelte`, `Availability.svelte`; dictionary keys.

**Verification**

| Command | Expected result |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | passes |
| Root Causes `2026-09-29` side by side with the old one | the 5-item summary equal; the JWT chart equal; **new**: "Expired refresh tokens: 237"; the 401 table shows 30 of 653 with "show next" |
| Availability `2026-09-30` | KPI pod connection errors **1,200** (old: 200) and retries **825**; 10 incidents; otherwise equal |
| Availability `2026-09-28` | note "uses the nginx ingress log…" |
| Checklist `04b` | complete |

---

## Stage 17 — Pods, Business, Request Tracing pages

**Goal.** DRD §3.7–§3.9, inventory §2.7–§2.9.

**Files created.** `web/src/pages/Pods.svelte`, `Business.svelte`, `Tracing.svelte`; dictionary keys.

**Verification**

| Command | Expected result |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | passes |
| Pods `2026-10-06` side by side with the old one | same KPIs; label "Pods with retries"; status "Corrupt" on corrupt files |
| Business `2026-09-29` | Reports created 12, Registrations 108, OTPs requested 35, OTPs verified 12, Files uploaded 314, Uploads rejected 18, Emails sent 55, PDF 813 / 32, Successful logins 389 |
| Business `2026-09-30` (no simpel-loop) | simpel-loop KPIs "–" with an explanation, not 0 |
| Tracing `2026-09-29` | 60,665 / 22,638 / 37.3 %; trace table of the first 300 with "show next" |
| Tracing `2026-09-27` | note "needs the simpel-loop and nginx ingress logs…" |
| Checklist `04b` | complete |

---

## Stage 18 — Admin screens: manage users, ingest, audit

**Goal.** The screens in TRD §8.4 (designed in the DRD in Stage 1), on top of the Stage 10 API.

**Files created.** `web/src/pages/AdminUsers.svelte`, `AdminIngest.svelte` (ingest status, "Ingest
now" button, audit log); dictionary keys.

**Verification**

| Command | Expected result |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | passes |
| As admin: add a new user (role user); sign in as that user in another window | must change password; then sees the whole dashboard like an admin, without the admin menu |
| The admin promotes that user to admin, then demotes them again | the admin menu appears and then disappears on the next request |
| The admin resets the password / deactivates the user | the user's session ends immediately |
| Try to delete or demote the only admin | refused with a message |
| Sign in as a regular user, open the admin screen address | "no access"; `GET /api/admin/users` → 403 |
| "Ingest now" | status running → done, "0 files changed"; the dashboard can still be opened while it runs |
| Audit log | all the actions above recorded with time, actor, IP; without passwords or tokens |
| Checklist `04b` for the admin screens | complete |


---

## Stage 19 — Import from an S3 prefix

**Goal.** TRD §3.8: link `s3://simpel4-backup/k8s-logs/<YYYY-MM-DD>/` → list objects → download to the
inbox → normal ingest. Credentials: fixed access keys in the server's `.env` (import can be automatic); an admin can
paste other credentials as a fallback (in memory only).

**Files created**

- `pyproject.toml`: optional extra `s3` containing `boto3`.
- `monishield/importer.py`: link checks (shape, bucket and prefix allowlist, date), object
  listing, selection (key pattern, `.log` wins over `.log.gz`, skip those whose size + ETag are the same), bounded
  download to a temporary directory, atomic move to the inbox, `import_job`, dry-run mode, in-memory storage of
  temporary credentials.
- `monishield/api/admin.py`: `POST /api/admin/import`, `GET /api/admin/import/{job_id}`,
  `POST`/`DELETE /api/admin/import/credentials`.
- `monishield/cli.py`: `import [--dry-run] s3://…`.
- `web/src/pages/AdminIngest.svelte`: link field, "Dry run" and "Import" buttons, import status, temporary
  credentials form with an expiry note.
- `tests/s3_tiruan.py` (a small S3 server for tests) and `tests/test_import.py`: the import and credentials items
  in TRD §9.6.
- `README.md` (import section): an example read-only IAM policy and how to fill in `.env`.

**Verification**

| Command | Expected result |
|---|---|
| `.venv/bin/pip install -e ".[test,s3]" && pytest tests/test_import.py -q` | all pass, without contacting AWS |
| Without `import_buckets`: `py -m monishield import s3://simpel4-backup/k8s-logs/2026-09-26/` | refused: "import is not enabled" |
| `py -m monishield import s3://bucket-lain/k8s-logs/2026-09-26/` and `…/k8s-logs/bukan-tanggal/` | both refused with a reason |
| Without credentials: import a valid link | message on how to provide credentials; no files written |
| **Manual, with real credentials**: `py -m monishield import --dry-run s3://simpel4-backup/k8s-logs/2026-09-26/` | list of objects; for each object "fetch" / "skip (reason)"; the layout matches the log folder pattern (proves T14); 0 bytes downloaded |
| **Manual**: a real import of `2026-09-26` into a separate test database (another `S4_DATA_DIR`, without a local log folder) | folder `2026-09-26` appears; its figures equal the local folder reference: 1,203 lines, 6 errors, 11 warnings |
| Send the same link again | "0 objects downloaded"; no duplicate data |
| `grep -rnE "AKIA|ASIA|aws_secret|SessionToken" data/ 2>/dev/null; py -m monishield status` | no credentials on disk; status only says "credentials: available (environment)" |
| As a regular user: open the import screen / call the endpoint | "no access" / 403 |
| With the real key (which can see all buckets): `py -m monishield import --dry-run s3://<another bucket in Jakarta>/x/2026-09-26/` | **refused by the allowlist before contacting AWS** |
| With the machine token: `curl -H "Authorization: Bearer $S4_JOB_TOKEN" -d '{"url":"s3://simpel4-backup/k8s-logs/2026-09-26/"}' …/api/admin/import` | 202; import then ingest run unattended (automation) |
| Restart the server after pasting temporary credentials | credentials gone; the import asks again |

The two rows marked **Manual** need real AWS credentials and internet access to S3; if they are not yet available when
the stage is done, the stage is reported as **PARTIAL** and those two rows are named as not yet tested.

The key in use is read-only but can see all buckets in the Jakarta region, so the allowlist test above is the
most important verification of this stage. The README includes the advice to replace the key with a dedicated read-only IAM user for
`simpel4-backup/k8s-logs/`.

⚠ **Depends on X2** (the server's outbound access to S3 Jakarta; the owner does not know yet, so it is checked on the server
with `curl -sI https://s3.ap-southeast-3.amazonaws.com` before relying on this feature) and **X3** (whether the mounted folder
is still used alongside the bucket). This stage does not block Stage 20.

---

## Stage 20 — IP map

**Goal.** A MapLibre map component (DRD §7) with no requests to outside domains, the IP Map page (DRD §3.2,
inventory §2.2), and a collapsed map on the service page (DRD §3.10).

**Files created**

- `web/public/fonts/<fontstack>/{0-255,256-511}.pbf` (Noto Sans glyphs, two weights) + their license file.
- `web/src/lib/MapView.svelte`: style without an external `sprite`/`glyphs`; the 13 layers of DRD §7.3; Indonesia
  and World presets; point clustering; arcs; tooltip; cooperative gestures; attribution; theme switch without
  losing the position.
- `web/src/pages/IpMap.svelte`; update of `Service.svelte` (module map, collapsed); dictionary keys.

**Verification**

| Command | Expected result |
|---|---|
| `cd web && npm run build && node ../tools/cek_i18n.mjs` | passes |
| IP Map `2026-10-06` side by side with the old one | KPIs: 516 IPs, 222 locations, 12 countries, 9 modules, 15 pods, 124,822 requests; "2,030 requests from outside Indonesia · 0 from internal IPs"; server point in Jakarta; the 6 largest locations labelled |
| Select module `om-be-simpel-loop` | KPIs, points, and table change; map position and zoom stay |
| Network panel in the browser developer tools, reload the map page | **all** requests go to the same origin; 0 to other domains |
| Turn off the computer's network, reload | map, labels, and points still shown |
| Mouse wheel over the map | the page scrolls; hint "Hold Ctrl…"; Ctrl + wheel zooms in |
| Phone / touch emulation 390 px | one finger scrolls the page; two fingers pan; pinch zooms; map 4 : 3 |
| Keyboard: focus on the map, arrows, `+`, `−`, `0`, `Esc` | pan, zoom, back to the preset, close the tooltip |
| Zoom from World to Java | clusters split into points; country → province → regency labels appear progressively without overlapping |
| Click a point → "Show in table" | the flow table filter is filled with the city name |
| Folder `2026-09-28` | note "The map needs the nginx ingress log…" |
| Change theme and language | map colours and country names change; MaxMind · GeoNames · Natural Earth attribution always visible |
| Service page `om-be-simpel-loop` | map collapsed; opened → only that module's flows |
| `pytest -q` (all tests) | all pass, including parity E1–E4 |
| Checklist `04b` for the IP Map | complete |

⚠ **Depends on Q3** (the Papua province boundaries may not include the new provinces; regency boundaries are not drawn),
**Q5** (map on the service page collapsed), **X7** (Noto Sans label font). All three are limited to
`MapView.svelte` and static files.

---

## Stage 21 — Attack detection: OWASP CRS rules, CAPEC categories

**Origin.** Owner request (2026-10-06): attack detection uses the OWASP Core Rule Set (CRS) and
its categories are named after CAPEC. Technical details in TRD §4.6.

**Why at the end.** Replacing the detection rules changes every figure in the Security tab. Parity with
the old system must first be proven with the old rules (Stage 8), and the Security page must already exist (Stage
15). After that the new rules come in as a deliberate, measured change.

**Scope of this stage = the "in the script" way**: CRS patterns are matched against the URL and User-Agent in the nginx log.
The "in the ingress" way (ModSecurity/Coraza in detection mode, which also inspects the body, headers, and cookies) is **not**
done here because it changes the cluster configuration, outside the reach of the dashboard project; see S1.

**Files created**

- `tools/ambil_crs.py`: downloads one CRS release with a **pinned version**, takes the rules from the files
  REQUEST-913 (scanners), 930 (LFI), 931 (RFI), 932 (RCE), 933 (PHP), 934 (generic), 941 (XSS), 942 (SQLi),
  944 (Java) whose targets are the URI, arguments, or User-Agent; stores the pattern, rule ID, severity,
  paranoia level, transformations, and CAPEC tags. Rules whose patterns the Python regex engine cannot use are
  recorded and skipped, not silently altered.
- `monishield/crs_rules.json` (output of the tool above; part of the repo, so there is no download at runtime) +
  the CRS license and notice files (Apache 2.0).
- `monishield/capec.json`: CAPEC ID → Indonesian and English names for the categories in use.
- `monishield/detect.py`: applies the needed CRS transformations (URL decode, lowercase, remove
  comments, etc.) and then matches; output per request: the IDs of the matched rules, CAPEC category, severity,
  anomaly score.
- `monishield/schema.sql`: new columns in `nginx_access` (`crs_rules`, `capec`, `crs_severity`, `crs_score`);
  the old `attack_cat` column is **kept** so the parity tests can still be run.
- `monishield/derive/`: attack aggregates computed from the new classification; `rules_version` bumped.
- `web/src/pages/Security.svelte`, dictionary: CAPEC categories, "Rules" column (CRS ID), method explanation.
- `tests/test_detect.py`: (a) known attack payloads per category → matched; (b) 22 thousand real paths that
  are currently "clean" → false-positive rate measured and reported; (c) all requests matched by the old rules
  → recorded which are also matched by CRS and which are not.
- `docs/04c-crs-detection.md`: old vs new comparison per folder, list of skipped rules, and
  limitations.

**Verification**

| Command | Expected result |
|---|---|
| `py tools/ambil_crs.py --check` | CRS version pinned; the number of rules taken and skipped printed; `crs_rules.json` does not change when re-run |
| `pytest tests/test_detect.py -q` | all pass; each category has a matching example |
| `py -m monishield derive --all` then `py tools/laporan_kesetaraan.py` | E1–E4 **still pass** for the old figures (`attack_cat` column); the new attack figures are reported separately |
| Read `docs/04c-crs-detection.md` | for each folder: old vs new attack requests, per category; false positives on normal traffic < 0.5 % at paranoia level 1, or the rules causing them are listed |
| `time py -m monishield ingest --folder 2026-09-29 --force` | still ≤ 60 seconds |
| Security page of folder `2026-10-06` | categories named after CAPEC in two languages; each row names the CRS rule ID; the footnote names CRS, its version, and that only the URL and User-Agent are inspected |

**Limitations that remain** (also written on the page): the POST body, headers other than User-Agent, and cookies
are not in the log, so they are not inspected. This is not a WAF replacement.

⚠ **Depends on S1** (below). With the assumptions used, this stage can be done without waiting.

---

## Stage 12a — Styling following the owner's design reference

**Goal.** Owner request 2026-10-06 (DRD §12): a look like the reference image, applied to the tokens and
shared components **before** the data pages are built, so that Stages 13–20 are not styled twice.
R6 answered: applies to **the whole dashboard**.

**Files changed**: `web/src/theme.css`, `lib/Sidebar.svelte` (bundled SVG icons), `lib/Kpi.svelte` (icon + badge),
`lib/Alert.svelte` → numbered attention cards with links, `App.svelte` (compact status line below the title).

**Verification**: `node tools/uji_browser.cjs` still passes; screenshots at 1440/390 px compared with the reference;
contrast of the new tokens computed (DRD §5.6); `grep` for URLs in `web/dist` still shows no outside domains.

---

## Stage 22 — Command Center (page)

**Goal.** A **world map** screen (R5): the IP origin → server map as the main content, surrounded by the main KPIs, "what
needs attention" cards, and a module picker; uses existing endpoints and components (TRD §12). Overview stays a separate
page. **ASSUMPTION**: absorbs the "IP Map" tab (Stage 20 builds the map component, this stage turns it into the Command Center). Its data comes from the log folder (the main source); updated when a new folder
is ingested or via the "Reload" button, with no realtime stream (Kafka postponed).
⚠ **Depends on R5**.

**Files** (added when the stage was done; this section previously had no file list or verification):

- `monishield/api/command.py`: `GET /api/folders/{folder}/command[?module=]` = main KPIs (HTTP requests, 5xx, errors of all
  services, upstream connection errors, attack source IPs, IPs with failed logins) + "what needs attention" items (key + figure +
  target page) + the IP Map response. No new calculations: every figure is read from the aggregates of its source page.
- `web/src/pages/CommandCenter.svelte` (replaces `IpMap.svelte`, the address stays `#/peta?modul=`), `lib/FlowMap.svelte`
  (`aside` slot, `tall` prop), `lib/MapView.svelte` (`tall` prop: full-screen-height map), dictionary `cc.*`, `tab.peta` =
  "Command Center".
- `tests/test_api.py::test_command_center_menyusun_angka_halaman_lain`; `tools/uji_tahap20.cjs` reads the map figures from
  the summary in the Command Center.

**Verification**

| Command | Expected result |
|---|---|
| `pytest tests/test_api.py -k command` | Command Center figures = the figures of the Security, Availability, Root Causes, IP Map pages; red items first; the module only filters the map |
| Page `#/peta?folder=2026-10-06` | 6 KPIs; map as wide and as tall as the screen; numbered attention cards with "Open …" links; no horizontal scroll at 1440 and 390 px |
| `#/peta?folder=2026-09-28` (no nginx) | request/5xx KPIs "–" + explanation; attention cards remain; note that the map needs nginx |
| `node tools/uji_tahap20.cjs` | the map still passes in its new place |

---

## Stage 23 — Realtime stream from Kafka

**POSTPONED** (owner decision 2026-10-06): the log folder remains the main source of updates; Kafka is only for the future.
This stage is not run by `migrate/06-eksekusi.md` until the owner reopens it.

**Goal (later).** A Kafka consumer inside the server process (K1), `rt_*` tables, an SSE endpoint `/api/stream`, a
"streaming · last event N seconds ago" indicator in the Command Center (TRD §12). Depends on R1, R2, R4.

---

## Stage 24 — Additional presentation (suggestions 1–9, owner request 2026-10-07)

**Origin.** The owner asked for frontend presentation suggestions, then chose items 1–9. All use data already in
the database (no new sources, nothing sent to third parties).

| # | Item | Implementation |
|--:|---|---|
| 1 | Change vs the previous folder in the Command Center | the 6 KPIs get ▲/▼ badges (`prev` in `/command`); ingress KPIs are compared only if yesterday's ingress log is ≥ 50 % (the Overview rule), the others if yesterday's total lines are ≥ 50 % |
| 2 | Hourly charts below the map | `by_hour` (ingress requests, 5xx, attack requests); two charts because the scales differ (not two axes) |
| 3 | Additional attention items | failed uptime, service errors spiking (≥ 2× AND +50 vs the previous folder, max. 3 services), restarts, failed PDFs, expired JWTs spiking (≥ 2× AND +20, only if yesterday's folder is comparable) — thresholds are an **ASSUMPTION** |
| 4 | IP profile + IP list (CSV) | `#/ip/<ip>` (`GET /api/folders/{f}/ips/{ip}`): offline owner & location, 8 KPIs, accounts tried, trail across all folders, ingress requests (max. 1,000); every IP cell links here. `GET …/security/attack-ips.csv` (cells starting with = + - @ are quoted) |
| 5 | CRS rule descriptions | `rule_msgs` in `/security` and the IP profile: "930130 · Restricted File Access Attempt" (original CRS text, in English) |
| 6 | Global search | 🔍 button in the header + **Ctrl+K** (`/` is already used by the table filter); `GET /api/search` → IP, account, requestId, URL; a result opens the target page with the table filter filled in (`?cari=`) and scrolls to its table |
| 7 | Data completeness in Trends | dates without a log folder, folders with corrupt files (link to Pods), last ingest |
| 8 | Hour × date heatmap | Trends: ingress requests / errors of all services, one sequential colour, 5 classes + legend, explanation on hover, "View as table" |
| 9 | Daily summary PDF | button in the Command Center → browser print (Save as PDF): A4 landscape **1 page**, light theme, KPIs + map figures + map image (canvas captured, attribution included) + attention items. **ASSUMPTION**: via browser print, with no PDF library on the server |

**Files**: `monishield/api/command.py` (extended), `api/ips.py`, `api/search.py` (new), `api/security.py`, `api/trends.py`,
`detect.py` (`rule_msgs`); `web/src/pages/IpProfile.svelte`, `lib/GlobalSearch.svelte`, `lib/Heatmap.svelte` (new),
`pages/CommandCenter.svelte`, `pages/Trends.svelte`, `pages/Security.svelte`, `pages/Service.svelte`, `lib/IpCell.svelte`,
`lib/DataTable.svelte` (a filter set from outside can scroll), `lib/MapView.svelte` (`preserveDrawingBuffer` for the
Command Center map), `lib/Header.svelte`, `state.js` (route `ip/…`, `?cari=`), dictionary (+73 keys); `tests/test_api.py` (+6 tests).

**Verification**

| Command | Result |
|---|---|
| `pytest tests/test_api.py tests/test_config.py tests/test_detect.py` | 108 passed, 2 skipped |
| `npm run build` + `node tools/cek_i18n.mjs` | passes; 732 keys equal in ID/EN |
| Browser (Chromium): Command Center 30 Sep / 6 Oct, search, IP profile, CSV download, Security, Trends, 390 px | all work, no console errors, no horizontal scroll |
| Summary PDF for 6 Oct (Chromium `page.pdf` during the print preparation pause) | 1 A4 landscape page, light theme, map printed; theme & map restored after `afterprint` |

---

## Stage 25 — "Sync data" button and the MoniShield name (owner request 2026-10-07)

- **Sync data**: a button in the header (admin only; **ASSUMPTION**: ingest writes to the database, same as the role
  matrix of Stage 10). `GET /api/admin/ingest/status` now includes `new_folders` = date folders in the log folder / inbox
  that contain log files but are not yet in the database (only a directory listing, read every minute and when the tab becomes active) →
  number badge. Click → `POST /api/admin/ingest` (new/changed files only; 409 = wait along) → progress → message →
  the folder list is reloaded and switches to the newest new folder. Files: `api/admin.py`, `lib/SyncButton.svelte`,
  `lib/Header.svelte`, `App.svelte`, `sync` icon, dictionary `sync.*`, test `test_sinkronisasi_mendeteksi_folder_baru`.
- **Application name MoniShield**: `brand.js` (`APP_NAME`, logo mark `APP_MARK` = "MS"), tab title, shield tab icon
  (`web/public/favicon.svg`), FastAPI title, README, Dockerfile/compose (image `monishield:2.0.0`, compose project
  `monishield`), example configuration, DRD Q8. **Not** changed: the Python package `simpel4`, the `S4_` variable prefix, the
  database file name (changing them would break existing configurations); SIMPeL4 is still named as the monitored system.
- **Login page** (a follow-up owner request, following their reference image): a large shield as the **background behind
  the form** (SVG in the page, thick teal outline + dark teal-tinted fill, not transparent; 46 % of the screen width, max.
  620 px; on phones 150 % of the screen width so that its top and tip are visible), a 60 px "M" shield logo + the title **MoniShield**
  (the owner's choice, without a tagline), then the form. **The eye button (show password) was removed** at the owner's request; the dictionary keys `login.show/hide/tagline/welcome`
  were removed too, and `lib/ShieldArt.svelte` (the previous version) was deleted.

**Verification**: `pytest tests/test_api.py` 75 passed; build + `cek_i18n` 740 keys; browser: test folder `2026-10-07`
(a copy of 26 Sep in `data/inbox`, the real log folder untouched) → badge "1" → click → "Sync finished: 1 folder
updated (7 Oct 2026)" → the page switches to 7 Oct → the badge disappears; no console errors. The test folder was then deleted
(`forget` + removal from the inbox).

---

## Stage 26 — Standalone repository and branch flow (2026-10-07)

**Origin.** Owner request: move the `v2/` folder of `apisdsn/dashboard-logging` into its own repository.

- `apisdsn/MoniShield` holds the former `v2/` contents **with their commit history**. The old repo stays as it was
  (`build_dashboard.py`, `dashboard_template.html` and the log folders are not touched).
- Default log folder: `logs/` in the project folder (formerly the parent folder of `v2/`).
- Branches `dev` (development) → `stg` (staging) → `prd` (production, default branch); `master` is no longer used and
  is deleted by the owner in the GitHub UI. Rules in `CONTRIBUTING.md`.
- Every commit follows Conventional Commits 1.0 in English: `tools/cek_commit.sh`, the `.githooks/commit-msg` hook
  (`git config core.hooksPath .githooks`) and the CI job "Conventional Commits". No `Co-Authored-By` trailers.
- 2026-10-08, owner request: the whole commit history was rewritten to English Conventional Commits and force-pushed
  (trees, authors and dates unchanged).

---

## Stage 27 — Clean architecture (2026-10-07)

**Origin.** Owner request to arrange the code by clean architecture. Result described in
[`08-architecture.md`](08-architecture.md).

- Four layers: `domain` (pure rules), `application` (use-case services + `ports.py`), `infrastructure` (DuckDB,
  SQLAlchemy, boto3, kafka-python, `.env`, notification channels, downloads, page queries), `interfaces` (FastAPI
  routers, CLI). Composition root: `interfaces/api/app.py` → `wire()`; services get `ctx` (= `app.state`).
- Read side (page reports) goes straight from `interfaces/api/pages.py` to `infrastructure/queries/<page>.py`.
- Errors: `domain.errors.Fail(code, message, status)` and subclasses → one API error handler.
- `tests/test_architecture.py` fails CI when an import breaks the dependency rule.

**Verification**: full pytest run green (339 passed, 62 skipped: the skipped tests need the real log folders, the
old dashboard or a real database); browser end-to-end checks of the admin screens repeated.

---

## Stage 28 — English everywhere except the UI text (2026-10-07 … 08)

**Origin.** Owner request: commit messages, code comments, `.md` files, server error messages, endpoint responses and
CLI output in English; GitHub Actions in English too.

- API status values are English: import job `running / done / failed / dry_run`, ingest run `running / ok / failed`,
  ingest file `ok / empty / corrupt / failed`, Kafka `off / connecting / running / error`, credential source
  `pasted / environment`, S3 actions `fetch / skip`. Old Indonesian values in existing databases are migrated when
  the database is opened (`tests/test_status_migration.py`).
- The UI stays bilingual: `web/src/srv.js` translates server text to Indonesian (`ID` table, `ERR_ID` full sentences
  for detailed errors, `LEGACY` table for old stored rows); errors are translated by code (`err.*` in `id.json`).
- All documents translated; their file names became English in Stage 31.
- Data identifiers that come from the old system stay as they are (TRD K9: attack categories, business metric
  names; the keys of `00-reference.json`).

---

## Stage 29 — Kafka folders labelled "(Kafka)" (2026-10-08)

**Origin.** Owner request: folders filled by Kafka must be told apart from S3 folders.

- The Kafka consumer marks the folders it writes (`.kafka-feed.json`); `/api/meta` and the admin folder list return
  `source` (`log`, `kafka`, `s3`, `upload`).
- The folder picker, page title and folder management show "YYYY-MM-DD (Kafka)" (i18n `folder.kafka`, `fm.tag.kafka`).
- Folder date D holds the logs of (D-1 00:00, D 00:00] WIB, like the S3 export, so today's Kafka lines go into the folder
  dated tomorrow.

---

## Stage 30 — GitHub Actions CI and automatic deployment (2026-10-08)

**Origin.** Owner request: set up GitHub Actions, then deploy to the server automatically without typing the
migration commands.

- `.github/workflows/ci.yml`: on push / pull request to `dev`, `stg`, `prd` and on "Run workflow": jobs
  **Conventional Commits**, **Python tests** (`pip install -e ".[test,s3,kafka]"`, pytest), **Web UI build**
  (`npm ci`, build, `tools/cek_i18n.mjs`, `tests/test_format.mjs`).
- Job **Deploy to the production server**: only on `prd`, after the three jobs pass, in the GitHub environment
  `production`; SSH as user `deploy`, runs `deploy/remote-deploy.sh` (fetch the tested commit, `docker compose build`,
  `up -d`, wait for the app healthcheck, `image prune`). The first run can copy `.env` from the old checkout
  (`DEPLOY_MIGRATE_FROM`). Settings may be environment variables or secrets.
- Server and GitHub setup, the release steps and a troubleshooting table: [`07-deploy-vps.md`](07-deploy-vps.md) §13.

**Verification**: CI green on `dev`; `remote-deploy.sh` tested with a stub `docker` (first deploy with migration,
update, missing `.env`). **Open**: the first real deploy happens when `dev` is promoted to `stg` and `prd`.

---

## Stage 31 — English documentation and hand-over (2026-10-08)

**Origin.** Owner request: documents in English, titles included, updated to what was built, so that the work can
continue with Claude Code on a local machine.

- File names: `00-acuan.json` → `00-reference.json`, `00-inventaris.md` → `00-inventory.md`, `04-rencana.md` →
  `04-plan.md`, `04a-hasil-ukur.md` → `04a-measurements.md`, `04b-daftar-periksa.md` → `04b-page-checklist.md`,
  `04c-deteksi-crs.md` → `04c-crs-detection.md`; every reference updated.
- New: [`README.md`](README.md) (index of the documents), [`09-status.md`](09-status.md) (state, open items, next
  steps) and `CLAUDE.md` in the repository root (instructions Claude Code loads automatically).
- The repository `README.md` follows Best-README-Template (owner request); its long how-to sections moved to
  [`10-user-guide.md`](10-user-guide.md).
- TRD §6.1 shows the current folder layout; old paths (`v2/`, `simpel4`) replaced where they described the current state.

---

## Stage 32 — Encrypted request and response bodies (2026-10-08)

**Origin.** Owner request: encrypt or obfuscate endpoint responses and the payloads sent to the backend without loading
the server. (An earlier attempt in the same session encrypted the credentials in `.env`; the owner had it rolled back
before it was committed.)

- Key agreement once per page load: `POST /api/crypto/handshake` (public, needed before sign-in) exchanges ephemeral
  ECDH P-256 keys; both sides derive AES-256-GCM with HKDF-SHA256 (`monishield-api-v1`). The server keeps
  `{key id: AES key}` in memory, at most 5,000 keys, expiring with the session length (`infrastructure/wirecrypto.py`).
- `interfaces/api/wire.py` (ASGI middleware): a request with `X-MS-Enc: <key id>` has an encrypted body
  (`application/octet-stream`, 12-byte nonce + ciphertext, AAD `req METHOD /path`) and gets an encrypted JSON response
  (AAD `resp METHOD /path`, header `X-MS-Enc: 1`). Unknown key → `enc_key_unknown`, bad body → `enc_invalid`; the browser
  agrees on a new key and repeats the request once.
- `web/src/wire.js` (WebCrypto) + `api.js`: every JSON call of the UI is encrypted. Without WebCrypto (plain http on a LAN
  address) or with `S4_API_ENCRYPTION=false` the UI uses plain JSON.
- Not encrypted, on purpose: requests without the header (Swagger, the cron job, curl), file downloads (CSV, block
  list), uploads of log files, the live map stream, URLs.

**Verification**: `tests/test_wire.py` (encrypted login and pages, plain clients, unknown key, a body replayed on another
path, CSV untouched, switch off, bounded key store). Browser: 13 of 13 API calls of a session encrypted, no plain JSON,
the password never in a request body. Cost measured on the server: handshake 0.09 ms, encrypting a 200 KB response 0.09 ms.

---

## Stage 33 — Data retention (2026-10-08)

**Origin.** Owner request (suggestion 2): keep the server disk from filling up.

- `S4_RETENTION_DAYS` (min. 8, so the 7-folder comparison keeps working) removes folders from the database;
  `S4_RETENTION_INBOX_DAYS` (min. 2) deletes inbox folders (S3 imports, uploads, Kafka) from disk; 0 = keep forever.
  Rules in `domain/retention.py`; cleanup in `application/retention_service.py` (holds the ingest lock, audited),
  daily (first run 5 minutes after start) and from Configuration → *Data retention* (preview + "Run now").
- Ingest, the "new folders" badge and the S3 sync skip folders past the cut-off, so removed folders do not come back.
  Files in the main log folder are never touched.

**Verification**: `tests/test_retention.py`; browser: card in both languages, 1280 and 390 px, invalid value refused
with the Indonesian message.

---

## Stage 34 — Notification thresholds per number and per service (2026-10-08)

**Origin.** Owner request (suggestion 5): a busy service and a quiet one need different spike thresholds.

- `S4_ALERT_SPIKE` overrides the threshold of each folder number (`n5xx=3:50,errors=off`); `S4_ALERT_SERVICE_SPIKE`
  compares the errors of each service with that service's own 7-folder average (`default=2:50` plus overrides, `off`
  mutes a service). Spike notifications list up to 5 services. The Command Center "service errors rose" item uses the
  same per-service thresholds (default unchanged: 2× and +50).
- Configuration → Notifications → *Spike thresholds*: table per number, default + per-service rows (service names
  suggested from the data).

**Verification**: `tests/test_alerts.py` (parsing, muted and overridden services, saving from the page); browser at
1280 and 390 px.

---

## Deviation notes

Filled in whenever a stage is finished: stage number, date, what differs from the plan or from the TRD/DRD, and why.
Module paths in older rows (`monishield/api/…`, `monishield/ingest.py`, …) are from before Stage 27; the current location
of each module is in [`08-architecture.md`](08-architecture.md).

| Stage | Date | Deviation |
|--:|---|---|
| 1 | 2026-10-06 | (a) `docs/03-trd.md` §10 also had two sentences changed: it was given the status "already applied" and the suggestions already carried out were removed; the technical content of the TRD did not change. (b) The DRD gained §6.9 (sign-in, session, role behaviour) alongside the planned §3.11, and changes U28–U32. (c) The PRD gained new risks R11–R13 and success criteria for login, phone, and S3 import, which are not named in this stage's file list but follow the owner decisions. Verification: 3 of 3 passed (grep for the old phrase = 0; the three screen terms found; 19 lines of TRD §10 have counterparts). |
| 2 | 2026-10-06 | (a) The `classify` test uses User-Agents from the nginx log **and** the frontend log: the nginx log alone has only 359 unique UAs, below the 500 requirement. (b) `rules.py` contains three things outside the TRD §4.1 list, all copies from the old source: 13 patterns that in the old system were written directly inside `parse()` are now named (a test ensures the pattern text exists in the old source); `pod_name()` and `split_relpath()` from `build()`. (c) `load_ip2asn()` and `map_labels()` take the file path as a parameter, because in v2 the cache location is configurable; their content did not change. (d) Additional tests beyond the plan: equality of the definitions of all patterns/tables, `map_labels` (177/38/514), and the `geo_scan` result vs the old `.cache/geo.json`. (e) `fetch()`, `HOSTS`, `SERVER_IP` were copied too; the tests never download. Verification 4 of 4 passed: installation without errors (duckdb 1.5.6, fastapi 0.142, uvicorn 0.54, pytest 9.1); `pytest tests/test_rules.py` 16 passed, 0 skipped, 27 seconds; `status` prints the configuration and "no database yet"; the old files and `.cache` did not change. |
| 3 | 2026-10-06 | (a) The minimum Python was raised to 3.12: the CSV uses `csv.QUOTE_NOTNULL` so that empty text and NULL are distinguished. (b) The parser CSV does not contain `file_id` and `folder`; ingest (Stage 4) adds them on load. List columns (`up_addrs`, `up_statuses`) are written as `a,b` and split on load. (c) The `alert`/`emerg` levels are counted as errors in the **ingress** too (old: warning), following TRD §4.4 item 3, which makes both services the same; there are no such lines in the current data. (d) `file_counter` of type `level` stores the **original** simpel-loop tag (same as the old system); the effective level (TRD §4.4 item 4) is computed in the Stage 5 SQL from `sl_event`. (e) The PDF template is remembered per thread **per file**, not per service across files as in the old system; on the three test folders the result is identical. (f) A Spring line that matches more than one login pattern fails the file (rather than silently losing an event); this does not happen in the data. (g) The `upstream_host`/`kind`/`request` columns are also filled for the frontend error log; the `v_upstream_error` view stays ingress-only. (h) Note for Stage 6: the error text of a simpel-loop event in the old system is `f"{name}: {message}"`, so an empty value must become the text `None` in SQL. (i) Test (b) is deeper than planned: besides lines/errors/warnings/levels per file, the content that will later be aggregated (status, IP, endpoint, flow, pod, retry, incidents, attacks, duration, messages + samples, simpel-loop events, login, restarts, JWT, PDF) is compared with the raw statistics of the old parser. Verification 3 of 3 passed: `pytest tests/test_parse.py` 36 passed, 2 skipped (folder 09-27 indeed has no nginx and coredns); parse of file 5v8j4: `lines=111301`, 3 CSVs, 4 seconds; schema: 43 tables + 4 views, safe to run twice. All tests: 52 passed, 2 skipped. |
| 4 | 2026-10-06 | (a) The test log folder is not stored as files in `tests/fixtures/logs_mini/`, but built for each test by `tests/logs_mini.py` from the real lines in `fixtures/lines/`, because the tests need to modify its files. (b) The scanner walks only the top-level date-shaped folders (not a `glob` of the whole tree), so that `v2/.venv` and `node_modules` are not walked; the result is the same as the old rule. (c) Addition beyond the TRD: when a `.log` is parsed and its `.log.gz` pair exists, that pair is hashed once too; if they differ a warning is recorded. **Result on the real data: 0 warnings, so all existing `.log`/`.log.gz` pairs are identical** (answers X5/P5 for the current data). (d) A file that fails to parse is recorded as `gagal` and retried on every ingest. (e) Fewer than 3 files are processed in-process, without a subprocess. (f) Times in the database are written as UTC from Python, not DuckDB's `now()`, which follows the machine's time zone. (g) `derive_folder()` only fills `folder_state` so far; the aggregates follow in Stage 5. (h) **At the owner's request in the middle of the stage**: all configuration and secrets can now (and preferably should) be put in `.env`; `config.py` reads `.env` itself, lists/dicts are written as JSON, `.env.example` was created, `tests/test_config.py` was added (11 tests), and TRD §6.3 was updated. Verification 6 of 6 passed: `pytest tests/test_ingest.py` 17 passed; initial ingest 195 files / 11 folders / 0 failed in 11 seconds (limit 3 minutes); total 774,264 lines, `nginx_access` 308,158, `fe_access` 148,049, `sl_event` 114,574, 52 files with 0 lines; second ingest 0 files changed in 0.1 seconds; checksums of 43 tables equal before and after; the log folder and old files did not change. Additionally: lines/errors/warnings per (folder, service) and the number of files equal `00-reference.json` for 81 pairs; re-ingest of the largest folder (09-29) 6 seconds. All tests: 80 passed, 2 skipped. Note for Stage 9: the database is 52 MB for 11 folders, roughly 24 MB per full folder, so ±9 GB per year **before** aggregates; close to the 10 GB limit. |
| 5 | 2026-10-06 | (a) `folder_state` is now filled by the `derive` package (not `ingest.py`); `ingest.derive_folder()` only calls it. (b) `agg_hour` can contain hours with `total = 0`: hours that contain only nginx/frontend error log lines (a consequence of TRD §4.4 item 2). (c) Found while writing the SQL and kept for parity: in the old system the **frontend** `perr` key does not include the HTTP method (only `path_key`), unlike the ingress and simpel-loop; inventory §1.3 describes it as uniform. (d) simpel-loop `err_http` = failed events with a 5xx status; `users_ok` is already computed in this stage. (e) `status --folder` now also prints an aggregate summary. (f) Tests deeper than planned: besides hand-computed values on `logs_mini`, all core aggregates for two real folders (09-30 and 10-06, 11 services) are compared with the raw statistics of the old parser without truncation; the tests were shown to fail when the SQL is deliberately broken (UA truncation, percentile index). Verification 5 of 5 passed: `pytest tests/test_derive_core.py` 14 passed; `derive --all` 11 folders in 1 second; folder 09-29: nginx requests 132,203 / 4xx 4,635 / 5xx 59 / errors 94 / warnings 164 / unique IPs 723 / flows 1,762, simpel-loop requests 60,665 / warnings 9,614; folder 09-30: errors 1,690, pod connection errors 1,200, retries 825; checksums equal after the second `derive --all`. Additionally: 910 figures of `00-reference.json` (all folders × services, for this stage's aggregates) exactly equal, 0 different. All tests: 94 passed, 2 skipped. Note for Stage 8: the simpel-loop level distribution deliberately differs from the reference (effective level) and goes into the list of expected differences. |
| 6 | 2026-10-06 | (a) Only three aggregates are written as SQL (`17_login`, `18_mail`, `19_report`). Attacks, accounts, incidents, correlation/trace, business/activity, and JWT are derived in **one** Python module `derive/steps.py` (not separate `accounts.py` + `incidents.py`), because they use the `rules.py` functions as-is or depend on `unquote_plus()` and order of appearance, which have no exact equivalent in SQL. Their input is the result of small queries, not the whole log. (b) `rules.accounts()` truncates its result at 150 rows; it is called per account so that `agg_account` is not truncated (TRD K4); its logic was not changed. (c) `agg_login_*`, `agg_account` only from `om-be-appsmanager` and `agg_report` only from `om-be-report`, as the old view reads them. (d) The cross-folder correlation refresh only catches matches that increase (marked `ponytail:`); if an nginx file is deleted, other folders are not refreshed until `derive --all`. In the real data, cross-folder matches = 0. (e) Two sources of instability were found through the checksum check and fixed: the key order in `agg_incident` (now follows the order of first appearance, same as the old system) and `dur_avg` in `agg_endpoint` from Stage 5 (parallel `DOUBLE` average; now computed from a sorted list). (f) Tests deeper than planned: three real folders (09-29, 09-30, 10-06) compared with the raw statistics of the old system, including `correlate()`; the tests were shown to fail when the code is deliberately broken. Verification 4 of 4 passed: `pytest tests/test_derive_features.py` 12 passed; folder 09-29: attacks 155 requests / 77 URLs / 12 IPs, correlation 22,638 of 60,665, trace 550 rows (old: truncated at 300), failed logins 86 / resets 24 / successes 389, accounts 39, incidents 7, PDF 813 / 32; folder 10-06: attacks 88, correlation 4,161 of 5,981, Laporan Dibuat 7; re-ingest of 09-29 with `--force` 6 seconds (limit 60). Additionally: 263 figures of `00-reference.json` for this stage's aggregates exactly equal; `derive --all` three times in a row gives identical checksums (4 seconds for 11 folders). All tests: 106 passed, 2 skipped. |
| 7 | 2026-10-06 | (a) The MaxMind download redirects to a signed URL that **rejects** the `Authorization` header (400); `refdata.py` drops that header when following the redirect. (b) The location sweep was rewritten for `int` ranges (`refdata.sweep`) because GeoLite2 blocks are CIDRs, not pairs of text IPs; its equivalence with the old `rules.geo_scan()` is proven by tests. (c) An `offline` field was added to the configuration (`S4_OFFLINE`, as well as `ingest --offline` and `refdata --offline`): without it the tests would download. All old tests now run offline. (d) GeoLite2 blocks without a `geoname_id` use the registered country: this yields a country without a city name. (e) The map files are regenerated only when incomplete; a failure there does not cancel the `ip_info` result. (f) GeoJSON coordinates are rounded to 2 decimals (≈ 1 km), same as the old map; `land.geojson` 992 KB, country borders 304 KB, province borders 342 KB. (g) **Finding for Stage 20 / Q3**: Natural Earth 10m contains only **33** Indonesian provinces; two provinces created in the 2022 split (Papua Barat Daya, Papua Pegunungan) have GeoNames labels but no boundary lines yet. (h) **Finding for Stage 20**: GeoLite2 gives coordinates for the server IP but **without a city name** (a country-level block), so the server point label needs to use `server_fallback`. 317 other IPs also have coordinates without a city name. (i) Comparison with the old DB-IP on the same 1,676 IPs: **same country 99 %** (1,657), same city 23 % (393) — an expected inter-vendor difference, recorded as a difference for Stage 8; examples: Citeureup→Bogor, Cimahi→Bandung, Jakarta→Central Jakarta. Verification 5 of 5 passed: `pytest tests/test_refdata.py` 13 passed (no test touches the network); `refdata` fills 2,691 IPs (2,689 get an owner and a location) and creates 4 map files; `status`: owners 2,689 (≥ 1,734), **100 %** of public v4 IPs have a location (requirement ≥ 95 %), server in Jakarta (−6.175; 106.8286); `labels.json` 177 countries / 38 provinces / 514 regencies-cities; `refdata --offline` **and** a full ingest with all outbound connections blocked (proxy to a dead port) finish without errors. Additionally: the network owner is **exactly the same as the old dashboard for all 1,734 IPs** (0 different, 0 missing) — early evidence for E3; the MaxMind key does not appear in the `status` output, the database (0 occurrences in all text columns), or any file other than `.env`. All tests: 119 passed, 2 skipped. |
| 8 | 2026-10-06 | (a) The comparator was put in one shared module `tools/kesetaraan.py` used by the tests **and** the report, so that its definitions do not diverge. (b) Two mistakes were found and fixed during this stage, both in the comparison/reference tools, not in v2: `login_ip` in `00-reference.json` turned out to mean *all* IPs that have a login event (including success only), not the KPI "IPs with failed logins"; and the "should be" value for `lambat ≥ 5 dtk` (slow ≥ 5 s) was originally computed from the trace list already truncated at 300 rows, and is now computed from the correlated events. (c) E4 item 1 also checks two measures whose limits have **never** been reached (failed-login IPs 100, accounts 150), so that it is noticed if they are reached later. (d) `tools/ekstrak_dashboard.py` stores the extraction result in `data/dashboard-lama.json` (not in git) and regenerates it when `dashboard.html` is newer. (e) Tests are skipped with an explanation when the database, `dashboard.html`, or the reference is absent, or when their folder lists do not match. Verification 3 of 3 passed: `tools/acuan_lama.py` re-run (11 folders, core figures unchanged); `pytest tests/test_equivalence.py` 12 passed; report: **E1 3,022 figures, 0 different; E3 1,734 IPs, 0 different; E4 169 checks, 0 mismatched**. The expected differences appear exactly at items 1, 2, 4, and 9 (item 3 does not change because there are no `crit` lines in the frontend): e.g. pod connection errors 09-30 200 → 1,200, 401 clients 09-29 30 → 653, Σ nginx errors per hour 09-29 59 → 94, simpel-loop level ERROR 552 → 0 / WARN 0 → 552, slow ≥ 5 s 09-29 15 → 24, trace 300 → 550 (no longer truncated). IP locations are deliberately not compared (the source is now GeoLite2): same country 99 %, same city 23 %, recorded in the report. The tool was tested by deliberately deleting some `agg_c401` rows: the report catches it in E1 **and** E4 and exits with code 1, and returns to 0 after `derive` restores them. Note: E1 compares summary figures (row counts, totals), not every value inside the rows; comparing list contents is E2 in Stage 11. All tests: 131 passed, 2 skipped. |
| 9 | 2026-10-06 | **Gate PASSED; ASSUMPTION T1 proven**, the dictionary-table fallback is not needed. (a) The free disk turned out to be 32 GB (not 17 GB as when the plan was written), so the simulation was run in full with **365 folders**, without extrapolation. (b) Request ids were given a per-folder prefix in the simulation so that correlation stays within a folder like the real data. (c) Ingest time was measured in two parts: parse + load + derive on the real database, and deriving the aggregates of one folder on top of the one-year database (the part that grows with data size). (d) The cost of password hashing was measured too, for Stage 10. Verification 4 of 4 passed: the 365-folder simulation finished (19 minutes; 48.3 million nginx lines); size **4.75 GB** (≤ 10 GB); 21 page queries in total **20.5 ms**, slowest 7.3 ms (≤ 200 ms); Trends over 365 folders **5.4 ms** (≤ 500 ms); ingest of the largest folder 6.9 s + 1.7 s derive at one-year scale (≤ 60 s); ingest without changes 0.4 s (≤ 5 s); `sim.duckdb` deleted, space reclaimed. Details and measurement limits in `docs/04a-measurements.md`. Honest note: the simulation duplicates one folder, so more varied real data could be larger; query times do not yet include the HTTP layer (measured again in Stage 11); `derive --all` for one year ±10 minutes. Parity is still 0 different after this stage. |
| 10 | 2026-10-06 | **Change at the owner's request in the middle of the stage**: "for tokens use JWT, for the database use PostgreSQL, and use an ORM". (a) Accounts, sessions, audit, and import records moved from raw `sqlite3` to the **SQLAlchemy ORM**; the server uses **PostgreSQL** (`S4_AUTH_DATABASE_URL`), and SQLite through the same ORM when it is empty (tests, local runs). (b) The session token became a **JWT HS256** (`S4_JWT_SECRET`, required, ≥ 32 characters) in an HttpOnly cookie; the session row is still checked in the database so that sign-out/reset/deactivation take effect immediately. (c) **ASSUMPTION T16**: DuckDB stays for the log data (see TRD K11); needs the owner's confirmation. (d) Three new dependencies: `sqlalchemy`, `psycopg[binary]`, `pyjwt`; compose (step 7) gains a `postgres` service + volume `s4-pgdata` replacing `s4-state`. (e) Tables named `app_user`/`app_session` (PostgreSQL keywords). (f) The schema is created with `create_all`; no migration tool yet. (g) The plan's verification was adjusted: the first admin must change the password before `/api/meta` (per TRD §8.2), and the lockout is tested on an existing account. Result: account + API tests **64 passed on SQLite and 64 passed on PostgreSQL 17**; all tests 195 passed, 2 skipped; a real server on PostgreSQL: 17 of 17 checks passed (401 without a session; JWT cookie HttpOnly SameSite=Strict; 11 folders; 2026-10-06 = 7 services, nginx err 125, attack_ip_count 14, the same for admin and user; user → `/api/admin/users` 403; `simpel4 ingest` via the API "0 files changed"; CSP/nosniff/Referrer-Policy headers; 6th wrong login → 429; session dead after sign-out; no secrets in the server log). |
| 11 | 2026-10-06 | (a) The page endpoints, the table endpoint, the Stage 11 tests in `test_api.py`, and E2 in `tools/kesetaraan.py`/`test_equivalence.py` **already existed in the repository** when this session started (done earlier but not yet marked finished); this session rebuilt the database from scratch, ran all the verifications, and completed what was missing. (b) Originally the ten pages were in a single `api/pages.py`; they are now **split into one module per page** per the TRD (`overview.py`, `map.py`, `trends.py`, `security.py`, `rootcause.py`, `availability.py`, `pods.py`, `business.py`, `tracing.py`, `service.py`); shared helpers (`_all`, `_one`, `_no`, `_has`, WIB hours) moved to `common.py`. (c) The definitions of the 25 tables and the table endpoint are in `api/tables.py`, **not** `common.py` as planned: a file dedicated to the table contract (sortable columns, `q` columns, old limits) is easier to review; `common.py` still holds validation, roles, the IP cell. (d) `tools/ukur.py --api HOST:PORT` was added: signs in with `--user` (password from `S4_UKUR_PASSWORD` or prompted), measures 19 endpoints (folder summary, 8 pages, 7 services, Trends 30/all, meta), exits with code 1 if any is > 300 ms or > 500 KB. (e) The E2 rule: every old row must be in the **complete** v2 list with exactly the same content, and the order of the sort values of the first N rows must be the same; the v2 list may be longer (no longer truncated, TRD K4). The E2 report is printed by `py tools/kesetaraan.py` (E1–E4); `tools/laporan_kesetaraan.py` stays E1/E3/E4. (f) **ASSUMPTION X6**: the default flow table is 100 rows (`flows.limit`), the rest via the table pages. (g) Searching `q=count` on `c401` 09-29 gives `matched` 208 (≤ 653). (h) In this session the accounts used SQLite through the ORM; PostgreSQL was not re-tested (no changes in `auth.py`). Verification 8 of 8 passed: `pytest tests/test_api.py tests/test_equivalence.py` 87 passed (the role matrix covers all routes); E1 3,022 figures 0 different, **E2 601 lists / 9,889 old rows, 0 different**, E3 1,734 IPs 0 different, E4 169 checks 0 mismatched; real server: `security` 10-06 `attack_requests` 88 / `attack_ips` 14; `availability` 09-30 pod connection errors 1,200; `map` 09-28 `available: false, reason: "no_nginx"`; `c401?limit=5&q=count` total 653, 5 rows; `sort=1;drop` → 400; `ukur.py --api`: 19 endpoints, slowest `security` 112 ms, largest `tracing` 178 KB, 0 misses. All tests: 239 passed, 2 skipped. **Merge note**: the next Stage 11 row comes from another session that came in via `master`; its item (a) (a single `api/pages.py` module) no longer applies because that module was split per page above, and `tools/ukur.py --api` now combines both versions (no host = in-process; with a host = `S4_COOKIE` or sign in with `--user`). |
| 12 | 2026-10-06 | **PARTIAL: not yet tested on a real phone** (DRD §8 requires it; from the cloud environment only Chromium emulation at 390/360 px). (a) The address uses a hash `#/<tab>?folder=…&modul=…` because the server serves a static `web/dist` without a path fallback; the old tab slugs (`#keamanan`, `#<layanan>`) still open. The folder is also in the address on Trends and the admin screens so that it persists when coming back. (b) `/api/me` and the login response now include `session_idle_minutes` (a small change in `api/session.py` + test) for the "Session ends in 5 minutes" band. (c) A small build plugin strips `https://` from Svelte's error documentation links (`svelte.dev/e/…`, error message text, never fetched) so that `web/dist` is free of outside addresses; the remaining URLs are only XML schemas. (d) **ASSUMPTION** "practically empty folder" (DRD §6.6) = < 1,000 log lines; corrupt files alone do not trigger the band because even full folders have 1–3 files with corrupt lines. (e) The folder picker on narrow screens shows only the date (`6 Okt 2026`) so that it is not cut off. (f) Q6 "–" for figures whose logs are absent, Q7 (column sorting, copy IP, `(i)`, "View as table", shortcuts `[` `]` `/`) done; Q8 logo stays "S4". (g) `Placeholder.svelte` doubles as a sample page of all components with real data (one `overview` request). (h) Browser test scripts kept: `tools/uji_browser.cjs` (50 checks) and `tools/uji_sesi.cjs` (7); Playwright is not a project dependency. (i) In the middle of the stage the owner asked for styling following the reference image and a realtime Command Center module via Kafka: recorded as Stages 12a, 22, 23 and questions R1–R6 (TRD §11.2, §12; DRD §12), **not yet done**. Verification: `npm ci && npm run build` without warnings; `node tools/cek_i18n.mjs` "keys match: 148"; `node --test tests/test_format.mjs` 8 passed; URLs in `web/dist` only XML schemas; `./run.sh` builds then serves; browser: 50/50 (Sign in without data before signing in, mandatory password change, sidebar with two groups + badge `14 IP`, 11 folders, subtitle with the log range, folder/tab in the address, back/shortcuts, table 25 + more + server filter + aria-sort, ID/EN and theme remembered, Tab: Skip to content → navigation → header with visible focus, user = same sidebar without the admin menu and `admin/user` → "No access", 390 & 360 px: no horizontal scroll, KPIs in 2 columns, tables become cards, touch ≥ 44 px, drawer + Esc, ⋯ menu) and 7/7 (session band, session expired → Sign in then back to the same address, server down → "Not connected" band → recovers on its own in 4 s); `pytest tests/test_api.py tests/test_auth.py` 100 passed. (j) The application name was changed to **SIMPeL4 Dashboard** by the owner's decision (one constant in `web/src/brand.js`; the logo mark stays "S4"). |
| 12a | 2026-10-06 | Run before the real-phone test of Stage 12 (which stays open) because this styling changes the look that will be tested; the owner ran `/loop` after being told the next step is 12a. (a) The tokens of both themes were switched to the reference style: a neutral greenish background, flat cards with thin borders, radius 16, plain white titles and KPI figures (the old title/KPI gradients dropped, DRD §12). Token names unchanged; new tokens `--icon-bg`, `--icon-border`, `--chip-bg`, `--brand-bg`, `--brand-fg`. (b) `lib/Icon.svelte`: 22 self-drawn line icons, bundled (no icon library/CDN); used by the sidebar, KPIs, buttons. (c) Sidebar: an icon per item, a filled teal square logo, a footer card with the time zone and the last ingest status. (d) The page header became a single sticky card: title + dimmed folder date, a **compact status line** (● N services · ● errors · ● warnings · ● attack IPs), tools on the right, an initials avatar in the user menu; below it a freshness line "Log folder … · contains logs … · updated …" (replacing "streaming · last event" while Kafka is postponed). At ≤ 900 px the 52 px bar stays. (e) **API**: `/api/meta` now includes `derived_at` per folder (WIB) for the freshness line; test added. (f) KPIs: icon, dimmed suffix, ▲/▼ badge next to the figure, dotted line; `format.delta` gains `short`/`rest`. Alerts became **numbered attention cards** with action links (the plain list form is still available). New component `SplitBar` (large proportion bar). Context chips (`chip`) in the ChartCard/DataTable titles; table headers in small caps; outlined tags; `.btn.accent` button. (g) `tools/cek_kontras.mjs` (new) computes 33 pairs per theme from `theme.css`; one failed (light control border 2.78) and was fixed to `#7b8794` (3.38). Verification: build without warnings; URLs in `web/dist` only XML schemas; `cek_i18n` 176 keys equal; `test_format` 8 passed; `cek_kontras` all pairs meet the threshold; `uji_browser.cjs` 50/50 (one check adjusted: the number of services is now in the status line, not the subtitle); `uji_sesi.cjs` 7/7; screenshots at 1440 dark/light and 390 px compared with the reference. Afterwards, at the owner's request: (h) the picker (`select`) arrow is self-drawn at a fixed 14 px from the edge (the browser's default arrow is cramped and differs per OS); (i) **lowercase system names** (DRD U33): `titleCase` replaced by `sysName`, class `sys`; `uji_browser.cjs` now has 51 checks, including lowercase service names in the sidebar and titles. |
| 13 | 2026-10-06 | Run via the owner's `/loop` after Stage 12a; the real-phone test of Stage 12 is still open. (a) Overview uses three sources per TRD §5.3: `/overview`, the folder summary already loaded by the shell (`/api/folders/{f}`), and `/services/nginx-ingress-controller` for the "HTTP traffic" section; the two page requests run concurrently and are shown together. (b) Card 1 (map + flows) of the service page follows in Stage 20, as planned. (c) Percentages in titles and KPIs follow the language (`37,3 %` / `37.3%`); the old one always used a dot. (d) The "Top errors across services" table now has the columns Service, Level, Message (expandable to the original log line), Count; the old one had a single text column `[Layanan] LEVEL | pesan`. The content and order of the first 25 rows are the same. (e) Small additions to shared components: a button to copy the original log line; horizontal bar labels truncated to the canvas width (Chart.js lets the text disappear off the left edge); logarithmic axes labelled only at multiples of 10, starting at 0.5 so that a count of 1 stays visible; system names in tables are not broken mid-word; a 44 px `(i)` tap area on narrow screens. (f) **ASSUMPTION**: Overview does not get a "What needs your attention" card (the DRD §3.1 layout is kept); that card belongs to the Command Center (Stage 22). (g) Created `tools/uji_tahap13.cjs`: opens the old `../dashboard.html` (Chart.js replaced by a stub, no network) and v2 side by side, then compares KPIs, ▲/▼ changes, the top 25 messages, and the card list; and `docs/04b-page-checklist.md`. Verification 7 of 7 passed: build and `cek_i18n` (228 keys equal); Overview 06 Oct equal to the old one (191,898 · 2,810 · 856 · 124,822 · 3.6 % · 0.04 % · 7 · 18; lines ▼ 36 %, errors ▼ 37 %; 25 messages with the same content and order; 20 cards); pages nginx, simpel-loop, appsmanager, coredns, frontend: KPIs and cards equal to the old ones (coredns "domains failing to resolve"); nginx Error line Σ 125 (item 2); simpel-loop donut 29 Sep WARN 9,614 without ERROR (item 4); 01 Oct band "contains only 4 log lines; 4 corrupt files" and the empty service explains why; filter "JWT" 3 rows + "3 matching rows"; checklist of 8 combinations (language × theme × width) for both pages. Scripts: `uji_tahap13.cjs` 39/39, `uji_browser.cjs` 51/51, `uji_sesi.cjs` 7/7; contrast and formatter tests still pass. |
| 14 | 2026-10-06 | (a) **API**: `services` in `/api/trends` is now ordered as in the old one (first appearance: oldest folder, then file order); previously alphabetical. Test added. (b) **ASSUMPTION Q4**: default range 30 folders; the choice is remembered per browser. The first column of a range has no ▲/▼ because the previous folder is outside the range (with 11 folders, same as the old one). (c) Data completeness: numeric cells get a "Corrupt" mark when that service has corrupt files, and "Corrupt" replaces "Empty" when there are 0 lines because of corruption (B05); 16 cells across 11 folders. (d) **Bug found and fixed in a shared component**: Chart.js attaches internal properties to data arrays; arrays from Svelte reactive state reject this (error `state_descriptors_fixed`, then "Canvas is already in use"). ChartCard now always copies arrays; Trends stores its data as `$state.raw`. (e) The range picker was tested on a **40-folder simulation database** (`tools/simulasi_setahun.py --folders 40` in the scratchpad, the real database only read, then deleted), because the 11 real folders are fewer than the smallest range. (f) In the middle of the stage, the branch received a merge from `master` (another session's Stage 11 note + another version of `ukur.py --api`); the merged `tools/ukur.py` was broken (two `ukur_api`, duplicate arguments) and was unified in a separate commit. Verification 5 of 5 passed: build + `cek_i18n` (250 keys); `tools/uji_tahap14.cjs` 21/21 side by side with the old dashboard (6 charts: every series and figure equal for 11 folders; error table + changes: every cell equal; completeness: equal except the Corrupt marks; simpel-loop 30 Sep "None"; 1 Oct "Corrupt"/"Empty"; folder picker disabled "Trends show all folders"; 390 px the table still scrolls; 8 combinations) and 6/6 on the simulation (14 / 30 / 90→40 / all = 40 columns; table starts at the right end; Service column pinned; range remembered). Regressions: `uji_tahap13` 39/39, `uji_browser` 51/51; `ukur.py --api` in-process and against the server: 21 endpoints, 0 above target. |
| 15 | 2026-10-06 | (a) "Key findings" are composed from `Findings.svelte` + keyed dictionary entries (bold part + sentence, two languages, data values as text parameters). The lists of IPs/upstreams/organisations/accounts in the sentences are taken from the first page of the table when that table is complete, so that the order is exactly as in the old one; when not complete, from the API `findings` (alphabetical). (b) `DataTable` gains custom cells via *snippets* (components, not HTML in a string) and a minimum column width (`minw`); `IpCell` no longer breaks IPs. Without `minw`, long URLs and account names break letter by letter in narrow columns. (c) Footnotes and attack categories, account flags, and event sentences ("… success from …") are translated as labels; event times stay as-is like the old one. (d) The "no nginx" note is shown only when the nginx log really is absent (old: also when nginx is present but without attacks, with a wrong sentence). (e) KPIs laid out 4 + 4 (U5) on wide screens, 2 columns on phones. Verification 5 of 5 passed: build + `cek_i18n` (322 keys); `tools/uji_tahap15.cjs` 35/35 side by side with the old one for 06 Oct, 29 Sep, 28 Sep (8 KPIs equal: 06 Oct 88 · 14 · 5 · 62 · 9 · 1 · 0 · 4; findings equal sentence by sentence: 06 Oct 6 items — Log4Shell, Rancher, 62 2xx endpoints, cloud, Ombudsman network, 4 resets — and 29 Sep 11 items; cards equal; 5 tables equal row by row on the core columns; 28 Sep the no-nginx note + login section); URLs `<script>alert(…)`/`onerror` on 29 Sep shown as text, 0 elements injected, 0 dialogs; `grep @html` 0; 8 combinations of language × theme × width. Regressions: `uji_tahap13` 39/39, `uji_tahap14` 21/21, `uji_browser` 51/51, contrast passes. |
| 16 | 2026-10-06 | (a) The "Root cause summary" uses a generic `Summary.svelte` component (text / bold / code fragments, two languages) because the old sentences contain `<code>` mid-sentence. (b) The upstream DNS in the DNS sentence is taken from the configuration (`/api/meta` → `dns_upstream`); the old one hard-coded `10.88.1.100` (same default value). If no domain is affected, the ", including …" fragment is omitted (the old one wrote "termasuk ke ."). (c) `ChartCard` gains a footer slot (`footer`) for the "Expired refresh tokens: N" note (B07) below the JWT chart; when there is more than one service, the breakdown is included. (d) The `.kpis.four` class (4 columns on wide screens) moved to `theme.css`, used by Security and Availability. (e) Availability percentages follow the language (`98,000 %` / `98.000%`); the old one always used a dot. (f) Test tooling: the old 401 table is compared with the first 30 rows of v2 by the E2 rule (count order identical; rows with equal values at the 30 boundary may be chosen differently). The table lookup in `uji_tahap15/16` now skips chart cards with similar titles (previously one check passed vacuously). Verification 5 of 5 passed: build + `cek_i18n` (389 keys); `tools/uji_tahap16.cjs` 65/65 side by side with the old one — Root Causes 29 Sep: the 5-item summary equal, the JWT chart equal, **new** "Expired refresh tokens: 237", the 401 table "Showing 30 of 653"; 06 Oct, 30 Sep (connection error item 200 → 1,200, expected), 27 Sep also equal; Availability 30 Sep: KPI pod connection errors **1,200** (old 200), retries **825**, **10** incidents, the other KPIs, 3 charts, and tables equal; 06 Oct equal; 28 Sep the no-nginx note; 8 combinations for both pages. |
| 17 | 2026-10-06 | (a) **ASSUMPTION (Tracing)**: folders that have simpel-loop but none of whose requestIds match nginx (`matched = 0`, e.g. 27 and 28 Sep) show the note "Tracing needs the om-be-simpel-loop and nginx ingress logs …" (DRD §6.6, plan for 27 Sep); the old dashboard showed a page with zero KPIs for those folders because `corr` = `[0, N]`. (b) The Tracing KPIs failed / failed IPs / slow and their two charts are computed from **all** traces (TRD §4.4 items 1, 9): 29 Sep failed 3,245 → 3,479, IPs 150 → 176, slow 15 → 24; the IP and error-type charts differ slightly from the old ones because the old one used 300 traces; 06 Oct (111 traces) exactly equal. (c) Business: KPIs whose logs are absent show "–" + "No <service> log in this folder" per source (simpel-loop 7 KPIs, report 2, appsmanager 2), not 0 (U16); the change vs the previous folder only for simpel-loop metrics with the old "comparable" rule. Business metric labels come from the `biz.<slug>` dictionary; metrics not yet in the dictionary are shown as-is. (d) Pods: the file status "Corrupt" replaces the old "Has Log"/"No Log" (B05; 06 Oct: 3 corrupt files containing 1 line, "Has Log" in the old one); "Pods with retries" gains an (i) explanation. (e) Trace table: the URL column uses `AttackUrl` (host from the configuration + path, UA below it), URLs truncated at 200 with the full text in a tooltip; the time column may wrap to two lines so that the table fits at 1440 px. (f) Test tooling: the activity table is compared by the E2 rule (ties at the 20 boundary may be chosen differently); the local server caches `index.html` at startup, so the server is restarted after a build. The a11y `tabindex` warning in `Trends.svelte` (since Stage 14) has not been changed yet. Verification 7 of 7 passed: build + `cek_i18n` (443 keys); `tools/uji_tahap17.cjs` **91/91** side by side with the old one — Pods 06 Oct / 29 Sep / 28 Sep: 5 KPIs, 2 charts, 3 tables equal, status "Corrupt" on 3 files; Business 29 Sep: 12 / 108 / 35 / 12 / 314 / 18 / 55 / PDF 813 / 32 / login 389, changes, 5 charts, 2 tables equal; 30 Sep: 9 KPIs "–" + explanation, login 110 / 66; Tracing 29 Sep: 60,665 / 22,638 / 37.3 %, the table "Showing 300 of 550" and after loading everything all 300 old rows are in v2; 27 Sep the note (ASSUMPTION) and 30 Sep without simpel-loop the note as in the old one; 8 combinations for all three pages. Regressions pass: `uji_browser` 51/51, `uji_sesi` 7/7 (server with `S4_SESSION_IDLE_MINUTES=5`), `uji_tahap13` 39/39, `uji_tahap14` 21/21, `uji_tahap15` 35/35, `uji_tahap16` 65/65; `test_format` 8/8; `cek_kontras` all pairs; URLs in `web/dist` only XML schemas. |
| 18 | 2026-10-06 | (a) **API added** beyond the file list: `GET /api/admin/ingest/status` now includes `last_run` (the last finished ingest, read from the `ingest_run` table: UTC time, status, files seen/changed, warnings), because the in-memory status is empty after the server restarts; a test in `test_api.py` added. (b) **ASSUMPTION "next request"**: the App re-reads `/api/me` on every tab change and reload; a page left open without navigation keeps the old menu until then (the API still refuses with 403 immediately). (c) **ASSUMPTION**: deactivating your own account is not offered (the server allows it if another admin remains), same as deleting yourself. (d) The audit log loads the 500 most recent entries; the table shows 50 + "show next" and filters in the browser; if there are more than 500, the note "latest 500 of N". (e) The "Import from S3" card contains the Stage 19 note. (f) New components `lib/Dialog.svelte` (native `<dialog>` + `showModal()`: focus trapped, Esc, focus back to the trigger; full screen at ≤ 560 px) and `lib/RowMenu.svelte` (⋯ menu with `position: fixed` so it is not clipped by the table; disabled items with a reason). `DataTable`: the phone row-card cells are now `justify-items: start` (tags do not stretch to full width) — applies to all pages, regressions run. (g) `format.utcToWib()` (account/ingest times are stored as UTC) + test. (h) Server error messages are in Indonesian; the screen maps error codes to the dictionary so that it is bilingual. (i) The `placeholder.admin` key removed. (j) The sidebar footer "Last ingest …" still comes from the in-memory status (`/api/meta`), not yet using `last_run`. (k) Test tooling: an ingest without changes finishes in < 0.5 s, so the "running" status is not always caught between two reads; this is proven with the disabled button + a new `run_id`, while "the dashboard stays open during ingest" is proven more strongly by `test_ingest_lewat_api_dan_dashboard_tetap_terbuka` (forced ingest). Verification 9 of 9 passed: build + `cek_i18n` (523 keys); `tools/uji_tahap18.cjs` **33/33** (twice in a row) with two windows — add rina → must change password → dashboard without the admin menu; promote/demote takes effect on the next tab change; a regular user on the admin screen gets "No access" + 403; password reset and deactivation end the session immediately, the temporary password is shown once; the last admin is not offered, PATCH → 409, stale list → message in the dialog; "Ingest now" → "0 files changed", data 200 while running; audit of 11 action types with time, actor, IP, without passwords/tokens; 8 combinations for both screens; full-screen dialog at 390 px. Regressions pass: `pytest` 239 passed, 2 skipped; `uji_browser` 51/51, `uji_sesi` 7/7, `uji_tahap13` 39/39, `uji_tahap14` 21/21, `uji_tahap15` 35/35, `uji_tahap16` 65/65, `uji_tahap17` 91/91 (after the `DataTable` change); `test_format` 9/9; `cek_kontras` all pairs. |
| 19 | 2026-10-06 | **PARTIAL.** (a) **Not yet tested: the two Manual rows** (dry run and import of `2026-09-26` with real credentials, including proof of ASSUMPTION T14 and the figures 1,203 / 6 / 11). `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` in this session's environment are only placeholder values (14 characters, not the shape of an AWS key); S3 answers `InvalidAccessKeyId`. The S3 Jakarta endpoint is **reachable** from this environment (via the proxy), but X2 must still be checked on the server. Steps for the owner: put the real key in `.env` + `S4_IMPORT_BUCKETS`, then `py -m monishield import --dry-run s3://simpel4-backup/k8s-logs/2026-09-26/` and import into a separate `S4_DATA_DIR` (README §Import). (b) **API addition**: `GET /api/admin/import` (admin only: enabled?, the accepted link shape, credential status, the last 20 jobs) for the history on screen; `/api/meta` gains `imports` (enabled, credentials available + source). (c) New configuration `import_timeout_minutes` (30). (d) The per-job object plan (fetch/skip + reason) is kept in **memory** (last 20 jobs), the `import_job` database table stores the summary; job statuses `berjalan` / `coba` / `selesai` / `gagal` (running / dry run / done / failed). (e) "Same as the previous download" is recorded in a `.s3-import.json` manifest in the inbox folder (size + ETag + file still present). (f) An unsafe object key (`..`, `//`, control characters) **cancels the whole import** (TRD §9.6); objects outside the pattern are only skipped. (g) The ingest after an import uses `IngestManager.run_blocking` (waits for other ingests, shares the lock). (h) Pasted credentials: the key ID must be uppercase letters/digits, 16–128, the secret 16–128; audited without the values. (i) Error messages: Indonesian = the server message (with details), EN = the dictionary per code; the short job messages in the history stay as Indonesian server text. (j) `tools/server_uji_impor.py` runs the dashboard + a fake S3 for browser tests; the S3 endpoint is redirected via `importer.ENDPOINT`, which is deliberately **not** available in the configuration. (k) `README.md` created (it did not exist yet) with an example read-only IAM policy for `simpel4-backup/k8s-logs/`. Verifications that could be run, all passed: `pip install -e ".[test,s3]"` + `pytest tests/test_import.py` **28 passed** without contacting AWS (the tests were shown to fail when the `.gz` pairing rule or the prefix allowlist is broken); without `import_buckets` → "Import is not enabled"; `bucket-lain`, `bukan-tanggal`, and another Jakarta bucket → refused before contacting AWS; without credentials → a message on how to provide them, no files written; no AWS keys in `data/` (key pattern 0; "ASIA" only as an ISP name) and `status` says "import credentials: available (environment)"; regular user → 403 (test); machine token → **202** on a real server (the job then fails at S3 because of the placeholder key), machine token to the credentials endpoint → 401; pasted credentials gone after the server restarts and absent from the server log and the account database; `tools/uji_tahap19.cjs` **22/22** (dry run 0 bytes, import + confirmation + ingest → folder appears, re-import 0 objects, paste/remove credentials, EN errors, audit without secrets, 8 combinations). Regressions: `pytest` 267 passed, 2 skipped; `uji_tahap18` 33/33; `cek_i18n` 582 keys; `test_format` 9/9; `cek_kontras` all pairs. |
| 20 | 2026-10-06 | (a) **Expected difference**: the planned KPIs "222 locations, 12 countries, 2,030 requests from outside Indonesia" are the old dashboard's DB-IP figures; v2 uses MaxMind GeoLite2 (Stage 7 plan, item i), so 06 Oct = **166 locations, 9 countries, 1,293** from outside Indonesia. Source IPs (516), modules (9), pods (15), total requests (124,822), and 0 from internal IPs are **the same** as the old one. (b) **Owner decision in the middle of the stage**: cluster circles **without numbers** (DRD §7.5/ASSUMPTION D5 changed; size still by requests, the number in the tooltip); the largest-location labels follow the owner's example style: bold name + a small line "N IP · N req". (c) **ASSUMPTION**: the labels of the 6 largest locations follow the collision rule (DRD §7.3 "without overlapping"); in the Indonesia view 5 are shown, the 6th label (Serang, ±15 px from Jakarta + the server label) appears when zoomed in — the old dashboard drew them overlapping. (d) **Owner's question: OpenStreetMap?** Online OSM tiles are not used (they would send the IP of whoever opens the dashboard to a third party, breaking the project rules; the OSM tile policy); OSM data could follow later as self-served vector tiles (e.g. PMTiles) if the owner decides — the map engine stays MapLibre. Until then ASSUMPTION D4 (Natural Earth) stands. (e) **Zoom smoothness**: in the test environment without a GPU (software WebGL) the zoom animation runs at ±10–12 frames/second; almost all of the load comes from filling the land polygons (without land 30 fps, background only 60 fps). Testing geometry simplification (`tolerance` 1 and 2) gave no consistent improvement, so it was not applied; **needs to be tried by the owner on a device with a GPU**. (f) Noto Sans Regular/Bold glyphs for the ranges 0–255, 256–511, 7680–7935 (Vietnamese city names), 8192–8447 from openmaptiles/fonts v2.0 + `OFL.txt` (780 KB). (g) MapLibre 5.24 (BSD-3) is loaded as a separate chunk (±1 MB) only when the map is opened; a build plugin strips the unused maplibre.org/GitHub links, so only XML schemas + the MaxMind and GeoNames attribution links remain in the build output. (h) Tooltip on cursor/tap; points can **not** be focused one by one with the keyboard (ASSUMPTION: the flow table is the equivalent, §7.9, with a "Skip the map" link); keyboard on the map: arrows, +/−, 0, Esc. (i) The full-screen button ⛶ at ≤ 900 px is separate from ⤢ (back to the preset). (j) The bilingual cooperative-gesture text is replaced via MapLibre's UI dictionary (`map._locale`) and then re-enabled. (k) Service page: the `services/{svc}` response gains `has_flows` (API added + test) so that services without flows do not request `/map` (which answers 404). (l) `DataTable` gains `search` (filter from outside). (m) Test hook `box.__map`. (n) The `Placeholder` page and the 14 `placeholder.*` keys removed (all tabs now have pages). (o) The flow table note names MaxMind; "at most 3,000 flows" removed (v2 does not truncate; first 100 + more, X6). (p) Not yet tested automatically: pinch to zoom (tested: two-finger pan, one finger does not pan the map). Verification: build + `cek_i18n` (608 keys); `tools/uji_tahap20.cjs` **26/26** — KPIs and flow table vs the old one, module switch (camera stays), mouse wheel + Ctrl hint, keyboard, click a point → "Show in table", world → Java (clusters split, labels progressive), theme/language (position stays, attribution), **internet cut → the map still shows**, **0 requests to other domains**, 28 Sep note, service om-be-simpel-loop collapsed → that module's flows, 390 px touch (CDP), 8 combinations. Regressions pass after the `DataTable` and service page changes: `pytest` 267 passed, 2 skipped (including parity E1–E4); `uji_browser` 51/51, `uji_sesi` 7/7, `uji_tahap13` 39/39 (previously 38/39: a 404 in the console of non-module service pages, fixed with `has_flows`), `uji_tahap14` 21/21, `uji_tahap15` 35/35, `uji_tahap16` 65/65, `uji_tahap17` 91/91, `uji_tahap18` 33/33; `test_format` 9/9; `cek_kontras` all pairs. |
| 21 | 2026-10-06 | (a) **View scheme** `S4_ATTACK_RULES` = `crs` (default) / `lama`, and `S4_ATTACK_PARANOIA` (1–4); the old rules (`attack_cat`, `agg_attack_*`) are still computed, the CRS aggregates are in new tables `agg_crs_url/ip/hour` (plan: the old aggregates replaced). The parity tests use `lama`. (b) Category = **CAPEC/CRS family** (e.g. `242/xss`), because some rules carry only a generic CAPEC; the CAPEC is chosen by the largest total score. (c) Automatic re-derivation uses `folder_state.crs_version` (not `rules_version`). (d) `@pm` is built as a regex trie (3.4 → ≈ 1 ms per path). (e) **Limitations**: libinjection (942100, 941100) is not available in Python, the tautology `' OR 1=1` is only caught at PL2; common tool UAs (curl, Go-http-client, python-requests) are not attacks according to CRS. (f) Figures changed deliberately: total attack requests 315 → 110, 06 Oct 88 → 50 and IPs 14 → 4; `tests/test_api.py::test_folder` attacker IPs 2 → 1; the critical KPI = CRITICAL severity (new label). Details in `docs/04c-crs-detection.md`. (g) Clean paths tested for false positives: 30,512 (the plan said 22 thousand): 0.043 %. Verification: `ambil_crs.py --check` equal (176 taken, 27 skipped); `pytest test_detect test_config` 34 passed, 2 skipped (real data in use by the server), earlier `test_detect` with real data + test_api 67 + test_refdata 13 passed; parity E1/E3/E4 0 differences with the `lama` scheme; `derive --all` 39 s, ingest 09-29 `--force` 24 s; `uji_tahap21.cjs` **22/22**. Browser regressions: uji_browser, uji_sesi, uji_tahap 13, 16, 17, 18, 20 pass. **Not re-run** at the owner's request: uji_tahap 14 and 15 with the server on `S4_ATTACK_RULES=lama` (the round that ran used CRS because uji_sesi restarted the server without that variable, so the difference in attack figures = a deliberate change) and the full pytest. |
| 22 | 2026-10-06 | (a) **ASSUMPTION** (DRD §12): the IP Map tab is absorbed at the same address `#/peta?modul=` (old links still work); the sidebar label and title become "Command Center"; `IpMap.svelte` deleted. (b) This stage's plan had no file list or verification; both were written when it was done (the Stage 22 section). (c) The main KPIs and attention items were chosen from the TRD §12 list (attacks, failed logins, 5xx, pod connection errors) + corrupt files; the 6 old map figures are shown as a compact line next to the module picker. (d) **Owner request in the middle of the stage**: the map as wide and as tall as the screen (`100dvh − 300 px`, phones `− 220 px`), attention cards below the map (initial design: beside it). As a consequence the Stage 20 390 px item "map 4:3" is replaced by "screen height". (e) Additions beyond the stage: `pyproject.toml` now includes `crs_rules.json`, `capec.json`, `CRS-LICENSE.txt` (Stage 21 forgot; a non-editable install failed to load the rules); the README gains a "How to run" guide (owner request). Verification: `pytest tests/test_api.py` 68 passed (including the new Command Center test); viewed at 1440/390 px and a folder without nginx (28 Sep) with no horizontal scroll and no console errors; `uji_tahap20.cjs` 25/26 in the new place, the only failure = the 4:3 size deliberately replaced (624 px = 844 − 220), its expectation updated but the test not re-run. |
| 24 | 2026-10-07 | (a) A new stage outside the original plan, at the owner's request (suggestions 1–9). (b) **ASSUMPTION** about the spike thresholds (2× and +50 errors / +20 JWT) and browser print as PDF. (c) The search shortcut is **Ctrl+K**, not `/` as in the suggestion, because since Stage 12 `/` focuses the table filter. (d) The IP profile uses the `service` slot in the route (`#/ip/<ip>`); the `?cari=` parameter is dropped when changing tabs via navigation. (e) `test_tren` updated: the Trends response now has the `completeness` and `heat` keys. (f) The old attention items did not change; the order is still red first. (g) Folder 6 Oct shows no ▲/▼ because 5 Oct is incomplete ("not compared"), deliberately. (h) The old browser tests (uji_tahap13–21) were not re-run; the Stage 24 checks were done with a one-off Playwright script. |
| 25 | 2026-10-07 | (a) A new stage at the owner's request. (b) **ASSUMPTION** the button is for admins only. (c) New folders are detected from the top-level directory listing only; new files in an old folder only become visible when a sync runs. (d) The compose/image names were changed too (`monishield`) because Docker is not yet installed on the server; if it were, the old volumes would be named `simpel4_*`. (e) The old browser tests were not re-run (the tab title is now "… · MoniShield"). |
| 25 | 2026-10-07 | (f) **Fixes from the owner's report**: (1) ingest failed with `Duplicate key "run_id: 28"` — DuckDB sequences (`seq_run_id`, also `seq_file_id`) can lag behind the stored rows after the process is killed; new numbers are now `max(nextval, max(id)+1)` (`ingest._next_id`, safe because there is a single writer), and databases that already lag heal themselves; test `test_sequence_tertinggal_tidak_membuat_duplicate_key` (fails with the same error without the fix). (2) import failed with `No module named 'botocore'` — the optional `s3` package was not installed: the import is now refused up front (`no_s3_library`, a message on how to install it, with no failed job), the screen disables import with an explanation, the CLI checks too; `run.sh` installs `.[s3]` and reinstalls when `pyproject.toml` changes (previously only when `.venv` did not exist yet); test `test_tanpa_boto3_ditolak_dengan_cara_memasang`. pytest import+ingest+api 122 passed. |
| 25 | 2026-10-07 | (g) **S3 import: automatic extraction** (owner request): `S4_IMPORT_EXTRACT` (default true) — each downloaded `.log.gz` is extracted to `.log` in the temporary folder and the `.gz` is discarded before moving to the inbox; corrupt/truncated gzip → `bad_gzip`, output > 20× the object limit → `extract_too_large` (import cancelled, inbox unchanged); the manifest records `stored`/`stored_size` so that a re-import does not download again; `.gz` files from older imports are extracted in place without downloading. Tests +5 (import+ingest+config 63 passed). |
| 25 | 2026-10-07 | (h) **Delete a log folder from the list** (owner request): a "Log folders" card in Ingest & import (`lib/FolderManager.svelte`; `GET /api/admin/folders`, `POST /api/admin/folders/{f}/delete` `{delete_inbox}`, `POST …/restore`, admin only, audited). The folder's data is deleted (`ingest.forget`); inbox files are deleted too if ticked; files in the main log folder are NOT deleted (read-only) — the folder is recorded in a new table `folder_ignored` (column `ignored_folder`, so that it is not wiped by `forget`), so that ingest, sync, and the new-folder badge skip it until it is restored. Test `test_hapus_folder_dari_dashboard_dan_pulihkan`; the role matrix test uses a non-existent date for the delete route so that it does not delete test data. pytest api+ingest+import 128 passed; browser: delete 26 Sep → Ignored (files on disk intact) → Restore + Sync → 19 files back. |
| 25 | 2026-10-07 | (i) **Package name `simpel4` → `monishield`** (owner request): code folder `monishield/`, `python -m monishield …`, `pyproject` (name + package + data), `run.sh`, Dockerfile (user `monishield`), compose, tools, tests, web package name, download User-Agent. **Not** renamed, so that old data/configuration keep working: the file `data/simpel4.duckdb`, the `S4_` prefix, the JWT issuer, the PostgreSQL user/db in compose, and names that refer to the SIMPeL4 system (host `*simpel4.ombudsman.go.id`, bucket `simpel4-backup`). When reinstalling: `pip install -e .` once (run.sh does it automatically because `pyproject.toml` changed). Also fixed: `test_kolom_csv_sama_dengan_skema` (failing since Stage 21 because of the derived CRS columns; the full pytest was not run at that time). **Full pytest: 308 passed, 2 skipped.** |
| L7 | 2026-10-07 | **Step 7 Docker Compose (migrate/07) done; details and output in `docs/06-docker.md`.** (a) Services: `app` (in-process ingest, K1) + `postgres` (K11); `ingest` in the `job` profile triggers `app` over HTTP; `proxy` (Caddy), `pgadmin`, `dbgate` optional per profile. (b) **Owner request**: pgAdmin 9.8 (PostgreSQL) and DbGate 6.6.4 for DuckDB — DbGate opens a **read-only copy** `data/snapshot/monishield.duckdb` (`S4_DUCKDB_SNAPSHOT`, format v1.2.0, refreshed on every ingest, replaced atomically) because DuckDB may only be opened by one process. (c) The DbGate DuckDB plugin always opens in write mode (fails on a `:ro` mount): only the `snapshot/` folder is mounted (`volume.subpath`), read-write. (d) Fixed during verification: `${PGADMIN_*:?}` made `up` fail without a profile (now `:-` + a check in the DbGate entrypoint); pgAdmin rejects `.local` emails and fails on `[::]` without IPv6; `kill -9` left a 194 MB temporary CSV + a `berjalan` (running) run (now cleaned up at the start of an ingest, `ingest._cleanup_killed`). (e) Application code changed: `config` (`S4_API_URL`, `S4_DUCKDB_SNAPSHOT`), `db.snapshot`, `api/admin`, `api/app`, `ingest`; tests +3. Verification: build 41 s, image 413 MB (105 MB compressed); `run --rm ingest` 195 files / 11 folders 73.4 s; healthy in ±11 s; `tools/uji_docker.cjs` **8/8** (summary, services, Command Center, pgAdmin, DbGate table `nginx_access`); 73/73 dashboard requests OK during a forced ingest; `down`/`up` data + accounts intact without re-ingest. |
| 25 | 2026-10-07 | (j) **Collapsible left navigation** (owner request): a button next to the logo (screens > 900 px) turns the 236 px sidebar into a 68 px icon rail; labels via `title`, badges become red dots, group titles become lines; page content, charts, and the map widen accordingly. The choice is stored per browser (`localStorage` `side`). Screens ≤ 900 px are unchanged (the ☰ drawer is always labelled). New keys `nav.collapse`/`nav.expand`, icons `side-close`/`side-open`, token `--side-w-c`. **ASSUMPTION** "close" = collapse to icons (not hide completely) so that navigation stays one click away. Playwright verification 10/10 (width, content shifts, Command Center map 1104 → 1272 px, remembered after reload, icon click, keyboard, 390 px, no JS errors); build + `cek_i18n` (762 keys) clean. |
| 25 | 2026-10-07 | (k) **Automatic S3 sync + folder upload** (owner request: "automate data sync from S3 when there is a new folder … add a folder upload feature"). (1) `S4_S3_WATCH` (parent folder, checked against `S4_IMPORT_BUCKETS`), `_MINUTES` 60, `_DAYS` 30, `_MAX_FOLDERS` 3, `_RECHECK_DAYS` 1: a scheduler in the `app` process (first run 1 minute after start) + `POST /api/admin/import/sync` (admin/machine token) + a "Check S3 now" button; folders listed via ListObjectsV2+Delimiter; unknown folders are imported via `importer.run` and then ingested, one job per folder; synced folders that are still recent are re-checked (only new objects downloaded). **ASSUMPTION**: a folder deleted by an admin while sync is on is recorded as *Ignored* (otherwise it would be downloaded again). (2) Upload: `monishield/upload.py` + `api/upload.py` (plan → PUT per file, streamed to disk, size must match → finish: extract .gz, move to the inbox, ingest in the background); limits = the S3 import limits; `..`/control paths reject the whole upload; folders that exist in the main log folder are skipped. UI: an Upload log folder card (`webkitdirectory`, 3 files at a time, byte progress via XHR), a sync section in the S3 Import card, the folder list reloaded whenever an ingest finishes; inbox tag "(S3/upload)". Tests: test_import +9 (selection, allowlist, sync API/token/re-check, deleted folder, scheduler), test_upload 10; the fake S3 supports Delimiter; Playwright e2e 10/10 (server + fake S3: Check S3 → 2 folders + 1 later, folder upload → ingest, 390 px, no JS errors). (3) **Owner request in the middle of the stage**: the browser's native `type=date` input replaced by `lib/DatePicker.svelte` (own calendar, Monday on the left, ID/EN via Intl, dark/light theme, dates after today WIB disabled, keyboard per the ARIA grid pattern, Esc/click outside closes); Playwright test 15/15. Full pytest 331 passed, 2 skipped. |
| 25 | 2026-10-07 | (l) **Owner request**: "just enter the URL s3://simpel4-backup/k8s-logs … auto download and ingest", Swagger with the same login, Indonesian text in English mode, the Sync button also checks S3. (1) The parent folder address is filled in from the screen (`PUT /api/admin/import/watch`, admin; a new table `app_setting` in the account database, created by `create_all`) and overrides `S4_S3_WATCH`; the trailing slash is optional; an address ending in a date is refused (`watch_is_date`); the scheduler is always running and is woken when the setting changes (first check in ±5 s). (2) The **Sync data** button: when sync is on, `POST /import/sync` + wait, then a local ingest; the S3 status is included in `GET /ingest/status` (`s3`). (3) Swagger UI `/api/docs` + `/api/openapi.json`: only for users with a session who have already changed their password (not yet → 303 to `/?next=/api/docs`, the SPA returns there; only that address is followed); `swagger-ui-dist` 5.33.1 assets (Apache-2.0) copied at build time, `validatorUrl` off, init in a separate file (CSP); the CSRF header added automatically; grouped per tag; a link in the user menu. (4) EN: `srv.js` translates text from the server piece by piece (ingest warnings, import job summaries, skipped-file reasons, triggers, audit details, "Lambat N dtk" (slow N s)) and `errText` maps error codes to the dictionary (`err.*`, `imp.err.*`, `adm.err.*`); failed import jobs are stored as "[code] message"; sync errors become an object {code, where, message}. Playwright audit of all pages in EN (real data): the only remaining Indonesian text is log data (SIMPeL4 endpoint paths). Tests: test_import +8 (address from the screen, kept after a restart, turned off overrides .env, user 403, scheduler woken), test_api +2 (Swagger); Playwright e2e 18/18. |
| 25 | 2026-10-07 | (m) **Owner request**: "remove every sentence that smells of simpel4" and "make the navbar logo the same as the logo on the login page". (1) Text: the map label "Server SIMPEL4" → key `map.server` ("Server aplikasi"/"Application server"), the sample bucket on screens/dictionary/server messages → `nama-bucket`/`my-bucket` (the sync placeholder is taken from the server's allowlist), the Swagger description, CLI help, package docstring, README, comments in `.env.example`/compose/Dockerfile, sample paths in docs/06. (2) Internal names: PostgreSQL user/database `monishield` (compose, pgAdmin, DbGate), file `monishield.duckdb` (the old file is moved automatically by `db.open`, test `test_berkas_nama_lama_dipindah`), JWT issuer `monishield`. (3) **Not changed, deliberately**: the addresses of the monitored system (`*.simpel4.ombudsman.go.id`, service `om-be-simpel-loop`) and the `S4_IMPORT_BUCKETS` allowlist value = the owner's log bucket (`simpel4-backup`) — data/configuration, removing them would break detection and sync; the `S4_` variable prefix (renaming all variables would break existing `.env` files); the old design documents (PRD/DRD/TRD/plan) as history. (4) Logo: `lib/Logo.svelte` (shield + M, same as the favicon) is used by the login page, the left navigation (also when collapsed), the narrow-screen header, and the Swagger header; `APP_MARK` (the "MS" box) removed. Verification: Playwright 5/5 (identical logo paths, no "SIMPEL4", 390 px, Swagger), docker compose with PostgreSQL `monishield` healthy. |
| 25 | 2026-10-07 | (n) **Owner request** (suggestions 1, 3, 5, 6). (1) **Notifications** via Telegram/Discord/email: `monishield/alerts.py` + `api/notify.py` + page `#/admin/notifikasi`; credentials filled in on screen, stored in `app_setting` in the account database (**ASSUMPTION**: not encrypted in the database — the `cryptography` library is not available; protected by PostgreSQL access rights), never sent back (`public()`), empty = unchanged, `clear` = delete; validation of the token/chat ID shape, webhooks only `https://discord.com/api/webhooks/…` (prevents SSRF), SMTP starttls/ssl/none. Events: spike vs the average (`command.baseline`, threshold per figure), critical attacks, ingest failed, S3 sync failed, today's folder still missing after hour N WIB (checked every hour), summary (off by default); once per key (table `alert_log`, history on screen); only folders ≤ 2 days from the newest folder (re-ingesting an old folder does not trigger); messages without IPs + `scrub()` as a safeguard; two languages; background thread. (3) **Real S3 test** — at first it seemed to fail (`InvalidAccessKeyId`), but it turned out to be a **testing mistake**: the container environment already had AWS_ACCESS_KEY_ID/SECRET variables holding 14-character dummy values, and environment variables override `.env`. Repeated without those variables: the key is valid (STS: user hafiz-TIM), `s3://simpel4-backup/k8s-logs/` contains 12 folders (26 Sep–7 Oct); automatic sync via the API fetched 2026-10-07 (18 objects, 18 .gz extracted, ingest 15 s). **Data finding**: the 7 Oct folder in S3 is corrupt at the source — 5 files contain a single error line from the export tool (`failed to get parse function: unsupported log format: "\x00…"`, 3–37 MB) and 13 files are empty; 5 Oct is normal. Ingest already marks them as corrupt; a dedicated warning was now added (`ingest._export_error`, test `test_berkas_berisi_galat_ekspor_diberi_peringatan`). Credentials only in the local `.env` (not in git). (5) **Average comparison**: `command.baseline` = the average of ≤ 7 previous comparable folders (lines ≥ 50 %; ingress separately), at least 3; the Command Center chooses average/yesterday (stored per browser); service & JWT spikes use the average when available. Overview/Business stay vs the previous folder. (6) **Block list**: `GET …/security/blocklist` (nginx/ingress/txt/json, 1–90 folders, minimum severity & hits), excludes private/reserved IPs, `S4_BLOCKLIST_EXCLUDE_ORG` (default OMBUDSMAN — the real data contains 2 Ombudsman IPs in the attacker list), `S4_BLOCKLIST_EXCLUDE`; a dialog in Security (preview, Download, Copy). The styling of number/email/url inputs was unified. Tests: test_alerts 16, test_api +2 (average, block list); Playwright e2e 14/14 (fake Telegram/Discord). |
| 25 | 2026-10-07 | (o) **Owner request**: "add one page about configuration covering everything to do with creds". (1) Page `#/admin/konfigurasi` (user menu → **Configuration**, admin only) replaces the Notifications menu; the old address `#/admin/notifikasi` opens the same page and scrolls to the Notifications section. Sections: AWS S3 (Access Key ID, Secret, Session token, region + the read-only bucket allowlist), automatic S3 folders (the same watch API), MaxMind GeoLite2, Notifications (the same component), block list exclusions, and the status of the keys that **stay .env-only** (`S4_JWT_SECRET`, `S4_JOB_TOKEN`, `S4_AUTH_DATABASE_URL`, `S4_ADMIN_PASSWORD`, `S4_IMPORT_BUCKETS` — the server's security foundation; the screen only shows set/empty). (2) `monishield/settings.py` + `api/config_api.py` (`GET/PUT /api/admin/config`, `POST /api/admin/config/test`): the values are stored in `app_setting 'config'` and then **applied onto the running server's configuration object** (`settings.apply`), so that S3 import/sync, MaxMind refdata, and the block list use them immediately without a restart. Order: pasted credentials (memory) > screen values > `.env`; "Clear screen values" falls back to `.env`. `create_app` now uses a copy of the configuration (`cfg_env` = the original .env values). The CLI without a server (local `ingest`/`import`) also reads the screen values (`settings.for_cli`). (3) Secrets are never sent back (Access Key ID/Account ID masked as `AKIA…1234`), an empty field = unchanged, the audit records only the group name. Values are checked before saving (AWS key shape, ID+secret pair, region, numeric Account ID, CIDR, regex). **ASSUMPTION** as in (n): not encrypted in the account database. (4) Connection test: AWS = `ListObjectsV2` of 1 object on the parent folder/first allowed prefix; MaxMind = HEAD to the GeoLite2 download link (302 = key accepted, without downloading; refused when `S4_OFFLINE`). The Ingest screen names the source "saved in Configuration". Tests: `tests/test_settings.py` (15), Playwright e2e 21/21 (ID/EN, light/dark, 390 px phone), full pytest 374 passed. Also: EN label "1 hours" → "1 h". |
| 25 | 2026-10-07 | (p) **Owner request**: "move everything to do with configuration, links, settings, URLs, etc. into .env"; the owner's choice: **keep the Configuration page, but have it write to the .env file**. Replaces the storage of (o)/(n)/(l) in the account database. (1) `monishield/envfile.py`: writes `.env` **in place** (safe for a Docker bind mount, file permissions kept), only the changed key lines; sample lines `# KEY=` are activated in place, the rest are appended below a marker; delete = `# KEY=` without the old value; the result is read back with `config.read_dotenv` and restored if it differs; values containing newlines are refused. (2) `settings.py`: AWS, MaxMind, block list, automatic S3 folders (`S4_S3_WATCH*`, new `S4_S3_WATCH_ENABLED`), and notifications (new: `S4_ALERT_*`, `TELEGRAM_BOT_TOKEN`, `DISCORD_WEBHOOK_URL`, `S4_SMTP_*`, `SMTP_PASSWORD`, `S4_DASHBOARD_URL`) are written to `.env` and then immediately applied onto the server configuration; `alerts.load(cfg)` reads from the configuration. Source of each value: `.env` / environment variable (overrides .env at start; marked on screen) / default. Old settings in `app_setting` are moved once to `.env` when the server starts and then deleted (if `.env` cannot be written: still used from memory + a warning). `create_app` with a `cfg` from the caller (tests) writes to `<state_dir>/.env`, not `.env`. (3) URLs/limits that used to be hard-coded are now configuration fields: `S4_URL_MAXMIND` (must contain `{}`), `S4_URL_IP2ASN`, `S4_URL_LAND`, `S4_URL_BORDERS`, `S4_URL_PROVINCES`, `S4_URL_COUNTRIES`, `S4_URL_GEONAMES`, `S4_TELEGRAM_API`, `S4_GEO_MAX_AGE_DAYS` (1–30, license), `S4_ASN_MAX_AGE_DAYS`, `S4_MAP_MAX_AGE_DAYS`, `S4_UPLOAD_SESSION_HOURS`; the `rules.*_URL` constants stay as defaults (old-system comparison). What deliberately STAYS in code: the list of allowed Discord hosts (SSRF safeguard), the license attribution links on the map, sample placeholders. (4) Docker: `app` no longer uses `env_file:`; `./.env` is mounted at `/app/.env` (rw), `ingest` read-only; requirement `chgrp 10001 .env && chmod 660`. Verified in Docker: write from the API → the host file changes (permissions kept) → survives `restart` and `up -d --force-recreate`; read-only `.env` → `env_not_writable`. `.env.example` now contains all variables (tested). Tests: `test_settings.py` 20, Configuration e2e 22/22, Notifications 14/14. |
| 25 | 2026-10-07 | (q) **Owner request**: "animate the map lines so that the direction towards the destination IP is visible" (preparation for realtime Kafka). `web/src/lib/mapFlow.js` + `MapView.svelte`: the base arcs now have a gradient (faint origin → bright server; the direction is readable without motion); particles (head + glow + fading tail, `line-gradient` per feature) travel along the same arcs (slow at the start/end, duration by arc length), frequency per arc ∝ √(requests/max) (0.6–3.8 s); a ripple at the server point on arrival. Max. 320 particles, ±30 fps, only 3 small GeoJSON sources updated; stops when the map is not visible (IntersectionObserver) / the tab is hidden. Play/pause button (aria-pressed, remembered in `map_anim`), paused by default under `prefers-reduced-motion` (WCAG 2.2.2/2.3.3). Realtime-ready: `pulse({lat, lon, n})` (bind:this) / window event `monishield:map-pulse`, the `live` prop turns off ambient particles; locations not yet on the map get a temporary arc. Tests: `tools/uji_animasi_peta.cjs` 17/17 (real data 6 Oct, 166 arcs; JS cost ±0.2 ms/frame); `tools/uji_tahap20.cjs` now pauses the animation (sources updated every frame make `map.loaded()` never true). The Kafka consumer itself has NOT been built yet. |
| 25 | 2026-10-07 | (r) **Owner request**: "how can the logging output from Kafka be checked? can it be made like the existing logging?" (Rancher cluster logging → Kafka). `monishield/kafka_in.py`: a consumer in a server thread (kafka-python 3, pure Python; SASL PLAIN/SCRAM, SSL) reads Rancher messages (`log` + `kubernetes.namespace_name/container_name/pod_name` + `time`; fallback from `tag`), writes them to the inbox with the SAME folder/file name layout as the S3 export, then ingests periodically via IngestManager (single DuckDB owner, K1). Folder date: (D-1 00.00, D 00.00] WIB → D, as in S3. Service name = container, or from the pod prefix (Helm ingress `controller`). ns/container/pod names are validated (cannot escape the inbox). Offsets are committed after writing (at-least-once). Unreadable messages are counted + a sample of the reason. API: `GET /api/admin/kafka` (status, last 50 messages), `POST /api/admin/kafka/peek` (last 10 messages directly from the topic without a consumer group, + target file), `POST /api/admin/kafka/ingest`, `GET /api/live/map` (SSE every second: [lat, lon, count, module] from the local ip_info — no IPs; 204 when Kafka is off). Screens: a "Logs from Kafka" card (Ingest & import, Configuration), Configuration → Kafka section (written to .env, consumer restarted), map: LIVE badge + live mode (particles only from real events) on the folder being filled. `.env`: `S4_KAFKA_*`, `KAFKA_PASSWORD`. Docker: the image includes kafka-python; `kafka` profile (apache/kafka 3.9.1 KRaft, 1 partition, EXTERNAL listener for Rancher restricted to 127.0.0.1 by default). Tests: `tests/test_kafka.py` 10 (including: the same lines via S3 vs Kafka → identical files and database contents; SSE via a real uvicorn); real broker: 3000 messages from the 6 Oct log → folder 2026-10-08 (14 files) → automatic ingest, "Check messages in topic", realtime map (e2e 10/10); Docker compose app↔kafka:9092. Also: the `api_version_auto_timeout_ms` option does not exist in kafka-python 3 (replaced by `bootstrap_timeout_ms` 10 s). NOT yet tested against the real Rancher cluster. |
| 25 | 2026-10-07 | (s) **Test fix** `tools/uji_tahap20.cjs` ("mouse wheel over the map … Ctrl + wheel zooms in" failed, also on the version before the animation): after a plain wheel scrolls the page by 300 px, the centre of the map is covered by the sticky page header (`elementFromPoint` = `HEADER.top`), so Ctrl + wheel lands on the page header. The application is correct; the test now scrolls the map back into view before Ctrl + wheel and checks that the target point is the map canvas. Result: 26/26 (zoom 5.00 → 5.50) on the real 6 Oct data. |
| 11 | 2026-10-06 | (a) **Files**: the ten page endpoints are written in one module `api/pages.py` and the 25 table definitions + table endpoint in `api/tables.py` (plan: one module per page + definitions in `common.py`); same content, far less code. (b) **A display difference not yet written in TRD §4.4**, now added to item 1: the *endpoint performance* table/chart takes the 25 highest P95s from ALL endpoints with ≥5 requests (TRD §5.4), whereas the old dashboard picked from the 150 busiest endpoints; the content differs for nginx in 5 of the 11 folders. Every old row is still in the complete v2 list (E2). **The owner should be aware of this.** (c) The "5xx responses per hour" chart (Availability) is read from that folder's raw `nginx_access` table, because `agg_hour.err` now also includes error log lines (item 2); 9 ms on the largest folder. (d) `ETag` is sent; 304 responses not yet implemented. (e) The `q` filter also searches the IP network owner name. (f) Tables limited to "all" use a limit of 500. (g) Security/Root Causes/Business are always `available: true` with a source marker (`nginx`, `sources`), because those pages still have content even when one source is absent. (h) `tools/ukur.py --api` by default runs the application in-process; against a running server it needs a session cookie in `S4_COOKIE`. (i) ASSUMPTION X6 stands: flow table of the first 100 rows. Result: `pytest` **239 passed, 2 skipped**; the role matrix covers 28 routes; **E2: 601 lists, 9,889 old rows, 0 different** (E1 3,022 / E3 1,734 / E4 169 still 0); real server + curl: security 10-06 = 88 requests / 14 IPs, pod connection errors 09-30 = 1,200, map 09-28 `no_nginx`, `c401` 09-29 total 653 (208 matching `count`, 5 rows), `sort=1;drop` → 400, without a session → 401; HTTP layer on the largest folder (09-29): slowest endpoint 56 ms (target 300), largest response 174 KB (target 500). |
