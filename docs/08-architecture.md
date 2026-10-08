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
| `maxmind` | MaxMind probe | `infrastructure/refdata.probe_maxmind` |
| `mailer` | Mailer | `infrastructure/mailer.Mailer` (letters from `domain/letters.py`, rendered by `infrastructure/letter.py`) |
| `ingest`, `imports`, `alerts`, `kafka`, `retention`, `resets`, `emails` | services | `application/*_service.py` (`resets` = `password_service.PasswordResets`, `emails` = `account_service.EmailChanges`) |
| `wire` | (interfaces only) | `infrastructure/wirecrypto.WireCrypto`, used by the `interfaces/api/wire.py` middleware for encrypted API bodies |

Tests build the same graph through `create_app(cfg)`; a service can also be tested with a hand-made `ctx` holding fakes
(see `tests/test_kafka.py`, which drives `KafkaFeed` without a broker).

## Read side

Page endpoints are read-only reports over the aggregate tables. They skip the application layer on purpose (light CQRS):
`interfaces/api/pages.py` checks the role and parameters, then calls a plain function in
`infrastructure/queries/<page>.py` with a DuckDB cursor. Downloads (block list, attack-IP CSV) return
`dict(file, media_type, filename)` and the router turns that into an attachment response.

## Errors

Domain and application code raise `monishield.domain.errors.Fail(code, message, status)` (or a subclass:
`ImportFail`, `KafkaFail`, `AuthError`, `SettingsFail`, `AlertFail`, `Busy`). `app.py` has one exception handler that
turns any `Fail` into the API error shape `{"error": {"code", "message"}}` with the given HTTP status. HTTP-only checks
(CSRF, session, request size) stay in `interfaces/api/common.py` as `ApiError`.

Messages are English; the web UI translates by error **code** in Indonesian mode (`web/src/i18n/id.json`, `err.*`) and
translates informational server text (warnings, job summaries, audit details) with `web/src/srv.js`.

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
  domain/          accounts.py alerts.py config_model.py detect.py errors.py kafka_message.py letters.py parse.py retention.py rules.py
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
