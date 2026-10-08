# MoniShield — notes for Claude Code

Log and security dashboard: FastAPI + DuckDB (+ PostgreSQL for accounts) on the server, Svelte 5 in the browser.
Start with `docs/09-status.md` (state and next steps), then `docs/08-architecture.md` (where code goes).

## Commands

```sh
.venv/bin/pip install -e ".[test,s3,kafka]"      # once
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN .venv/bin/python -m pytest -q
(cd web && npm ci && npm run build) && node tools/cek_i18n.mjs && node --test tests/test_format.mjs
.venv/bin/python -m monishield serve             # http://127.0.0.1:8000
tools/cek_commit.sh origin/dev..HEAD             # commit messages before pushing
```

Unset the `AWS_*` variables for pytest: real or placeholder keys in the environment override the test settings.
About 60 tests skip in this repo because they compare against the old system; every other test must pass.

## Rules agreed with the owner

- **Language.** Commit messages, code comments, Markdown docs (titles and file names too), server error messages,
  API responses, CLI output and GitHub Actions step names are English. The UI stays bilingual: add every new text to
  both `web/src/i18n/id.json` and `en.json`; server text shown in the UI needs an Indonesian entry in
  `web/src/srv.js` (`ID`, or `ERR_ID` for full error sentences). API status values are English.
- **Commits.** Conventional Commits 1.0, English. No `Co-Authored-By` or `Claude-Session` trailers. Enable the hook
  once per clone: `git config core.hooksPath .githooks`.
- **Branches.** Work on `dev` (or a `feat/…`/`fix/…` branch into `dev`). Promote `dev` → `stg` → `prd` with pull
  requests merged by **Create a merge commit**. A merge into `prd` deploys to production: only do it when the owner
  asks. No force-push, history rewrite or branch deletion without the owner's explicit approval.
- **Privacy.** User IP addresses are never sent to a third-party service. IP owner and location are matched offline
  from downloaded databases; notifications carry numbers and links only; the live map receives coordinates only.
- **Secrets.** Never commit `.env`, keys or tokens, and never print credential values. Before a commit, check the staged
  diff for anything that looks like a key (`git diff --cached`).
- **Architecture.** Keep the dependency rule of `docs/08-architecture.md`; `tests/test_architecture.py` enforces it.
  Domain and application code import no third-party packages.
- **Old repo.** `apisdsn/dashboard-logging` is the old system: never change its `build_dashboard.py`,
  `dashboard_template.html` or log folders.
- **Owner.** The owner writes in Indonesian; answer in Indonesian. Documentation and code stay English.

## When you finish a piece of work

Update `docs/09-status.md` (and `docs/04-plan.md` for a new stage), add a line to the *Unreleased* section of
`CHANGELOG.md`, run the commands above, then commit and push to `dev`.
