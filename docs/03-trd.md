# TRD — Technical requirements for the SIMPEL4 log dashboard (v2)

Technical decisions for the migration. Basis: [`00-inventaris.md`](00-inventaris.md) ("inv. §x"),
[`01-prd.md`](01-prd.md) (F/B/T/A/P-nn), [`02-drd.md`](02-drd.md) (U/D/Q-nn), all three re-read from
file. This document contains no implementation code; table, column, and endpoint names are a contract.

The stack is already fixed in the context: Python + FastAPI, DuckDB, Svelte + Vite, Chart.js, MapLibre GL JS.

Technical **ASSUMPTIONS** are numbered T-nn and summarized in [§11](#11-assumptions-and-open-questions).

### Product owner decisions (received 2026-10-06, while this document was being written)

Four PRD questions were answered. These answers **override** conflicting PRD/DRD assumptions; their impact on
other documents is listed in §10.

| PRD | Owner's answer | Technical consequence |
|---|---|---|
| P1, X10 | There is a login with two roles, **admin** and **user**. **For now** that is all: a regular user sees the whole dashboard; an admin can also add users. Per-module restrictions (the original P1 request) are **postponed**. | Authentication, sessions, two roles: §8.2–§8.4, §2.6, §5.6 |
| P2 | "Day" **stays per folder**. Plan: automation; when a link to a folder in the bucket is sent, the folder is downloaded and processed automatically. | A1 becomes a decision. Import from a link: §3.8, §5.5 |
| X1 | **Local** accounts in this application's database; not SSO. | T6 becomes a decision: §8.2 |
| X11 | The details of the definition fixes are **approved**: in line with good practice. | T11 becomes a decision: §4.4 |
| DRD Q1 | The phone layout is done **seriously**. | DRD §8 applies in full, including wide tables becoming row cards |
| X9 | The link is an S3 prefix, e.g. `s3://simpel4-backup/k8s-logs/2026-09-26/`. The credential is a **long-term access key**, created through the AWS website; the key **can only read** (it cannot write or delete), but it can see **all buckets in the Jakarta region**. | S3 client, credentials in `.env`, import can be automatic: §3.8. Because the key is broad, restriction on the application side is mandatory |
| P3 | The dashboard is opened from **many computers**. | Accessed over the network, HTTPS and login are mandatory; A3 is dropped: §7, §8 |
| P4 | Wrong/odd definitions are **fixed** in line with good practice. | List of fixes and the expected differences: §4.4, §9.3 |

Contents: [1 Architecture](#1-architecture-and-data-flow) · [2 Schema](#2-duckdb-schema) · [3 Ingest](#3-ingest) ·
[4 Reuse vs SQL](#4-what-is-reused-and-what-is-replaced-by-sql) · [5 API](#5-api-contract) ·
[6 Structure](#6-folder-structure-how-to-run-dependencies) · [7 Deployment](#7-deployment-with-docker-compose) ·
[8 Security](#8-security) · [9 Tests](#9-test-strategy) · [10 Impact on other documents](#10-impact-on-other-documents) ·
[11 Assumptions](#11-assumptions-and-open-questions)

---

## 1. Architecture and data flow

### 1.1 Overview

```
 log folder (read-only)                         one "app" process
 <date>/[ns/]<service>/*.log(.gz)  ┌──────────────────────────────────────────────┐
        │                          │  FastAPI (1 worker)                          │
        │  1. scan + fingerprint   │   ├─ /api/...      read aggregate tables     │
        ▼                          │   ├─ /api/admin/ingest   trigger ingest      │
 ┌──────────────┐  2. parse        │   └─ static files: Svelte app, map           │
 │ parser proc. │  (subprocess,    │                                              │
 │ rules.py     │   per file)      │  Ingest (thread in the same process)         │
 └──────┬───────┘                  │   3. load CSV → raw tables     ┐ one         │
        │ temporary CSV            │   4. derive aggregates (SQL)   │ transaction │
        └─────────────────────────►│   5. record file status        ┘ per folder  │
                                   │                                              │
 IP databases (downloaded) ──────► │   6. fill in IP owner & location (offline)   │
 .cache: ip2asn, GeoLite2,         │                                              │
 Natural Earth, GeoNames           │        simpel4.duckdb  (one file)            │
                                   └──────────────────────────────────────────────┘
                                                      ▲
                                    browser ──────────┘  only to this server
```

### 1.2 Decisions

| # | Decision | Reason |
|--:|---|---|
| K1 | **One process owns the DuckDB file**: the API process. Ingest runs **inside that process** (background thread), not as a separate process. | DuckDB allows only one writer process, and the writer locks the file against other processes, including readers. Within one process, readers and one writer run concurrently and safely (MVCC). This removes the whole "conflict" problem without a file-swap mechanism. |
| K2 | **Parsing in a subprocess**, producing temporary CSV; the main process only loads the CSV and runs SQL. | Parsing is pure-Python CPU work; in a thread it would hold the GIL and slow the API down. The subprocess does not open DuckDB, so K1 still holds. `read_csv` is also the fastest way to get hundreds of thousands of rows into DuckDB without extra libraries. |
| K3 | **Two data layers**: raw tables (one row per meaningful log line) and per-folder aggregate tables **materialized at ingest**. The API reads only aggregates. | Response time does not depend on the size of the raw data (PRD §5.1 target on one year of data). Raw data is kept to re-derive aggregates without re-parsing, for cross-folder correlation, and for cross-folder analysis (T02) later. |
| K4 | **Aggregates are stored untruncated**; top-N is applied at query time. | Resolves M3/B03/B04: KPIs are computed from complete data, tables can "show next", filters search all data. The old limits (inv. §5.2) become the default `limit`. |
| K5 | **Parse and classification rules are reused from the old system**, copied as-is into one module; only the counting moves to SQL. | Equal numbers (PRD §6.2) are easiest to guarantee if the regexes and decision functions are not rewritten. Details in §4. |
| K6 | **Data unit = export folder** (A1). Every raw row carries `folder` and its original UTC timestamp. | Numbers can be compared directly with the reference; a per-calendar-date view (T01) remains possible later because the original time is stored. |
| K7 | **One transaction per folder**: delete the old rows of the changed folder/file, load the new ones, derive aggregates, record status. | Readers never see a half-finished folder; an interrupted ingest leaves nothing behind; repeating an ingest yields the same state. |
| K8 | **The frontend is built into static files** and served by the same FastAPI. | One service, one port, no CORS; sufficient for internal use. |
| K9 | **Text that is currently data stays in Indonesian as identifiers** (attack categories, account flags, business metrics, JWT buckets). Translation is done by the frontend via a dictionary (U15). | Same as the old system and as the keys in `00-acuan.json`; the API needs no language parameter. |
| K10 | **Automatic finding sentences are composed in the frontend** from data, as they are now. | The sentences are bilingual and contain markup; the rules (inv. §2.4, §2.5) stay in one place together with their display. |
| K11 | **Accounts, sessions, and the audit log are stored in PostgreSQL via an ORM (SQLAlchemy)**, separate from DuckDB. *(Decided by the owner 2026-10-06: "untuk token gunakan jwt untuk database gunakan postgresql dan pakai orm" (for tokens use JWT, for the database use PostgreSQL and use an ORM).)* | DuckDB is designed for analytics, not for many small writes; and the DuckDB file must be deletable and rebuildable from the logs without losing accounts. The ORM makes the account code the same on PostgreSQL (server) and SQLite (tests, running locally without a database server; used when `S4_AUTH_DATABASE_URL` is empty). **ASSUMPTION T16**: that decision applies to accounts, sessions, audit, and import records only; log data stays in DuckDB, because replacing it would mean redoing Stages 3–9 (schema, ingest, aggregates, equivalence, the 4.75 GB/20 ms size gate) and would contradict the stack in `migrate/00-konteks.md`. Needs confirmation by the owner. |
| K12 | **Roles are enforced in the API**, in one place; hiding the admin menu in the frontend is only a convenience. | Many computers means the API can be called directly; the only meaningful boundary is on the server. |
| K13 | **Import from the bucket only adds folders to the "inbox" directory** and then triggers a normal ingest. | One ingest path for all sources; the original log folder stays read-only. |

---

## 2. DuckDB schema

One file: `simpel4.duckdb`. Conventions:

- `folder` has type `DATE` (the export folder name). Times are stored as `TIMESTAMP` **UTC**; WIB is computed
  when deriving aggregates (`+ 7 hours`). Hourly aggregates store `hour_wib`.
- The key of raw tables is `(file_id, line_no)`; it is **not** declared as a `PRIMARY KEY` in DuckDB.
  Reason: a key index over tens of millions of rows slows bulk loading and uses memory; uniqueness is already
  guaranteed by the per-file delete-then-load pattern (K7) and checked by tests (§9.4).
- Aggregate tables are small; their keys are declared as `PRIMARY KEY`.
- Rows are loaded in folder order, so `folder = ?` filtering is served by DuckDB's block min/max statistics.
- Text is not truncated when stored. The old truncation (inv. §5.3) is applied when deriving aggregates, at
  the same place as in the old system, because it affects grouping.

### 2.1 Control tables

**`ingest_file`** — one row per logical log file. PK `file_id`; unique `relpath`.

| Column | Type | Content |
|---|---|---|
| `file_id` | INTEGER | sequence number |
| `relpath` | VARCHAR | relative path **without** the `.gz` suffix (logical identity, §3.2) |
| `source_ext` | VARCHAR | `.log` or `.log.gz`: the file actually read |
| `folder` | DATE | first path component |
| `ns` | VARCHAR | middle component, or `-` |
| `service` | VARCHAR | parent folder of the file |
| `pod` | VARCHAR | from the file name (old rule, inv. §1.1) |
| `size_bytes` | BIGINT | size of the file read (same as `D.files.size`) |
| `mtime_ns` | BIGINT | file modification time |
| `sha256` | VARCHAR | fingerprint of the content **after decompression** |
| `lines` | BIGINT | all lines, including those not parsed |
| `err`, `warn` | INTEGER | old per-file counters (inv. §4.9) |
| `corrupt_lines` | INTEGER | `unsupported log format` lines (B05) |
| `status` | VARCHAR | `ok`, `kosong`, `rusak`, `gagal` |
| `rules_version` | INTEGER | parse rules version at processing time |
| `ingested_at` | TIMESTAMP | |

**`file_counter`** — per-file counters for lines not worth storing one by one.
PK `(file_id, kind, key)`.

| Column | Type | Content |
|---|---|---|
| `file_id` | INTEGER | |
| `kind` | VARCHAR | `level` (inv. `extra`), `biz`, `mail` |
| `key` | VARCHAR | e.g. `INFO`, `Hibernate SQL`, `Email Terkirim`, `Email Gagal`, notification email type |
| `n` | BIGINT | |

Reason: the ±31 thousand `Hibernate:` lines per day only need to be counted.

**`folder_state`** — PK `folder`: `derived_at`, `rules_version`, `range_start_utc`, `range_end_utc`,
`lines`, `files`, `files_empty`, `files_corrupt`. Source of the folder list and the time range label (B06).

**`ip_info`** — PK `ip`: `asn` INTEGER, `cc` VARCHAR, `org` VARCHAR, `is_private` BOOLEAN, `city`,
`region`, `country` VARCHAR, `lat`, `lon` DOUBLE, `geo_checked` BOOLEAN, `asn_db_date`, `geo_db_date` DATE.
Replaces `D.ipinfo`, `D.geo`, and `.cache/geo.json`. Filled for **all** IPs that appear, not only those
displayed.

**`ingest_run`** — ingest history: `run_id`, `started_at`, `finished_at`, `status`, `files_seen`,
`files_changed`, `message`.

### 2.2 Raw tables

All have `file_id` INTEGER, `line_no` INTEGER, `folder` DATE (not repeated below).

**`nginx_access`** — ingress nginx access lines that match the regex (inv. §3.1). ±130 thousand lines/day.

| Column | Type | Content |
|---|---|---|
| `ts_utc` | TIMESTAMP | second precision |
| `ip` | VARCHAR | client IP |
| `method` | VARCHAR | |
| `path` | VARCHAR | path + query, raw |
| `path_key` | VARCHAR | result of `path_key()` |
| `status` | SMALLINT | |
| `bytes` | BIGINT | response size |
| `ua` | VARCHAR | full User-Agent |
| `request_time` | DOUBLE | seconds |
| `upstream` | VARCHAR | without the `ombudsman-ombudsman-` prefix; `-` when empty |
| `request_id` | VARCHAR | NULL when the line tail does not match |
| `pod_final` | VARCHAR | address of the pod that answered; `-` when there is none (old rule) |
| `up_addrs` | VARCHAR[] | list of attempted addresses; NULL when the tail does not contain 4 parts |
| `up_statuses` | VARCHAR[] | status of each attempt, parallel to `up_addrs` |
| `attack_cat` | VARCHAR | result of `classify()`; NULL when clean |
| `is_uptime_kuma` | BOOLEAN | UA contains `Uptime-Kuma` |

**`nginx_error`** — error log lines that match the regex (inv. §3.2); also used for the frontend error log.

| Column | Type | Content |
|---|---|---|
| `service` | VARCHAR | `nginx-ingress-controller` or `om-fe-inhouse` |
| `ts_utc` | TIMESTAMP | |
| `level` | VARCHAR | `error`, `warn`, `crit`, … |
| `message` | VARCHAR | up to `, client:` |
| `upstream_host` | VARCHAR | pod address; NULL when not an upstream error |
| `kind` | VARCHAR | message without the errno number, 100 characters (old rule) |
| `request` | VARCHAR | `METHOD path`, 120 characters |

**`fe_access`** — frontend access log (inv. §3.3). ±86 thousand lines/day.
Columns: `ts_utc` TIMESTAMP, `ip` VARCHAR (first X-Forwarded-For entry), `method`, `path`, `path_key`
VARCHAR, `status` SMALLINT.

**`sl_event`** — simpel-loop HTTP events (JSON with `statusCode`, inv. §3.4). ±60 thousand lines/day.

| Column | Type | Content |
|---|---|---|
| `level` | VARCHAR | from `[OM-<level>]` |
| `request_id` | VARCHAR | |
| `event` | VARCHAR | `http.request.completed` / `.failed` |
| `method`, `path`, `path_key` | VARCHAR | |
| `status` | SMALLINT | |
| `ip` | VARCHAR | NULL on failed events |
| `duration_ms` | DOUBLE | 0 when absent |
| `failed` | BOOLEAN | |
| `err_name`, `err_message` | VARCHAR | |

No time column: this log has no timestamps (inv. §8 item 4).

**`spring_line`** — every Spring Boot line that matches the main regex (inv. §3.5). ±7 thousand lines/day.

| Column | Type | Content |
|---|---|---|
| `service` | VARCHAR | |
| `ts_utc` | TIMESTAMP | |
| `level` | VARCHAR | |
| `thread`, `logger` | VARCHAR | |
| `restart_app` | VARCHAR | from `Started <App> in …` |
| `restart_seconds` | DOUBLE | |
| `jwt_expired_ms` | BIGINT | difference in milliseconds |
| `refresh_expired` | BOOLEAN | |
| `pdf_template` | VARCHAR | filled on `Jasper template path` lines (the parser remembers the template per thread) |
| `pdf_failed` | BOOLEAN | path `null` |
| `login_kind` | VARCHAR | `fail`, `lock`, `ok` |
| `login_account` | VARCHAR | original text in the log |
| `login_ip` | VARCHAR | |

**`coredns_error`** — inv. §3.6. Columns: `level`, `domain`, `rtype`, `message` VARCHAR.

**`log_message`** — one row per ERROR/WARN/EXC message that enters grouping (every `add_msg` call in the
old system). ±15 thousand lines/day.
Columns: `service`, `level` VARCHAR, `msg_key` VARCHAR (`LEVEL | normalized message`), `raw` VARCHAR (original
line, 600 characters, **only filled on the first occurrence of that key in the file**; otherwise NULL).
Reason: a sample line only needs the first one; storing all of them doubles the size for nothing.

Intentionally **not** stored: lines that match no rule (banners, stack traces, ingress controller logs,
multi-line continuations). They only add to `ingest_file.lines`, as in the old system.

### 2.3 Aggregate tables

All are keyed by `folder` (+ other columns). Refilled per folder in the "derive" step (§3.4).

| Table | Key | Other columns | Source |
|---|---|---|---|
| `agg_service` | folder, service | lines, err, warn, err_http, err_log, files, files_empty, files_corrupt, requests, n4xx, n5xx, ip_unique, users_ok | `ingest_file`, raw tables |
| `agg_hour` | folder, service, hour_wib | total, err | nginx/fe/spring; simpel-loop from correlation |
| `agg_status` | folder, service, status | n | nginx, fe, sl |
| `agg_endpoint` | folder, service, key | requests, n4xx, n5xx, dur_n, dur_avg, dur_max, p50, p95, p99 | nginx, fe, sl; coredns (`key` = domain) |
| `agg_endpoint_error` | folder, service, status, key | n | nginx/fe: all 4xx/5xx; sl: failed events only |
| `agg_ip` | folder, service, ip | requests, n4xx, ua_first_4xx | nginx, fe, sl |
| `agg_upstream` | folder, upstream | requests, n5xx | nginx |
| `agg_ua` | folder, ua90 | n | nginx |
| `agg_level` | folder, service, level | n | `file_counter` |
| `agg_message` | folder, service, msg_key | level, n, sample_raw | `log_message` |
| `agg_slow` | folder, seq | duration_ms, key, status | `sl_event` ≥ 1,000 ms |
| `agg_attack_url` | folder, category, method_path | hits, ip_count, top_ip, status_counts MAP(VARCHAR,INTEGER), sizes BIGINT[], upstreams VARCHAR[], ua_first, first_wib, last_wib | nginx |
| `agg_attack_ip` | folder, ip | hits, cats MAP, status_counts MAP, ua_top, first_wib, last_wib | nginx |
| `agg_attack_hour` | folder, hour_wib | n | nginx |
| `agg_login_ip` | folder, ip | fail, lock, ok, accounts VARCHAR[], first_wib, last_wib | `spring_line` |
| `agg_login_hour` | folder, hour_wib | fail, ok | `spring_line` |
| `agg_account` | folder, account | fail, lock, ok, fail_ips VARCHAR[], ok_ips VARCHAR[], flags VARCHAR[], first_wib, last_wib, notes VARCHAR[] | old `accounts()` function |
| `agg_incident` | folder, seq | start_wib, end_wib, n, upstreams MAP, statuses MAP | old `incidents()` function |
| `agg_c401` | folder, ip, key | n, peak_per_min, first_wib, last_wib | nginx status 401 |
| `agg_uk_hour` | folder, hour_wib | n, fail | nginx |
| `agg_uk_target` | folder, target | n | nginx |
| `agg_flow` | folder, ip, upstream, pod | n | nginx |
| `agg_pod` | folder, upstream, addr | attempts, n5xx | nginx `up_addrs` |
| `agg_retry` | folder, upstream, addr_first, status_first | n | nginx |
| `agg_corr` | folder | matched, total | sl ⋈ nginx |
| `agg_trace` | folder, ip, status, error, key | n, url, upstream, ua, first_wib, last_wib, max_ms | sl ⋈ nginx |
| `agg_biz` | folder, metric | n | sl + `file_counter` |
| `agg_mail` | folder, kind | n | `file_counter` |
| `agg_activity` | folder, key | n | sl |
| `agg_jwt` | folder, service, bucket | n | `spring_line` |
| `agg_report` | folder, template | ok, fail | `spring_line` |

Views (not tables, because they are already small and folder-filtered):
`v_upstream_error` (`nginx_error` with `upstream_host` set, ingress service), `v_restart`
(`spring_line` with `restart_app` set, joined with `ingest_file.pod`), `v_attack_cat` (sum of `hits` per
category from `agg_attack_url`), `v_dns` (`agg_endpoint` for the coredns service).

`agg_service` and a few other small aggregates are the only ones read by the Trends tab, so 365 folders
means a few thousand rows.

### 2.4 Mapping of inventory fields → columns

Field = output of the old system's `summarize()` (inv. §1.3). "N" = old limit, now the default `limit`.

| Old field | In v2 | Notes |
|---|---|---|
| `lines` | `agg_service.lines` = Σ `ingest_file.lines` | |
| `err`, `warn` | `agg_service.err/warn` = Σ `ingest_file.err/warn` | Per-file counters from the parser; old definition except for the §4.4 fixes. `err` now has a breakdown `err_http` + `err_log` |
| `hour` | `agg_hour.total` | |
| `herr` | `agg_hour.err` | **fixed**: nginx/FE now also include error log lines (§4.4 item 2) |
| `status` | `agg_status` | |
| `paths` (N=20) | `agg_endpoint.requests`; coredns: `key` = domain | |
| `perr` (20) | `agg_endpoint_error` | |
| `pe` | `agg_endpoint.n4xx/n5xx` | |
| `ips` (15) | `agg_ip.requests` | |
| `ip4` (20) | `agg_ip.n4xx`, `ua_first_4xx` | UA truncated to 100 when derived |
| `up` (12), `up5` | `agg_upstream` | |
| `ua` (12) | `agg_ua` | key = first 90 characters |
| `extra` | `agg_level` | **fixed** for simpel-loop (§4.4 item 4) |
| `dur` (15) | `agg_endpoint.dur_avg/dur_max` | not displayed (inv. §8 item 16); stored because it is free |
| `ep` (150, min. 5) | `agg_endpoint` where `dur_n ≥ 5` | percentiles with the old index rule (§4.3) |
| `slow` (15) | `agg_slow` | |
| `msgs` (40) + `samples` | `agg_message` | sample = first `raw` by (file order, `line_no`) |
| `atk` (300) | `agg_attack_url` | `sizes` = 5 smallest; `ua_first` = UA of the first occurrence |
| `atk_ip` (100) | `agg_attack_ip` | |
| `atk_h` | `agg_attack_hour` | |
| `atk_cat` | `v_attack_cat` | |
| `login` (100) | `agg_login_ip` where `fail > 0` or `lock > 0` | |
| `login_h` | `agg_login_hour.fail` | |
| `login_okh` | `agg_login_hour.ok` | |
| `login_ok` | Σ `agg_login_hour.ok` | |
| `users_ok` | number of unique accounts with `login_kind = 'ok'` in `spring_line` (stored in `agg_service` as an extra appsmanager column: `users_ok`) | |
| `acct` (150) | `agg_account` | |
| `incidents` | `agg_incident` | |
| `c401` (30) | `agg_c401` | |
| `uk`, `ukf` | `agg_uk_hour` | |
| `uk_t` (5) | `agg_uk_target` | |
| `pod` | `agg_pod` | |
| `retry` (30) | `agg_retry` | |
| `uperr` (last 200) | `v_upstream_error` | |
| `corr` | `agg_corr` | |
| `trace` (300) | `agg_trace` | |
| `biz` | `agg_biz` | |
| `mail` | `agg_mail` | |
| `act` (20) | `agg_activity` | |
| `restart` | `v_restart` | |
| `jwt` | `agg_jwt` | includes `Refresh Token Kedaluwarsa` (B07) |
| `rep` | `agg_report` | |
| `flow` (3,000; 3 pods) | `agg_flow` | stored per pod; "top 3 pods" at query time |
| `D.files` | `ingest_file` | |
| `D.ipinfo`, `D.geo` | `ip_info` | |
| `D.hosts`, `D.server` | configuration (§6.3), sent via `/api/meta` | |
| `D.land` | static GeoJSON file (§5.7) | no longer an SVG path string |
| `D.labels` | static file `labels.json` | same content |

`err_http` (5xx responses) and `err_log` (log lines with error level) are the breakdown of `err`; see §4.4.

### 2.5 Size estimate

| Table | Rows/day (full folder) | Rows/year |
|---|--:|--:|
| `nginx_access` | 130 thousand | 48 million |
| `fe_access` | 86 thousand | 31 million |
| `sl_event` | 60 thousand | 22 million |
| `log_message` | 15 thousand | 5.5 million |
| `spring_line` | 7 thousand | 2.6 million |
| all aggregates | a few thousand | ±2 million |

PRD budget ≤ 10 GB/year (A8). **ASSUMPTION T1**: achieved thanks to DuckDB column compression (paths, UAs, and
IPs are highly repetitive). This figure has **not been measured yet**; measuring it is the first job once ingest
runs (§9.7). If it misses, the most wasteful columns (`ua`, `path`) move to a dictionary table; the rest of the
schema does not change.

### 2.6 Accounts (PostgreSQL via ORM, K11)

SQLAlchemy models in `monishield/auth.py`; tables are created when the application starts (`create_all`). Table
names have the `app_` prefix because `user` and `session` are keywords in PostgreSQL.

| Table | Key | Columns |
|---|---|---|
| `app_user` | `user_id` | `username` (unique, lowercase), `display_name`, `role` (`admin` \| `user`), `password_hash`, `password_salt`, `hash_params`, `must_change_password` (0/1), `active` (0/1), `failed_logins`, `locked_until`, `created_at`, `created_by`, `last_login_at` |
| `app_session` | `sid` (random, carried in the JWT) | `user_id`, `created_at`, `last_seen_at`, `expires_at`, `ip`, `user_agent` |
| `audit_log` | `id` | `at`, `user_id`, `username`, `action`, `detail`, `ip` |
| `import_job` | `job_id` | `requested_by`, `bucket`, `prefix`, `folder`, `status`, `bytes`, `files`, `skipped`, `message`, `started_at`, `finished_at` |

There is no per-module access rights table yet; if needed later, adding one `user_module` table is enough
(§8.3) without changing the `app_user` table.

Not stored here: plaintext passwords, session tokens (JWT) or their signing secret, and AWS credentials (§3.8).

`ponytail:` the schema is created with `create_all`, without a migration tool; add Alembic the first time a column
changes on a database that already holds accounts.

---

## 3. Ingest

### 3.1 Order

1. **Scan** the log folder: all `*.log`, and `*.log.gz` only when their `.log` counterpart is absent (old
   rule). The top folder must be a date and the path must have at least 3 components.
2. **Compare** with `ingest_file` (§3.2) → list of new, changed, missing, and unchanged files.
3. For each folder with changes:
   a. **Parse** new/changed files in a subprocess (parallel per file, at most 4) → temporary CSV per table.
   b. In **one transaction**: delete the raw rows belonging to changed/missing files; load the CSV; update
      `ingest_file` and `file_counter`; **derive** all aggregates of that folder; update `folder_state`.
4. **Cross-folder correlation** (§3.5) for other affected folders.
5. **Fill in `ip_info`** for IPs that have no data yet (§3.6).
6. Delete the temporary CSV; record `ingest_run`.

Only one ingest runs at a time (an in-process lock). A second request gets the answer
"already running".

### 3.2 Recognizing files

Logical identity = `relpath` **without `.gz`**. So `x.log` and `x.log.gz` are the same file.

| State | Recognized by | Action |
|---|---|---|
| Already processed, unchanged | same `size_bytes` and `mtime_ns`, same `rules_version` | Skip, without reading the content |
| Touched but content is the same | size/mtime differ, same `sha256` | Update `mtime_ns` only |
| **Content grew** or changed | `sha256` differs | Delete the file's rows, **re-parse the whole file**, re-derive the folder |
| Identical `.log`/`.log.gz` pair | `.log` appears after the `.gz` was processed (or conversely `.log` disappears and the `.gz` remains): same `sha256` of the decompressed content | Replace `source_ext` and `size_bytes` only; no re-parse |
| The pair turns out to **differ** | `sha256` differs | Treat as changed; the source follows the old rule (`.log` wins); record a warning in `ingest_run` |
| File missing from the folder | in `ingest_file`, not on disk | Delete its rows, re-derive the folder |
| **Folder** missing entirely | not a single file of that folder exists | **Data is kept** (ASSUMPTION T2) |
| Parse rules changed | `rules_version` in the code > the recorded one | Re-parse all files |

Reasons:

- **Size + mtime first, then hash**: running an ingest without changes must take ≤ 5 seconds (PRD §5.2);
  reading 47 GB/year to hash every time is impossible. The hash is only computed for files whose size
  or mtime changed, and for new files.
- **Re-parse the whole file, not continue from an offset**: the parser has state (PDF template per
  thread, multi-line continuations, "first sample"), and the largest file (±60 MB) finishes in a few seconds.
  Continuing from an offset saves little and opens a class of bugs that is hard to test. The limit: if a
  single file one day reaches gigabytes and is written continuously, this needs to be revisited.
- **Hash of the decompressed content**: the only way to prove that a `.log`/`.log.gz` pair is identical (PRD P5),
  and at the same time to answer it with data: differences are recorded as warnings.
- **T2 (missing folder → data kept)**: the raw logs (±47 GB/year) will most likely be moved off the
  server before a year has passed; the dashboard must not lose history along with them. The old system behaves
  the other way around (missing folder = gone from the dashboard). Deletion is provided as an explicit command.

### 3.3 Safe to repeat

- All writes for one folder are in one transaction (K7). The process dying midway = the transaction is rolled back.
- There is no `INSERT` without its paired `DELETE` on the same key (file for raw tables, folder for
  aggregates). Running ingest twice yields the same table contents.
- Temporary CSVs are written to a single-use directory on the data volume and deleted at the end, also on failure.
- One file failing to parse (unexpected error): `status = 'gagal'` + message; the other files in that folder are
  still loaded (PRD §5.2). An `unsupported log format` line is not an error: it is counted as a line and marks
  the file `rusak` (A6, B05).

### 3.4 Deriving aggregates

One SQL file per aggregate table, each of the form "delete this folder's rows, insert the result of a SELECT
over this folder's raw tables". The order is fixed; two aggregates use old Python functions over a small query
result: `agg_account` (`accounts()`) and `agg_incident` (`incidents()`).

Changing an aggregate definition needs no re-parse: re-deriving all folders from the raw tables is enough
(command `derive --all`).

### 3.5 nginx ↔ simpel-loop correlation

The old system uses one request id dictionary **for all folders** (inv. §4.4, §8 item 11); the last
occurrence wins. v2 mimics this: `sl_event` is joined with `nginx_access` **without** a folder boundary; when a
request id appears more than once, the one used is the last one by (`relpath`, `line_no`).

Consequence for incremental ingest: a new folder can make events in an old folder "matched". So after
loading folder F, the correlation aggregates (`agg_corr`, `agg_trace`, simpel-loop `agg_hour`) are derived for F
**and** for other folders that have simpel-loop events with the same request id as nginx in F.

Measured on the current data (11 folders, 308,157 request ids): **0 cross-folder matches and 0 duplicate
request ids**. So in practice this step does nothing, but without it equivalence is not
guaranteed. Consequence: the PRD criterion "adding a 12th folder does not change the numbers of folders 1–11"
holds except for these three correlation aggregates (see §10).

### 3.6 IP owner and location

**Decided by the owner (2026-10-06): IP location uses MaxMind GeoLite2**, replacing DB-IP City Lite.
The network owner (ASN) still comes from ip2asn (**ASSUMPTION T15**: the request was only about location).

| Item | Decision |
|---|---|
| File | `GeoLite2-City-CSV` (zip ±49 MB): IPv4 network blocks (CIDR) + location table. The CSV variant is chosen so the standard library suffices; there is no `.mmdb` reader library |
| Download | `https://download.maxmind.com/geoip/databases/GeoLite2-City-CSV/download?suffix=zip` with `MAXMIND_ACCOUNT_ID` and `MAXMIND_LICENSE_KEY` from the environment (`.env`). The credentials were tested and accepted by MaxMind (2026-10-06) |
| Privacy | Unchanged: the whole file is downloaded; matching happens on our own server; no IP is sent |
| Matching | CIDR blocks are converted to sorted start–end ranges, then matched with the same sweep as the old `geo_scan()`. City/province names are taken in English (`en`), as with DB-IP; the country stays an ISO code |
| Updates | Re-downloaded when the file is older than 7 days. GeoLite2 license terms: do not use a database older than 30 days after a new release, so the old file is **deleted** once the new one has been downloaded successfully |
| No key or failed download | Ingest still finishes; location is empty for new IPs, with an explanation (PRD §5.5). It does **not** silently fall back to DB-IP |
| Attribution | "This product includes GeoLite2 data created by MaxMind, available from https://www.maxmind.com" on every map and in the flow table note |
| Equivalence | Location is **no longer** compared with the old system (the source differs). E3 still applies to the network owner. The location/country counts on the IP Map go into the list of expected differences |
| Credentials | Only in `.env`; not in the repo, image, logs, or API responses |

The items below apply as before, except that "DB-IP" is read as "GeoLite2":

- Source, URL, and cache age are the same as in the old system (inv. §6, §5.5). Downloads only fetch whole files;
  no IP is sent (PRD §5.4).
- After each ingest: IPs in the raw tables that are not yet in `ip_info` are matched with the old functions
  (`ip_owner`, `geo_scan`). The 86 MB database is only read when there are new IPs, as now.
- If the database does not exist yet and the download fails: ingest still finishes; `ip_info` is empty for those
  IPs; it is retried on the next ingest (PRD §5.5).
- **ASSUMPTION T3**: the result for an IP is not updated when a new database is downloaded (same as the old
  `geo.json`, which never expires). `asn_db_date`/`geo_db_date` are recorded so that a bulk update
  can be added later.
- Map data (land, borders, labels) is built once into static files on the data volume (§5.7).

### 3.7 Target performance

The old parser processes ±55 thousand lines/second (774 thousand lines in 14 seconds, including summarizing). The
largest folder (359 thousand lines): parse ±7 seconds on one core, faster in parallel; loading the CSV and deriving
aggregates is estimated at a few seconds. The PRD target of ≤ 60 seconds has a lot of headroom; it is still measured (§9.7).

### 3.8 Automatic import from a bucket link (P2, X9)

The owner receives links in the form of an **S3 prefix**, e.g. `s3://simpel4-backup/k8s-logs/2026-09-26/`, and
AWS credentials can only be obtained through the AWS website. The dashboard must download the contents of that prefix and process them.

**Flow**

1. An admin (through the "Ingest & import" screen) or an external system with a **machine token** sends the link to
   `POST /api/admin/import` (§5.5).
2. The server checks the link, **lists the objects** under that prefix, selects the objects to fetch, downloads them
   to a temporary directory, then atomically moves the `YYYY-MM-DD` folder into the **inbox**
   (`S4_INBOX_DIR`).
3. A normal ingest (§3.1) is run. The scanner reads two roots: the log folder and the inbox. When a folder
   with the same date exists in both, the log folder wins and a warning is recorded.
4. The status is recorded in `import_job` (bucket, prefix, number of objects fetched/skipped, bytes) and can be queried
   through the API.

**Link and object rules**

- Required form: `s3://<bucket>/<prefix>/<YYYY-MM-DD>/`. The last component must be a valid date; that is the
  folder name. Other forms are rejected.
- `<bucket>` must be on the **allowlist** (`import_buckets`) and `<prefix>` must start with one of the
  prefixes allowed for that bucket. The configuration default is empty = feature off. Expected value:
  bucket `simpel4-backup`, prefix `k8s-logs/`.
- The object key, after the prefix is stripped, must match the pattern `[ns/]<service>/<name>.log` or `.log.gz` (the
  same pattern as the scanner, §3.1). Other objects (e.g. `.DS_Store`) are skipped and counted in `skipped`.
  Keys containing `..`, double slashes, or control characters are rejected.
- **Download economy**: when both `x.log` and `x.log.gz` exist, only the `.log` is fetched (old rule:
  `.gz` is only read when the `.log` is absent). Objects whose size and ETag equal those of a previous download
  are not downloaded again, so sending the same link twice is cheap and safe.
- Limits: number of objects, size per object, total size (default 500 objects / 1 GB / 5 GB), and a time limit.
  Exceeding a limit = the import fails without touching the inbox.
- The server only contacts the official S3 endpoint for the configured region. No free-form URL from
  users is fetched, so there is no "server fetches an arbitrary address" hole.
- One import at a time; it shares the lock with ingest.

**AWS credentials** (decided by the owner, X9)

The credential is a **long-term access key** created through the AWS website. It is given to the dashboard via the
standard AWS environment variables in the server `.env` (not in the image or the repo), so the import can run
**automatically** without a person. Bucket region: Jakarta (`ap-southeast-3`), changeable via `import_region`.

As a fallback, an admin can still paste other credentials on the import screen (e.g. while the key on the server
is being replaced); pasted credentials are only kept in process memory and are lost when the server restarts. Lookup
order: those pasted by the admin, then environment variables. When neither exists, the import answers with a
message explaining how to provide them.

**The key is read-only but broad**: according to the owner it cannot write or delete, but it can
see all buckets in the Jakarta region. Consequently:

- **The bucket and prefix allowlist in the application is the only barrier** between the import screen and other
  buckets. It must not be possible to disable or loosen it from the interface; only from the server configuration.
  The dashboard has no "browse bucket" feature; it only accepts complete links that pass the allowlist.
- The dashboard uses only two read operations: listing objects and getting objects. There is no code that
  writes, deletes, or lists buckets.
- If the server or `.env` leaks, nothing can be damaged or deleted in AWS, but **the contents of all
  buckets** reachable by that key can be read, not only logs. **Recommendation** (not a prerequisite for starting): create a dashboard-specific IAM user with read-only rights on
  `simpel4-backup` prefix `k8s-logs/` only, and use that key on the server. An example policy is included
  in the README during the implementation stage.
- Rotating (replacing) the key only requires changing `.env` and restarting `app`.

**ASSUMPTION T14**: the object layout under the prefix is the same as in the local log folder
(`[ns/]<service>/log_<service>_<pod>_<date>.log[.gz]`). Verified on first use with
**dry run** mode (`simpel4 import --dry-run s3://…`), which only lists objects and prints which would be
fetched or skipped, without downloading.

Credentials are never sent to the browser, do not appear in API responses, and are not written to logs.
`/api/meta` only reports "credentials available: yes/no, source, expiry".

This feature is scheduled **after** equivalence is proven (PRD R9); its API interface is fixed now so that the
schema and access rights do not change again.

---

## 4. What is reused and what is replaced by SQL

`build_dashboard.py` must not be changed and will not go into the image. So the reused parts are
**copied as-is** into one module (`rules.py`) with notes on the original lines, and a test compares
that module's output with the old module as long as the old file still exists (§9.2).

### 4.1 Copied as-is

| From `build_dashboard.py` | Purpose |
|---|---|
| Regexes `NGINX`, `FE`, `JAVA`, `NGX_TAIL`, `NGX_ERR`, `LOGIN_FAIL`, `LOGIN_LOCK`, `LOGIN_OK`, simpel-loop and coredns patterns, `MON` | matching lines |
| `ATTACKS`, `SCANNER_UA`, `path_attack()`, `classify()` | attack classification |
| `norm()`, `path_key()` | message and path normalization |
| `BIZ_EP`, `jwt_bucket()` | business metrics, JWT age buckets |
| `accounts()`, `incidents()`, `dt()` | account analysis, 5xx incidents |
| `load_ip2asn()`, `ip_owner()`, `fetch()`, `ip_int()`, `geo_scan()` | offline IP owner and location |
| `map_labels()`, `kab_name()`, `PROV` | region labels |
| `HOSTS`, `SERVER_IP`, `SERVER_FALLBACK` | become **configuration defaults** (B11) |
| File selection and pod naming rules in `build()` | scanning |
| Contents of `demo()` | become unit tests |

### 4.2 Rewritten with the same behavior

| Old part | In v2 | What changes |
|---|---|---|
| `parse()` | a parser that **emits rows** (to CSV) instead of incrementing counters. Branches, check order, and the per-file `err`/`warn`/`lines` counters stay. | Only the output form. Tested line by line and against the old parser's counters (§9.3) |
| `wib()` | Time is stored as UTC with second precision; WIB and truncation to minute/hour in SQL | Seconds are no longer dropped on store |
| `geolocate()` | Uses the old `geo_scan()`; the cache moves from `geo.json` to `ip_info` | Cache location |
| `land_path()` | Replaced by a GeoJSON file for MapLibre (DRD §7.2) | Output form |

### 4.3 Replaced by SQL

| Old part | Replacement |
|---|---|
| All `Counter`s in `parse()` and `add_attack()` | `GROUP BY` over raw tables → aggregate tables |
| `summarize()` (sort + cut top-N) | `ORDER BY … LIMIT` at query time; old limit = default |
| `pct()` percentile | Durations sorted per endpoint, taking the element at `min(n−1, ⌊q·n⌋)` (0-based index), **not** DuckDB's built-in quantile function, so that the numbers are the same |
| `correlate()` | `JOIN sl_event ⋈ nginx_access` on request id (§3.5) |
| `shown_ips()` | Not needed: `ip_info` contains all IPs |
| Per-file `err`/`warn` computation (`D.files`) | Emitted by the parser per file (not a counter difference) |

Equivalence pitfalls that must be guarded in SQL:

- **"The first one"**: the message sample line, the first UA per attack URL, the first UA per IP with 4xx, the first
  URL per trace. All = minimum by (`relpath`, `line_no`), i.e. the old system's read order.
- **"The most frequent"** (top IP per attack URL, most frequent UA per IP): on a tie, the old system picks
  the one that appeared first. v2 uses the same rule (tie → first occurrence).
- **Text truncation before grouping** (UA 90, attack path 200 after decoding, `path_key` 120).
- **Minute precision** in the account analysis, incidents, and the 401 peak per minute.
- **Exclusions**: status 101 does not count toward duration; simpel-loop `ips` only from events with `ipAddress`.

### 4.4 Definition fixes (decision P4)

The owner asked for wrong or odd definitions (inv. §8 items 6–14) to be fixed. The details of each fix
below are **already approved by the owner** (X11), chosen so that the main numbers stay comparable with the reference and
every difference can be explained. All of them go into the list of **expected differences** in the equivalence test (§9.3).

| # | Inv. §8 | Old | v2 | Numbers that change |
|--:|---|---|---|---|
| 1 | 6 | KPIs computed from truncated lists (pod connection errors, retries, unique source IPs, failed login IPs, critical attacks, total requests and destination IPs on the IP Map, connection error type chart, **endpoint performance table and chart**, which used to be picked from the 150 busiest endpoints only) | Computed from complete data (K4) | Those KPIs, on folders whose list exceeds the limit (e.g. pod connection errors 09-30: 200 → 1,200); the contents of the 25 endpoints with the highest P95 in nginx on 5 of 11 folders (rarely called slow endpoints now show up too) |
| 2 | 7 | nginx/FE `err` = 5xx + error log lines, but the hourly chart (`herr`) only 5xx | `err` stays the sum of both, now with the breakdown `err_http` and `err_log`; **the hourly chart includes both**, so the hourly sum = the KPI | nginx and FE `herr`; the Error KPI does **not** change |
| 3 | 8 | `crit` = error in the ingress, warning in the frontend | `error`, `crit`, `alert`, `emerg` = error in **both**; other levels = warning | frontend `err`/`warn` when there are `crit` lines (on current data: 0 lines, so no difference) |
| 4 | 9 | The simpel-loop level donut uses the application tag: failed 4xx events count as `ERROR` even though the KPI counts them as warnings | The donut uses the **effective level**, same as the KPI rule: failed 5xx event → `ERROR`, other failed events → `WARN`; other lines use their tag | simpel-loop `extra` (e.g. 09-29: ERROR 9,614 → 0, WARN 0 → 9,614) |
| 5 | 10 | `EXC` lines appear in the message table but do not add to Error | **Still not counted**: such a line is the exception detail of the ERROR line above it; counting it would double count. Explained in the table (DRD U8) | none |
| 6 | 11 | Cross-folder correlation | **Kept** (§3.5): a request at the folder boundary really is one event | none |
| 7 | 12 | Account and incident analysis is cut at the folder boundary | **Stays per folder**, consistent with P2. Looking back into the previous folder is T02 and stays postponed | none |
| 8 | 13 | Label "Pod dengan retry 502" (Pods with 502 retries) | "Pod dengan retry" (Pods with retries) | text |
| 9 | 14 | KPI "Request lambat ≥ 5 dtk" (Slow requests ≥ 5 s) only sums traces with 2xx status | Sums all slow traces that **did not fail** (including 3xx) | That KPI, when there are slow 3xx traces |
| 10 | 15 | "Refresh token kedaluwarsa" (expired refresh tokens) counted but not displayed | Displayed (B07) | display |

**Not** touched even though debatable, because they are not mistakes: the percentile index rule, the definition
of "Empty file" (0 bytes), and corrupt file lines still being counted as lines (A6).

The core reference numbers (lines, requests, 4xx, 5xx, errors, warnings, unique IPs, IP flows) are **not** affected by
any of the fixes above, except item 3 if `crit` lines ever appear in the frontend.

### 4.5 Dropped

Embedding JSON into HTML, `snapshot()` and `watch()` (A7), the `lru_cache` on `wib()`, `.cache/geo.json`,
and the land SVG path.

### 4.6 Plan: attack detection with OWASP CRS and CAPEC naming

Owner request (2026-10-06). Done in Stage 21, **after** equivalence with the old rules is
proven, because replacing the rules changes every number on the Security tab.

| Item | Decision | Reason |
|---|---|---|
| Method | **In the script**: CRS patterns are matched against the URL and User-Agent in the nginx log, at ingest | The only method within the dashboard project's control. The **in-ingress** method (ModSecurity/Coraza in detection mode) is more accurate because it inspects the body, headers, and cookies, but it changes the cluster configuration; it is proposed to the cluster operators, not done here |
| Rule source | One CRS release with a pinned version; processed once by a tool into a JSON file committed to the repo | No downloads at runtime; rule changes happen through a visible version change |
| CRS files used | 913 scanners, 930 LFI, 931 RFI, 932 RCE, 933 PHP, 934 generic, 941 XSS, 942 SQLi, 944 Java; only rules whose targets are the URI, arguments, or User-Agent | The rest inspect request parts that are not in the log |
| Categories | From the CAPEC tags each CRS rule already carries; Indonesian and English names from a small dictionary | Standard naming; no self-invented categories |
| Severity | From the CRS rule severity (critical/error/warning/notice), mapped to three display tag levels | Replaces the hand-written severity table |
| Paranoia level | 1 (**ASSUMPTION**, question S1) | Fewest false accusations; can be raised via configuration |
| Regex engine | Python standard library. Rules whose patterns are not supported are recorded and skipped | No new dependencies; the skipped ones are visible in the report |
| Storage | New columns in `nginx_access`: `crs_rules` (list of IDs), `capec`, `crs_severity`, `crs_score`. The old `attack_cat` stays | The old equivalence test can still be run; old vs new comparisons can be computed |
| No re-parse | The new classification is computed from the `path` and `ua` already stored in full, per unique pair | Changing the CRS version does not require reading the logs again |
| License | CRS is Apache 2.0 licensed: the license file and notice are included; the Security page mentions CRS and its version | Compliance |
| Equivalence | Attack numbers in the display **intentionally differ** from the old system after this stage; reported per folder (old vs new) | The list of expected differences gains one group: all attack numbers |

Limitations that do not change: the POST body, other headers, and cookies are not in the log. If the ingress one day
runs CRS itself, its audit log becomes a better detection source and the dashboard will need an additional
parser for it.

---

## 5. API contract

### 5.1 General rules

- Prefix `/api`. Only `GET`, except for the ingest trigger.
- Times in responses: WIB text `YYYY-MM-DD HH:MM` (hour: `YYYY-MM-DD HH`), the same as the old data format,
  so the old display formatters (inv. §2.0) are used without changes.
- Every IP in a response comes with its owner when known: an object `{"ip", "asn", "cc", "org"}`; `asn` null and
  `cc: "-"` for private IPs; only `{"ip"}` when unknown.
- A tab response contains **KPIs + chart series + the first page of each table** (row count = the old limit) and
  each table's `total`. Further rows, filters, and sorting go through the table endpoint (§5.4). This keeps one tab
  ≤ 500 KB (PRD §5.1).
- Errors: `{"error": {"code": "…", "message": "…"}}` with status 400 (bad parameter), 401 (not
  signed in / session expired), 403 (not an admin), 404 (folder / service / table does not exist), 409
  (ingest running), 429 (too many sign-in attempts), 503 (no data yet).
- All endpoints other than `/api/health` and `/api/auth/login` require a session. Data endpoints are open to both
  roles; `/api/admin/*` is admin only (§8.3).
- Cache: data responses carry `ETag` = the last ingest time of that folder. (Stage 11: the header is sent; the 304 answer is not built yet because the slowest endpoint takes 56 ms.)

### 5.2 Frame

| Endpoint | Purpose | DRD page |
|---|---|---|
| `GET /api/health` | Liveness (no data, no session) | — |
| `GET /api/meta` | Folder list, display configuration, ingest status | Frame (§2), folder picker (§6.1) |
| `GET /api/folders/{folder}` | Services + badges, files, previous folder's numbers for comparison. | Sidebar, Overview, Pods |

Example `GET /api/meta`:

```json
{
  "version": "2.0.0",
  "folders": [
    {"folder": "2026-10-06", "range_start": "2026-10-05 09:00", "range_end": "2026-10-06 00:59",
     "lines": 191898, "services": 7, "files": 18, "files_empty": 1, "files_corrupt": 4},
    {"folder": "2026-10-05", "range_start": "2026-10-04 00:00", "range_end": "2026-10-05 00:59",
     "lines": 18611, "services": 7, "files": 16, "files_empty": 1, "files_corrupt": 9}
  ],
  "hosts": {"om-be-simpel-loop-3000": "https://api-simpel4.ombudsman.go.id"},
  "server": {"ip": "103.170.104.228", "city": "Jakarta", "region": "Jakarta", "cc": "ID",
             "lat": -6.17494, "lon": 106.822},
  "dns_upstream": "10.88.1.100",
  "ip_data": {"owner": true, "location": true},
  "ingest": {"running": false, "last_finished": "2026-10-06 17:51", "last_status": "ok"}
}
```

Example `GET /api/folders/2026-10-06` (abridged):

```json
{
  "folder": "2026-10-06", "prev_folder": "2026-10-05",
  "attack_ip_count": 14,
  "services": [
    {"service": "nginx-ingress-controller", "lines": 125097, "err": 125, "warn": 136, "files": 3,
     "requests": 124822, "n4xx": 4533, "n5xx": 51, "prev": {"lines": 17751, "err": 2, "warn": 25}},
    {"service": "om-be-appsmanager", "lines": 24544, "err": 2419, "warn": 71, "files": 3,
     "requests": 0, "n4xx": 0, "n5xx": 0, "prev": {"lines": 3, "err": 0, "warn": 0}}
  ],
  "files": [
    {"service": "nginx-ingress-controller", "pod": "nginx-ingress-controller-5v8j4", "ns": "ingress-nginx",
     "lines": 111301, "err": 110, "warn": 120, "size_bytes": 61938892, "status": "ok"}
  ]
}
```

The "comparable" rule and the ▲/▼ text (inv. §2.0) are computed by the frontend from `prev`, as now.

### 5.3 One endpoint per page

| Endpoint | Parameters | DRD page | Content |
|---|---|---|---|
| `GET /api/folders/{folder}/overview` | — | §3.1 Overview | period, errors per hour per service, top 25 messages across services. (KPIs and the service/file table come from `/api/folders/{folder}`; the "HTTP traffic" part from the nginx service endpoint) |
| `GET /api/folders/{folder}/map` | `module` (optional) | §3.2 IP Map; map in §3.10 | module list, 6 KPIs, location points, abroad / unlocated counts, first page of flows |
| `GET /api/trends` | `last` = 14 \| 30 \| 90 \| `all` (default 30) | §3.3 Trends | per folder × service: lines, errors, warnings; nginx total/4xx/5xx; attacks; wrong passwords; resets; 5 business metrics |
| `GET /api/folders/{folder}/security` | — | §3.4 Security | 8 KPIs, series for 6 charts, material for "Key findings", first page of 5 tables |
| `GET /api/folders/{folder}/rootcause` | — | §3.5 Root Causes | summary material, series for 4 charts, first page of 3 tables, expired refresh tokens |
| `GET /api/folders/{folder}/availability` | — | §3.6 Availability | 7 KPIs, series for 3 charts, first page of 4 tables |
| `GET /api/folders/{folder}/pods` | — | §3.7 Pods | KPIs, series for 2 charts, first page of 2 tables (pod health from `/api/folders/{folder}`) |
| `GET /api/folders/{folder}/business` | — | §3.8 Business | 11 KPIs + previous folder values, series for 5 charts, 2 tables |
| `GET /api/folders/{folder}/tracing` | — | §3.9 Request Tracing | `corr`, KPIs, series for 2 charts, first page of traces |
| `GET /api/folders/{folder}/services/{service}` | — | §3.10 Service; §3.1 traffic part | KPIs, per hour, status, upstream, level, top 10/20 of each list, endpoint performance, messages |

When the log a page needs does not exist, the response is still 200 with `"available": false` and
`"reason"` (`no_nginx`, `no_correlation`, `no_simpel_loop`, `empty`), so that the frontend shows the right empty
state (DRD §6.6) and can tell "0" from "no log" (U16).

Example `GET /api/folders/2026-10-06/security` (abridged):

```json
{
  "available": true,
  "kpi": {"attack_requests": 88, "attack_ips": 14, "critical_hits": 5, "attack_urls_2xx": 62,
          "login_fail_ips": 9, "accounts_ok_after_fail": 1, "accounts_ok_other_ip": 0, "resets": 4},
  "by_category": [["Probe PHP / CGI", 35], ["Probe file sensitif", 28], ["Scan CMS / WordPress", 15]],
  "by_hour": [["2026-10-05 12", 1], ["2026-10-05 21", 30]],
  "top_ips": [{"ip": "45.148.10.238", "asn": 48090, "cc": "NL", "org": "DMZHOST", "hits": 47,
               "max_severity": 2}],
  "by_owner": [["DMZHOST", 47], ["GOOGLE-CLOUD-PLATFORM", 30]],
  "login_by_hour": [["2026-10-05 12", 2], ["2026-10-05 13", 10]],
  "login_top_ips": [{"ip": "39.194.1.60", "asn": 23693, "cc": "ID", "org": "TELKOMSEL-ASN-ID", "fail": 6}],
  "findings": {
    "log4shell": {"hits": 5, "ips": ["34.19.127.176", "34.19.127.195"],
                  "upstreams": ["cattle-system-rancher-80", "om-fe-inhouse-3000"]},
    "by_critical_category": [],
    "rancher_probe_hits": 25,
    "cloud_owners": ["GOOGLE-CLOUD-PLATFORM", "OVH"],
    "ombudsman_login_ips": ["103.160.147.100"],
    "multi_account_ips": [],
    "accounts_other_ip": []
  },
  "tables": {
    "attack-urls": {"total": 71, "rows": [
      {"category": "Log4Shell / RCE", "method_path": "GET /", "hits": 2, "ip_count": 2,
       "top_ip": {"ip": "34.19.127.176", "asn": 396982, "cc": "US", "org": "GOOGLE-CLOUD-PLATFORM"},
       "status_counts": {"200": 2}, "sizes": [6599, 10046],
       "upstreams": ["cattle-system-rancher-80", "om-fe-inhouse-3000"],
       "ua": "${${4b2w:g:-j}${i6a3:-n}…", "first": "2026-10-05 21:30", "last": "2026-10-05 21:30"}]},
    "attack-ips": {"total": 14, "rows": []},
    "accounts": {"total": 10, "rows": []},
    "login-ips": {"total": 9, "rows": []},
    "ip-4xx": {"total": 216, "rows": []}
  }
}
```

Example `GET /api/folders/2026-10-06/map` (abridged):

```json
{
  "available": true, "module": null,
  "modules": ["cattle-system-rancher", "om-be-appsmanager", "om-be-simpel-loop", "om-fe-inhouse"],
  "kpi": {"source_ips": 516, "locations": 222, "countries": 12, "modules": 9, "dest_pods": 15,
          "requests": 124822},
  "abroad_requests": 2030, "unlocated_requests": 0,
  "points": [
    {"lat": -6.2114, "lon": 106.8446, "city": "Jakarta", "region": "Jakarta", "cc": "ID",
     "ips": 211, "requests": 18855, "modules": {"om-be-simpel-loop": 15102, "om-fe-inhouse": 3753}}
  ],
  "tables": {"flows": {"total": 1242, "rows": [
    {"src": {"ip": "103.160.147.100", "asn": 141576, "cc": "ID", "org": "IDNIC-OMBUDSMAN-AS-ID …"},
     "location": {"city": "Jakarta", "region": "Jakarta", "cc": "ID"},
     "module": "om-be-simpel-loop", "requests": 13565,
     "pods": [["10.42.233.181:3000", 6783], ["10.42.233.147:3000", 6782]]}]}}
}
```

Example `GET /api/trends?last=30` (abridged):

```json
{
  "folders": ["2026-10-05", "2026-10-06"],
  "services": ["nginx-ingress-controller", "om-be-appsmanager"],
  "lines": {"nginx-ingress-controller": [17751, 125097], "om-be-appsmanager": [3, 24544]},
  "err":   {"nginx-ingress-controller": [2, 125],        "om-be-appsmanager": [0, 2419]},
  "warn":  {"nginx-ingress-controller": [25, 136],       "om-be-appsmanager": [0, 71]},
  "http": {"total": [17313, 124822], "n4xx": [544, 4533], "n5xx": [0, 51]},
  "security": {"attack_requests": [30, 88], "login_fail": [0, 19], "resets": [0, 4]},
  "business": {"Laporan Dibuat": [0, 7], "Registrasi Laporan": [0, 1], "File Diunggah": [0, 27],
               "Email Terkirim": [0, 1], "OTP Diminta": [0, 7]},
  "file_status": {"om-be-appsmanager": ["rusak", "ok"]}
}
```

A service that is absent from a folder has the value `null` at that position ("None" in the completeness table).

### 5.4 Table endpoint

`GET /api/folders/{folder}/tables/{table}` — one contract for every table that can be continued,
filtered, and sorted (DRD §4.3).

| Parameter | Value | Default |
|---|---|---|
| `service` | service name; required for per-service tables | — |
| `module` | destination module; `flows` only | all |
| `q` | filter text, max. 200 characters; case-insensitive substring on that table's text columns, and on the network owner name of the row's main IP (like the old filter, which searched the whole row text) | empty |
| `sort` | one of the columns allowed for that table | old order |
| `dir` | `asc` \| `desc` | `desc` |
| `limit` | 1–500 | that table's old limit |
| `offset` | ≥ 0 | 0 |

Response: `{"table": "…", "total": N, "matched": M, "limit": L, "offset": O, "rows": […]}`; the shape of each
row is the same as in the page response.

| `table` | Page | Per service | Default limit | Source |
|---|---|:-:|--:|---|
| `endpoints` | Service | yes | 20 | `agg_endpoint` |
| `endpoint-errors` | Service | yes | 20 | `agg_endpoint_error` |
| `endpoint-perf` | Service | yes | 25 | `agg_endpoint` (`dur_n ≥ 5`) |
| `endpoint-error-rate` | Service | yes | 20 | `agg_endpoint` (≥ 20 requests) |
| `slow` | Service | yes | 15 | `agg_slow` |
| `ips` | Service | yes | 15 | `agg_ip` |
| `user-agents` | Service | yes | 12 | `agg_ua` |
| `messages` | Service, Overview | yes | 40 | `agg_message` |
| `flows` | IP Map, Service | — | 3,000 → **100** | `agg_flow` |
| `attack-urls` | Security | — | 300 | `agg_attack_url` |
| `attack-ips` | Security | — | 100 | `agg_attack_ip` |
| `accounts` | Security | — | 150 | `agg_account` |
| `login-ips` | Security | — | 100 | `agg_login_ip` |
| `ip-4xx` | Security | — | 20 | `agg_ip` |
| `c401` | Root Causes | — | 30 | `agg_c401` |
| `pdf-templates` | Root Causes, Business | — | all | `agg_report` |
| `dns` | Root Causes | — | 20 | `v_dns` |
| `upstreams` | Availability | — | 12 | `agg_upstream` |
| `incidents` | Availability | — | all | `agg_incident` |
| `upstream-errors` | Availability | — | 200 | `v_upstream_error` |
| `uptime-targets` | Availability | — | 5 | `agg_uk_target` |
| `backend-pods` | Pods | — | all | `agg_pod` + `agg_retry` |
| `restarts` | Pods | — | all | `v_restart` |
| `activity` | Business | — | 20 | `agg_activity` |
| `trace` | Request Tracing | — | 300 | `agg_trace` |

One deviation from the old limits: `flows` shows the first 100 rows (not 3,000) because it can now be
continued and filtered; 3,000 rows × IP cells was the largest rendering load on the old page. The KPIs and map
points are still computed from all flows.

Example `GET /api/folders/2026-10-06/tables/c401?limit=2`:

```json
{"table": "c401", "total": 555, "matched": 555, "limit": 2, "offset": 0, "rows": [
  {"client": {"ip": "36.75.23.204", "asn": 7713, "cc": "ID", "org": "TELKOMNET-AS-AP PT Telekomunikasi Indonesia"},
   "endpoint": "GET /tx-laporan/count", "n": 412, "peak_per_min": 24,
   "first": "2026-10-05 17:02", "last": "2026-10-05 23:58"},
  {"client": {"ip": "103.142.111.209", "asn": 38758, "cc": "ID", "org": "HYPERNET-AS-ID PT. HIPERNET INDODATA"},
   "endpoint": "GET /v-monitoring", "n": 180, "peak_per_min": 12,
   "first": "2026-10-05 18:10", "last": "2026-10-05 22:41"}
]}
```

(The numbers in the §5.2–§5.4 examples illustrate the response shape; only numbers that also appear in
`00-acuan.json` are real.)

### 5.5 Admin

| Endpoint | Purpose |
|---|---|
| `POST /api/admin/ingest` | Starts an ingest in the API process. Optional body `{"folder": "YYYY-MM-DD", "force": false}`. Answer 202 + `run_id`; 409 when one is running |
| `GET /api/admin/ingest/status` | Status of the running/last ingest: phase, folder, files done/total, warnings |
| `POST /api/admin/derive` | Re-derive aggregates from the raw tables (all or one folder) |
| `POST /api/admin/forget` | Delete one folder's data (replacing the old "missing folder" behavior) |

| `POST /api/admin/import` | Import from an S3 prefix (§3.8). Body `{"url": "s3://simpel4-backup/k8s-logs/2026-09-26/", "dry_run": false}`. Answer 202 + `job_id`; `dry_run` only lists objects |
| `POST /api/admin/import/credentials` | **Admin only** (not the machine token). Stores temporary AWS credentials in memory: `access_key_id`, `secret_access_key`, `session_token`. The answer does not contain the values |
| `DELETE /api/admin/import/credentials` | Removes the credentials from memory |
| `GET /api/admin/import/{job_id}` | Import status |

Only for the **admin** role, or for machine callers with a token (§8.2): the `ingest` task in compose and
external systems that send bucket links.

### 5.6 Authentication and user management (P1)

| Endpoint | Who | Purpose |
|---|---|---|
| `POST /api/auth/login` | public | Body `{"username", "password"}` → creates a session (cookie). 401 with the same message for "user does not exist" and "wrong password"; 429 when rate-limited |
| `POST /api/auth/logout` | session | Deletes the session |
| `GET /api/me` | session | User, role, `must_change_password` |
| `POST /api/me/password` | session | Change one's own password (requires the old password); the user's other sessions are revoked |
| `GET /api/admin/users` | admin | User list |
| `POST /api/admin/users` | admin | Create a user: `username`, `display_name`, `role` (`admin` \| `user`), initial password (must be changed at first sign-in) |
| `PATCH /api/admin/users/{id}` | admin | Change name, role, active/inactive |
| `POST /api/admin/users/{id}/reset-password` | admin | New temporary password; all of the user's sessions are revoked |
| `DELETE /api/admin/users/{id}` | admin | Delete a user (the last admin cannot be deleted/demoted) |
| `GET /api/admin/audit` | admin | Audit log, newest first, paginated |

Example `GET /api/me`:

```json
{"username": "rina", "display_name": "Rina", "role": "user", "must_change_password": false}
```

Example `POST /api/admin/users`:

```json
{"username": "budi", "display_name": "Budi", "role": "user", "password": "<initial password>"}
```

### 5.7 Static files

| Path | Content | Created |
|---|---|---|
| `/` and `/assets/*` | Built Svelte application, including Chart.js, MapLibre, the Outfit and JetBrains Mono fonts | at image build |
| `/map/land.geojson` | Natural Earth 50m land | at the first ingest, from the download cache |
| `/map/borders-country.geojson` | Natural Earth 50m country borders | same |
| `/map/borders-province-id.geojson` | Indonesian province borders, Natural Earth 10m | same |
| `/map/labels.json` | Country / province / regency-city labels (content of `D.labels`) | same |
| `/fonts/{fontstack}/{range}.pbf` | Map label glyphs for MapLibre, Latin range | committed to the repo (§6.4) |

When the `/map/*` files do not exist yet (download failed), `/api/meta` reports it and the frontend shows the map's
empty state (DRD §6.6).

---

## 6. Folder structure, how to run, dependencies

### 6.1 Structure

```
v2/
├─ README.md
├─ run.sh                    run locally: one command
├─ pyproject.toml            Python dependencies
├─ config.example.toml       example configuration (all optional)
├─ monishield/                  Python package
│  ├─ config.py              read configuration + environment variables
│  ├─ rules.py               copy of the old rules (§4.1)
│  ├─ parse.py               per-service parser → CSV rows (§4.2)
│  ├─ ingest.py              scan, fingerprint, per-folder transaction (§3)
│  ├─ schema.sql             table definitions (§2)
│  ├─ derive/                one .sql per aggregate table (+ accounts, incidents)
│  ├─ refdata.py             downloads + IP owner/location + map files
│  ├─ db.py                  one DuckDB connection for the whole process
│  ├─ auth.py                passwords, JWT sessions, roles, audit (ORM, §8)
│  ├─ importer.py            import from an S3 prefix (§3.8)
│  ├─ api/
│  │  ├─ app.py              FastAPI, static files, errors, security headers
│  │  ├─ common.py           parameter validation, IP cell, table endpoint
│  │  └─ overview.py map.py trends.py security.py rootcause.py availability.py
│  │     pods.py business.py tracing.py service.py              ← one module per page
│  │     admin.py users.py session.py                           ← ingest/import, users, sign-in/out
│  └─ cli.py                 serve | ingest | derive | forget | status | user (create the first admin)
├─ web/                      Svelte + Vite
│  ├─ package.json  vite.config.js  index.html
│  ├─ public/fonts/          .pbf glyphs for map labels
│  └─ src/
│     ├─ App.svelte  api.js  state.js (folder, tab, module ↔ URL)  format.js (time, duration, numbers)
│     ├─ theme.css           DRD §5 tokens
│     ├─ i18n/  id.json  en.json
│     ├─ lib/                Kpi, ChartCard, DataTable, IpCell, SeverityTag, Alert, Note, MapView, …
│     └─ pages/              Overview, IpMap, Trends, Security, RootCause, Availability, Pods,
│                            Business, Tracing, Service      ← one file per page
│                            Login, ChangePassword, AdminUsers, AdminIngest
├─ tests/
│  ├─ fixtures/lines/        original log lines per format (from inv. §3)
│  ├─ test_rules.py  test_parse.py  test_ingest.py  test_api.py  test_auth.py  test_import.py
│  └─ test_equivalence.py    against the old system (§9.3)
├─ tools/acuan_lama.py       (already exists) reference numbers from the old system
├─ docs/
├─ Dockerfile  docker-compose.yml          (done in step 7)
└─ data/                     simpel4.duckdb, map/, inbox/, tmp/ (auth.db only without PostgreSQL)     ← not in the repo
```

One backend module and one frontend file per page satisfy PRD §5.6 (changing one tab does not
touch other tabs). The only shared parts are `common.py` and `web/src/lib/`.

### 6.2 Running locally

Prerequisites: Python ≥ 3.11 and Node.js ≥ 20 (Node only to build the frontend).

`./v2/run.sh` does the following, in order, skipping what is already done: creates the Python environment and installs
dependencies; builds the frontend if it does not exist yet or its sources changed; runs the server on
`127.0.0.1:8000`; the server ingests folders not yet loaded; opens the browser. On the first run the script
asks for the name and password of the first admin (only once).

The next day, the same command updates (PRD §5.5). If the server is already running,
`./v2/run.sh ingest` only triggers an ingest through the API (K1).

Development mode: Vite server with an `/api` proxy to FastAPI; not used outside development.

### 6.3 Configuration

Everything has a default = the old system's behavior. **One place for all configuration and secrets: `.env`**
(owner decision 2026-10-06). Priority order: environment variables > `v2/.env` > `config.toml` (optional)
> default values. Every key below can be written in `.env` as `S4_<NAME>` (uppercase); lists and
dictionaries (`hosts`, `server_fallback`, `import_buckets`) are written as single-line JSON. Secrets may only be
in `.env`/the environment, not in `config.toml`, and are never printed. `.env.example` (in the repo, without
secrets) contains all keys with their default values; `.env` goes into neither git nor the image. Unknown `S4_*`
keys in `.env` make startup fail, so typos are not silently ignored.

| Key | Default | Purpose |
|---|---|---|
| `S4_LOG_DIR` | parent folder of `v2/` | log folder (read only) |
| `S4_DATA_DIR` | `v2/data` | DuckDB, map files, temporary CSV |
| `S4_CACHE_DIR` | `<log dir>/.cache` | downloads; the local default uses the old cache so as not to re-download 100 MB |
| `S4_BIND` | `127.0.0.1:8000` | listen address |
| `S4_INGEST_ON_START` | `true` | ingest when the server starts |
| `S4_STATE_DIR` | `v2/data` | SQLite `auth.db`, only when `S4_AUTH_DATABASE_URL` is empty |
| `S4_AUTH_DATABASE_URL` | empty | **Secret.** PostgreSQL URL for accounts: `postgresql+psycopg://user:password@host:5432/db` |
| `S4_JWT_SECRET` | — (required) | **Secret.** Session token signing key, at least 32 random characters; the server refuses to start when it is empty or short |
| `S4_INBOX_DIR` | `v2/data/inbox` | folder for bucket import results (§3.8) |
| `S4_ADMIN_USER`, `S4_ADMIN_PASSWORD` | empty | creates the first admin **only when there are no users yet**; the password must be changed at first sign-in |
| `MAXMIND_ACCOUNT_ID`, `MAXMIND_LICENSE_KEY` | empty | GeoLite2 download for IP location (§3.6); without both, location is empty |
| `S4_JOB_TOKEN` | empty | token for machine callers: the `ingest` task and bucket link senders (§8.2) |
| `S4_COOKIE_SECURE` | `true` | cookie only over HTTPS; `false` only for running locally without TLS |
| `import_buckets` | empty (import off) | allowlist: bucket → allowed prefixes, e.g. `simpel4-backup` → `k8s-logs/` |
| `import_region` | `ap-southeast-3` | bucket region (Jakarta) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | empty | read-only credentials for import; standard AWS names |
| `import_max_objects`, `import_max_object_mb`, `import_max_total_mb` | 500, 1024, 5120 | import limits |
| `session_idle_minutes`, `session_max_hours` | 60, 12 | session lifetime |
| `server_ip`, `server_fallback` | old values | map destination point |
| `hosts` | 6 old entries | upstream → base URL |
| `dns_upstream` | `10.88.1.100` | Root Causes text |
| `upstream_prefix` | `ombudsman-ombudsman-` | upstream prefix that is stripped |

### 6.4 Dependencies

Principle: as few as possible; standard library first.

**Python (runtime)**

| Package | Purpose |
|---|---|
| `duckdb` | storage and queries |
| `fastapi` | API and static file serving |
| `uvicorn` | ASGI server |

| `sqlalchemy` | ORM for accounts, sessions, audit (K11) |
| `psycopg[binary]` | PostgreSQL driver |
| `pyjwt` | creating and verifying session tokens (JWT HS256) |

Password hashing stays `hashlib.scrypt` from the standard library; the machine token is compared with `hmac`.

**Python (optional, only for S3 import)**

| Package | Purpose |
|---|---|
| `boto3` | listing and downloading S3 objects with AWS credentials (including session tokens, list pagination, retries) |

Installed as an optional extra (`simpel4[s3]`) and only imported when the feature is used; without this package
the dashboard runs fully and import answers "not available". Reason for not writing it ourselves: signing
AWS requests by hand is security code that is easy to get wrong in edge cases, and this is the only
place where the dashboard holds a third party's credentials.

Intentionally not used: pandas/pyarrow (CSV from the standard library is enough), ORM (SQL is written directly),
scheduler (triggered from outside), HTTP libraries (downloads use `urllib`, as now), geo libraries (labels
and locations are already handled by the old functions).

**Python (tests)**: `pytest` (runs the tests), `httpx` (needed by the FastAPI test client).

**Frontend (runtime)**

| Package | Purpose |
|---|---|
| `svelte` | view components |
| `chart.js` | charts (same as now, version 4) |
| `maplibre-gl` | map |
| `@fontsource/outfit`, `@fontsource/jetbrains-mono` | bundled fonts, no Google Fonts (B09) |

**Frontend (build)**: `vite`, `@sveltejs/vite-plugin-svelte`.

Intentionally not used: SvelteKit and router libraries (three URL parameters are handled by `state.js`), i18n libraries
(two JSON files and one function), UI component libraries, state libraries, Chart.js wrappers.

**Assets committed to the repo**: `.pbf` glyphs for map labels (two Latin ranges, two weights, ±200 KB).
MapLibre needs glyphs in this format and usually fetches them from a third-party server; storing them in the
repo is how "no external domains" is met. **ASSUMPTION T4**: uses Noto Sans (OFL license) from a ready-made
glyph collection; the map label font therefore differs from Outfit in the interface.

---

## 7. Deployment with Docker Compose

The `Dockerfile` and `docker-compose.yml` files are written in step 7; what is decided here:

### 7.1 Service split

| Service | Role | Opens DuckDB? |
|---|---|:-:|
| `app` | The only long-running service: API + static frontend + in-process ingest. **Uvicorn 1 worker.** | **yes, the only one** |
| `ingest` | One-shot task (profile `job`): calls `POST /api/admin/ingest` on `app` with `S4_JOB_TOKEN`, waits until done, exits with a success/failure code. Mounts no volumes at all. | no |
| `proxy` | **HTTPS** termination in front of `app`. Required because the dashboard is opened from many computers (P3) and the session cookie is only sent over HTTPS. Can be a proxy that already exists on the server, or a service in this compose file (ASSUMPTION T5). | no |
| `postgres` | PostgreSQL for accounts, sessions, audit (K11). Only reachable from `app` on the compose network, with no external port; password from `.env`. | no |

DuckDB stays embedded in `app`; the only database service is `postgres` for accounts. There is no separate frontend service (K8).
**ASSUMPTION T5**: step 7 includes a `proxy` service in compose with certificates provided by the server
owner; if the server already has a proxy, that service is skipped and `app` is simply registered with that proxy.

### 7.2 Sharing the DuckDB file without conflicts

It is not shared: only `app` opens it (K1). `ingest` is only a trigger over HTTP. The rules that guard this:

- `app` runs with **one worker**; more than one would mean more than one writer process. This is
  written as a constant, not configuration.
- Command-line commands (`simpel4 ingest|derive|forget`) always try the API first; they open DuckDB themselves only
  when the server is not running, and fail with a clear message when the file is locked.
- Readers are never blocked: ingest writes in a transaction; API requests during ingest see the
  state before the transaction finished.
- Accepted limitation: the API cannot be scaled to many processes. For a few internal users and
  queries over small aggregates this is not a problem.

### 7.3 Volumes and mounts

| Mount | Kind | Mode | Content |
|---|---|---|---|
| host log folder → `/logs` | bind | **read-only** | log exports; read-only mode also guarantees the "do not change the log folder" rule |
| `s4-data` → `/data` | named volume | read-write | `simpel4.duckdb`, map files, temporary CSV |
| `s4-cache` → `/cache` | named volume | read-write | ip2asn, GeoLite2, Natural Earth, GeoNames downloads (±70 MB) |
| `s4-pgdata` → PostgreSQL data | named volume | read-write | accounts, sessions, audit, import records. **Cannot be rebuilt**; must be backed up (`pg_dump`) |
| `s4-inbox` → `/inbox` | named volume | read-write | log folders from bucket imports (§3.8) |

The four volumes are split by nature: `s4-data` can be rebuilt from the logs, `s4-cache` can be downloaded
again, `s4-state` is irreplaceable, `s4-inbox` holds raw logs that exist only here (and in the bucket). The host log folder path is given via a `.env` variable.

### 7.4 Miscellaneous

- **Image**: two stages; the Node stage builds `web/`, the Python stage carries only the package, the build output, and
  the glyphs. Runs as a non-root user.
- **Ports**: `app` opens no external port; only `proxy` opens 443. When using the server's existing
  proxy, the `app` port is mapped to the host's `127.0.0.1` only.
- `app` trusts the `X-Forwarded-For`/`-Proto` headers **only** from that proxy (for the audit log and
  sign-in attempt limiting).
- **Health check**: `GET /api/health`.
- **Daily ingest**: two paths. (a) Mounted log folder: a cron job on the host runs
  `docker compose run --rm ingest` after the log export arrives (ASSUMPTION T7; the export time is not known yet).
  (b) Bucket: the link sender calls `POST /api/admin/import` (§3.8), which ends with an ingest. `S4_INGEST_ON_START` also catches folders missed while the
  service was restarting.
- **Outbound network**: to download the IP databases and map data (`iptoasn.com`, `download.maxmind.com`
  and its download storage, `raw.githubusercontent.com`, `download.geonames.org`), and to S3 in the
  bucket region (`s3.ap-southeast-3.amazonaws.com` and `simpel4-backup.s3.ap-southeast-3.amazonaws.com`). If the server
  has no outbound access, the `s4-cache` volume is filled manually; ingest still runs without location/owner.
- **Backups**: `s4-state` is mandatory (accounts and audit). `s4-data` can be rebuilt from the logs as long as the logs
  still exist; because T2 makes it the only copy once old logs are moved away, it also needs to be in the
  server backup schedule (copy the file while `app` is stopped, or via an export command).
- **Resources**: the DuckDB memory limit and thread count are set via configuration; initial value 1 GB.

---

## 8. Security

### 8.1 Parameter validation

| Parameter | Rule |
|---|---|
| `folder` | must be a valid `YYYY-MM-DD` **and** exist in `folder_state`; otherwise 404 |
| `service` | must exist in that folder (matched against data, not a pattern) |
| `table` | fixed list in §5.4 |
| `sort` | fixed column list per table; the value is mapped to a column name by code, never inserted from input |
| `dir` | `asc` \| `desc` |
| `limit`, `offset` | integers within range; `limit` max. 500 |
| `module` | must be one of the modules in that folder |
| `q` | max. 200 characters; always as a **bound parameter**; pattern characters (`%`, `_`) are escaped |
| `last` | `14` \| `30` \| `90` \| `all` |
| `username` | 3–32 characters `[a-z0-9._-]`; stored lowercase |
| `password` | 12–128 characters; rejected when equal to the username |
| `role` | `admin` \| `user` |
| `url` (import) | must be `s3://<bucket>/<prefix>/<YYYY-MM-DD>/`; bucket and prefix from the allowlist (§3.8) |
| AWS credentials | the length and character pattern of the access key are checked; the value is never echoed in errors |

General rules:

- All values go into SQL as bound parameters. No SQL is assembled from input text.
- No parameter becomes a file path. Static files come only from two fixed directories.
- Log content is **untrusted data** (attack URLs contain `<script>`, `${jndi:…}`). The frontend
  displays it as text; Svelte escapes by default and `{@html}` is **not used** for anything
  that comes from the logs. Finding sentences that need bold text are composed from components, not from HTML
  in strings (in the old system HTML was assembled as strings).
- Headers: `Content-Security-Policy` with `default-src 'self'` (plus `worker-src blob:` and
  `img-src 'self' data: blob:`, which MapLibre needs), `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, `frame-ancestors 'none'`. The CSP also **enforces** the privacy rule:
  the browser refuses requests to external domains even if some code tries.
- No CORS (same origin).
- Response size and `limit` are capped; queries run with a time limit.

### 8.2 Login and sessions (decisions P1, P3)

The dashboard is opened from many computers and contains account emails, client IPs, full URLs, and sample log lines
(inv. §8 item 19). Therefore: **all access goes over HTTPS and requires login.**

| Item | Decision | Reason |
|---|---|---|
| Accounts | Created by an admin. There is no self-registration and no "forgot password" by email; the admin gives a temporary password. | Few, known users; no dependency on email |
| First admin | From `S4_ADMIN_USER`/`S4_ADMIN_PASSWORD` when there are no users yet, or the `simpel4 user` command. Must change the password at first sign-in. | No default password in the code |
| Passwords | At least 12 characters, no composition rules. Stored as a per-user salted **scrypt** hash; the parameters are stored so they can be raised. Constant-time comparison. | Common recommendation (length matters more than composition); scrypt is in the standard library |
| Sessions | **JWT** (HS256, signed with `S4_JWT_SECRET`) containing `sub` (user id), `sid` (session id), `iat`, `exp`; sent only via an `HttpOnly`, `Secure`, `SameSite=Strict` **cookie**, not accepted from the `Authorization` header. After the signature, issuer, and validity period pass, the `sid` session row is **still checked in the database**. Expires after 60 minutes without activity or 12 hours in total. Sign-out, password change, reset, and deactivation revoke sessions immediately. The role is not carried in the token. | Requested by the owner (JWT). A pure JWT cannot be revoked before it expires; the `sid` check preserves immediate revocation. Only the HS256 algorithm is accepted (`alg: none` and other algorithms are rejected). The token cannot be read by page scripts |
| CSRF | `SameSite=Strict` + every data-changing request must carry a custom header and a matching `Origin`. | API and pages share one origin; no separate token needed |
| Sign-in attempts | After 5 failures: the account is locked for 15 minutes; also limited per IP. The error message does not distinguish "user does not exist" from "wrong password". The hash is still computed for nonexistent users. | Resists password guessing and user enumeration |
| Machine callers | The `ingest` task and bucket link senders use `S4_JOB_TOKEN` in a header; the token is only valid for `POST /api/admin/ingest`, `POST /api/admin/import`, and the status of both. | Machines have no session; the token scope is as narrow as possible |
| Audit | Recorded: successful/failed sign-in, sign-out, password change/reset, user create/update/delete, role changes, ingest, import, `forget`. Not recorded: passwords, tokens, the content of pages opened. | A trail for actions that change access or data |
| No session | The API answers 401; the frontend goes to the sign-in page and returns to the original address after success. | |

**Decided by the owner (X1)**: login is managed by this application with local accounts in the account database (K11); there is no SSO.

Out of scope: two-factor authentication, password history, periodic password expiry.

### 8.3 Roles (decisions P1, X10)

For now only two roles, without per-module restrictions:

| Role | Can |
|---|---|
| **user** | See the **whole** dashboard: all analysis tabs and all service pages, all folders. Change their own password |
| **admin** | Everything a user can, plus: add, edit, deactivate, and delete users; reset passwords; trigger ingest, import, `derive`, `forget`; view the audit log |

| Endpoint | Who |
|---|---|
| `/api/health`, `/api/auth/login` | public |
| All data endpoints (§5.2–§5.4), `/api/me`, `/api/auth/logout`, `/api/me/password` | user and admin |
| `/api/admin/*` | admin; machine token only for ingest and import (§8.2) |

Rules:

- The check is in one place (a FastAPI dependency attached per router), not in each function.
  A router without a role declaration is **rejected when the application starts** (secure by default).
- A regular user calling an admin endpoint → 403; the frontend shows "You do not have access to this page".
- Role changes or deactivation take effect on the next request (read from the account database per
  request; no cache).
- The last admin cannot be deleted, deactivated, or demoted to user.

**Per-module restrictions are postponed**, not dropped. If requested later, adding them is localized: one
`user_module` table, one extra check in the same dependency, a checklist on the Manage users
screen, and a filtering sidebar. Data endpoints are already one-per-page (§5.3), so they need not be split.
Hence there is no work now that would have to be torn down later.

### 8.4 New screens needed (input for the DRD)

The DRD was written before P1 was answered and does not contain these screens yet. Their minimum requirements:

| Screen | Content |
|---|---|
| Sign in | Username, password, button; generic error message; language and theme pickers remain |
| Change password | Mandatory at first sign-in / after a reset; also from the user menu |
| User menu (in the header) | Name, role, "Change password", "Sign out"; for admins: "Manage users", "Ingest & import" |
| Manage users (admin) | User table (name, role, active, last sign-in); add user (name, role, initial password); change role; reset password; deactivate; delete |
| Ingest & import (admin) | Status of the last and the running ingest, warnings, "Ingest now" button; bucket link field + import status; audit log |
| No access | Only for regular users who open an admin screen address (403) |
| Session expired | Back to the Sign in screen with an explanation, then to the original address |

The sidebar is the same for all users; the admin items ("Manage users", "Ingest & import") exist only in the admin's user menu.

### 8.5 Miscellaneous

- Container: non-root user; log folder read-only.
- Credentials only via environment variables / a `.env` that is not in the repo.
- Database downloads: HTTPS, written to a temporary file and then renamed (as now); the content is
  treated as data (parsed, not executed).
- Dependency versions are pinned (`pyproject` with version bounds, `package-lock.json`).
- The application log does not write the content of users' log lines.

---

## 9. Test strategy

### 9.1 Parser unit tests with original lines

- Source: the original lines in inv. §3 and §4.1, stored per format in `tests/fixtures/lines/` (account names
  masked as in the inventory). At least one line per pattern in inv. §3, including: nginx access
  normal / with retry / without upstream / Uptime-Kuma; nginx error with and without upstream; frontend access and
  error; successful and failed simpel-loop events; every meaningful simpel-loop text line; the eight
  Spring patterns; exception lines; `Hibernate:` lines; coredns; `unsupported log format` lines; lines that
  must be ignored.
- For each line: the expected output row (table and column values) and the counter changes
  (`lines`, `err`, `warn`, `file_counter`).
- The contents of the old `demo()` (IP location, `kab_name`, flows with retries) are moved into tests.

### 9.2 Rule tests against the old module

As long as `build_dashboard.py` is in the parent folder: for a set of real inputs (paths, UAs, messages taken
from logs), `rules.py` and the old module must give identical results for `classify`, `path_key`, `norm`,
`jwt_bucket`, `accounts`, `incidents`, `ip_owner`, `geo_scan`. This test is skipped (not failed) when the old
module does not exist, e.g. inside the image.

### 9.3 Equivalence test

Answers PRD §6.2. Run against the real log folders; requires the old system.

| Level | What is compared | Condition |
|---|---|---|
| E1 Reference numbers | Every number in `00-acuan.json` (regenerated by `tools/acuan_lama.py` right before the test) vs a query on the aggregate tables, per folder × service | exactly equal |
| E2 List contents | Every list in `D` extracted from `dashboard.html` (`paths`, `perr`, `ips`, `msgs`, `atk`, `atk_ip`, `login`, `acct`, `ep`, `c401`, `incidents`, `pod`, `retry`, `uperr`, `trace`, `flow`, `rep`, …) vs the API response with `limit` = the old limit | same rows and values; order may differ only among rows with equal values; percentiles equal up to display rounding |
| E3 IP data | `D.ipinfo` (network owner) vs `ip_info` for the same IPs, with the same ip2asn file | equal. Location is not compared: its source is now GeoLite2 (§3.6); tested against that GeoLite2 file itself |
| E4 Expected differences | The §4.4 fixes: for each item, the old value, the new value, and the correct value (from `00-acuan.json` for item 1; computed from the old system's raw data for items 2, 4, 9) | new value = correct value; the list of differences is **closed** (items 1, 2, 3, 4, 9 in §4.4), any other difference = failure |

The E1–E4 results are written to the equivalence report (step 8). E1 runs from the moment the ingest stage is done, before
any display exists (PRD R2, R9).

### 9.4 Ingest tests

With a small artificial log folder built from sample files:

- Ingest twice → the contents of all tables are identical (compared via row counts and a checksum per table).
- A file's content grows → only that folder changes; the result equals a clean ingest.
- `.log.gz` only → then an identical `.log` appears → no re-parse, no duplicate rows.
- A differing `.log`/`.log.gz` pair → a warning is recorded; the `.log` is used.
- File deleted → its rows disappear, the folder's aggregates are re-derived.
- Corrupt file → `status = rusak`, lines counted, other files still loaded.
- Process killed midway through a transaction → the next ingest yields a clean state.
- `(file_id, line_no)` unique in every raw table.
- Folders without a namespace (A9) and unknown service folders (A10, with a warning).

### 9.5 API tests

- Each endpoint: response shape, `available: false` on folders without the relevant log, 400/404 errors.
- Validation: values outside the list, `q` containing quotes / `%` / scripts, `limit` out of range, folders
  that do not exist, SQL injection attempts on every parameter.
- Response size of each page ≤ 500 KB on the largest folder.
- Security headers present on all responses.

### 9.6 Login, role, and import tests

- Passwords: hashes differ for the same password; correct/incorrect verification; short passwords rejected.
- Sessions: no cookie → 401; expired session → 401; sign-out/reset/deactivation revoke sessions; the cookie carries
  `HttpOnly`, `Secure`, `SameSite=Strict`.
- Lockout after 5 failures; the same error message whether the user exists or not.
- **Role matrix**: for every endpoint × {no session, user, admin, machine token} → the expected
  status (401 / 200 / 403). The matrix is built from the §8.3 table, so a new endpoint without a row in the
  matrix fails the test.
- Data-changing requests without the correct header/`Origin` are rejected.
- The last admin cannot be deleted, deactivated, or demoted.
- The machine token is only accepted at the ingest/import endpoints.
- Import, against a **local fake S3** (a small server inside the test, no real AWS): a link that is not
  `s3://`, a bucket outside the allowlist, a prefix outside the allowed ones, a last component that is not a date, a key
  containing `..`, objects outside the pattern, exceeding the count/size limits, no credentials, credentials rejected by S3 →
  all fail with a clear message without writing to the inbox. A valid prefix → the folder appears and
  is ingested; a `.log`/`.log.gz` pair → only the `.log` is downloaded; the same link twice → 0 objects downloaded
  again; `dry_run` → no files written.
- Credentials: do not appear in responses, logs, the account database, or the audit; the machine token cannot call
  the credentials endpoint; temporary credentials are gone after the server restarts.
- Testing against the real bucket **cannot** be automated; it is done manually once in dry run mode (T14).

### 9.7 Performance and size tests

- **Artificial one-year data**: the raw rows of folder `2026-09-29` are duplicated to 365 folder dates with a query
  (without re-parsing), then the aggregates are derived. Measured: file size (target ≤ 10 GB), response time of each
  page endpoint (PRD §5.1 target), time to ingest one more folder on top of that data (≤ 60 seconds), time of
  an ingest without changes (≤ 5 seconds).
- Done **right after ingest and the schema are ready**, before the frontend (PRD R4). This is also what confirms
  or refutes ASSUMPTION T1.
- Login cost: the scrypt hash is measured and its parameters chosen so that one verification takes ±100 ms on the server.

### 9.8 Frontend and privacy tests

- Dictionary completeness: every key in `id.json` exists in `en.json` and vice versa (a small script, no
  test framework).
- The build output contains no URLs to external domains other than attribution links (a text check over `dist/`).
- Manual checklist-based checks for each page × {ID, EN} × {dark, light} × {wide, narrow}
  against inv. §2 and DRD §3 (PRD §6.1), with the network turned off.
- **ASSUMPTION T8**: no automated browser tests (Playwright etc.) in this migration; a manual checklist
  is enough for 10 pages and saves one heavy dependency. Added if the display changes often.

---

## 10. Impact on other documents

Things decided here that change or sharpen earlier documents.
**Status: already applied** to the PRD and DRD in Stage 1 of the plan (2026-10-06); the screens in §8.4 are now
designed in DRD §3.11 and §6.9.

| Document | Item | Change |
|---|---|---|
| PRD A1, P2, T01 | "day" | **Decided**: per folder. T01 (per calendar date) is no longer planned |
| PRD A2, P4, T05 | definitions copied | **Decided**: fixed. Details in §4.4; T05 is mostly done now |
| PRD A3, P3, §5.4 item 4, §7 | "only opened on the computer that runs it"; "running on a server is out of scope" | **Dropped**: runs on a server, accessed by many computers over HTTPS with login |
| PRD A5, P1, T03, §7 | users assumed; login postponed and out of scope | **Decided**: login with two roles is in scope (§8.2–§8.4); per-module access rights postponed |
| PRD A7, T04 | no automatic ingest | Added an import path from bucket links (§3.8), scheduled after equivalence is proven |
| PRD §4 | feature list | New features: login, user management, audit, bucket import; postponed: per-module access rights |
| PRD §5.5 | "one command" | Stays for local use (`run.sh`, creates the admin once); on the server: `docker compose up -d` |
| PRD §6.2 | expected differences only inv. §8 item 6 | The closed list is now items 1, 2, 3, 4, 9 in §4.4 |
| PRD §6.3 | "adding a 12th folder does not change the numbers of folders 1–11" | Holds except for the correlation aggregates (§3.5) |
| PRD T09 | retention | Log folders that disappear do not delete data (T2); explicit deletion via `forget` |
| PRD R7 | personal data risk | Handled by login + access rights + audit; new risks: password management and the import feature (SSRF) |
| DRD D7, Q2 | no login | **Dropped**: needs the screens in §8.4 (not yet designed in the DRD) |
| DRD Q1 | how seriously to do the phone layout | **Decided**: seriously; DRD §8 applies in full |
| DRD §1.1, §2 | frame | The sidebar still shows all tabs; the header gets a user menu (admin: + "Manage users", "Ingest & import") |
| DRD §6.6–§6.7 | empty/failed states | Added "no access" and "session expired" |
| DRD U8 | `(i)` explanations | Mandatory for Error (5xx + log breakdown), `EXC` lines, and simpel-loop levels (§4.4) |
| DRD §4.3, flow table | initial limit 3,000 | Initial view of 100 rows, the rest via "show next" |
| DRD §6.5 | loading per card | One request per page; cards appear together. "Failure per card" becomes "failure per page" + "failure per continued table" |
| DRD §7.2–§7.3 | map sources | Five static files in §5.7; label font Noto Sans (T4) |

---

## 11. Assumptions and open questions

### 11.1 Technical ASSUMPTIONS

| # | ASSUMPTION | If wrong |
|--:|---|---|
| T1 | One year of raw data fits in ≤ 10 GB thanks to DuckDB compression | Move `ua`/`path` to a dictionary table, or keep raw data only for the last N months (aggregates stay) |
| T2 | A log folder that disappears from disk does **not** delete its data from the dashboard | Run `forget` automatically when a folder disappears (old behavior) |
| T3 | The owner/location of an IP is not updated when a new database is downloaded | Add a bulk update command |
| T4 | Map label glyphs = Noto Sans stored in the repo | Build glyphs from Outfit (needs a one-off generator tool) |
| T5 | Compose includes an HTTPS proxy service; certificates are provided by the server owner | Use the existing proxy; `app` only on loopback |
| T7 | Daily ingest is triggered by host cron | A scheduler inside `app` (one time-of-day setting) |
| T8 | No automated browser tests | Add Playwright |
| T9 | Inherits unanswered PRD items: no CDN (A4), corrupt files still counted (A6), folders without a namespace and unknown services supported (A9, A10) | See PRD §9 |
| T14 | Object layout under the prefix = local log folder layout | Add a name mapping in `importer.py`; found out from dry run mode |
| T15 | Only **location** moves to GeoLite2; the network owner (ASN, organization) stays ip2asn | Also switch to `GeoLite2-ASN-CSV` (same credentials); the E3 owner test is dropped |

### 11.2 Questions for the product owner

Already answered: PRD P1, P2, P3, P4; X1 (local accounts); X11 (definition fixes); DRD Q1 (phone done seriously);
X9 (S3 prefix, long-term key, Jakarta region); X10 (for now only admin and user, without
per-module restrictions). The remaining ones, ordered by their impact on steps 5–7:

| # | Question | Interim assumption |
|--:|---|---|
| X9 | **S3 import** (key type, region, and read-only nature already answered): who will send the links, an admin through the screen or another system through the API? Can a dedicated IAM user that only reads `simpel4-backup/k8s-logs/` be created later? | Both are supported; the existing key is used first |
| X2 | **Server** (the owner does not know yet; asked of the server operators): is there already a reverse proxy/HTTPS and a domain name? Is there outbound access to S3 Jakarta and to the five IP database download addresses? How much disk and memory? All of it is **checked with commands at deployment** (step 7), not assumed | Proxy included in compose (T5); outbound access exists; ≥ 20 GB, ≥ 2 GB |
| X3 | **Log folder on the server**: will exports to the mounted folder continue, or will everything go through the bucket? At what time does data arrive; how long is it kept? | Both are supported |
| X4 | **Log folders that disappear**: is the dashboard data kept (T2) or does it disappear too, like the old system? | Kept |
| X5 | `.log` and `.log.gz`: v2 records a warning when their contents differ. Which one is correct when they differ? (= PRD P5) | `.log` |
| X6 | The IP flow table shows the first 100 rows, not 3,000: agreed? | Yes |
| X7 | The map label font differs from the interface font (T4): acceptable? | Yes |
| X8 | Backups of the `s4-state` (mandatory) and `s4-data` volumes: part of the server backup schedule? | Yes |

DRD questions Q3, Q6, Q7 are still open; the schema and API above do not depend on their answers.

**New owner request (2026-10-06, during Stage 12)**: a **Command Center** module (map, overview, and all info
on one screen, **realtime**) because the data will later be streamed via **Kafka**. This changes K1/A7 (daily ingest, no
automatic updates); the proposal and its assumptions are in §12. **The owner answered (2026-10-06): Kafka is only for the future;
updates still come through the log folders as the main source.** So R1, R2, R4 only need answers when a Kafka stream
is actually planned. R5 and R6 are already answered (see the table). Questions:

| # | Question | Interim assumption |
|--:|---|---|
| R1 | **Kafka stream content**: raw log lines per service (same format as the files now) or already-structured events? Who is the producer (Fluent Bit/Vector/the applications)? Topic names? | Raw log lines, one topic per service, sent by the cluster log collector |
| R2 | **How realtime**: how late may the numbers on screen be (seconds/minutes)? | ≤ 10 seconds |
| R3 | ~~Relationship with the daily folders?~~ **Answered 2026-10-06: log folders stay the main source of updates**; Kafka is only a future plan | — |
| R4 | **Kafka access**: broker address, authentication (SASL/TLS), reachable from the dashboard server? | Not known yet; checked at deployment (like X2) |
| R5 | ~~Does Command Center replace Overview?~~ **Answered 2026-10-06: Overview stays; Command Center is the world map screen** (map of IP origin → server as the main content, with KPIs and "what needs attention" around it). **ASSUMPTION**: the "IP Map" tab is merged into Command Center (one map component, no two map pages) | — |
| R6 | ~~Reference style for the whole dashboard?~~ **Answered 2026-10-06: yes, the whole dashboard** | — |

---

## 12. Proposal: Command Center and realtime streaming (Kafka) — Kafka POSTPONED (future)

Written during Stage 12 at the owner's request. **Decision 2026-10-06: log folders stay the main source of updates;
Kafka is only for the future.** Command Center is built first on top of folder data (ingest as now); the streaming
items below are a design for later and remain an **ASSUMPTION** until R1, R2, R4 are answered. What must be preserved from
now on: the Command Center page gets its data through one module (`api.js` + one endpoint), so that later
a stream can be added as a source without changing the display.

- **Still one process owns DuckDB (K1).** The Kafka consumer runs as a thread in the same server process (like
  in-process ingest, Stage 10), writing in small batches (e.g. every 2 seconds or 5,000 messages) to time-windowed
  `rt_*` tables, using the same parser (`parse.py`) so that number definitions do not diverge.
- **To the browser via Server-Sent Events** (`GET /api/stream`, one-way, the same session cookie, passes the CSP `'self'`,
  reconnects automatically). WebSocket is not needed because the browser sends nothing.
- **Command Center** = one page using shared components: running KPIs, the map, "what needs attention"
  (the existing automatic findings: attacks, failed logins, 5xx, pod connection errors), and a stream of recent events;
  a "streaming · last event N seconds ago" marker and a Live/disconnected status.
- **The daily folders stay the source of truth (R3)**: a folder ingest replaces the stream data for that date, so the
  equivalence tests E1–E4 still apply.
- New optional dependency `simpel4[kafka]` (`confluent-kafka`), only imported when `S4_KAFKA_BROKERS` is set;
  without it the dashboard runs as now and Command Center uses the latest folder data.

