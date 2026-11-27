# Contributing

> **Status:** Draft v0.4, a living document. Coding rules are in [`docs/CODE_STYLE.md`](docs/CODE_STYLE.md); testing and CI gates are in [`docs/TESTING.md`](docs/TESTING.md); secrets and configuration rules are in [`docs/SECRETS.md`](docs/SECRETS.md); UI rules are in [`docs/UI_UX.md`](docs/UI_UX.md).
> **Last updated:** 2026-11-26

## 1. Workflow (GitHub Flow, kept simple)

We have about two weeks of build time, so we keep the workflow light.

1. `main` is always working and deployable. Nobody commits to it directly. Merging to `main` automatically runs CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) and builds, pushes, and rolls out updated container images to Azure ([`.github/workflows/build-push-acr.yml`](.github/workflows/build-push-acr.yml) — see [`docs/DEPLOY_AZURE.md`](docs/DEPLOY_AZURE.md)).
2. Create a short-lived branch from `main` for each task. FastAPI and Streamlit co-deploy from `main` without API route versioning, so breaking API changes must update `web/backend/`, `web/streamlit/api_client.py`, and tests in the same PR.
3. Open a pull request (PR) early, even if it is a draft.
4. At least one teammate reviews before merging.
5. Merge with "Squash and merge" so history stays readable.
6. Delete the branch after merging.

## 2. Branch names

`<type>/<area>-<short-description>`

| Type | Use |
| ------ | ----- |
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change without behavior change |
| `test` | Tests only |
| `chore` | Tooling, config, dependencies |

Areas: `pipeline`, `sql`, `backend`, `streamlit`, `web`, `infra`, `docs`.
Example: `feat/pipeline-zomato-bronze-ingestion`

## 3. Commit messages (Conventional Commits)

```text
<type>(<area>): <short summary in imperative mood>

Optional body: what and why, not how.
Refs #12
```

Examples:

- `feat(pipeline): add dynamic Zomato Kaggle ingestion to Bronze`
- `fix(backend): handle unrated restaurants in rating filter`
- `docs(srs): promote incremental loads and pipeline status endpoint`

Rules: summary under 72 characters, no trailing period, one logical change per commit.

## 4. Pull requests

Every PR description should include:

- **What** changed and **why**
- Linked issue or requirement ID (for example `FR-S5` or `FR-D7`)
- How it was tested
- Screenshots (desktop + ~375 px mobile, Light + Dark modes) for UI changes (`docs/UI_UX.md` §9)
- Checklist:
  - [ ] Code follows `docs/CODE_STYLE.md`
  - [ ] Linters (`ruff check`, `ruff format --check`) and type checks (`mypy`) pass
  - [ ] Tests (`pytest`, including `tests/test_architecture.py` and `tests/test_streamlit_smoke.py`) pass
  - [ ] Every new env var is added to `.env.example` (`replace_with_...` placeholder), and every new tunable setting is added to `config/settings.toml` (`docs/SECRETS.md`)
  - [ ] Docs updated if behavior, schema, or configuration changed
  - [ ] No secrets, `.env` files, or manually downloaded datasets committed

## 5. Review checklist

- Does it do what the issue asks, and nothing hidden?
- Are SQL queries parameterized, and do PyMySQL routes use plain `def` (not `async def`)?
- Does Streamlit access data strictly via `web/streamlit/api_client.py` without embedding SQL, importing database/backend/pipeline packages, using raw HTML/CSS, or storing database credentials?
- Are `os.environ` / `os.getenv` / `settings.toml` reads confined strictly to each app's `settings.py`, and shared constants placed in `constants.py`?
- Do Airflow DAGs contain wiring only and reference `AIRFLOW_CONN_*` connections strictly by `conn_id`?
- Are errors handled, and are failures logged as structured JSON (with user query text truncated to 220 chars and zero secrets)?
- Is the pipeline step idempotent, change-checked, and guarded by the 15% quarantine rate threshold?
- Is anything duplicated that already exists?

Review comments should be specific and kind. Prefer questions over commands.

## 6. Definition of Done

A task is done when it is merged to `main` through a reviewed PR, passes CI checks, and its documentation and configuration catalogues (`.env.example`, `config/settings.toml`) are updated.

## 7. Secrets and data

- Never commit credentials, API keys, or `.env`. Use `.env.example` for variable names and fake placeholders only, and `config/settings.toml` for non-secret tunables (`docs/SECRETS.md`).
- If a secret is committed by mistake, tell the team immediately and rotate it. Deleting the commit is not enough.
- Do not commit manually downloaded datasets for production use. Pipeline modules fetch sources programmatically (e.g., via the Kaggle API) into Bronze storage (`docs/DATA_SOURCES.md`). Respect each source's license.
