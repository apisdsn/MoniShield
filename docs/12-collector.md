# Plan — collector (stage 54)

Status: planned with the owner on 2026-11-04. Mockups: the "Rencana" page of the MoniShield mockup canvas
(Admin › Collectors, Servers & Endpoints, collector flow).

## 1. Goal

Today MoniShield reads logs that arrive from an S3 export or from Kafka. A **collector** lets a site send logs (and later
metrics) straight from its servers and clusters: Linux and Windows servers, Docker hosts and Kubernetes clusters. Nothing
listens on the client's servers; the collector connects out to MoniShield over HTTPS.

## 2. Decisions (owner, 2026-11-04)

1. Step **1c of the log formats** ([`11-log-formats.md`](11-log-formats.md)) comes first, so logs of servers that are not
   the Kubernetes ingress show up on the pages, not only in Raw Logs.
2. The collector is a **third data source** next to S3 and Kafka: own database, inbox, retention, notifications and
   ingest schedule, and a third option in the header's source switch.
3. The receiver runs on a **subdomain without the Cloudflare proxy** (DNS only, TLS from Caddy), so the logs of a client
   do not pass through a third party.
4. Logs and collector management first (part 1); metrics follow (part 2).
5. Install scripts and the Helm chart use the name MoniShield for now; they are renamed with the rest of the app.

## 3. How it works

- The collector is the **OpenTelemetry Collector** (`otelcol-contrib`, pinned version) with a configuration MoniShield
  writes. No agent of our own: its receivers already cover log files, journald, Windows Event Log, host metrics, Docker,
  Kubernetes, HTTP checks, SQL queries and SNMP.
- It sends **OTLP/HTTP with JSON encoding and gzip** to `/v1/logs` (later `/v1/metrics`), with its own key as a Bearer
  token. JSON needs no new Python dependency.
- The receiver turns each log record into the same thing the Kafka consumer makes today: namespace, service, pod or host,
  the original line, and a time. Lines are appended to the collector source's inbox in the S3 folder layout, one file per
  host or pod **per hour** (`log_<service>_<pod>_<date>-HH-00.log`), so ingest only re-reads the current hour.
- Ingest, the parsers, the log format rules and Raw Logs work on those files unchanged.

## 4. Steps (each one a commit on `dev`, tested)

Code is written by Sonnet 5.5 from a written specification; planning and the review of steps 2, 3 and 4 by Opus 5.5.

| Step | Delivers |
|---|---|
| 0 | Log formats step 1c (prerequisite) |
| 1 (done) | `domain/otlp_logs.py` (pure): OTLP/JSON log records → namespace, service, pod/host, line, time. Kubernetes attributes as for Kafka (`service_of`); plain servers by `host.name` and `service.name`; journald (`MESSAGE`, unit) and Windows Event Log (one JSON line); a structured body becomes one JSON line; names checked so they cannot leave the folder; times far in the future capped at the receive time. Tests on sample payloads in `tests/fixtures/otlp/`. Done: `parse_logs(payload, collector, now)` returns the records (`ns`, `svc`, `pod`, `line`, `t`, `relpath`) and the rejected counts by reason; `partial_success` builds the OTLP answer; journald lines are written as RFC 5424 so the `syslog` preset reads their time and level |
| 2 (done) | Collector registry (accounts database): name, platform, version, last seen, revoked; one-time enrollment token (24 h) exchanged for a long-lived key, both stored as hashes; replace and revoke the key; audit `collector.add`, `collector.enroll`, `collector.rotate`, `collector.revoke`. Application service + port |
| 3 (done) | Receiver `POST /v1/logs`: Bearer key, outside the CSRF guard and the payload encryption (a machine client), size limits before and after gunzip, rate limit per collector, written to disk before the 200, OTLP partial-success answer, 401 / 413 / 429 with `Retry-After` |
| 4 (done) | Third source `collector`: database, inbox, retention, notifications, ingest schedule; hourly files; source switch in the header; dictionaries id/en. See "Collector source" below |
| 5 | Configuration writer and install: collector YAML per platform and chosen data (file logs, journald, Windows Event Log, Docker, Kubernetes), `otlphttp` exporter with a disk queue and retries; `install.sh` (systemd), `install.ps1` (Windows service), Helm values |
| 6 | Admin › Collectors page (after the mockup): list, status counts, add dialog with platform tabs and the install command, details, replace / revoke key |
| 7 | End-to-end check with a real `otelcol-contrib`: lines reach Raw Logs and the pages; data queued while the link is down arrives later; a revoked key is refused |
| 8 | Deploy and docs: receiver subdomain, new `.env` settings, user guide, status, changelog |
| 9 | Part 2: `POST /v1/metrics`, time-series tables in DuckDB (minute → hour roll-up, retention) |
| 10 | Part 2: Servers and Kubernetes pages, z-score anomalies |

### Step 2: registry, enrollment and keys

- Texts: enrollment token `mse_<id>_<secret>`, key `msk_<id>_<secret>`; `<id>` is the collector's row id (so the server
  finds the row without scanning), `<secret>` is `secrets.token_urlsafe(32)` (43 characters). Only the SHA-256 of the
  secret is stored and compared in constant time; the texts are shown once (create, new token, enroll, rotate).
- Flow: `POST /api/admin/collectors` (admin) returns the token (valid 24 h); the install script calls
  `POST /api/collector/enroll` with `X-Requested-With: monishield-collector` and gets the key. The token works once.
  Every bad token gives the same error and counts toward the login's per-IP limit (20 per 15 minutes).
- Rotate: the new key is returned once; the previous key keeps working for 24 h (`previous_valid_until`), so a running
  collector can be updated without losing data. Revoke refuses every key at once. Delete only after revoke (or before
  enrolling).
- Status: `revoked`, `waiting`, `online` (seen within 5 min), `late` (within 60 min), `offline`. `last_seen` is written at
  most once a minute per collector. Step 3 calls `CollectorService.authenticate(key, ip, version)`.
- Step 6 must add Indonesian entries for the new messages to `web/src/srv.js` (`ERR_ID`).

### Step 3: the receiver

The OpenTelemetry Collector's `otlphttp` exporter uses `endpoint: https://<host>/api/collector`, `encoding: json`,
`compression: gzip` and the header `Authorization: Bearer <key>`; it posts to `POST /api/collector/v1/logs`. The route needs
no session and no `X-Requested-With`, is not audited and is not touched by the payload encryption (no `X-MS-Enc`). The lines
are appended to the **collector inbox** (`S4_COLLECTOR_INBOX_DIR`, default `<inbox>/collector`), one write per file under a
lock, flushed and `fsync`ed before the 200. Step 4 turns that inbox into the third source.

| Code | `error.code` | When | Collector |
|---|---|---|---|
| 200 | | taken; `{}`, or `partialSuccess` with `rejectedLogRecords` and the reasons (the rest was written) | done |
| 400 | `invalid_body` | corrupt gzip, not UTF-8 / JSON, not a JSON object | drops the batch |
| 401 | `invalid_collector_key` | missing, wrong, revoked or expired key | drops the batch |
| 413 | `body_too_large` | body over `S4_COLLECTOR_MAX_BODY_MB` (by `Content-Length` and while reading), or over `S4_COLLECTOR_MAX_RAW_MB` after gunzip (stopped while unpacking) | drops the batch |
| 415 | `unsupported_media_type` | not `application/json` (protobuf gets the hint to set `encoding: json`), or an encoding other than gzip / identity | drops the batch |
| 429 | `rate_limited` | more than `S4_COLLECTOR_RATE_PER_MIN` requests in a minute from one collector; `Retry-After: 30` | retries |
| 429 | `too_many_attempts` | more than 60 wrong keys in a minute from one address: blocked 5 minutes; `Retry-After: 300` | retries |
| 503 | `disk_full` | free space under the inbox below `S4_COLLECTOR_MIN_FREE_MB`; `Retry-After: 60` | retries, keeps its queue |
| 503 | `busy` | `S4_COLLECTOR_MAX_CONCURRENT` requests are already being read and stored; `Retry-After: 5` | retries |
| 503 | `storage_error` | the lines could not be written; `Retry-After: 60` | retries |

Memory: a raw JSON body becomes about ten times as many bytes of Python objects, so peak memory is roughly
`S4_COLLECTOR_MAX_CONCURRENT` x `S4_COLLECTOR_MAX_RAW_MB` x 10 (default 4 x 16 MB x 10 = about 640 MB). The collector
configuration of step 5 must keep batches under the limit (batch processor `send_batch_max_size`).

Wrong keys have their own per-IP limit in memory (not the login's), so bad keys never lock people out of sign-in. The rate
limit is a per-minute window per collector. A batch with a write error halfway can leave lines of its first files behind;
the retry then writes them again (see known limits).

### Collector source (step 4)

The collector is a data source like S3 and Kafka (`?source=collector`, option **Collector** in the header switch). It has its
own database `<data_dir>/collector/monishield.duckdb` (`collector_db_path`), its own inbox (`S4_COLLECTOR_INBOX_DIR`, default
`<inbox>/collector`) and its own ingest, retention, notifications and backup (`collector.duckdb.gz`). The switch offers it
once a collector is registered or its database holds a day.

- **Ingest.** The receiver adds the folders it wrote to `CollectorFeed.pending`. A small thread (`collector-ingest`, started
  and stopped with the server) ingests them through the collector source's ingest at most every `S4_COLLECTOR_INGEST_SECONDS`
  (default 300): one folder alone, several as one ingest of the inbox, where only changed files are read again (the current
  hour's file). It waits for other ingests like Kafka's does (one ingest at a time, one DuckDB owner) and does not start
  while the source's own ingest is running. A folder leaves `pending` only when its ingest succeeded; after a failure it is
  tried again at the next round.
- **Catch-up.** When the server starts, one ingest of the whole collector inbox runs at once (only files whose size or time
  changed are read again), so lines received before a restart show up, also in a folder the database already knows, without
  waiting for a new batch.
- **Days.** Folder D holds (D-1 00:00, D 00:00] local time, like Kafka's, so the folder dated tomorrow is still filling up:
  notifications look at the day in progress only and the daily report waits for a complete folder.
- **Left to Kafka.** The consumer, "Check messages" and the live map belong to Kafka. The rule "S3 replaces Kafka's files" never
  applied to the collector inbox.

### Log format rules for collector data

Records from the collector arrive as plain lines, so a rule in `log-formats.toml` tells the parsers how to read them.
Windows Event Log records are one JSON object per line, journald records are RFC 5424 syslog lines:

```toml
[[service]]
match = "windows-*"
format = "json"
fields = { time = "system_time", level = "level", message = "message" }

[[service]]
match = "sshd"             # a journald unit or syslog identifier; list the services of the host
format = "syslog"
```

Kubernetes and Docker records keep the original line, so they use the same rule as the Kafka source. Plain files use the
rule of their service name (`service.name` of the collector's file group, else the file name without rotation suffix).

## 5. Safety

- One key per collector, stored as a hash, revocable; enrollment tokens work once and expire.
- Size limits before and after decompression (no zip bombs), a rate limit per collector, names validated like the Kafka
  consumer's, no path built from unchecked input.
- The receiver only writes inbox files; ingest keeps the database lock as today.
- Logs go from the client's server to MoniShield only (no third party on the way).

## 6. Known limits

- A retried batch whose answer was lost, or that failed halfway through its files, can be written twice; rare, accepted for now.
- The receiver's counts (`CollectorFeed.status()`) are in memory and start again at every restart.
- Metrics (part 2) need their own storage and pages; they do not touch the log parsers.
- Replacing a key twice within 24 h ends the grace of the first key at once (only one previous key is kept).
- Wrong enrollment tokens share the login's per-IP limit (20 per 15 minutes), so many bad installs from one address can
  also block sign-ins from that address for 15 minutes, and the reverse.
