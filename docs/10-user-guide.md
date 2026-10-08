# 10 — User guide

How to use MoniShield once it runs: loading logs, the admin screens, the command line, Kafka and S3. Installation is
in the [README](../README.md); server deployment in [`07-deploy-vps.md`](07-deploy-vps.md).

- [Day-to-day use](#day-to-day-use)
- [Command line](#command-line)
- [Logs from Kafka (Rancher, real time)](#logs-from-kafka-rancher-real-time)
- [Import from S3](#import-from-s3)
- [Encrypted API traffic](#encrypted-api-traffic)
- [Developing the UI](#developing-the-ui)
- [Tests](#tests)

## Day-to-day use

### New log folders

Copy the folder (`YYYY-MM-DD/…`) into the log folder, then an admin just presses the **Sync data** button
(folder icon in the page header). The number badge on that button shows how many new folders have not been loaded yet; after
the sync the dashboard switches to the newest folder. Only new or changed files are processed.

### Automatic S3 sync

**Ingest & import** → *Automatic sync from S3* → enter the parent folder, e.g.
`s3://nama-bucket/k8s-logs` → **Save & enable**. The first check runs a few seconds later, then at every
chosen interval (default 1 hour); new date folders are downloaded and ingested. The **Sync data** button in the page
header also checks S3 first, then the local log folder. (Alternative without the UI: `S4_S3_WATCH` in `.env`.)

### Configuration

User menu → **Configuration**. Contains the AWS S3 access keys + region,
the automatic S3 parent folder, the MaxMind GeoLite2 key, notifications, and block list exclusions; each section has
**Save** and (for AWS/MaxMind) **Test connection**. **Save writes directly to the `.env` file** (existing lines are replaced,
comments are kept) and takes effect immediately without a restart; **Remove from .env** disables the line (default value).
All URLs/addresses of external services and limits that used to be hard-coded are also in `.env` (section 10 of `.env.example`:
`S4_URL_*`, `S4_TELEGRAM_API`, `S4_*_MAX_AGE_DAYS`, …). The server must be allowed to write `.env`. Credentials are never shown again
(the Access Key ID is only shown masked, `AKIA…1234`). Settings that remain `.env`-only (the basis of server security: `S4_JWT_SECRET`,
`S4_JOB_TOKEN`, the account database, `S4_ADMIN_PASSWORD`, `S4_IMPORT_BUCKETS`) only have their status shown.

### Notifications

User menu → **Configuration** → *Notifications* section → tick Telegram / Discord / Email, fill in the credentials (bot token + chat ID,
webhook URL, or SMTP server), **Save**, then **Send test**. Sent on: spikes (≥ 2× the average of 7 comparable folders),
critical attacks, failed ingest, S3 sync problems, today's log folder not arrived yet (the hour can be set), and — if
ticked — a summary of every new folder. Messages contain only numbers and links, **no IP addresses**; credentials are never
shown again after saving.

### Mail server and email letters

Configuration → *Mail server (SMTP)*: server, port, security (STARTTLS 587, SSL/TLS 465, or none for an internal relay),
account, password and sender address (`MoniShield <monishield@example.go.id>`). **Send test email** sends a letter to the
address you enter (default: your own account's email). The same server sends the notification emails and the
forgot-password emails. Every email uses one MoniShield letter: logo, title, text, an optional code box (temporary
password, OTP code), an optional list and button, in Indonesian or English; there is also a plain-text part.
`.env`: `S4_SMTP_HOST`, `S4_SMTP_PORT`, `S4_SMTP_SECURITY`, `S4_SMTP_USERNAME`, `SMTP_PASSWORD`, `S4_SMTP_FROM`.

- **Port and security go together**: 465 with SSL/TLS, 587 with STARTTLS. Choosing the security mode moves a standard
  port along; a mismatch is reported as such when sending.
- **Sender domain**: the domain of the sender address must be the one verified at the mail provider (SPF/DKIM records).
  With an unverified domain, providers such as SumoPod (kirim.email) send from their own address
  (`…@…sumosender.com`) and put your account email in *Reply-To*. If the provider verified `monishield.example.go.id`,
  the sender is `MoniShield <noreply@monishield.example.go.id>`, not `…@example.go.id`.
- **Logo**: with `S4_DASHBOARD_URL` set to the public `https://` address, the logo is loaded from
  `<address>/mail-logo.png` (public, no data). Without it the logo is attached to the email; some relays rewrite
  messages and break such attached images.

### Forgot password

The sign-in page always shows *Forgot password?*. Until the mail server is set up (or with `S4_PASSWORD_RESET=false`)
it explains that an admin resets the password and where the admin enables email resets. Otherwise the user enters a
username or email; the account's email receives a temporary password of 16 characters (upper and lower case letters,
digits, special characters), valid 30 minutes (`S4_PASSWORD_RESET_MINUTES`) and usable once. Signing in with it asks for
a new password straight away.

- The page gives the same answer whether or not the account exists or has an email.
- The old password keeps working until the temporary one is used, and any sign-in cancels a pending temporary password,
  so nobody can lock a user out by asking for resets. At most one per account per minute and 5 requests per address
  per 15 minutes.
- Users need an email address: admin → Manage users → add or edit a user. One address per account.
- The audit log records each request (`password.forgot`) and its use (`password.reset_used`), never the password.

### Account email

Every user can change their own email under user menu (⋯) → *Account email*; like *Change password*, it opens as a
pop-up over the current page. It needs the mail server.

1. Enter the new email and your current password, then *Send verification codes*.
2. A 6-digit code goes to the old email (skipped when the account has none yet) and another to the new email.
3. Enter both codes. The email changes and the old address gets a notice.

Codes are valid 10 minutes; after 5 wrong codes the request ends and you start again. Changing the email also cancels a
pending temporary password. A hijacked session alone cannot change the email: it needs the password and access to the
old mailbox. Admins can still set any user's email in Manage users.

### Spike thresholds

Configuration → Notifications → *Spike thresholds*. A number is a spike when it is at least *factor × the average of
the 7 folders before it* AND rose by at least the *minimum increase*. Untick a row to stop reporting it.

- **Numbers** (5xx responses, errors of all services, upstream errors, attack requests, attack IPs, IPs with failed
  logins): one threshold each. `.env`: `S4_ALERT_SPIKE=n5xx=3:50,errors=off` (only the changed ones).
- **Errors per service**: each service is compared with its own average. *All other services* is the default
  (2× and +50); add a row for a busy service that needs a higher threshold, or untick it to mute it.
  `.env`: `S4_ALERT_SERVICE_SPIKE=default=2:50,om-be-report=3:200,coredns=off`. The Command Center's "service errors
  rose" item uses the same thresholds. A notification lists at most 5 services, largest increase first.

### Data retention

Configuration → *Data retention*, 0 = keep forever:

- **Remove from the database after N days** (`S4_RETENTION_DAYS`, at least 8 because each folder is compared with
  the 7 before it). Files in the main log folder are not touched; ingest, the Sync data badge and the S3 sync skip
  folders past the cut-off, so they do not come back. To bring them back, raise or clear the setting and press Sync data.
- **Delete inbox files after N days** (`S4_RETENTION_INBOX_DAYS`, at least 2): S3 imports, uploads and Kafka folders.
  For Kafka and uploaded folders the inbox is the only copy of the log files; their data stays in the dashboard until
  the database setting removes it.

The cleanup runs once a day (first run 5 minutes after the server starts). The card shows what the next run removes;
**Run now** asks for a confirmation, then removes it at once. Each run is in the audit log (`retention.run`).
DuckDB reuses the freed space for new data; the database file does not shrink.

### Comparison with earlier folders

The Command Center compares the numbers with the **average of the previous 7** complete folders (can be switched to
"Previous folder"); if there are not yet 3 complete folders, it automatically uses the previous folder.

### Flow animation on the map

Particles move from the source location to the server point (destination IP), with a ripple on arrival; the
more requests, the more frequent the particles. The ❚❚/▶ button in the map corner pauses it (remembered per browser; paused by default when
the system asks for reduced motion). With Kafka, every new nginx-ingress request also sends one pulse to the page as a
`monishield:map-pulse` `{lat, lon, n}` event (see `web/src/lib/mapFlow.js`), shown with the **LIVE** badge.

### Block list

Security → **Block list…** → nginx format (`deny`), ingress-nginx (`denylist-source-range`), or
text; range 1/7/30 folders; minimum severity → **Download** / **Copy**. Private IPs, your own network
(`S4_BLOCKLIST_EXCLUDE_ORG`, default OMBUDSMAN), and `S4_BLOCKLIST_EXCLUDE` are never included. Review it before applying.

### API documentation (Swagger)

User menu → **API documentation**, or open `/api/docs`. Sign in with the same account
as on the login page (not signed in → redirected to login and back); "Try it out" uses that session and is still subject to
the role. Raw schema: `/api/openapi.json`.

### Upload from your computer

**Ingest & import** → **Upload log folder** → **Choose folder…** (a `YYYY-MM-DD` folder, its parent,
or the contents of one date + fill in its date) → **Upload**. Only `.log`/`.log.gz` are sent (same size limits as
S3 import); the files go to the inbox and are then ingested. Behind nginx, raise `client_max_body_size` (nginx default 1 MB).

### Removing a folder from the list

Admin → **Ingest & import** → **Log folders** card → **Delete**. The folder's data disappears from
the dashboard; files from S3 import (inbox) can be deleted as well. Files in the main log folder are never deleted: the folder
is marked *Ignored* so the sync does not load it again, and it can be brought back with **Restore** + Sync.

## Command line

| Command (`.venv/bin/python -m monishield …`) | Function |
|---|---|
| `status` | effective configuration (without secrets), database contents, latest folder |
| `ingest [--folder 2026-10-06] [--force] [--offline]` | load new/changed log folders; also available from the **Ingest & import** page (admin) |
| `derive --all` | recompute aggregates without re-reading the logs (e.g. after updating the detection rules) |
| `user list`, `user create` | manage accounts from the command line |
| `refdata [--offline]` | update IP owner & location data and map files |
| `import [--dry-run] s3://…/YYYY-MM-DD/` | import a log folder from S3 (see [Import from S3](#import-from-s3)) |
| `forget YYYY-MM-DD` | delete one folder's data from the database |

Data lives in `data/` (`monishield.duckdb`, map files). Accounts, sessions and the audit log live in PostgreSQL
(`S4_AUTH_DATABASE_URL`, back it up with `pg_dump`) or, without PostgreSQL, in `auth.db` in `S4_STATE_DIR` (back it up); `monishield.duckdb` can be rebuilt from the log folder. The server uses a single process: do not
run two `serve` or `ingest` processes at the same time on the same database (DuckDB locks its file).

## Logs from Kafka (Rancher, real time)

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

**Automatic sync without a link**: enter the parent folder on the page (see [Automatic S3 sync](#automatic-s3-sync)), or in `.env` and then restart the server:

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
      "Sid": "ListLogPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::nama-bucket",
      "Condition": { "StringLike": { "s3:prefix": ["k8s-logs/*"] } }
    },
    {
      "Sid": "ReadLogObjects",
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

## Encrypted API traffic

On top of HTTPS, the web UI encrypts the bodies of its API calls, so they are unreadable in the browser's network panel,
in proxy or CDN logs and to TLS-intercepting middleboxes:

1. When a page loads, the browser and the server exchange ephemeral ECDH P-256 keys (`POST /api/crypto/handshake`) and
   both derive the same AES-256-GCM key (HKDF-SHA256). The browser's key cannot be exported from the tab.
2. Every JSON request body and response is `nonce + ciphertext`, bound to the method and path, marked with the header
   `X-MS-Enc`. A body cannot be replayed on another endpoint.
3. After a server restart the old keys are gone; the page agrees on a new key and repeats the request by itself.

Cost: about 0.1 ms per page load for the key exchange and about 0.1 ms per 200 KB response.

Not encrypted: requests without `X-MS-Enc` (Swagger, the cron job, curl, other systems with the job token), file
downloads (CSV, block list), log file uploads, the live map stream (coordinates only), and URLs. The key lives in the
browser tab, so a signed-in user can always read their own traffic; HTTPS remains the protection in transit.
Browsers only offer WebCrypto over HTTPS or `localhost`: over plain `http://` to a LAN address the UI falls back to
plain JSON. Turn it off with `S4_API_ENCRYPTION=false`.

## Developing the UI

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
