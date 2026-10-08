# Deploying MoniShield to a new VPS until it can be opened via a domain

Flow: **DNS → prepare the VPS (user, firewall, Docker) → fetch the code → fill in `.env` → build + run the `https` profile
(automatic Let's Encrypt certificate) → sign in → set up the data sources (S3 / Kafka)**. Estimated time: 30–60 minutes.

All commands below are run on the VPS unless stated otherwise. Replace `monishield.domainanda.id`, `IP_VPS`, and
`admin@domainanda.id` with your own.

---

## 0. What you need

| Requirement | Minimum | Notes |
|---|---|---|
| VPS | Ubuntu 24.04 LTS (or 22.04), 2 vCPU, **4 GB RAM**, 40 GB SSD | +2 GB RAM if running Kafka on the same VPS (`kafka` profile) |
| Domain | one (sub)domain, e.g. `monishield.domainanda.id` | access to its DNS settings |
| GitHub access | repo `apisdsn/MoniShield` | private repo: a GitHub token (fine-grained, *Contents: read*) or a deploy key |
| Ports open from the internet | 22 (SSH), 80, 443 | 80 is required for Let's Encrypt verification + the redirect to https |
| VPS outbound access | internet | downloading images/packages at build time, map & IP reference data (see `06-docker.md` §7) |

---

## 1. Point the domain to the VPS

In your domain's DNS panel create the records:

| Type | Name | Value | TTL |
|---|---|---|---|
| `A` | `monishield` | `IP_VPS` | 300 |
| `AAAA` (if the VPS has IPv6) | `monishield` | VPS IPv6 | 300 |

Check from your computer (may take a few minutes):

```sh
dig +short monishield.domainanda.id      # must show IP_VPS
```

> **Cloudflare**: the first time, set the record to **DNS only** (grey cloud) so Let's Encrypt can verify.
> If you want to use the Cloudflare proxy (orange cloud) afterwards, set SSL/TLS to **Full (strict)**.

---

## 2. Prepare the VPS (once)

Sign in as root (or the sudo user from the VPS provider):

```sh
ssh root@IP_VPS

# dedicated user + the same SSH key
adduser monishield
usermod -aG sudo monishield
rsync --archive --chown=monishield:monishield ~/.ssh /home/monishield

# updates + tools
apt update && apt -y upgrade
apt -y install git curl ufw fail2ban unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades        # automatic security updates: choose "Yes"

# firewall: only SSH, http, https
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw enable

# 4 GB RAM: add 2 GB of swap so the build and the first ingest do not run out of memory
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Log out, then sign in again as the new user: `ssh monishield@IP_VPS`.
(Optional, recommended: disable root login & SSH passwords — `PermitRootLogin no`, `PasswordAuthentication no` in
`/etc/ssh/sshd_config`, then `sudo systemctl restart ssh`. Make sure key-based login works first.)

---

## 3. Install Docker

```sh
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker monishield
newgrp docker                                   # or log out and back in over SSH
docker version && docker compose version       # Docker 24+ and Compose v2
```

> **Important — Docker bypasses ufw** for ports published by containers. The MoniShield compose file deliberately only
> publishes 80/443 (https proxy) to the internet; app, pgAdmin, DbGate, and Kafka are bound to `127.0.0.1`.
> Do not change that binding to `0.0.0.0` without `DOCKER-USER` rules (see §9).

---

## 4. Fetch the code

```sh
sudo mkdir -p /srv && sudo chown monishield: /srv
cd /srv
git clone https://github.com/apisdsn/MoniShield.git             # private repo: GitHub username + token as the password
cd MoniShield
git checkout prd                                                 # production branch (dev -> stg -> prd, see CONTRIBUTING.md)
mkdir -p /srv/logs                                               # date log folders (may stay empty when using S3/Kafka)
```

The date log folders (`YYYY-MM-DD/<namespace>/<service>/…`) are not in the repo. Copy old log folders to `/srv/logs`
if you want their history to show, or leave it empty and fill it via S3 sync, Kafka, or **Upload log folder** in the UI.

---

## 5. Fill in `.env`

```sh
cp .env.example .env
# three random secrets (run 3 times, copy each one)
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
nano .env
```

Minimum contents (find the lines in `.env.example`; for lines starting with `#`, remove the `#`):

```sh
DOCKER_LOG_DIR=/srv/logs                       # log folder on the host (mounted read-only)
POSTGRES_PASSWORD=<random secret 1>
S4_JWT_SECRET=<random secret 2>
S4_JOB_TOKEN=<random secret 3>
S4_ADMIN_USER=admin
S4_ADMIN_PASSWORD=<first admin password, min. 12 characters>
S4_COOKIE_SECURE=true                          # must be true on https
DOCKER_DOMAIN=monishield.domainanda.id
DOCKER_ACME_EMAIL=admin@domainanda.id          # Let's Encrypt notifications
```

Optional now (can also be done later from the **Configuration** page): `MAXMIND_ACCOUNT_ID`/`MAXMIND_LICENSE_KEY` (IP locations
on the map), `S4_IMPORT_BUCKETS` + AWS keys (S3 import), `S4_KAFKA_*` (logs from Rancher), notifications.
`S4_IMPORT_BUCKETS` can only be set in `.env`.

Allow the container (uid/gid 10001) to read **and write** `.env` (the Configuration page saves to it):

```sh
sudo chgrp 10001 .env && chmod 660 .env
```

---

## 6. Build and run

```sh
docker compose build                           # ±3–6 minutes the first time
docker compose --profile https up -d           # app + PostgreSQL + Caddy (automatic https)
docker compose ps                              # app "healthy", https "running"
docker compose logs -f https                   # wait for "certificate obtained successfully", then Ctrl+C
```

On its first start the app ingests all folders in `DOCKER_LOG_DIR` and downloads the map/IP reference data; follow
its progress with `docker compose logs -f app`. Docker restarts all services by itself after a VPS reboot
(`restart: unless-stopped`).

> Docker Hub rate-limits anonymous pulls. If build/up fails with `429 Too Many Requests`: `docker login` (free account),
> then retry.

---

## 7. Check from the internet

```sh
curl -I http://monishield.domainanda.id        # 308 -> https://…
curl -s https://monishield.domainanda.id/api/health    # {"ok":true}
```

Open `https://monishield.domainanda.id` → sign in as `admin` + `S4_ADMIN_PASSWORD` → change the password when asked.

---

## 8. After the first sign-in

1. **User menu → Configuration** (everything is saved to `.env` and takes effect immediately):
   - **AWS S3** + **Automatic S3 folders** (e.g. `s3://simpel4-backup/k8s-logs`) → *Test connection*.
   - **Kafka** (for realtime logs from Rancher; §9) → *Check messages in topic*.
   - **MaxMind GeoLite2** → *Test connection*.
   - **Notifications**: dashboard address = `https://monishield.domainanda.id`; Telegram/Discord/email → *Send test*.
2. **User menu → Manage users**: create accounts for team members (role *user* = view only).
3. **Ingest & import**: check the ingest status and the S3 and Kafka cards.

---

## 9. (Optional) Realtime logs from Rancher via Kafka

**A. An office Kafka already exists (recommended, with SASL/TLS)**: enter the broker, topic, security, username & password in
**Configuration → Kafka**. The VPS only needs to be able to reach that broker (outbound).

**B. Kafka on this VPS** (`kafka` profile). Add to `.env`:

```sh
DOCKER_KAFKA_HOST=IP_VPS                       # address entered in Rancher
DOCKER_KAFKA_BIND=0.0.0.0
DOCKER_KAFKA_PORT=9094
S4_KAFKA_BROKERS=kafka:9092
S4_KAFKA_TOPIC=k8s-logs
```

```sh
docker compose --profile https --profile kafka up -d
```

This listener has **no password and no encryption** — the logs contain user IP addresses. Restrict port 9094 to the outbound IPs of the
cluster nodes only (ufw does not apply to Docker ports, so use the `DOCKER-USER` chain):

```sh
IP_CLUSTER=203.0.113.10                         # public outbound IP of the Rancher nodes (ask the network admin)
sudo iptables -I DOCKER-USER -p tcp -m conntrack --ctorigdstport 9094 -j DROP
sudo iptables -I DOCKER-USER -p tcp -m conntrack --ctorigdstport 9094 -s $IP_CLUSTER -j ACCEPT
sudo apt -y install iptables-persistent && sudo netfilter-persistent save
```

Safer still: connect the cluster and the VPS via a VPN (e.g. WireGuard) and set `DOCKER_KAFKA_HOST` to the VPN address.

In **Rancher → Cluster → Tools → Logging → Kafka**: Endpoint Type **Broker**, Endpoint `IP_VPS:9094`, Topic
`k8s-logs`, Flush Interval **5–10** seconds, **Enable JSON Parsing unticked** → Save. Within a few seconds the
**Logs from Kafka** card on the Ingest & import page shows incoming messages; the map shows the **LIVE** badge.

---

## 10. Backups

```sh
mkdir -p /srv/backup
# accounts, sessions, audit, history (required): every night at 01.30
( crontab -l 2>/dev/null; echo '30 1 * * * cd /srv/MoniShield && docker compose exec -T postgres pg_dump -U monishield monishield | gzip > /srv/backup/pg-$(date +\%F).sql.gz && find /srv/backup -name "pg-*.sql.gz" -mtime +14 -delete' ) | crontab -
cp /srv/MoniShield/.env /srv/backup/env-$(date +%F)    # after changing the configuration (contains secrets: store it safely)
```

Raw logs from S3/Kafka import are in the `monishield_s4-inbox` volume; the DuckDB database (`s4-data`) can be rebuilt
from the logs. Details: `06-docker.md` §8.

---

## 11. Application updates

```sh
cd /srv/MoniShield && git pull                 # prd branch
docker compose build && docker compose --profile https up -d     # add --profile kafka if used
```

Data, accounts, and certificates are kept (they live in volumes). With automatic deployment (§13) this happens by
itself on every push to `prd`.

---

## 12. Common problems

| Symptom | Cause / action |
|---|---|
| `https` fails to obtain a certificate (`docker compose logs https`) | DNS does not point to the VPS yet (`dig`), ports 80/443 are closed in the VPS provider's firewall, or the Cloudflare proxy was orange the first time. Fix it, then `docker compose restart https`. Do not retry too often (Let's Encrypt rate limits). |
| The `https` container stops immediately: "set DOCKER_DOMAIN and DOCKER_ACME_EMAIL in .env" | Those two lines are not filled in `.env` yet. |
| 502 page | the app is not healthy yet: `docker compose ps`, `docker compose logs app` (the first ingest can take a few minutes). |
| Sign-in succeeds but you are signed out right away | `S4_COOKIE_SECURE` must be `true` on https and the address must be opened via `https://`. |
| Configuration page: "The server cannot write this file" (`.env`) | `sudo chgrp 10001 .env && chmod 660 .env` in `/srv/MoniShield`. |
| Map without locations | MaxMind not set yet (Configuration → MaxMind) or the VPS cannot reach `download.maxmind.com`. |
| Opening pgAdmin / DbGate | only from the VPS: from your computer `ssh -L 5050:127.0.0.1:5050 -L 5051:127.0.0.1:5051 monishield@IP_VPS`, then `docker compose --profile pgadmin --profile dbgate up -d` and open `http://localhost:5050` / `:5051`. |

---

## 13. Automatic deployment with GitHub Actions

Every push to `prd` runs the CI checks (commit messages, Python tests, web build); when all pass, the **Deploy** job
connects to the server over SSH and runs `deploy/remote-deploy.sh`: fetch the exact tested commit, build, restart, and
wait until the app's healthcheck reports `healthy`. A failed check never deploys. `.env` (all secrets) stays on the
server; GitHub only holds an SSH key.

The first run can also migrate an older checkout (e.g. `/srv/dashboard-logging/v2`): it clones the repo and copies the
old `.env`. Both checkouts use the compose project name `monishield`, so the same containers and volumes (data,
accounts, inbox, Kafka, certificates) are reused — nothing is lost and no `down` is needed.

### Once on the server (as your sudo user, e.g. `ubuntu`)

```sh
sudo adduser --disabled-password --gecos "" deploy        # dedicated user for deployments
sudo usermod -aG docker deploy                            # note: the docker group is root-equivalent; keep this key safe
sudo install -d -o deploy -g deploy /srv/MoniShield       # where the repo is cloned
sudo install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
```

On your own computer (Linux, macOS, or Git Bash on Windows), create a key pair for GitHub only and put the public half
on the server. `/home/deploy/.ssh` belongs to `deploy` (mode 700), so the key is appended with `sudo tee`; a plain
`cat >> …` as your own user fails with *Permission denied*. The key text travels inside the command, so no file has
to be copied first, and `-t` lets `sudo` ask for your password:

```sh
ssh-keygen -t ed25519 -C monishield-deploy -N "" -f ~/monishield-deploy
KEY=$(cat ~/monishield-deploy.pub)
ssh -t ubuntu@SERVER_IP "echo '$KEY' | sudo tee -a /home/deploy/.ssh/authorized_keys > /dev/null \
  && sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys && sudo chmod 600 /home/deploy/.ssh/authorized_keys && echo OK"
ssh -i ~/monishield-deploy deploy@SERVER_IP 'id && docker ps --format "{{.Names}}"'   # no password prompt; groups include docker
ssh-keyscan -p 22 SERVER_IP                         # copy the output for DEPLOY_KNOWN_HOSTS
```

GitHub's hosted runners connect from changing addresses, so SSH (port 22, key only — `PasswordAuthentication no` in
`/etc/ssh/sshd_config`) must be reachable from the internet; keep the Kafka (9094) and other ports restricted as in §2.

### Once on GitHub

Repository **Settings → Environments → New environment `production`** (optionally add *Required reviewers* so every
deploy waits for an approval click), then in that environment:

| Kind | Name | Value |
|---|---|---|
| Secret | `DEPLOY_HOST` | server IP or host name |
| Secret | `DEPLOY_USER` | `deploy` |
| Secret | `DEPLOY_SSH_KEY` | contents of the private key `monishield-deploy` |
| Secret | `DEPLOY_KNOWN_HOSTS` | output of `ssh-keyscan` above |
| Secret (optional) | `DEPLOY_PORT` | SSH port when not 22 |
| Variable | `DEPLOY_DIR` | `/srv/MoniShield` (default) |
| Variable | `DEPLOY_PROFILES` | compose profiles, comma-separated, e.g. `https,kafka` (default `https`) |
| Variable (first run only) | `DEPLOY_MIGRATE_FROM` | `/srv/dashboard-logging/v2` to copy its `.env`; remove after the first deploy |

### Every release

Merge `dev` → `stg` → `prd` (CONTRIBUTING.md). The push to `prd` deploys; the run is listed under **Actions → CI**.
To deploy the current `prd` again without a new commit: **Actions → CI → Run workflow → branch `prd`**.
If the job fails, its log shows the last 40 lines of the app log; the previous containers keep running when the build
fails.

---

*Verified 2026-10-07 in the developer environment (Docker 29.8.2): `https` profile with Caddy 2.10.2 — http → https
(308), HSTS, login with a `Secure; HttpOnly` cookie over https; a real Let's Encrypt certificate could not be tested
there (it needs a public domain), so steps 6–7 are the first check on your VPS.*
