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
| 1 | `domain/otlp_logs.py` (pure): OTLP/JSON log records → namespace, service, pod/host, line, time. Kubernetes attributes as for Kafka (`service_of`); plain servers by `host.name` and `service.name`; journald (`MESSAGE`, unit) and Windows Event Log (one JSON line); a structured body becomes one JSON line; names checked so they cannot leave the folder; times far in the future capped at the receive time. Tests on sample payloads in `tests/fixtures/otlp/` |
| 2 | Collector registry (accounts database): name, platform, version, last seen, revoked; one-time enrollment token (24 h) exchanged for a long-lived key, both stored as hashes; replace and revoke the key; audit `collector.add`, `collector.enroll`, `collector.rotate`, `collector.revoke`. Application service + port |
| 3 | Receiver `POST /v1/logs`: Bearer key, outside the CSRF guard and the payload encryption (a machine client), size limits before and after gunzip, rate limit per collector, written to disk before the 200, OTLP partial-success answer, 401 / 413 / 429 with `Retry-After` |
| 4 | Third source `collector`: database, inbox, retention, notifications, ingest schedule; hourly files; source switch in the header; dictionaries id/en |
| 5 | Configuration writer and install: collector YAML per platform and chosen data (file logs, journald, Windows Event Log, Docker, Kubernetes), `otlphttp` exporter with a disk queue and retries; `install.sh` (systemd), `install.ps1` (Windows service), Helm values |
| 6 | Admin › Collectors page (after the mockup): list, status counts, add dialog with platform tabs and the install command, details, replace / revoke key |
| 7 | End-to-end check with a real `otelcol-contrib`: lines reach Raw Logs and the pages; data queued while the link is down arrives later; a revoked key is refused |
| 8 | Deploy and docs: receiver subdomain, new `.env` settings, user guide, status, changelog |
| 9 | Part 2: `POST /v1/metrics`, time-series tables in DuckDB (minute → hour roll-up, retention) |
| 10 | Part 2: Servers and Kubernetes pages, z-score anomalies |

## 5. Safety

- One key per collector, stored as a hash, revocable; enrollment tokens work once and expire.
- Size limits before and after decompression (no zip bombs), a rate limit per collector, names validated like the Kafka
  consumer's, no path built from unchecked input.
- The receiver only writes inbox files; ingest keeps the database lock as today.
- Logs go from the client's server to MoniShield only (no third party on the way).

## 6. Known limits

- A retried batch whose answer was lost can be written twice; rare, accepted for now.
- Metrics (part 2) need their own storage and pages; they do not touch the log parsers.
