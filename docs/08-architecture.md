# 08 — Code architecture (clean architecture)

The Python package `monishield/` is split into four layers. Dependencies point **inward only**; the rule is enforced by
`tests/test_architecture.py`, so a violating import fails CI.

```
interfaces  ──►  application  ──►  domain
     │                ▲               ▲
     └──► infrastructure ─────────────┘   (implements the application ports)
```

| Layer | Folder | May import | Holds |
|---|---|---|---|
| domain | `monishield/domain/` | standard library, domain | Pure rules: log parsing, old-system rules, CRS detection, configuration model, account/password rules, S3 import and upload planning, Kafka message mapping, alert rules and texts, Configuration-page rules, domain errors |
| application | `monishield/application/` | standard library, domain, application | Use cases: ingest + folder management, S3 import and automatic sync, alerts, settings (`.env`), Kafka consumer, browser upload; ports (`ports.py`) |
| infrastructure | `monishield/infrastructure/` | everything except interfaces | Adapters: DuckDB warehouse + ingest + derive SQL, read-side queries per page, accounts (SQLAlchemy/JWT), S3 (boto3), Kafka (kafka-python), `.env` file, notification channels, reference data downloads, log files on disk |
| interfaces | `monishield/interfaces/` | everything | FastAPI routers, the composition root (`api/app.py`), the CLI |

The domain and application layers import **no third-party package** (no FastAPI, SQLAlchemy, DuckDB, boto3,
kafka-python). The only files the domain reads are its own bundled rule data (`crs_rules.json`, `capec.json`).

## Composition root and `ctx`

`monishield/interfaces/api/app.py` → `wire(state, cfg, env_path)` builds every adapter and service and stores them on
FastAPI's `app.state`. Application services receive that object as `ctx` and only use what `ports.py` documents:

| `ctx` attribute | Port | Adapter |
|---|---|---|
| `cfg` | configuration | `domain/config_model.Config` (loaded by `infrastructure/config.py`) |
| `auth` | AccountStore | `infrastructure/auth.Auth` |
| `warehouse` | Warehouse | `infrastructure/warehouse.DuckWarehouse` |
| `logfolders` | LogFolders | `infrastructure/logfolders.LogFolders` |
| `s3` | S3Gateway | `infrastructure/importer.S3Gateway` |
| `env` | EnvStore | `infrastructure/envfile.EnvStore` |
| `channels` | NotificationChannels | `infrastructure/notify_channels.Channels` |
| `kafka_client` | KafkaClient | `infrastructure/kafka_client.KafkaClient` |
| `inbox` | Inbox factory | `infrastructure/inbox.Spool` |
| `uploads` | UploadStore | `infrastructure/uploads.Uploads` |
| `metrics` | MetricsStore | `infrastructure/metrics_store.MetricsStore` (own file `metrics.duckdb`) |
| `maxmind` | MaxMind probe | `infrastructure/refdata.probe_maxmind` |
| `mailer` | Mailer | `infrastructure/mailer.Mailer` (letters from `domain/letters.py`, rendered by `infrastructure/letter.py`) |
| `ingest`, `imports`, `alerts`, `kafka`, `retention`, `resets`, `emails` | services | `application/*_service.py` (`resets` = `password_service.PasswordResets`, `emails` = `account_service.EmailChanges`) |
| `metrics_feed` | service | `application/metrics_feed.MetricsFeed` (receives collector metrics through the `metrics` port) |
| `wire` | (interfaces only) | `infrastructure/wirecrypto.WireCrypto`, used by the `interfaces/api/wire.py` middleware for encrypted API bodies |

Tests build the same graph through `create_app(cfg)`; a service can also be tested with a hand-made `ctx` holding fakes
(see `tests/test_kafka.py`, which drives `KafkaFeed` without a broker).

## Read side

Page endpoints are read-only reports over the aggregate tables. They skip the application layer on purpose (light CQRS):
`interfaces/api/pages.py` checks the role and parameters, then calls a plain function in
`infrastructure/queries/<page>.py` with a DuckDB cursor. A read whose parameters can hold personal data (search text, IP,
email, request ID, file name) also gets a POST form with the same parameters in the JSON body (`pages._params`); the web
UI uses only that form so the values travel in the encrypted body and never in a URL. Downloads (block list, attack-IP CSV) return
`dict(file, media_type, filename)` and the router turns that into an attachment response.

## Errors

Domain and application code raise `monishield.domain.errors.Fail(code, message, status)` (or a subclass:
`ImportFail`, `KafkaFail`, `AuthError`, `SettingsFail`, `AlertFail`, `Busy`). `app.py` has one exception handler that
turns any `Fail` into the API error shape `{"error": {"code", "message"}}` with the given HTTP status. HTTP-only checks
(CSRF, session, request size) stay in `interfaces/api/common.py` as `ApiError`.

Messages are English; the web UI translates by error **code** in Indonesian mode (`web/src/i18n/id.json`, `err.*`) and
translates informational server text (warnings, job summaries, audit details) with `web/src/srv.js`.

## UI text

Every text the user reads is in `web/src/i18n/id.json` and `en.json` (the same keys in both); the capitalisation follows one rule, checked by
`node tools/check_i18n.mjs` (the code is `tools/i18n_case.mjs`, tested by `tests/test_i18n_case.mjs`).

- **Labels are Title Case**: page titles, section and card headings, buttons, tabs, menu items, table column headers, field labels and
  badges ("Add Collector", "Open in Raw Logs", "Last Seen"). The small words `a an and as at by for from in into of on or over per than the to via vs with` stay lower case
  inside a title unless they come first ("Errors per Service", "Import from S3"). Both parts of a hyphenated word are capitalised
  ("Last Sign-In", "Comma-Separated"), and so is the particle of a phrasal verb ("Sign In", "Back Up Now"). Product names and acronyms keep their form (MoniShield, S3, Kafka, CPU, RAM, SMTP, IP, URL, HTTP, ID,
  EN, nginx, requestId); placeholders (`{n}`), numbers and units after a number (`24 h`) are left as they are.
- **Sentences are sentence case**: sentences, descriptions, hints, placeholders, empty states, errors, toasts and status lines ("No ingest since
  server start", "All times in WIB"). A short status line gets no period; a badge is a label ("1 Late", "All Online"). A full sentence ends with a
  period; a placeholder does not ("Search by name or host").
- **Indonesian** follows the same split ("Tambah Collector", "Buka di Log Mentah"); the small words are `di ke dari dan atau yang untuk per dengan`.
- The CSS never changes case (no `text-transform: capitalize`): the text is written the way it is shown.

How the check tells a label from a sentence, so that a new key needs no extra step:

1. A key is a **sentence** when one part of its name is (or ends with `_` and) `hint`, `text`, `note`, `intro`, `desc`, `ph` (placeholder), `err`,
   `msg`, `sub`, `toast`, `done`, `saved`, `cleared`, `why`, `help`, `tip`, `lead`, `body`, `cap`, `aria`, `count`, or it starts with `err.`.
2. Also a sentence or fragment: a text that ends with `. ? ! : …`, starts with a lower-case letter or a placeholder (`{n} offline`), has more
   than seven words, or holds `{msg}`, `{list}` or a quoted placeholder.
3. Everything else is a label and must be Title Case. Name a sentence key with one of the parts above, and the check stays quiet.
4. A sentence in a `hint`, `text`, `note`, `intro`, `desc`, `toast`, `done`, `saved`, `cleared`, `why`, `help`, `tip`, `lead` or `body` key
   (four words or more) must end with a period.
5. The few that the rules cannot tell are listed in `tools/i18n_sentence_keys.json`: `keys` are left alone, `sentences` are messages that
   must end with a period.

`node tools/check_i18n.mjs --fix` rewrites the findings (labels to Title Case, missing periods); read the diff before committing.

## Where new code goes

| You are adding… | Put it in |
|---|---|
| a rule, a calculation, validation of user input, message text of a rule | `domain/` (pure function, unit-testable without I/O) |
| a workflow that coordinates storage, network and other services | `application/<feature>_service.py`, talking to `ctx` ports |
| a new external system (database, API, broker, files) | `infrastructure/` adapter + a Protocol in `application/ports.py` + wiring in `app.wire()` |
| a new report page | `infrastructure/queries/<page>.py` + an endpoint in `interfaces/api/pages.py` |
| a new endpoint for a use case | a thin router in `interfaces/api/` that calls the service and writes the audit entry |

## Layer map of the modules

```
monishield/
  domain/          accounts.py alerts.py config_model.py detect.py errors.py kafka_message.py letters.py parse.py retention.py rules.py storage.py
                   s3_import.py settings.py uploads.py  (+ crs_rules.json, capec.json, CRS-LICENSE.txt)
  application/     ports.py ingest_service.py import_service.py alert_service.py settings_service.py
                   kafka_service.py password_service.py retention_service.py upload_service.py account_service.py
  infrastructure/  auth.py config.py db.py derive/ envfile.py importer.py inbox.py ingest.py kafka_client.py
                   logfiles.py logfolders.py notify_channels.py queries/ refdata.py schema.sql uploads.py warehouse.py
                   wirecrypto.py letter.py mailer.py assets/logo.png
  interfaces/      api/ (app.py common.py pages.py admin.py config_api.py kafka.py notify.py upload.py session.py
                   users.py meta.py docs.py wire.py)   cli.py
```

The CLI (`interfaces/cli.py`) is a second composition root for offline maintenance (ingest, derive, forget, import
without a running server); it calls infrastructure directly because it runs without the API process.
