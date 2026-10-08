# 06 — Running MoniShield with Docker

Step 7 (`migrate/07-docker-compose.md`), following TRD §7. Files: `Dockerfile`, `docker-compose.yml`,
`.dockerignore`, `.env.example`, `deploy/Caddyfile`, `deploy/pgadmin/servers.json`, `tools/uji_docker.cjs`.

## 1. Services

| Service | Always? | For | Why it exists |
|---|---|---|---|
| `app` | yes | API + UI (Svelte build output) + **in-process ingest** | core; the only process that opens DuckDB (§3) |
| `postgres` | yes | accounts, sessions, audit, S3 import history | TRD K11: account data must not be lost when `s4-data` is rebuilt, and `pg_dump` is needed |
| `ingest` | `job` profile, one-off | triggers ingest in `app` over HTTP, waits, then exits | entry point for cron (§4); no volumes, does not open DuckDB itself |
| `proxy` | `proxy` profile, optional | HTTPS (Caddy) | only if the server has no reverse proxy yet (TRD §7.1 ASSUMPTION T5); the dashboard requires HTTPS + login |
| `pgadmin` | `pgadmin` profile, optional | viewing PostgreSQL | owner request 2026-10-07 |
| `dbgate` | `dbgate` profile, optional | viewing **log data** (DuckDB) and PostgreSQL | owner request 2026-10-07: pgAdmin cannot open DuckDB |

Without `--profile`, `docker compose up -d` only starts `app` and `postgres`.

## 2. Running

Prerequisites: Docker Engine 26+ with Compose 2.30+ (tested with Engine 29.8, Compose 5.6). Those versions are needed for
`volume.subpath` in the `dbgate` service.

```sh
cd MoniShield
cp .env.example .env && chmod 600 .env       # contents: see the table below; .env goes into neither git nor the image
sudo chgrp 10001 .env && chmod 660 .env      # the container user (gid 10001) may read + write .env (Configuration page)
docker compose build                         # ±1–3 minutes the first time
docker compose up -d                         # app + postgres; wait for "healthy":
docker compose ps
```

| `.env` variable | Required | Value |
|---|---|---|
| `DOCKER_LOG_DIR` | yes | log folder on the **host**, e.g. `/srv/log` (mounted read-only at `/logs`) |
| `POSTGRES_PASSWORD` | yes | random, no need to remember it |
| `S4_JWT_SECRET` | yes | random ≥ 32 characters |
| `S4_ADMIN_PASSWORD` | yes | first admin password; must be changed at first sign-in |
| `S4_JOB_TOKEN` | yes for cron | machine token used by the `ingest` service |
| `S4_COOKIE_SECURE` | — | `true` (default) behind HTTPS; `false` only for trying it out via `http://127.0.0.1:8000` |
| `MAXMIND_ACCOUNT_ID`, `MAXMIND_LICENSE_KEY` | — | IP locations on the map (GeoLite2, free) |
| `PGADMIN_EMAIL`, `PGADMIN_PASSWORD` | if pgAdmin | pgAdmin login (the email is only a login name; `.local` is accepted) |
| `DBGATE_LOGIN`, `DBGATE_PASSWORD` | if DbGate | DbGate login; password ≥ 12 characters, otherwise DbGate refuses to start |

Then open `http://127.0.0.1:8000` (or the proxy domain), sign in as `admin` with `S4_ADMIN_PASSWORD`, change the password.
The server ingests all folders on start (`S4_INGEST_ON_START`, default `true`); the dashboard can already be opened meanwhile.

**Server without internet:** fill the cache volume from an existing copy of `.cache` (±190 MB) before `up`:

```sh
docker compose create                        # creates the volumes without starting anything
docker run --rm -v "$PWD/../.cache":/src:ro -v monishield_s4-cache:/cache --entrypoint sh monishield:2.0.0 -c 'cp -r /src/. /cache/'
```

**From another computer:** all ports are bound to the host's `127.0.0.1`. For the dashboard use the server's reverse proxy (or
`--profile proxy`). For pgAdmin/DbGate use an SSH tunnel, e.g. `ssh -L 5051:127.0.0.1:5051 server`.

## 3. DuckDB has a single opener — decision

DuckDB allows **one process** to open a file for writing, and meanwhile other processes cannot open it, not even
read-only. The chosen option (TRD §7.2, K1): **ingest runs inside the `app` process**, in a separate thread, with the
same DuckDB connection. Dashboard reads use their own cursor and keep seeing the old, consistent data until the per-folder
ingest transaction is committed (DuckDB MVCC).

- The `ingest` service does **not** mount the data volume. It calls `POST /api/admin/ingest` on `app` with
  `S4_JOB_TOKEN`, waits until it finishes, then exits with code 0 (success) or ≠ 0 (failure / server stopped).
- Rejected: "read-only app + ingest writes a new file that is then swapped in". That approach copies ±100 MB per ingest and requires
  `app` to reopen its connection. Moreover, DuckDB cannot be opened read-only while another process is writing the same file.
- **External viewers (DbGate)** must not open the file owned by `app` either. Therefore `app` writes a **read-only copy**
  `/data/snapshot/monishield.duckdb` (`S4_DUCKDB_SNAPSHOT=true`, default in compose) on start if it does not exist yet and every
  time an ingest finishes. The copy is written to `.tmp` and then replaced atomically (`os.replace`); a connected DbGate keeps
  reading the old version until it reconnects. Its format is `STORAGE_VERSION 'v1.2.0'` so that DuckDB 1.2.1 in DbGate
  6.6.4 can read it. Cost: ±4 seconds and ±50 % of the database size. Set `S4_DUCKDB_SNAPSHOT=false` if DbGate is not used.

Tested in the container (§8): 73 dashboard data requests during a 51-second forced ingest, all 200 (median 54 ms, max 610 ms).

## 4. Daily ingest

The server already ingests on start. An admin can also press **Sync data** in the dashboard. For a fixed schedule, use
cron on the host:

```cron
# every day at 06.15 WIB (server in the Asia/Jakarta time zone); output to a host log
15 6 * * *  cd /srv/monishield/v2 && docker compose run --rm ingest >> /var/log/monishield-ingest.log 2>&1
```

| Situation | What happens |
|---|---|
| No new folders | finishes in < 1 second ("0 files changed"); only new/changed files are parsed |
| Run twice at the same time (cron + button, or two crons) | the second one waits for the running ingest and then reports its result ("ingest already running on the server; waiting for it to finish"); nothing is parsed twice |
| Interrupted midway (container stopped, `kill -9`, power) | each folder is committed in one transaction: finished folders stay, the folder being processed returns to its previous contents. The next ingest marks the interrupted run as `failed` ("interrupted: …"), deletes its temporary CSVs, and reprocesses the unfinished folders |
| `app` down / unhealthy | `ingest` exits with code ≠ 0 ("server stopped responding while ingest was running"); cron records it in the log |
| Reference database download fails | ingest still ends `ok` with the warning "refdata failed …"; IP location/owner uses the old file in the cache, or is left empty if there never was one |

### Log folders without copying to the server

- **Automatic sync from S3**: set `S4_IMPORT_BUCKETS` and the AWS keys in `.env`, then on the Ingest & import page enter the parent folder
  (e.g. `s3://nama-bucket/k8s-logs`) → Save & enable (stored in PostgreSQL, table `app_setting`). Alternative: `S4_S3_WATCH` in `.env`.
  `app` checks the bucket every `S4_S3_WATCH_MINUTES` minutes, downloads new date folders to the `s4-inbox` volume, then
  ingests them. The first check is 1 minute after the container starts. A cron job with the machine token can also trigger it:
  `curl -X POST -H "Authorization: Bearer $S4_JOB_TOKEN" -H "X-Requested-With: job" http://127.0.0.1:8000/api/admin/import/sync`.
- **Upload from the browser**: Ingest & import page → Upload log folder. Files go to `s4-inbox` and are then ingested. The reverse proxy
  in front of `app` must allow request bodies as large as the largest log file (nginx: `client_max_body_size 1024m;`;
  Caddy from the `proxy` profile has no limit).

### API documentation

Swagger UI at `https://<server>/api/docs` (schema: `/api/openapi.json`), only after signing in with the same dashboard
account. The Swagger UI assets are copied into the image at build time (`web/dist/swagger/`, from `swagger-ui-dist`); there is no CDN.

## 5. Viewing the database contents

| Tool | Address | Shows | Notes |
|---|---|---|---|
| pgAdmin 9.8 | `http://127.0.0.1:5050` | PostgreSQL: `app_user`, `app_session`, `audit_log`, `import_job` | `docker compose --profile pgadmin up -d`. The "MoniShield" server is already registered (`deploy/pgadmin/servers.json`); database password = `POSTGRES_PASSWORD` |
| DbGate 6.6.4 | `http://127.0.0.1:5051` | **log data** (DuckDB, read-only copy) + PostgreSQL | `docker compose --profile dbgate up -d`. Both connections are registered and marked read-only |

**Log data is not in PostgreSQL.** Tables such as `nginx_access`, `spring_line`, `agg_*`, and `folder_state` are in
DuckDB, so view them through DbGate. pgAdmin is only for accounts and audit. If DbGate shows old data after an ingest,
right-click the DuckDB connection and choose *Refresh* / reconnect.

DbGate cannot mount the copy as a `:ro` mount: its DuckDB plugin always opens the file in write mode and
ignores `READONLY_`. Therefore only the `snapshot/` **folder** is mounted (`volume.subpath`), read-write. The DuckDB file
owned by `app` is not visible from the DbGate container. Anything written only affects the copy, and leftover WAL of the
old copy is discarded before the new copy is put in place.

## 6. Security

- The `app` process runs as the `monishield` user (uid 10001), with `read_only: true`, `cap_drop: ALL`, and
  `no-new-privileges`. Only the data volumes and `/tmp` (tmpfs) are writable.
- Ports are only `127.0.0.1:8000` (dashboard); pgAdmin/DbGate `127.0.0.1:5050/5051`, and only when their profile is enabled.
  PostgreSQL has no port on the host. `proxy` opens 443.
- No secrets in the image or in `docker-compose.yml`: everything comes from `.env`, and `.env` is excluded by
  `.dockerignore` and `.gitignore`. The proxy CA for the build comes in as a *build secret* and is not stored in an image layer.
- Logs (containing user IPs and emails) are **never** copied into the image. `.dockerignore` rejects `*.log`, `*.log.gz`, `data/`,
  and date folders. Logs are mounted read-only from the host at `/logs`.
- IP location and owner are matched **offline** against databases downloaded into `s4-cache`. No user IP is
  sent to an external service.
- Health check `GET /api/health` every 30 seconds; `restart: unless-stopped` for `app`, `postgres`, `proxy`,
  `pgadmin`, and `dbgate`.
- pgAdmin: `SERVER_MODE`, no version check over the internet. DbGate: refuses to start without a login and a password ≥ 12 characters, because
  without `LOGIN` DbGate is open to anyone.

## 7. Internet access (outbound firewall)

Only `app`, and only during ingest (refdata), with a cache retention period. `S4_OFFLINE=true` turns off all downloads.

| Host | File | If it fails |
|---|---|---|
| `iptoasn.com` | `ip2asn-v4.tsv.gz` (IP owner) | IP owner from the old file / empty |
| `download.maxmind.com` | GeoLite2-City CSV (needs a free account) | falls back to `download.db-ip.com` |
| `download.db-ip.com` | `dbip-city-lite-YYYY-MM.csv.gz` (IP location) | IP location from the old file / empty |
| `raw.githubusercontent.com` | Natural Earth: land, country borders, provinces, country names | the map uses the old files |
| `download.geonames.org` | `ID.zip` (Indonesian region names) | region labels use the old file |
| S3 endpoint (if S3 import is used) | log folders `s3://…` | the import fails with a message; other data is unaffected |

Notifications (if enabled on the Configuration → Notifications page): `api.telegram.org`, `discord.com`, and/or the office SMTP
server. Messages contain only summary numbers + a dashboard link, without user IP addresses. The MaxMind **Test connection** button on
the Configuration page only requests a download link from `download.maxmind.com` (without downloading, without user IP addresses).

### `.env` is mounted into the container, and the Configuration page writes to it

`app` no longer uses `env_file:`; `./.env` is mounted as a file at `/app/.env` and read by the server itself on start.
The **Configuration** page (AWS keys, MaxMind, automatic S3 folders, notifications, block list) writes to that file **in
place** (no rename, safe for bind mounts), and the values take effect immediately; after `docker compose restart` or
`up -d` the values persist. Requirement: the container user (uid/gid 10001) must be allowed to write:

```sh
sudo chgrp 10001 .env && chmod 660 .env
```

Without that permission the page shows a "not writable" warning and refuses **Save** (other values keep working).
Variables in the compose `environment:` block (path `/logs`, `/data`, PostgreSQL URL, etc.) still override `.env`.
`ingest` mounts the same file read-only. Editing `.env` with an editor is fine too — restart `app` afterwards;
use an editor that writes in place (e.g. `nano`, `vi` with `:set backupcopy=yes`), because editors that rename the
file break the bind mount until the container is recreated.

The download source addresses (MaxMind, ip2asn, Natural Earth, GeoNames) and the Telegram API are also set in `.env`
(`S4_URL_*`, `S4_TELEGRAM_API`, section 10 of `.env.example`) — useful if the server may only go out through an internal mirror/proxy.

At build time only: `registry-1.docker.io` / `production.cloudflare.docker.com` (base images), `registry.npmjs.org`, and
`pypi.org` + `files.pythonhosted.org`.

### Kafka for Rancher logs (`kafka` profile, optional)

If there is no Kafka yet, compose provides a single-node broker (Apache Kafka 3.9, KRaft, without Zookeeper):

```sh
# .env
DOCKER_KAFKA_HOST=10.10.1.5          # address of this server reachable from the cluster nodes (entered in Rancher)
DOCKER_KAFKA_BIND=0.0.0.0            # default 127.0.0.1 (this host only)
DOCKER_KAFKA_PORT=9094
S4_KAFKA_BROKERS=kafka:9092          # app reads over the compose network
S4_KAFKA_TOPIC=k8s-logs
docker compose --profile kafka up -d
```

In Rancher: Endpoint Type **Broker**, Endpoint `10.10.1.5:9094`, Topic `k8s-logs`. This listener has **no password**:
restrict port 9094 with a firewall to the cluster node IPs only (or use the office Kafka with SASL and set
`S4_KAFKA_SECURITY`/`S4_KAFKA_USERNAME`/`KAFKA_PASSWORD`). One partition (line order per pod is preserved); retention
`DOCKER_KAFKA_RETENTION_HOURS` (default 168 hours). What MoniShield has already written to `s4-inbox` does not depend on that
retention. Verified 2026-10-07: the app in the container reads `kafka:9092`, 500 Rancher messages → folder 2026-10-08
(14 files) → automatic ingest.

## 8. Backups and updates

| Volume | Contents | Back up? |
|---|---|---|
| `s4-pgdata` | accounts, sessions, audit | **required**: `docker compose exec postgres pg_dump -U monishield monishield > akun.sql` |
| `s4-inbox` | log folders from S3 import | yes (raw logs) |
| `s4-data` | `monishield.duckdb`, read-only copy, map files | not required: can be rebuilt from the logs |
| `s4-cache` | reference databases ±190 MB | no: can be downloaded again |
| `s4-pgadmin`, `s4-dbgate` | viewer settings | no |

Application update: `git pull && docker compose build && docker compose up -d`. The DuckDB schema is re-applied on start
(safe to repeat).

### Rename 2026-10-07 (simpel4 → monishield)

The PostgreSQL user and database in compose are now `monishield` (formerly `simpel4`), the DuckDB file is `monishield.duckdb`
(formerly `simpel4.duckdb`; moved automatically when the server starts, without re-ingesting), the JWT issuer is `monishield` (old sessions
end, just sign in again). An `s4-pgdata` volume created by an earlier version still contains the `simpel4` user: since it
has not been deployed on the server yet, simply recreate it with `docker compose down -v` (the accounts in that volume are deleted too).

## 9. Verification results (2026-10-07, developer machine, Docker 29.8.2, Compose 5.6.0)

| # | Step | Result |
|---|---|---|
| 1 | `docker compose build` | succeeded, 41 seconds (dependency layers from cache); image `monishield:2.0.0` **413 MB on disk / 105 MB compressed**; no Node/`node_modules` |
| 2 | `docker compose run --rm ingest` (11 folders, 195 files) | `ok; 195 files seen, 195 files changed … 11 folders changed; 73.44 seconds` (the job waited for the start-up ingest that was running); forced re-ingest 50.75 seconds; no changes 0.03 seconds |
| 3 | `docker compose up -d` | `app` *healthy* within ±11 seconds |
| 4 | browser (`tools/uji_docker.cjs`) | 8/8 PASSED: sign-in + forced password change, Overview (KPIs), service `nginx-ingress-controller`, Command Center (MapLibre map), 11 folders, no JS errors; pgAdmin sign-in + registered server; DbGate sign-in + `nginx_access` table readable from the copy |
| 5 | `down` then `up -d` | data intact without re-ingesting (`last_run ok 195`, start-up ingest "0 files changed"); admin account with the changed password and 4 audit rows still present |
| — | dashboard during ingest | 73 `/api/folders/…` requests during a 51-second forced ingest: 73 OK, 0 failed |
| — | `kill -9` in the middle of an ingest | the job exits ≠ 0; after `up`, data intact; leftover `tmp/run-6` (194 MB of CSV) and the `running` run row cleaned up by the next ingest |
| — | ingest while DbGate has the copy open | `snapshot_error: None`; the copy is replaced, DbGate reads the new version after reconnecting |

Problems found and fixed during verification:

- `${PGADMIN_EMAIL:?}` made `docker compose up` fail even when the pgAdmin profile was not used. Now uses `:-`;
  pgAdmin refuses by itself if it is empty, and DbGate uses a check in its `entrypoint`.
- pgAdmin rejects `@….local` emails → `ALLOW_SPECIAL_EMAIL_DOMAINS`.
- pgAdmin listens on `[::]` and fails on a docker network without IPv6 → `PGADMIN_LISTEN_ADDRESS=0.0.0.0`.
- DbGate fails to open the copy on a `:ro` mount → read-write mount of the `snapshot/` folder (§5).
- `kill -9` leaves temporary CSVs and a `running` run behind → cleaned up at the start of the next ingest.

## 10. Application code changes in this step

| File | Change | Reason |
|---|---|---|
| `config.py` | `S4_API_URL` | `ingest` in the container calls `app` over HTTP and does not open DuckDB |
| `config.py`, `db.py`, `api/admin.py`, `api/app.py` | `S4_DUCKDB_SNAPSHOT` + `db.snapshot()` | read-only copy for DbGate (§3) |
| `ingest.py` | `_cleanup_killed()` at the start of ingest | leftovers of a forcibly killed run (§4) |
| `cli.py` | `ingest` with `S4_API_URL` → via the API, waits, exit code | the `ingest` service / cron |

Tests: `tests/test_ingest.py::test_salinan_baca_untuk_dbgate`,
`::test_dimatikan_paksa_dibersihkan_pada_ingest_berikutnya`, and `tests/test_api.py::test_salinan_duckdb_untuk_dbgate`.
