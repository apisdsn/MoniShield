# MoniShield documentation

Read [`09-status.md`](09-status.md) first: it says where the project stands and what comes next.

| File | What it covers |
|---|---|
| [`00-inventory.md`](00-inventory.md) | Inventory of the old static dashboard (`build_dashboard.py`, `dashboard_template.html`): every tab, number and rule that had to survive the migration |
| [`00-reference.json`](00-reference.json) | Reference numbers produced by the old build (`tools/acuan_lama.py`), used by the equivalence tests |
| [`01-prd.md`](01-prd.md) | Product requirements: who uses it, features, priorities, risks, success criteria |
| [`02-drd.md`](02-drd.md) | Design requirements: layout, components, colours, text, both themes and languages |
| [`03-trd.md`](03-trd.md) | Technical requirements: data model, ingest, aggregates, API, security, Docker, configuration |
| [`04-plan.md`](04-plan.md) | Implementation plan, stage by stage, with status and deviation notes |
| [`04a-measurements.md`](04a-measurements.md) | Size and performance gate (one year of simulated folders) |
| [`04b-page-checklist.md`](04b-page-checklist.md) | Page checklist: ID/EN × dark/light × wide/narrow |
| [`04c-crs-detection.md`](04c-crs-detection.md) | Attack detection with OWASP CRS + CAPEC compared with the old rules |
| [`06-docker.md`](06-docker.md) | Running with Docker Compose, profiles, volumes, backups |
| [`07-deploy-vps.md`](07-deploy-vps.md) | New VPS with a domain and automatic HTTPS; §13 automatic deployment and the release steps |
| [`08-architecture.md`](08-architecture.md) | Code architecture (clean architecture layers) and where new code goes |
| [`09-status.md`](09-status.md) | Current state, owner requests and where they live, next steps, known issues |

Repository rules (branches, commit messages, checks) are in `../CONTRIBUTING.md`; release
history is in `../CHANGELOG.md`.
