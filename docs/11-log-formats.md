# Plan — configurable log formats (stage 1 of "any log")

Status: approved by the owner 2026-10-29 (public sample formats; rules in a file **and** on the Configuration page).
Step 1a is built (rules model, file, validation, built-in rules); 1b–1e follow.

## 1. Goal

Today MoniShield reads five log formats, fixed in `monishield/domain/parse.py`: ingress-nginx (access + error), CoreDNS,
an nginx-style frontend access log, JSON events `[TAG-LEVEL] {...}`, and Spring Boot. Service *names* are already
configuration (`S4_SERVICE_NAMES`), but a service whose log has another format is read as Spring Boot and its numbers are
wrong. Stage 1 lets each site describe **how every service logs**, so a site with 7–10 services in different formats
works without code changes.

Not in stage 1: configurable Business metrics and optional pages (stage 2); an HTTP endpoint for Vector / Fluent Bit and a
configurable folder layout (stage 3).

## 2. How it works

1. **One rules file**, `log-formats.toml` (path `S4_LOG_FORMATS_FILE`, default `<state dir>/log-formats.toml`; the
   Configuration page edits the same file). Without the file, MoniShield builds the rules of today from the site profile,
   so nothing changes for existing sites.
2. **Matching.** Every service folder (S3 export, upload) or Kafka container is matched against the rules **from top to
   bottom; the first match wins**. `match` is a name or a glob (`web-*`, `*-worker`), optionally with a namespace
   (`shop/orders-*`). One rule can cover many services. The last rule is usually `match = "*"`.
3. **Format.** A rule names a built-in preset or describes the format:

   | `format` | Reads |
   |---|---|
   | `ingress-nginx` | ingress-nginx access + error log (today's parser) |
| `nginx-frontend` | today's frontend parser: nginx-style access log, client = first `X-Forwarded-For` entry |
   | `nginx-combined`, `apache-combined` | standard access logs, optional upstream time / request id at the end |
   | `json` | one JSON object per line (pino, winston, zap, logrus, Serilog, …); `fields` maps keys, dotted paths allowed |
   | `logfmt` | `key=value key="quoted value"` lines (Go, Heroku style) |
   | `spring-boot` | Spring Boot / Logback default pattern (today's parser, login and JasperReports rules as features) |
   | `events-json` | `[TAG-LEVEL] {...}` lines (today's events parser; `tag` setting) |
   | `syslog` | RFC 3164 / 5424 |
   | `coredns` | CoreDNS (today's parser) |
   | `regex` | a regular expression with named groups (`time`, `level`, `ip`, `method`, `path`, `status`, `duration_ms`, `request_id`, `user`, `message`) |
   | `auto` | tries the presets on the first 200 lines and keeps the one that reads the most |
   | `plain` | counts lines only; level guessed from words like ERROR / WARN |

4. **Kind.** `kind = "http"` (an access log) or `kind = "app"` (an application log). The kind decides which pages a
   service feeds: http → map, attack detection (OWASP CRS), endpoints, status codes, IPs; app → errors, levels, messages.
   An app log with method/path/status (JSON request logs) also feeds endpoints and status codes.
5. **Features** (optional, per rule): `logins` (failed-login and lockout lines for Security), `pdf` (JasperReports lines),
   `tracing` (its `request_id` is joined with the access log of the same requests). Today's site turns them on for the
   same services as now.
6. **Normal form.** Every line becomes the same columns (section 4), whatever the format, so the derive SQL and the pages
   do not care where a line came from.
7. **Visible quality.** Each file records how many lines did not match its format. The Pods / Trends completeness view
   and the service page show the rate; above 5 % the service gets a warning "format does not fit".

### Example: a site with 8 services

```toml
[[service]]
match  = "ingress-nginx*"
format = "ingress-nginx"
kind   = "http"

[[service]]
match  = "web-*"                      # web-shop, web-admin
format = "nginx-combined"
kind   = "http"

[[service]]
match  = "orders-api"
format = "json"
kind   = "app"
features = ["tracing"]
fields = { time = "ts", level = "severity", message = "msg", request_id = "trace_id",
           method = "req.method", path = "req.url", status = "res.status", duration_ms = "latency_ms", ip = "req.ip" }

[[service]]
match  = "payments"
format = "logfmt"
kind   = "app"

[[service]]
match  = "auth-service"
format = "spring-boot"
kind   = "app"
features = ["logins"]

[[service]]
match   = "legacy-erp"
format  = "regex"
pattern = '^\[(?P<time>[^\]]+)\] (?P<level>\w+) (?P<message>.*)$'
time_format = "%d/%m/%Y %H:%M:%S"     # strptime; time zone = S4_TIMEZONE_OFFSET unless the value carries one
multiline   = '^\['                   # a line that does not match starts no new entry (stack traces)
levels      = { SEVERE = "ERROR", WARNING = "WARN", FINE = "DEBUG" }

[[service]]
match  = "worker-*"
format = "auto"

[[service]]
match  = "*"
format = "plain"
```

## 3. Rule reference

| Key | Meaning |
|---|---|
| `match` | name or glob of the service folder; `namespace/name` to restrict the namespace |
| `format` | preset or `json` / `logfmt` / `regex` / `auto` / `plain` |
| `kind` | `http` or `app` (default from the preset) |
| `fields` | normal column → source key (`json`, `logfmt`); dotted paths for nested JSON |
| `pattern` | `regex` only; named groups as in section 2.3 |
| `time_format` | `iso` (default), `epoch`, `epoch_ms`, `clf` (`10/Oct/2026:13:55:36 +0000`), or a `strptime` pattern |
| `multiline` | regex that marks the first line of an entry; other lines are appended to the previous entry |
| `levels` | map of the site's level words to ERROR / WARN / INFO / DEBUG |
| `tag` | `events-json` only: the `[TAG-…]` prefix (today `S4_EVENT_TAG`) |
| `features` | `logins`, `pdf`, `tracing` |
| `ip_header` | `http` only: take the client from `X-Forwarded-For`-style field instead of the peer column |

Validation at start (like the other settings): unknown keys, unknown presets, a `regex` without `message` or `time`,
patterns longer than 2,000 characters or with nested quantifiers (`(a+)+`) are refused with the rule's position.

## 4. Data model

- Two new raw tables in DuckDB, filled by every non-legacy format:
  - `http_access` (file_id, line_no, folder, service, ts_utc, ip, method, path, path_key, status, bytes, duration_ms,
    upstream, request_id, ua, referer)
  - `app_line` (file_id, line_no, folder, service, ts_utc, level, logger, message, msg_key, request_id, method, path_key,
    status, duration_ms, user)
- The five current parsers keep writing their own tables (`nginx_access`, `fe_access`, `sl_event`, `spring_line`, …), so
  today's numbers stay exactly the same; the derive SQL adds a `UNION ALL` from the two new tables to the aggregates that
  are already per service (`agg_service`, `agg_hour`, `agg_status`, `agg_endpoint`, `agg_ip`, `agg_level`, `agg_message`, …).
- Attack detection (CRS) runs on `http_access` rows as well as on `nginx_access`; the map uses both.
- `ingest_file` gains `format_key` (hash of the rule that read the file) and `lines_unmatched`.

## 5. Ingest

- The rules are compiled once per run and passed to the parser workers with each file (like the site profile today).
- A file is parsed again when its rule changes (`format_key` differs), not when another service's rule changes.
- `auto` stores the preset it chose per service, so later files of the service do not guess again; the choice is shown
  on the Log formats page and can be pinned.
- Budget: the same folder may take at most 1.5× today's ingest time; JSON and regex lines are parsed in the worker
  processes, as now.

## 6. Screens and commands

- **Configuration → Log formats** (admin): the rules in order, the services each rule matched in the newest folder, the
  share of unread lines per service, edit and reorder, **Test**: paste up to 50 lines or pick a file, see the columns
  found per line and the lines that did not match. Saving writes `log-formats.toml` and asks to re-read the affected
  services. Mockup first, as usual.
- Service page: the format in use and the unread-line rate next to the file counts.
- CLI: `monishield formats list` (rules and matched services), `monishield formats test <file> --service <name>`.

## 7. The current site

`S4_SERVICE_NAMES`, `S4_EVENT_TAG` and the business endpoints keep working: without `log-formats.toml` they become the
rules of today (ingress-nginx, coredns, frontend `nginx-frontend`, events `events-json`, auth `spring-boot` + logins, report
`spring-boot` + pdf, everything else `spring-boot`). An admin can export them to a file from the Log formats page and
edit from there. No re-parse is needed after the upgrade.

## 8. Safety

- Only admins can change rules; the file is read like `.env` (no secrets in it).
- Regexes are checked for length and nested quantifiers, and each file is parsed in a worker process with a time limit,
  so a bad pattern cannot hang the server.
- Sample lines pasted into **Test** stay in memory, are never stored or logged, and never leave the server.

## 9. Delivery in steps (each one a commit on `dev`, tested)

| Step | Delivers |
|---|---|
| 1a | **Done.** Rules model + loader + validation (`domain/log_formats.py`, `config.log_format_rules`, `S4_LOG_FORMATS_FILE`, `log-formats.example.toml`), today's rules built from the site profile; tests |
| 1b | Presets `nginx-combined`, `apache-combined`, `json`, `logfmt`, `regex`, `plain`, `syslog`, multiline; `http_access` / `app_line`; tests with sample lines per preset |
| 1c | Derive and pages read the new tables; CRS detection and map on `http_access`; unread-line rate |
| 1d | `auto` detection; per-file `format_key` re-parse; CLI `formats list/test` |
| 1e | Configuration → Log formats page (after the mockup), docs, `.env.example`, user guide |

## 10. Questions for the owner

1. Is there a real second site or a set of sample logs (anonymised) to design and test against? The presets will be
   tested with public sample formats otherwise.
2. Rules in a file edited on the server **and** on the Configuration page (proposed), or the page only?
3. Which formats matter first besides JSON and nginx/apache (e.g. Laravel, Django, .NET, Windows Event Log, AWS ALB)?
