# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/id/1.1.0/); versions follow [SemVer](https://semver.org/lang/id/).
Starting with this repo, every commit uses [Conventional Commits](https://www.conventionalcommits.org/id/v1.0.0/)
(see `CONTRIBUTING.md`), so the *Unreleased* section can be assembled from the commit history.

## [Unreleased]

### Added
- Automatic deployment: a push to `prd` that passes CI is deployed to the server over SSH
  (`deploy/remote-deploy.sh`, `docs/07-deploy-vps.md` §13); the first run can migrate the old checkout.
- Kafka folders are labelled "(Kafka)" in the folder picker, page title and folder management.
- `docs/09-status.md` (state, owner requests, next steps), `docs/README.md` (document index) and `CLAUDE.md`
  (working rules for Claude Code) for continuing the work on another machine.
- `docs/10-user-guide.md`: the detailed usage, command line, Kafka and S3 sections formerly in the README.
- Encrypted request and response bodies between the web UI and the API (ECDH P-256 + AES-256-GCM per page load,
  `S4_API_ENCRYPTION`); Swagger, the ingest job and curl keep plain JSON.
- Data retention: `S4_RETENTION_DAYS` (database) and `S4_RETENTION_INBOX_DAYS` (inbox files), cleaned daily and from
  Configuration → Data retention.
- Forgot password by email: a unique temporary password (letters, digits, special characters) valid 30 minutes,
  the old password keeps working until it is used; users get an email address (Manage users).
- One MoniShield email letter with the logo for every email (password reset, OTP code, notifications, test email),
  and a Mail server (SMTP) section on the Configuration page with a test email.
- Users change their own email (user menu → Account email) with their password and a code sent to the old and to the
  new address; the old address gets a notice.
- The sign-in page always shows a *Forgot password?* button; without a mail server it explains that an admin resets
  the password.
- *Change password* and *Account email* open as pop-ups over the current page instead of separate pages.
- Verification codes are entered in six digit boxes (`lib/OtpInput.svelte`; paste and the phone's code suggestion work),
  each with the address it was sent to.
- Notification thresholds per number (`S4_ALERT_SPIKE`) and per service (`S4_ALERT_SERVICE_SPIKE`), editable under
  Configuration → Notifications; the Command Center uses the same per-service thresholds.

### Changed
- The repo stands alone: the contents of the `v2/` folder of the `apisdsn/dashboard-logging` repo were moved to `apisdsn/MoniShield` together with
  their commit history. The default log folder is now `logs/` in the project folder (formerly the parent folder of `v2/`).
- Branches: `dev` (development) → `stg` (testing/staging) → `prd` (production); rules in `CONTRIBUTING.md`.
- Code comments, documentation, commit messages, server error messages, API responses and CLI output are now in English;
  API status values are English (old values in existing databases are migrated on start). The web UI remains bilingual.
- Document file names are English: `00-reference.json`, `00-inventory.md`, `04-plan.md`, `04a-measurements.md`,
  `04b-page-checklist.md`, `04c-crs-detection.md`; the plan gained stages 26–31 and the TRD shows the current folder layout.
- `README.md` rewritten in the layout of Best-README-Template.
- Deploy settings `DEPLOY_DIR`, `DEPLOY_PROFILES`, `DEPLOY_MIGRATE_FROM` may be GitHub environment variables or secrets.

## [2.0.0] — 2026-10-07

Replacement for the old static HTML dashboard (`build_dashboard.py` → `dashboard.html`): FastAPI + DuckDB on the server, Svelte in the
browser, role-based accounts (admin/user), two languages (ID/EN), light/dark theme, usable on phones. Its key numbers are tested
to match the old system. Design: `docs/` (PRD, DRD, TRD, plan `04-plan.md`).

### Additions at the owner's request

Summarized from the plan notes (`docs/04-plan.md`, stages 12a–25 and deviation lines 25 (a)–(s)).

**Accounts, security, and database**
- Login sessions use **JWT**; accounts, sessions, audit, and import history are in **PostgreSQL via an ORM (SQLAlchemy)**
  (SQLite only for tests/local use).
- Attack detection based on the **OWASP Core Rule Set (CRS)** + **CAPEC** categories, with an adjustable paranoia level;
  the old rules remain available for comparison.
- **Swagger / OpenAPI** at `/api/docs` is protected by the same login as the dashboard.

**UI**
- The visual style follows the owner's reference images (color tokens for both themes, icons, cards, chips, tables).
- Application name **MoniShield**; the same shield logo on the login page, navigation, Swagger, and tab icon; every mention of
  "SIMPeL4" in the UI and configuration removed (package name `simpel4` → `monishield`, database `monishield.duckdb`).
- Login page with a large shield as the background; the "show password" button removed.
- **The left navigation can be collapsed** into an icon rail.
- A new, clearer **date picker** (calendar).
- All text from the server is translated as well in **English** mode.
- **Command Center** (full-width map + summary): changes vs the previous folder, hourly charts, new attention
  items, comparison with the **average of the previous 7 folders** (can be switched to "previous folder").
- **IP profile** + IP list download (CSV), CRS rule descriptions, **global search** (Ctrl+K), data completeness and an
  **hour × date heatmap** in Trends, **daily PDF summary** (1 A4 page).
- **Flow animation on the map**: particles move from the source location to the destination IP (server), with a ripple on arrival, and
  gradient lines show the direction; pause button; respects the "reduce motion" setting.

**Incoming data**
- **Sync data** button in the page header: detects new log folders, checks S3 first, then ingests.
- **Import from S3** with a bucket allowlist; `.log.gz` is extracted automatically.
- **Automatic S3 sync**: just enter the parent folder (e.g. `s3://simpel4-backup/k8s-logs`), and new date folders are downloaded
  and ingested periodically on their own.
- **Upload log folders from the browser**.
- **Manage log folders**: delete folders from the dashboard and restore them again.
- A specific warning when a file from S3 contains an error message from the export tool instead of logs.
- **Logs from Kafka** (Rancher cluster logging → Kafka): messages are rewritten into the same folders as the S3 logs and then
  ingested periodically (results tested identical to S3); status card + **"Check messages in topic"**; **realtime map** with
  a LIVE badge (only location coordinates are sent to the browser, not IP addresses).

**Notifications and settings**
- **Telegram / Discord / email notifications** (spikes, critical attacks, failed ingest, S3 sync problems, log folder
  not arrived yet, daily summary); messages without IP addresses.
- **Ready-to-use block list** (nginx `deny`, ingress-nginx, text) with exclusion of your own network.
- **Configuration** page (admin): AWS S3, automatic S3 folders, Kafka, MaxMind, notifications, block list, and the status of
  keys that are `.env`-only — with a **Test connection** button.
- **All configuration in `.env`**: the Configuration page writes directly to the `.env` file (takes effect immediately without a
  restart); all download source URLs, the Telegram API, and limits that used to be hard-coded are now `.env` variables.

**Deploy**
- **Docker Compose**: app + PostgreSQL, optional profiles pgAdmin (accounts/audit) and **DbGate** (DuckDB log data via a
  read-only copy), `kafka` (Apache Kafka broker for Rancher logs), `https` (Caddy + **automatic Let's Encrypt certificates**),
  `proxy` (your own certificate).
- Guide for **deploying to a new VPS until it can be opened via a domain**: `docs/07-deploy-vps.md`.
- Documents on architecture, mechanisms, usage, and data flow (separate artifact).

### Known issues / not yet done
- Kafka not yet tested against a real Rancher cluster; Let's Encrypt certificates only tested with Caddy's local certificates.
- Credentials entered via the UI are stored in `.env` without additional encryption (protect the file permissions and the server).
