# 09 — Project status and next steps

Snapshot of **2026-10-08**, written so that the work can continue on another machine (for example with Claude Code
on a local computer). Update this file whenever an item below changes. The stage-by-stage history is in
[`04-plan.md`](04-plan.md); how the code is arranged is in [`08-architecture.md`](08-architecture.md).

## Where things stand

| Area | State |
|---|---|
| Repository | `apisdsn/MoniShield` (public since 2026-10-28, started from one clean commit). Branches `dev` → `stg` → `prd`; `dev` is the default branch. Daily work happens here. The history before the public release, which still holds the client's data, is the private archive `apisdsn/MoniShield-internal`: read it if needed, never push to it or copy its history here. |
| Version | 2.0.0 + the *Unreleased* changes in `CHANGELOG.md` |
| Code | Clean architecture (domain / application / infrastructure / interfaces), enforced by `tests/test_architecture.py` |
| Language | Code, comments, docs, commit messages, server messages, API values, CLI output: English. UI: Indonesian and English. |
| Tests | pytest: every test passes on the sample lines in `tests/fixtures/` (2 skip without optional services). Web: build, `tools/check_i18n.mjs`, `tests/test_format.mjs`. |
| CI | `.github/workflows/ci.yml`: commit messages, pytest, web build, browser smoke test (`tools/smoke_browser.cjs`, every page for both sources and languages); all four must pass before the deploy job on `prd`. |
| Deploy | Automatic deploy of `prd` from this repository, first run 2026-10-28 (`2e564e4`, app healthy). Secrets in the GitHub environment `production`. |
| Server today | `/srv/MoniShield`, a checkout of this repository (compose project `monishield`, profiles `https,kafka`). The site's own values are in its `.env`; the portfolio site is `deploy/sites/portfolio.caddy` there (not in git). |

## What the owner asked for, and where it is

In order of the requests. "Plan" = section of [`04-plan.md`](04-plan.md).

| # | Request | Result | Where |
|--:|---|---|---|
| 1 | Replace the static HTML dashboard with an application (ingest once a day, data per tab) | FastAPI + DuckDB + Svelte, stages 1–22 | PRD, DRD, TRD, plan |
| 2 | JWT sessions, PostgreSQL through an ORM | SQLAlchemy accounts, sessions, audit | plan stage 10 |
| 3 | Attack detection with OWASP CRS + CAPEC | `domain/detect.py`, paranoia levels | plan stage 21, [`04c-crs-detection.md`](04c-crs-detection.md) |
| 4 | Command Center, extra presentation (suggestions 1–9), Sync data button, MoniShield name and logo | | plan stages 22, 24, 25 |
| 5 | Import from S3, automatic S3 sync from a parent folder, folder upload from the browser, delete/restore folders | | plan deviations 25 (g), (h), (k), (l) |
| 6 | Swagger behind the same login; server text translated in English mode | `/api/docs` | plan deviation 25 (l) |
| 7 | Notifications (Telegram/Discord/email), 7-folder baseline, ready-made block list | | plan deviation 25 (n) |
| 8 | One Configuration page for all credentials, and all settings in `.env` | Configuration page writes `.env` | plan deviations 25 (o), (p) |
| 9 | Map flow animation towards the destination IP | `web/src/lib/mapFlow.js` | plan deviation 25 (q) |
| 10 | Logs from Rancher through Kafka, checkable like the existing logs | Consumer writes S3-style folders; LIVE map | plan deviation 25 (r), [`10-user-guide.md`](10-user-guide.md) |
| 11 | Docker Compose with pgAdmin and DbGate; a guide for a new VPS with a domain and automatic HTTPS | | [`06-docker.md`](06-docker.md), [`07-deploy-vps.md`](07-deploy-vps.md) |
| 12 | Own repository with dev/stg/prd branches and Conventional Commits | | plan stage 26, `CONTRIBUTING.md` |
| 13 | Clean architecture | | plan stage 27, [`08-architecture.md`](08-architecture.md) |
| 14 | English for commits, comments, docs, error messages, responses, CLI, GitHub Actions | | plan stage 28 |
| 15 | Kafka folders recognisable by name | "YYYY-MM-DD (Kafka)" | plan stage 29 |
| 16 | Rewrite the old commit history to English Conventional Commits, without `Co-Authored-By` | Done and force-pushed | plan stage 26 |
| 17 | GitHub Actions, then automatic deploy to the server without typing commands; remove `master` from the workflow | | plan stage 30, [`07-deploy-vps.md`](07-deploy-vps.md) §13 |
| 18 | A step-by-step release guide (which merge deploys, which merge button) | | [`07-deploy-vps.md`](07-deploy-vps.md) §13 |
| 19 | English documents including their titles, updated for local hand-over | This file, [`README.md`](README.md), `CLAUDE.md` | plan stage 31 |
| 20 | A README in the style of Best-README-Template | `README.md`; the detailed how-to moved to [`10-user-guide.md`](10-user-guide.md) | plan stage 31 |
| 21 | Encrypt the credentials in `.env` | Built, then **rolled back at the owner's request** before it was committed | — |
| 22 | Encrypt / obfuscate API responses and request payloads without loading the server | ECDH + AES-GCM bodies for the web UI | plan stage 32, [`10-user-guide.md`](10-user-guide.md) |
| 23 | Data retention (database, inbox) | Daily cleanup, Configuration → *Data retention* | plan stage 33 |
| 24 | Notification thresholds per service | Configuration → Notifications → *Spike thresholds* | plan stage 34 |
| 25 | Forgot password by email (unique temporary password), user emails, MoniShield letter for every email (also OTP), mail server settings | Sign-in page → *Forgot password?*; Manage users; Configuration → *Mail server (SMTP)* | plan stage 35, [`10-user-guide.md`](10-user-guide.md) |
| 26 | Users change their own email, verified through the old address | User menu → *Account email*; password + code to the old email + code to the new email | plan stage 36, [`10-user-guide.md`](10-user-guide.md) |
| 27 | Configuration in the sidebar as pop-ups, folding sidebar groups, object storage with a choice of providers (S3, R2, MinIO, Wasabi, GCS, Spaces, Azure), free-text region, `example.com` placeholders | Sidebar → *Configuration* | plan stage 37, [`10-user-guide.md`](10-user-guide.md) |
| 28 | Manage users must not change emails without a code (option B) | Admin enters a new address with own password; it counts once the user confirms the code; own email only via Account email | plan stage 38, [`10-user-guide.md`](10-user-guide.md) |
| 29 | English endpoints and web addresses, REST best practices, no `#` in web addresses | Renamed API paths (old ones removed), plain web paths served by the server, `monishield sync` command for scripts | [`03-trd.md`](03-trd.md) §5 |
| 30 | One date per folder: every screen and notification shows the day the logs cover (S3 and Kafka folders alike), not the folder name; a folder holds one source (S3 or Kafka), marked `(S3)` / `(Kafka)` | Folder picker, Trends, IP profile, Command Center, notifications; `logDay`/`fLabel` in `web/src/format.js` | [`10-user-guide.md`](10-user-guide.md) |
| 31 | S3 and Kafka are two separate data sources, each with its own database and folders; source switch in the header, `?source=` in the API, notifications from both | Header → *S3 \| Kafka*; `monishield ingest --source kafka` | [`10-user-guide.md`](10-user-guide.md) |
| 32 | Ingest 18× faster (59 MB folder 207 s → 11.6 s; 237 MB: 27 s); seconds per derive step reported | `monishield ingest`; status API `last.timings`; `db.insert_rows`, `rules.accounts` | plan stage 40 |
| 33 | Daily backup of both databases and the accounts, kept 7 days, optional copy to object storage, notified when it fails; restore command | Ingest & import → *Backup*; `monishield backup`, `monishield restore`; `S4_BACKUP_*` | plan stage 41, [`10-user-guide.md`](10-user-guide.md) |
| 34 | Redesign: one-row header, date shown once, Overview status card, neutral zeros, "not compared" once, service search in the sidebar, phone layout | Mockup artifact "Overview MoniShield — sebelum & sesudah" | plan stage 43 |
| 35 | Daily summary notification as a daily report (status, vs 7-day average, needs a look, ingest result, system), emoji on Telegram/Discord, no emoji in email, id/en | Configuration → Notifications → *Daily summary* | plan stage 46 |
| 36 | Total log lines and HTTP requests visible at once on every page (volume band with 7-day bars) | top of every analysis page | plan stage 47 |
| 37 | Daily report every day at a set hour, send the report of any older folder or every one not sent yet; sign-in page at `/login?next=…` | Configuration → Notifications; `/login` | plan stage 48 |
| 38 | Public home page at `/` (dashboard preview with sample data, traffic map without IPs, architecture, privacy, sign in) | `/`; Configuration → Home page | plan stage 49 |
| 39 | Home page: link preview card in ID/EN, dashboard preview with tabs (Overview, Security, Command Center), map loaded only near the screen, `robots.txt`; language from the browser on a first visit | `/`, `/?lang=en`; `monishield/interfaces/api/home_meta.py` | mockups "Saran 1" and "Saran 3" on the design canvas |
| 40 | No client data in the code: service names, event tag, business endpoints, hosts, server IP, upstream prefix, own network and the source link come from `.env`; tests, fixtures, examples and docs use example names, `example.com` and synthetic IPs; old-system comparison tools removed | `.env.example` §9, [`10-user-guide.md`](10-user-guide.md) *Site profile* | plan stage 50 |
| 41 | Every function, variable, file, i18n key and stored key in the code in English, following common naming practice | Renamed tools and tests; business metric keys migrated in place; `S4_ATTACK_RULES=legacy` | plan stage 50 |
| 42 | Real visitor IPs behind Cloudflare; WIB as configuration | `S4_TRUST_CLOUDFLARE`; `S4_TIMEZONE_OFFSET` / `S4_TIMEZONE_LABEL` ([`10-user-guide.md`](10-user-guide.md) *Time zone*) | plan stage 51 |
| 43 | Raw log lines of every service, searchable (all users for now; role per module later), no masking, audited | Raw Logs page in Analysis: text / regex / request ID / IP search over the folder's log files, follow a request across services, lines around an entry, `.log` download; `raw.search` / `raw.download` in the audit log | plan stage 53 |
| 44 | Scrolling pop-ups cut their own rounded corners | Dialog body scrolls, title and buttons stay | plan stage 53 |

Questions answered along the way, recorded so they are not asked again:

- **Real phone test** (plan stage 12): done by the owner on 2026-10-08, no problems found.
- **Several admins** share one configuration: there is one `.env` per server and only admins can change it through
  the Configuration page. Per-admin settings do not exist.
- **Viewing Kafka logs**: Ingest & import → *Logs from Kafka* (status, counts, last 50 messages, "Check messages in
  topic"); folders appear in the folder picker as "YYYY-MM-DD (Kafka)" after the next ingest (every 5 minutes).
- **Rancher nginx logs**: configured as cluster-level logging (Cluster → Tools → Logging → Kafka output, Endpoint
  Type Broker, JSON parsing off). It needs permission on `clusterloggings`: Cluster Owner, or Project Owner of the
  `System` project. A project-level logging config only sees the namespaces of that project.

## Next steps (in order)

0. **Before relying on forgot password in production**: fill in Configuration → Mail server (SMTP), send the test email,
   and give every user an email address in Manage users (or let users set their own under *Account email*). Users without an email still need an admin to reset them.
1. **Archive the internal repository**: in `apisdsn/MoniShield-internal`, delete the `production` environment secrets
   (or turn Actions off) so nothing deploys from it, and keep it private. `apisdsn/dashboard-logging` private too.
2. **Rancher → Kafka for ingress-nginx**: ask a cluster owner to grant the `clusterloggings` permission, or to create
   the cluster-level Kafka output, so that nginx lines (needed for the map and attack detection) arrive.
3. **Next release**: add `S4_TRUST_CLOUDFLARE=true` to the server's `.env` right before the release reaches `prd` (the
   running version refuses unknown keys), so the audit log and login limits see visitors instead of Cloudflare servers.
4. **Check `S4_IMPORT_REGION`** on the server: it no longer defaults to `ap-southeast-3`; set it in Configuration →
   Object storage if S3 requests should go straight to the bucket's region.
5. The old checkout `/srv/dashboard-logging/v2` on the server can be removed once nothing points to it.

6. **Configurable log formats** (stage 52, [`11-log-formats.md`](11-log-formats.md)): approved; step 1a (rules model,
   file, validation) and 1b (common formats read into `http_access` / `app_line`, unread lines counted) done; next 1c
   (derive and pages read the new tables, CRS detection and map on `http_access`, unread-line rate).

## Known issues

- Fixed 2026-10-12: the S3 sync used to skip dates that already had a Kafka folder. Now, once Kafka writes the next
  folder, the S3 copy of that date is fetched and replaces Kafka's files of the same services (services only Kafka has
  are kept); Kafka lines that arrive later for that date are dropped.
- Credentials entered on the Configuration page are stored in `.env` in plain text (encrypting them was tried and
  rolled back at the owner's request): protect the file permissions (the app writes it as group 10001, mode 660).
- HSTS includes subdomains: every subdomain of the served domains (also `apisdsn.com` through `deploy/sites/`) must work
  over https; a broken one is undone with `max-age=0` ([`07-deploy-vps.md`](07-deploy-vps.md) *HTTPS and HSTS*).
- Encrypted API bodies only keep JSON bodies out of the network panel and passive proxy/CDN logs: not a defence against
  an active man in the middle (unauthenticated handshake, downgrade to plain JSON), the tab or the server, and not an
  access control ([`10-user-guide.md`](10-user-guide.md) *Encrypted API traffic*).
- Encrypted API bodies need WebCrypto, which browsers only offer on HTTPS or `localhost`; over plain `http://` to a LAN
  address the web UI falls back to plain JSON. URLs (paths, query strings) and the live map stream stay unencrypted.
- With retention on, DuckDB reuses the space of removed folders for new data; the database file itself does not shrink.

## Continuing on a local machine

```sh
git clone https://github.com/apisdsn/MoniShield.git && cd MoniShield
git checkout dev
git config core.hooksPath .githooks              # rejects non-Conventional commit messages
cp .env.example .env && chmod 600 .env           # local values only; never commit .env
python3 -m venv .venv && .venv/bin/pip install -e ".[test,s3,kafka]"
(cd web && npm ci && npm run build)
.venv/bin/python -m pytest -q                    # expect only skips for old-system comparisons
.venv/bin/python -m monishield serve             # http://127.0.0.1:8000
```

With Claude Code, `CLAUDE.md` in the repository root is loaded automatically; it lists the working rules that were
agreed with the owner. Start a session by reading this file and asking for the next step from the list above.
