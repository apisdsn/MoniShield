<a id="readme-top"></a>

[![CI][ci-shield]][ci-url]
[![Last commit][commit-shield]][commit-url]
[![Issues][issues-shield]][issues-url]
[![Version][version-shield]][changelog-url]

<br />
<div align="center">
  <a href="https://github.com/apisdsn/MoniShield">
    <img src="web/public/favicon.svg" alt="MoniShield logo" width="80" height="80">
  </a>

<h3 align="center">MoniShield</h3>

  <p align="center">
    A self-hosted dashboard that turns Kubernetes logs into service health, traffic and attack reports.
    <br />
    <a href="docs/README.md"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="docs/10-user-guide.md">User guide</a>
    &middot;
    <a href="https://github.com/apisdsn/MoniShield/issues/new?labels=bug">Report Bug</a>
    &middot;
    <a href="https://github.com/apisdsn/MoniShield/issues/new?labels=enhancement">Request Feature</a>
  </p>
</div>

<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
        <li><a href="#running-with-docker">Running with Docker</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>



## About The Project

MoniShield reads the daily log folders of a Kubernetes application (ingress-nginx, CoreDNS, Spring services, the
frontend) and keeps them in DuckDB. Admins and users sign in to see what happened on a given day:

* which services were slow or failing, and why (upstream errors, DNS errors, restarts)
* which requests looked like attacks, scored with the OWASP Core Rule Set and grouped by CAPEC category
* where traffic came from, on a world map that can also show live requests from Kafka
* how today compares with the average of the last seven days

Logs can come from a folder on the server, an S3 bucket (synced automatically), a browser upload, or Rancher cluster
logging through Kafka. IP owners and locations are looked up offline from downloaded databases, so user IP addresses
never leave the server.

MoniShield replaces an older static HTML report (`build_dashboard.py` in
[apisdsn/dashboard-logging](https://github.com/apisdsn/dashboard-logging)). Its numbers are tested against that report.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



### Built With

* [![Python][Python-badge]][Python-url]
* [![FastAPI][FastAPI-badge]][FastAPI-url]
* [![DuckDB][DuckDB-badge]][DuckDB-url]
* [![PostgreSQL][PostgreSQL-badge]][PostgreSQL-url]
* [![Svelte][Svelte-badge]][Svelte-url]
* [![Vite][Vite-badge]][Vite-url]
* [![MapLibre][MapLibre-badge]][MapLibre-url]
* [![Apache Kafka][Kafka-badge]][Kafka-url]
* [![Docker][Docker-badge]][Docker-url]
* [![Caddy][Caddy-badge]][Caddy-url]

<p align="right">(<a href="#readme-top">back to top</a>)</p>



## Getting Started

This gets a copy running on your own computer. For a server with a domain and HTTPS, follow
[`docs/07-deploy-vps.md`](docs/07-deploy-vps.md) instead.

### Prerequisites

* Python 3.12 or newer
* Node.js 20.19 or newer, with npm (only to build the UI)
* Some logs in the layout `YYYY-MM-DD/<namespace>/<service>/<pod>.log`, by default in `logs/` inside the project.
  You can also start empty and load logs later from S3, Kafka or a browser upload.

### Installation

1. Clone the repo
   ```sh
   git clone https://github.com/apisdsn/MoniShield.git
   cd MoniShield
   ```
2. Create your configuration file
   ```sh
   cp .env.example .env && chmod 600 .env
   ```
3. Fill in at least these values in `.env`
   ```sh
   S4_JWT_SECRET=...        # random, 32+ characters: python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   S4_ADMIN_PASSWORD=...    # first admin password, 12+ characters, changed at first sign-in
   S4_COOKIE_SECURE=false   # only while trying it over http:// on your own computer
   ```
   Every other setting (MaxMind key for the map, S3, Kafka, notifications, PostgreSQL) is explained in `.env.example`
   and can mostly be set later on the **Configuration** page.
4. Install, build and start
   ```sh
   ./run.sh
   ```
   Or step by step:
   ```sh
   python3 -m venv .venv
   .venv/bin/pip install -e ".[s3,kafka]"
   (cd web && npm ci && npm run build)
   .venv/bin/python -m monishield serve
   ```
5. Open http://127.0.0.1:8000, sign in as `admin` and change the password.

### Running with Docker

```sh
cp .env.example .env && chmod 600 .env    # also fill in DOCKER_LOG_DIR, POSTGRES_PASSWORD, S4_JOB_TOKEN
sudo chgrp 10001 .env && chmod 660 .env   # lets the container save changes from the Configuration page
docker compose up -d --build              # app + PostgreSQL on http://127.0.0.1:8000
```

Optional profiles: `https` (Caddy with Let's Encrypt), `kafka` (a broker for Rancher), `pgadmin`, `dbgate`. See
[`docs/06-docker.md`](docs/06-docker.md).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



## Usage

* **New logs**: put a date folder in the log folder and press **Sync data** in the page header. New or changed files are
  read; nothing else is processed again.
* **S3**: Ingest & import → *Automatic sync from S3* → enter `s3://your-bucket/k8s-logs` → **Save & enable**.
* **Kafka**: Configuration → Kafka. Folders filled from Kafka show up as `YYYY-MM-DD (Kafka)`.
* **Search**: `Ctrl+K` finds an IP, account, request id or URL.
* **API**: `/api/docs` (Swagger), behind the same sign-in.

Command line, Kafka and S3 details, notifications and the block list are in the
[user guide](docs/10-user-guide.md).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



## Roadmap

- [x] Dashboard pages, accounts and roles, ID/EN, dark/light theme
- [x] OWASP CRS attack detection with CAPEC categories
- [x] S3 import and automatic sync, browser upload
- [x] Logs from Rancher through Kafka with a live map
- [x] Telegram, Discord and email notifications
- [x] Docker Compose, automatic HTTPS, automatic deploy from `prd`
- [ ] First automatic deploy to the production server
- [ ] ingress-nginx logs from Rancher cluster logging
- [ ] Test on a real phone

The current state and the reasons behind each item are in [`docs/09-status.md`](docs/09-status.md).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



## Contributing

Work happens on `dev`, then moves to `stg` for testing and to `prd` for production. A merge into `prd` deploys.

1. Create a branch from `dev` (`git checkout -b feat/short-name dev`)
2. Enable the commit hook once (`git config core.hooksPath .githooks`)
3. Commit with a Conventional Commit message in English (`git commit -m "feat(map): show the request count"`)
4. Run the tests (`.venv/bin/python -m pytest -q`, `cd web && npm run build`)
5. Push the branch and open a pull request into `dev`

The full rules are in [`CONTRIBUTING.md`](CONTRIBUTING.md); the code layout is in
[`docs/08-architecture.md`](docs/08-architecture.md).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



## License

No license has been chosen yet, so all rights are reserved by the owner. Bundled third-party data keeps its own
license: OWASP CRS rules in `monishield/domain/CRS-LICENSE.txt` (Apache 2.0).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



## Contact

apisdsn - [@apisdsn](https://github.com/apisdsn)

Project Link: [https://github.com/apisdsn/MoniShield](https://github.com/apisdsn/MoniShield)

<p align="right">(<a href="#readme-top">back to top</a>)</p>



## Acknowledgments

* [OWASP Core Rule Set](https://coreruleset.org/) and [MITRE CAPEC](https://capec.mitre.org/)
* [MaxMind GeoLite2](https://www.maxmind.com/) and [DB-IP](https://db-ip.com/) for IP locations
* [iptoasn.com](https://iptoasn.com/) for IP owners
* [Natural Earth](https://www.naturalearthdata.com/) and [GeoNames](https://www.geonames.org/) for map data
* [Shields.io](https://shields.io/)
* [Best-README-Template](https://github.com/othneildrew/Best-README-Template)

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- MARKDOWN LINKS & IMAGES -->
[ci-shield]: https://img.shields.io/github/actions/workflow/status/apisdsn/MoniShield/ci.yml?branch=dev&style=for-the-badge&label=CI
[ci-url]: https://github.com/apisdsn/MoniShield/actions/workflows/ci.yml
[commit-shield]: https://img.shields.io/github/last-commit/apisdsn/MoniShield/dev?style=for-the-badge
[commit-url]: https://github.com/apisdsn/MoniShield/commits/dev
[issues-shield]: https://img.shields.io/github/issues/apisdsn/MoniShield.svg?style=for-the-badge
[issues-url]: https://github.com/apisdsn/MoniShield/issues
[version-shield]: https://img.shields.io/badge/version-2.0.0-2dd4bf?style=for-the-badge
[changelog-url]: CHANGELOG.md
[Python-badge]: https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white
[Python-url]: https://www.python.org/
[FastAPI-badge]: https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white
[FastAPI-url]: https://fastapi.tiangolo.com/
[DuckDB-badge]: https://img.shields.io/badge/DuckDB-FFF000?style=for-the-badge&logo=duckdb&logoColor=black
[DuckDB-url]: https://duckdb.org/
[PostgreSQL-badge]: https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white
[PostgreSQL-url]: https://www.postgresql.org/
[Svelte-badge]: https://img.shields.io/badge/Svelte-FF3E00?style=for-the-badge&logo=svelte&logoColor=white
[Svelte-url]: https://svelte.dev/
[Vite-badge]: https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white
[Vite-url]: https://vite.dev/
[MapLibre-badge]: https://img.shields.io/badge/MapLibre-396CB2?style=for-the-badge&logo=maplibre&logoColor=white
[MapLibre-url]: https://maplibre.org/
[Kafka-badge]: https://img.shields.io/badge/Apache%20Kafka-231F20?style=for-the-badge&logo=apachekafka&logoColor=white
[Kafka-url]: https://kafka.apache.org/
[Docker-badge]: https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white
[Docker-url]: https://www.docker.com/
[Caddy-badge]: https://img.shields.io/badge/Caddy-1F88C0?style=for-the-badge&logo=caddy&logoColor=white
[Caddy-url]: https://caddyserver.com/
