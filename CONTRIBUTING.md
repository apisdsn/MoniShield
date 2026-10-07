# Contributing to MoniShield

## Branches

| Branch | For | Merged from |
|---|---|---|
| `dev` | day-to-day development; always runnable | feature branches (`feat/…`, `fix/…`) via pull request |
| `stg` | shared testing / staging before release | `dev` via pull request |
| `prd` | production (what is deployed on the VPS, `docs/07-deploy-vps.md`) | `stg` via pull request |

Flow: create a branch from `dev` → pull request to `dev` → after testing on `dev`, PR `dev` → `stg` → after passing staging
tests, PR `stg` → `prd`. Production hotfixes: a `fix/…` branch from `prd`, PR to `prd`, then merge back into
`stg` and `dev`. (`master` = the initial copy made when the repo was created.)

Recommended in GitHub → Settings → Branches: protect `stg` and `prd` (PR + green CI required), and make `dev` the default branch.

## Language

Commit messages (Conventional Commits, below), code comments, documentation, server error messages and API responses are
written in **English**. The web UI stays bilingual (Indonesian/English) via `web/src/i18n` (`id.json`, `en.json`).

## Commit messages: Conventional Commits

Every commit uses [Conventional Commits 1.0](https://www.conventionalcommits.org/id/v1.0.0/):

```
<type>[(<scope>)][!]: <short summary>

[body: what and why, may be several paragraphs]

[BREAKING CHANGE: … if it breaks compatibility]
```

| Type | When |
|---|---|
| `feat` | new feature for users |
| `fix` | bug fix |
| `docs` | documentation only |
| `style` | code formatting without changing behavior |
| `refactor` | code change without a new feature/fix |
| `perf` | speed-up |
| `test` | adding/fixing tests |
| `build` | build system, dependencies, Docker |
| `ci` | GitHub Actions |
| `chore` | other maintenance |
| `revert` | reverting a commit |

Common scopes (lowercase): `api`, `ingest`, `kafka`, `s3`, `peta`, `ui`, `config`, `auth`, `alerts`, `docker`,
`deps`, `i18n`. Examples:

```
feat(kafka): write Rancher messages into folders like the S3 export
fix(peta): particles stop when the tab is hidden
docs: VPS deploy guide
build(deps)!: bump DuckDB to 2.x

BREAKING CHANGE: old database files must be re-ingested.
```

Automatic checks:

```sh
git config core.hooksPath .githooks          # once per clone: non-conforming commits are rejected on your computer
tools/cek_commit.sh origin/dev..HEAD          # check commits before pushing
```

CI (`.github/workflows/ci.yml`) checks the commit messages on every pull request and push to `dev`/`stg`/`prd`, then
runs the Python tests and the UI build.

## Before opening a pull request

```sh
.venv/bin/pip install -e ".[test,s3,kafka]"
.venv/bin/python -m pytest -q                 # all tests
(cd web && npm ci && npm run build) && node tools/cek_i18n.mjs   # UI build + complete ID/EN dictionaries
```

In this repo ±60 comparison tests against the old system (`build_dashboard.py`, `dashboard.html`, real log folders) are automatically
**skipped**: those files only exist in the old repo `apisdsn/dashboard-logging`. All other tests must pass.

Never commit `.env` (it contains secrets; it is already in `.gitignore`).
