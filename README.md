# MoniShield — log & security dashboard

Log and security dashboard: FastAPI + DuckDB on the server, Svelte in the browser. The full design is in `docs/`
(PRD, DRD, TRD, plan). Formerly the `v2/` folder of the `dashboard-logging` repo; since 2026-10-07 it stands alone in this repo
(commit history moved along). Summary of all additions made at the owner's request: `CHANGELOG.md`. Commit and
branch rules (`dev` → `stg` → `prd`): `CONTRIBUTING.md`.

## How to run

### 1. Prerequisites

| Tool | Version | For |
|---|---|---|
| Python | 3.12 or newer | server (FastAPI + DuckDB) |
| Node.js + npm | 20.19 or newer (tested with 22) | building the UI (Svelte/Vite); not needed while the server runs |
| Log folder | `YYYY-MM-DD/<namespace>/<service>/…` | data; default: `logs/` in the project folder (e.g. `logs/2026-10-06/`), or S3 / Kafka / upload from the browser |

### 2. Prepare the configuration

```sh
git clone https://github.com/apisdsn/MoniShield.git && cd MoniShield
cp .env.example .env && chmod 600 .env
```

Minimum contents of `.env`:

| Variable | Value |
|---|---|
| `S4_JWT_SECRET` | random secret ≥ 32 characters, e.g. the output of `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `S4_ADMIN_PASSWORD` | first admin password (≥ 12 characters); must be changed at first sign-in |
| `S4_COOKIE_SECURE` | `true` on an HTTPS server; **`false` only for trying it out on your own computer** over `http://` |
| `S4_LOG_DIR` | log folder, if not `logs/` in the project folder |
| `MAXMIND_ACCOUNT_ID`, `MAXMIND_LICENSE_KEY` | optional: IP locations on the map (GeoLite2, free; can also be set on the **Configuration** page). Without them, or with `S4_OFFLINE=true`, the map still works without new locations |

Other options (port, S3 import, attack detection rules, PostgreSQL for accounts) are explained in `.env.example`.

### 3. Run

Short way (installs `.venv` if missing, builds the UI if its sources changed, then starts the server):

```sh
./run.sh
```

Manual way, step by step:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .                    # add ".[s3,kafka]" for S3 import + Kafka logs, ".[test,s3,kafka]" for tests
(cd web && npm ci && npm run build)           # output in web/dist, served by the same server
.venv/bin/python -m monishield ingest            # optional: initial ingest (the server also ingests on start, S4_INGEST_ON_START)
.venv/bin/python -m monishield serve             # http://127.0.0.1:8000 (S4_BIND)
```

Open `http://127.0.0.1:8000`, sign in as `admin` with `S4_ADMIN_PASSWORD`, then change the password.
The first ingest of 11 folders takes ±10–40 seconds; after that only new or changed folders are processed.

### 3b. Or with Docker (server)

```sh
cp .env.example .env && chmod 600 .env        # fill in DOCKER_LOG_DIR, POSTGRES_PASSWORD, S4_JWT_SECRET, S4_ADMIN_PASSWORD, S4_JOB_TOKEN
sudo chgrp 10001 .env && chmod 660 .env       # the container (uid/gid 10001) may write .env from the Configuration page
docker compose build && docker compose up -d  # app + PostgreSQL, http://127.0.0.1:8000
docker compose run --rm ingest                # one-off ingest (for a daily cron)
docker compose --profile pgadmin up -d        # optional: pgAdmin  http://127.0.0.1:5050 (accounts, sessions, audit)
docker compose --profile dbgate up -d         # optional: DbGate   http://127.0.0.1:5051 (DuckDB log data + PostgreSQL)
```

Details (DuckDB decision, cron, security, internet addresses contacted, backups): `docs/06-docker.md`.

**New VPS + domain (automatic Let's Encrypt HTTPS)**: follow `docs/07-deploy-vps.md` step by step
(`docker compose --profile https up -d`).

### 4. Day-to-day use

**New log folder?** Copy the folder (`YYYY-MM-DD/…`) into the log folder, then an admin just presses the **Sync data** button
(folder icon in the page header). The number badge on that button shows how many new folders have not been loaded yet; after
the sync the dashboard switches to the newest folder. Only new or changed files are processed.

**New folders in S3 are fetched automatically**: **Ingest & import** → *Automatic sync from S3* → enter the parent folder, e.g.
`s3://nama-bucket/k8s-logs` → **Save & enable**. The first check runs a few seconds later, then at every
chosen interval (default 1 hour); new date folders are downloaded and ingested. The **Sync data** button in the page
header also checks S3 first, then the local log folder. (Alternative without the UI: `S4_S3_WATCH` in `.env`.)

**Configuration (all credentials on one page)**: user menu → **Configuration**. Contains the AWS S3 access keys + region,
the automatic S3 parent folder, the MaxMind GeoLite2 key, notifications, and block list exclusions; each section has
**Save** and (for AWS/MaxMind) **Test connection**. **Save writes directly to the `.env` file** (existing lines are replaced,
comments are kept) and takes effect immediately without a restart; **Remove from .env** disables the line (default value).
All URLs/addresses of external services and limits that used to be hard-coded are also in `.env` (section 10 of `.env.example`:
`S4_URL_*`, `S4_TELEGRAM_API`, `S4_*_MAX_AGE_DAYS`, …). The server must be allowed to write `.env`. Credentials are never shown again
(the Access Key ID is only shown masked, `AKIA…1234`). Settings that remain `.env`-only (the basis of server security: `S4_JWT_SECRET`,
`S4_JOB_TOKEN`, the account database, `S4_ADMIN_PASSWORD`, `S4_IMPORT_BUCKETS`) only have their status shown.

**Notifications**: user menu → **Configuration** → *Notifications* section → tick Telegram / Discord / Email, fill in the credentials (bot token + chat ID,
webhook URL, or SMTP server), **Save**, then **Send test**. Sent on: spikes (≥ 2× the average of 7 comparable folders),
critical attacks, failed ingest, S3 sync problems, today's log folder not arrived yet (the hour can be set), and — if
ticked — a summary of every new folder. Messages contain only numbers and links, **no IP addresses**; credentials are never
shown again after saving.

**Comparison**: the Command Center compares the numbers with the **average of the previous 7** complete folders (can be switched to
"Previous folder"); if there are not yet 3 complete folders, it automatically uses the previous folder.

**Flow animation on the map**: particles move from the source location to the server point (destination IP), with a ripple on arrival; the
more requests, the more frequent the particles. The ❚❚/▶ button in the map corner pauses it (remembered per browser; paused by default when
the system asks for reduced motion). For realtime later (Kafka): each event only needs to be sent to the page as a
`monishield:map-pulse` `{lat, lon, n}` event (see `web/src/lib/mapFlow.js`).

**Block list**: Security → **Block list…** → nginx format (`deny`), ingress-nginx (`denylist-source-range`), or
text; range 1/7/30 folders; minimum severity → **Download** / **Copy**. Private IPs, your own network
(`S4_BLOCKLIST_EXCLUDE_ORG`, default OMBUDSMAN), and `S4_BLOCKLIST_EXCLUDE` are never included. Review it before applying.

**API documentation (Swagger)**: user menu → **API documentation**, or open `/api/docs`. Sign in with the same account
as on the login page (not signed in → redirected to login and back); "Try it out" uses that session and is still subject to
the role. Raw schema: `/api/openapi.json`.

**Upload from your computer**: **Ingest & import** → **Upload log folder** → **Choose folder…** (a `YYYY-MM-DD` folder, its parent,
or the contents of one date + fill in its date) → **Upload**. Only `.log`/`.log.gz` are sent (same size limits as
S3 import); the files go to the inbox and are then ingested. Behind nginx, raise `client_max_body_size` (nginx default 1 MB).

**Removing a folder from the list**: admin → **Ingest & import** → **Log folders** card → **Delete**. The folder's data disappears from
the dashboard; files from S3 import (inbox) can be deleted as well. Files in the main log folder are never deleted: the folder
is marked *Ignored* so the sync does not load it again, and it can be brought back with **Restore** + Sync.


| Command (`.venv/bin/python -m monishield …`) | Function |
|---|---|
| `status` | effective configuration (without secrets), database contents, latest folder |
| `ingest [--folder 2026-10-06] [--force] [--offline]` | load new/changed log folders; also available from the **Ingest & import** page (admin) |
| `derive --all` | recompute aggregates without re-reading the logs (e.g. after updating the detection rules) |
| `user list`, `user create` | manage accounts from the command line |
| `refdata [--offline]` | update IP owner & location data and map files |
| `import [--dry-run] s3://…/YYYY-MM-DD/` | import a log folder from S3 (see the Import from S3 section) |
| `forget YYYY-MM-DD` | delete one folder's data from the database |

Data lives in `data/` (`monishield.duckdb`, map files) and `auth.db` in `S4_STATE_DIR`: **back up `auth.db`**
(accounts, sessions, audit); `monishield.duckdb` can be rebuilt from the log folder. The server uses a single process: do not
run two `serve` or `ingest` processes at the same time on the same database (DuckDB locks its file).

### 5. Developing the UI

```sh
.venv/bin/python -m monishield serve             # terminal 1: API on :8000
cd web && npm run dev                         # terminal 2: Vite on :5173, /api requests are forwarded to :8000
```

## Tests

```sh
.venv/bin/pip install -e ".[test,s3,kafka]"
.venv/bin/pytest -q                       # includes tests/test_import.py (local fake S3, no AWS)
```

Side-by-side browser tests against the old dashboard are in `tools/uji_*.cjs` (Playwright; see the header of each file).

## Logs from Kafka (Rancher, realtime)

Rancher (Cluster → Tools → Logging → **Kafka**) sends one message per container log line:

```json
{"log": "36.81.72.112 - - [05/Oct/2026:09:27:37 +0000] \"GET /mat-view …\" 200 …", "stream": "stdout",
 "kubernetes": {"namespace_name": "ingress-nginx", "container_name": "nginx-ingress-controller", "pod_name": "nginx-ingress-controller-v4v2g"},
 "time": 1791383741, "tag": "…", "docker": {"container_id": "…"}}
```

Its content is **just as complete** as the S3 logs: `log` = one line of the log file, and the namespace/service/pod that in S3 are in the
folder/file names are taken from `kubernetes.*`. MoniShield rewrites the messages into the **same** folder layout as the S3
export (`<date>/<namespace>/<service>/log_<service>_<pod>_<date>-00-00.log` in the inbox), then ingests every
`S4_KAFKA_INGEST_MINUTES` (default 5) — all pages work right away. Tested: the same lines via S3 and via Kafka
produce identical files and identical database contents (`tests/test_kafka.py`). Folder D contains the logs of
(D-1 00.00, D 00.00] WIB like the S3 export, so today's logs go into the folder dated tomorrow. nginx-ingress lines are also
sent to the map (**LIVE** badge): a dot moves on every new request — only the location coordinates are sent to the
browser, not the IP address.

**Setting up in Rancher**: Endpoint Type **Broker** (not Zookeeper), Endpoint `host:9092`, Topic e.g. `k8s-logs`,
**Flush Interval 5–10 seconds** (60 = the map lags by 1 minute), **Enable JSON Parsing NOT ticked** (if ticked,
the JSON line is split into columns and the original line is lost), SASL if the broker uses it (Plain/Scram).
No Kafka yet: `docker compose --profile kafka up -d` (see `docs/06-docker.md`).

**Setting up in MoniShield**: the **Configuration → Kafka** page (broker, topic, SASL; written to `.env`, the consumer is
restarted immediately), or `.env`: `S4_KAFKA_BROKERS`, `S4_KAFKA_TOPIC`, … (section 8a of `.env.example`).

**Checking the result**:
- The **Ingest & import → Logs from Kafka** page: connected/error status, messages received / written / skipped (+ reasons and
  examples of unreadable messages), counts per service, last ingest, last 50 messages.
- The **Check messages in topic** button: fetches the 10 LATEST messages directly from Kafka (without moving the read position) and
  shows the target file of each message — the fastest way to confirm the Rancher format is readable.
- From the command line on the Kafka server (without MoniShield):
  ```sh
  kafka-console-consumer.sh --bootstrap-server HOST:9092 --topic k8s-logs --max-messages 5            # 5 new messages
  kafka-console-consumer.sh --bootstrap-server HOST:9092 --topic k8s-logs --from-beginning --max-messages 5
  kafka-consumer-groups.sh --bootstrap-server HOST:9092 --describe --group monishield                 # LAG = not read yet
  # Docker kafka profile: docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic k8s-logs --max-messages 5
  ```
- After ingest: the new date folder appears in the folder picker just like S3 folders.

Note: offsets are committed after the lines are written to disk (at-least-once) — if the server dies in between, some lines
may be recorded twice. Folders already filled by Kafka are not fetched again by the S3 sync; do not import S3 manually
for the same date.

## Import from S3

An admin (the **Ingest & import** page) or an external system with a machine token sends a prefix link, e.g.
`s3://nama-bucket/k8s-logs/2026-09-26/`. The server checks the link against the allowlist, lists the objects,
downloads the log files to the inbox (`S4_INBOX_DIR`, default `data/inbox/`), then runs the ingest for that folder.
Sending the same link again does not re-download objects whose size and ETag are unchanged.

**Enabling** (in the server's `.env`, then restart):

```sh
pip install -e ".[s3]"                                        # boto3
S4_IMPORT_BUCKETS={"nama-bucket": ["k8s-logs/"]}              # allowlist bucket -> prefixes; {} = import off
S4_IMPORT_REGION=ap-southeast-3                               # Jakarta
AWS_ACCESS_KEY_ID=…                                           # read-only access key
AWS_SECRET_ACCESS_KEY=…
```

The allowlist is the **only** barrier between the import page and other buckets that key can read;
it can only be changed in the server configuration, not from the UI. Default limits: 500 objects, 1 GB per object,
5 GB per import, 30 minutes (`S4_IMPORT_MAX_*`, `S4_IMPORT_TIMEOUT_MINUTES`).

**Automatic sync without a link** (owner request 2026-10-07): enter the parent folder on the page (see Day-to-day use), or in `.env` and then restart the server:

```sh
S4_S3_WATCH=s3://nama-bucket/k8s-logs/      # must be within S4_IMPORT_BUCKETS; comma for more than one
S4_S3_WATCH_MINUTES=60                         # 0 = only the "Check S3 now" button / cron
S4_S3_WATCH_DAYS=30                            # only folders from the last 30 days (0 = the whole history)
S4_S3_WATCH_MAX_FOLDERS=3                      # max. new folders per check, newest first
```

Each check: list the `YYYY-MM-DD` folders directly under the prefix (ListObjectsV2 + Delimiter, folder contents are not
listed) → folders not yet in the dashboard, the log folder, the inbox, or the *Ignored* list are imported + ingested
one by one (recorded in the Import history) → recently synced folders (`S4_S3_WATCH_RECHECK_DAYS`) are re-checked
and only new/changed objects are downloaded. Folders deleted by an admin are marked *Ignored* so they are not downloaded
again (bring them back with **Restore**). From cron: `curl -X POST -H "Authorization: Bearer $S4_JOB_TOKEN"
-H "X-Requested-With: job" https://<server>/api/admin/import/sync`.

Do a dry run first without downloading anything (proves the object layout matches the local log folder):

```sh
python -m monishield import --dry-run s3://nama-bucket/k8s-logs/2026-09-26/
```

From an external system (automated, unattended):

```sh
curl -H "Authorization: Bearer $S4_JOB_TOKEN" -H "X-Requested-With: job" -H "Content-Type: application/json" \
     -d '{"url": "s3://nama-bucket/k8s-logs/2026-09-26/"}' https://<server>/api/admin/import      # 202 + job_id
curl -H "Authorization: Bearer $S4_JOB_TOKEN" https://<server>/api/admin/import/<job_id>           # status
```

Credentials are never sent to the browser and never appear in API responses, logs, the database, or the audit log.
An admin can paste temporary credentials on the import page (e.g. while the server key is being replaced); the
pasted credentials are only kept in process memory and are gone when the server restarts. Rotating keys: change `.env`,
restart `app`.

**Security advice.** The key currently in use is read-only but can see every bucket in the Jakarta region.
Create a dashboard-specific IAM user that can only read the log prefix, and use its key on the server:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DaftarAwalanLog",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::nama-bucket",
      "Condition": { "StringLike": { "s3:prefix": ["k8s-logs/*"] } }
    },
    {
      "Sid": "BacaObjekLog",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::nama-bucket/k8s-logs/*"
    }
  ]
}
```

The dashboard only uses those two operations (ListObjectsV2 and GetObject); there is no code that writes,
deletes, or lists buckets. Before relying on this feature, make sure the server can reach S3:
`curl -sI https://s3.ap-southeast-3.amazonaws.com`.
