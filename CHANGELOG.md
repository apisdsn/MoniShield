# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/id/1.1.0/); versions follow [SemVer](https://semver.org/lang/id/).
Starting with this repo, every commit uses [Conventional Commits](https://www.conventionalcommits.org/id/v1.0.0/)
(see `CONTRIBUTING.md`), so the *Unreleased* section can be assembled from the commit history.

## [Unreleased]

### Changed
- No client data in the code: the service folder names of each log role (`S4_SERVICE_NAMES`), the events tag (`S4_EVENT_TAG`), the
  Business endpoints (`S4_BUSINESS_ENDPOINTS`), hosts, server IP, upstream prefix, DNS upstream and own network
  (`S4_BLOCKLIST_EXCLUDE_ORG`, also tags "Own network" in IP cells) come from `.env`; the defaults name nothing real. The home page
  "Source code" link is `S4_SOURCE_URL`, the preview shows the address being visited, the deploy clones the repository CI runs in,
  and extra Caddy sites live in `deploy/sites/*.caddy` on the server. `/api/meta` sends `roles` and `own_org`; the Security
  finding for failed logins from the own network is `own_network_login_ips` and the Tracing reason is `no_events_service`.
- Tests, fixtures, `.env.example`, `config.example.toml` and the docs use example names, `example.com` and synthetic IPs; the
  old-system comparison tools and tests (`tools/kesetaraan.py`, `tools/acuan_lama.py`, `tests/test_equivalence.py`,
  `docs/00-reference.json`) are removed, so no test is skipped for missing old files.
- Indonesian names in the code are English: variables, functions and test names, the tools (`tools/measure.py`,
  `simulate_year.py`, `check_commit.sh`, `check_i18n.mjs`, `check_contrast.mjs`, `fetch_crs.py`, `check_docker.cjs`),
  `tests/fake_s3.py`, i18n keys (`file.*`, `imp.ph.*`, `ingest.failed`, `biz.*`), the IP CSV columns, the business metric keys
  (`reports_created`, `otp_verified`, …; stored keys are rewritten once when the database opens) and `S4_ATTACK_RULES=legacy`
  (`lama` still accepted). The sidebar now names a failed last ingest instead of showing a raw dictionary key.

### Security
- HSTS on the `https` profile includes subdomains (`max-age=31536000; includeSubDomains`, no `preload`); the extra sites in
  `deploy/sites/*.caddy` use the same header. Every subdomain must then work over https; `docs/07-deploy-vps.md` explains
  the `max-age=0` way back.
- Encrypted API bodies: the comments, `.env.example` and the user guide now state the real scope. They keep JSON bodies out
  of the network panel and passive proxy/CDN logs only; an active man in the middle can swap the unauthenticated keys or
  downgrade to plain JSON, the tab and the server see plain data, URLs/headers/cookies/non-JSON responses are not
  encrypted, and plain requests are still served (not an access control). Algorithm and wire format unchanged.
- MapLibre GL 5.24 -> 6.16 (GHSA-jrc7-96c5-q579, XSS sanitizer bypass); the import follows the named exports of 6.x and the
  map worker file is bundled and set with `setWorkerUrl` (6.x loads it separately); the browser smoke test (software
  WebGL) fails when the home page map does not draw or logs a console error.
- Public map: the live pulses only cover cells already shown, so a cell under the minimum never appears through its animation.
- Behind the proxy the client IP is the LAST `X-Forwarded-For` address (the one the proxy added), so the login limits per IP
  cannot be dodged with a forged header; `?next=` of the sign-in page also refuses `/\…`.

### Maintenance
- Unused code removed: the `SplitBar` component, 31 dictionary entries no screen uses, dead Python helpers
  (`detect.capec_name`, `rules.geo_scan`, `rules.DBIP_URL`, `rules.NGX_ERR_TS`, `alerts.DEFAULT`, two in `tools/kesetaraan.py`),
  unused imports and re-exports (callers now import from the domain module), and the 12 old browser scripts `tools/uji_*.cjs`
  plus `tools/server_uji_impor.py` that still used the removed `/#/` addresses (replaced by the smoke test). `pyflakes` is clean.
- CI opens every page in a real browser (both sources, both languages) before a deploy: `tools/smoke_server.py` +
  `tools/smoke_browser.cjs`, job *Browser smoke test*.
- GitHub Actions use `actions/checkout`, `setup-python` and `setup-node` v6 (Node 24; Node 20 actions are deprecated).
- `dev` carries the portfolio site on Caddy that was merged straight into `prd` (PR #10).

### Performance
- Home page: the map library loads only when the map section comes near the screen, and the map refreshes every 5 s only
  while it can be seen; before that the page asks for the map once.
- Ingest is about 18× faster on a 59 MB folder (207 s → 11.6 s) and finishes a 237 MB folder in 27 s (it did not finish in 29
  minutes). The profile showed that parsing was 1% of the time: the derive steps spent it adding rows one at a time with
  `executemany` (2-4 ms per row) and in a quadratic account analysis. Rows are now inserted in one statement (`db.insert_rows`,
  about 0.01 ms per row) and `rules.accounts` parses each time once and finds its windows by bisection. The aggregates are
  identical (47 tables, 92,000 rows compared old against new). New IP owner/location rows use the same fast insert.
- The ingest result, the status API (`last.timings`) and `monishield ingest` report the seconds per derive step, so a slow
  ingest shows where the time went.

### Fixed
- Home page map: when the newest folder has no located requests yet (empty, still arriving), the map uses the newest
  of the last 7 folders that has them instead of staying empty; with no traffic at all it shows sample dots marked
  "Sample data".
- Email: a message the mail server received but did not confirm (connection closed after the message) is shown as
  "not confirmed" instead of "failed" and is no longer sent again an hour later (that made duplicate daily reports); the
  wait for the server is 60 s instead of 15 s and a timeout is named as such; email-change and reset codes are not
  cancelled in that case.
- The open folder list (and every select list) is readable in both themes: Chrome/Edge on Windows drew it white under
  light text in the dark theme; option colours now come from the theme, and the browser smoke test checks their contrast.
- Deploy: the script makes the deploy user the owner of `.env` (group 10001, mode 660), so a `.env` replaced as root no
  longer stops the deploy with `open .env: permission denied`.
- The volume band (total log lines, HTTP requests of the whole folder) is no longer shown on a service or IP page, where it
  read as contradicting that page's own numbers; its labels now name the scope (all services, nginx-ingress).
- The daily report went out only right after an S3 ingest and only when *Daily summary* was ticked, so it often never
  arrived. It now goes out every day from the report hour (default 08:00 WIB) for the newest complete folder (Kafka when there
  is no S3 data), once per folder; a report that failed on every channel is tried again an hour later.
- The sign-in page has its own address, `/login?next=<page>`, instead of showing under `/overview`; after signing in the
  app returns to the page that was asked for. Swagger sends signed-out visitors to `/login?next=/api/docs`.
- Changes are compared with the day the previous folder's logs cover ("vs 7 Oct", was "vs 8 Oct" on the 8 Oct page); a 5xx
  rate below 5 % is no longer red; the Overview summary heading is no longer capitalised word by word ("Summary of").
- The date picker no longer shows a second rounded focus ring inside its pill, and the sidebar's service search (and the
  links in the folding sidebar groups) no longer have their focus ring cut off on the left.

### Changed
- Email layout: every email links the logo from the dashboard (notifications attached it, and the mail relay turned the
  attachment into a broken box; the codes already linked it), with a mark drawn in HTML when the dashboard has no https
  address; the daily report status is a coloured banner, numbers are a label/value table with the change as a small tag, and "Needs a look"
  items are numbered badges.
- Home page navbar: the apisdsn.com link, the divider and the arrow after "Source code" are gone.
- Home page dashboard preview: the sidebar shows the same icons as the real sidebar instead of empty squares, and its
  Configuration group; the chart grows to the sidebar height.
- Every analysis page opens with a volume band (owner choice "Volume B"): the day's total log lines and HTTP requests in large
  numbers, each with the last 7 days as small bars, plus files, services and the 4xx/5xx rates. It replaces Overview's compact
  number row; `/api/meta` now gives the HTTP requests per folder.
- The *Daily summary* notification is now a daily report (owner template 2026-10-28): status line (🟢 / 🟡 / 🔴), the main
  numbers against the 7-day average, what needs a look, the ingest result (files, lines, seconds, completeness, Kafka side) and
  the system (backup, S3 sync, Kafka); a short version when all is clear. Emoji and bold section titles on Telegram (now sent as
  HTML) and Discord; the email letter drops the emoji and shows each part as a heading with a list. Indonesian and English.
- Colour palette C "Grafit netral" (owner choice from five mockups): neutral graphite backgrounds with cards a few steps
  lighter, teal brand used sparingly, and red/amber/green kept for status only: chart series use teal, blue, violet, pink,
  grey and other non-status hues, in both the dark and the light theme. All pairs pass `tools/check_contrast.mjs`.
- New look (mockup approved 2026-10-27): the header is one row (source, date, search, Sync, avatar menu that now holds
  language, theme and reload); the date is shown once, in the picker, with the log period in its tooltip. Overview opens
  with a status card (*Critical* / *Needs a look* / *All clear* with up to three reasons and links), four large numbers, the
  other numbers in one row and a *Services to check* card. A zero is never red or yellow, the "not compared" note appears
  once per page, and the sidebar's service list has a search box. On phones the header has a
  second row for source and date (they no longer overlap) and KPIs are a one-column list.
- S3 and Kafka are two data sources, each with its own database and its own folders (`<inbox>/kafka/<date>/`,
  `<data>/kafka/monishield.duckdb`): a day is never a mix of both. The header has a source switch (`S3 | Kafka`, also
  `?source=kafka` in the address and in the API); the date list, every page, Trends, search, downloads and the admin folder
  tools follow the source being shown. The S3 import no longer touches Kafka's files and the Kafka consumer no longer yields
  to S3. `monishield ingest --source kafka` ingests the Kafka source.
- Notifications come from both sources: the title names the source (`(S3)` / `(Kafka)`), the link opens that source, and a
  Kafka notification never silences the S3 one for the same day. Summaries, the "folder not arrived" check and the S3 sync
  warning stay S3-only.
- On the first start of this version the old shared layout is moved: Kafka-only folders and the Kafka files that sat beside an
  S3 copy go to the Kafka inbox, `<inbox>/.kafka-superseded/<date>/` joins the Kafka folder of that date, and the S3 database
  forgets the days that were Kafka's alone. Nothing is deleted; for days the S3 copy had already replaced, the Kafka source
  only has the services that S3 does not carry.
- The folder picker, page title and folder list mark the data source being shown: `(S3)` or `(Kafka)`.
- One date per folder everywhere: the folder picker, page title, Trends, IP profile, Command Center, sync and upload
  messages, retention plan and notifications show the day the logs cover (folder `21 Oct` = logs of `20 Oct`), for S3 and
  Kafka folders alike. The old second "· log …" date, taken from the earliest line in the data, is gone. Folder names are
  unchanged in addresses, API and on disk.

### Added
- Home page link preview (WhatsApp, LinkedIn, Telegram, X): the server writes the title, description and a 1200 × 630
  image (`og-id.png`, `og-en.png`, built by `tools/og_image.cjs`) into the page, in Indonesian or English; the language
  follows `?lang=` when given, else the language the client asks for, else Indonesian.
- Home page dashboard preview with tabs: Overview, Security and Command Center, all with sample data (documentation IP
  ranges, example.com).
- The web UI follows the browser's language on a first visit (no saved choice); `?lang=en|id` in the address wins.
- `robots.txt`: search engines may index the public home page, not the sign-in page, the dashboard pages or the API;
  checked by the browser smoke test.
- Public home page at `/`: what MoniShield is, a dashboard preview with sample data, the traffic map, the architecture,
  privacy points and *Sign in*; bilingual, dark/light, phone menu. The app itself stays at `/overview`, sign-in at `/login`.
- Public traffic map (`GET /api/public/map`, no sign-in): request origins in ~55 km cells, cells under 3 requests left out,
  no IP addresses; live (last minute of the Kafka feed) or the newest folder. Shared snapshot every 3 s. On/off under
  Configuration → Home page (`S4_PUBLIC_MAP`, on by default). The sign-in page links back to the home page.
- Configuration → Notifications: *Daily report hour (WIB)* (`S4_ALERT_SUMMARY_HOUR`), and *Send a daily report* to send the
  report of any folder now (again if it already went out) or every report of the latest 7 folders not sent yet
  (`POST /api/admin/alerts/report`). *Daily summary* is on by default for new installations.
- Daily backup at 02:00 WIB (`S4_BACKUP_HOUR`): both DuckDB databases (S3 and Kafka sources) and every account table in
  `<data>/backup/<date>/`, with a SHA-256 manifest, private files, the newest 7 kept (`S4_BACKUP_KEEP`) and an optional copy to
  object storage (`S4_BACKUP_S3`). Ingest & import has a *Backup* card (next run, last result, stored backups, *Back up now*);
  a failed backup is notified (new event *Backup failed*). `monishield backup` and `monishield restore <folder>` (server stopped)
  on the command line.
- Sidebar group *Configuration* (admins): Object storage, Kafka broker, GeoIP (MaxMind), Mail server, Notifications,
  Block list, Data retention and Server keys open as pop-ups; the Configuration page and its user-menu item are gone.
- Sidebar groups (Analysis, Services, Configuration) fold open and closed with an animation, remembered per browser.
- Object storage providers: Amazon S3, Cloudflare R2, MinIO, Wasabi, Google Cloud Storage (HMAC), DigitalOcean Spaces,
  other S3-compatible services and Azure Blob Storage (`S4_STORAGE_PROVIDER`, `S4_STORAGE_ENDPOINT`,
  `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_KEY`; `azure` extra in the Docker image).
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
  centred, each with the address it was sent to.
- Notification thresholds per number (`S4_ALERT_SPIKE`) and per service (`S4_ALERT_SERVICE_SPIKE`), editable under
  Configuration → Notifications; the Command Center uses the same per-service thresholds.

### Changed
- Web addresses are plain English paths without `#`: `/command-center`, `/trends`, `/security`, `/root-causes`,
  `/availability`, `/pods`, `/business`, `/tracing`, `/services/<name>`, `/ips/<ip>`, `/admin/users`, `?module=`,
  `?search=`; the server answers them with the web app; notifications link to these paths. Addresses with `#` are no
  longer supported (they open the Overview).
- REST-style English API paths: `/api/admin/imports…`, `/api/admin/uploads…`, `GET /api/admin/ingest`,
  `DELETE /api/admin/folders/{folder}`, `/command-center`, `/root-causes`, `/api/me/email/change…`,
  `/api/admin/users/{id}/email/change`. The old paths are removed (docs/03-trd.md §5).
- `python -m monishield sync`: checks the automatic sync folder now through the running server (for scripts; the server
  already checks by itself, so no cron job is needed).
- Manage users no longer sets a new email directly: the admin confirms with their own password, a code goes to the new
  address (valid 24 hours) and a notice to the current one, and the address counts once the user enters the code
  (banner + Account email). An admin's own email changes only under Account email; removing an email stays direct.
- With Kafka streaming on, the automatic S3 sync now fetches and ingests the S3 folder of a date Kafka has filled (it
  was skipped as "already known"): the S3 files replace Kafka's files of the same services, so lines are not counted
  twice; the folder Kafka is still writing is left alone.
- `S4_IMPORT_REGION` has no default any more and is free text (any region name without spaces); set it for AWS buckets
  outside `us-east-1`.
- Every placeholder in the UI uses `example.com` / `example` values.
- Failures of an outside service (mail server, S3, Kafka, MaxMind) are answered with HTTP 424 instead of 502/504:
  Cloudflare replaced those answers with its own error page, so the screen showed only "502".
- The email logo is loaded from `S4_DASHBOARD_URL/mail-logo.png` when the dashboard has a public https address, instead
  of an attached image that relays such as SumoPod break (empty box plus "One attachment").
- Choosing SMTP security moves the standard port along (465 / 587), and a port/security mismatch is named in the error.
- Saving a section of the Configuration page only checks that section: an invalid value elsewhere (for example an AWS
  key from the process environment) no longer blocks saving the mail server, retention or other sections.
- The page title in the header no longer breaks into one word per line on medium screens (around 1280 px, English):
  the header tools move to a second line instead.
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
  "the old name" in the UI and configuration removed (package name `legacy` → `monishield`, database `monishield.duckdb`).
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
- **Automatic S3 sync**: just enter the parent folder (e.g. `s3://example-log-bucket/k8s-logs`), and new date folders are downloaded
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
