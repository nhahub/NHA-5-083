# Contributing

## 1. Workflow (GitHub Flow, kept simple)

We have about two weeks of build time, so we keep the workflow light.

1. `main` is always working and deployable. Nobody commits to it directly (allegedly?).
2. Create a short-lived branch from `main` for each task.
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

Areas: `pipeline`, `sql`, `api`, `web`, `infra`, `docs`.
Example: `feat/pipeline-zomato-bronze-ingestion`

## 3. Commit messages (Conventional Commits)

```text
<type>(<area>): <short summary in imperative mood>

Optional body: what and why, not how.
Refs #12
```

Examples:

- `feat(pipeline): add Zomato CSV ingestion to Bronze`
- `fix(api): handle unrated restaurants in rating filter`
- `docs(srs): add UC-06 rejected records`

Rules: summary under 72 characters, no trailing period, one logical change per commit.

## 4. Pull requests

Every PR description should include:

- **What** changed and **why**
- Linked issue or requirement ID (for example `FR-S5`)
- How it was tested
- Screenshots for UI changes
- Checklist:
  - [ ] Code follows `docs/CODE_STYLE.md`
  - [ ] Linters and formatters pass
  - [ ] Tests added or updated where applicable
  - [ ] Docs updated if behavior or setup changed
  - [ ] No secrets, `.env` files, or large data files committed

## 5. Review checklist

- Does it do what the issue asks, and nothing hidden?
- Are SQL queries parameterized?
- Are errors handled, and are failures logged rather than swallowed?
- Are names clear and consistent?
- Is the pipeline step idempotent (safe to re-run)?
- Is anything duplicated that already exists?

Review comments should be specific and kind. Prefer questions over commands.

## 6. Definition of Done

A task is done when it is merged to `main` through a reviewed PR, passes checks, and its documentation is updated.

## 7. Secrets and data

- Never commit credentials, API keys, or `.env`. Use `.env.example` for variable names only.
- If a secret is committed by mistake, tell the team immediately and rotate it. Deleting the commit is not enough.
- Do not commit raw datasets. Large data lives in Azure Blob Storage or is downloaded by scripts. Respect each source's license.
