# 09 — Project status and next steps

Snapshot of **2026-10-08**, written so that the work can continue on another machine (for example with Claude Code
on a local computer). Update this file whenever an item below changes. The stage-by-stage history is in
[`04-plan.md`](04-plan.md); how the code is arranged is in [`08-architecture.md`](08-architecture.md).

## Where things stand

| Area | State |
|---|---|
| Repository | `apisdsn/MoniShield` (public). Branches `dev` → `stg` → `prd`; `prd` is the default branch. |
| Version | 2.0.0 + the *Unreleased* changes in `CHANGELOG.md` |
| Code | Clean architecture (domain / application / infrastructure / interfaces), enforced by `tests/test_architecture.py` |
| Language | Code, comments, docs, commit messages, server messages, API values, CLI output: English. UI: Indonesian and English. |
| Tests | pytest: 366 passed, 62 skipped (the skipped ones need the old repo's `build_dashboard.py`, `dashboard.html` or real log folders). Web: build, `tools/cek_i18n.mjs`, `tests/test_format.mjs`. |
| CI | `.github/workflows/ci.yml` green on `dev`. `stg` and `prd` still point to the commit before the deploy job. |
| Deploy | Automatic deploy of `prd` built and tested with a stub; **not yet run against the real server** (see next steps). |
| Server today | Still runs from the old checkout `/srv/dashboard-logging/v2` (compose project `monishield`). The first automatic deploy moves it to `/srv/MoniShield`, reusing the same containers and volumes. |

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

1. **First automatic deploy.**
   - In the GitHub environment `production`: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`,
     `DEPLOY_PORT` are set (2026-10-08). Add `DEPLOY_MIGRATE_FROM` = `/srv/dashboard-logging/v2` and check that
     `DEPLOY_PROFILES` = `https,kafka`.
   - From your own computer: `ssh -i ~/monishield-deploy deploy@SERVER_IP 'id && docker ps'` must work without a password.
   - Promote: pull request `dev` → `stg` (open as #1 at the time of writing), merge with **Create a merge commit**;
     then `stg` → `prd`. The merge into `prd` deploys. Follow [`07-deploy-vps.md`](07-deploy-vps.md) §13.
   - After `==> deployed …: app is healthy`: open the site, then delete `DEPLOY_MIGRATE_FROM`.
2. **Delete the `master` branch** in the GitHub UI (Branches page). Deleting it from a cloud session was refused by
   the git proxy.
3. **Rancher → Kafka for ingress-nginx**: ask a cluster owner to grant the `clusterloggings` permission, or to create
   the cluster-level Kafka output, so that nginx lines (needed for the map and attack detection) arrive.
4. **Let's Encrypt on the real domain**: checked with Caddy's local certificates only; the first deploy with the
   `https` profile is the real check ([`07-deploy-vps.md`](07-deploy-vps.md) §6–7).
5. After the server runs from `/srv/MoniShield`: the old checkout `/srv/dashboard-logging/v2` can be removed and the
   old repo archived (the old repo's `build_dashboard.py`, `dashboard_template.html` and log folders are never edited).

## Known issues

- `tools/uji_browser.cjs`: two checks fail and did so before the recent changes ("14 IP" count, Tab focus order).
- The S3 sync skips dates that already have a Kafka folder, so a Kafka folder that misses some services (for example
  ingress-nginx before step 3 above) is not completed from S3. Offered as an option, not requested yet.
- Credentials entered on the Configuration page are stored in `.env` in plain text (encrypting them was tried and
  rolled back at the owner's request): protect the file permissions (the app writes it as group 10001, mode 660).
- Encrypted API bodies need WebCrypto, which browsers only offer on HTTPS or `localhost`; over plain `http://` to a LAN
  address the web UI falls back to plain JSON. URLs (paths, query strings) and the live map stream stay unencrypted.
- With retention on, DuckDB reuses the space of removed folders for new data; the database file itself does not shrink.
- `00-reference.json` keeps the old system's Indonesian key names on purpose: they are a data contract with
  `tools/kesetaraan.py` and the old build (TRD K9).

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
