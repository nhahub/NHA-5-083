# AGENTS.md

Instructions for AI coding agents and LLM assistants working in this repository. Where any conflict arises between documents, `docs/CODE_STYLE.md` takes precedence for technical/architectural rules and `docs/SRS.md` for scope.

## 1. Project Context & Current Increment

- **System:** Data engineering platform ingesting restaurant datasets through a Medallion pipeline (**Bronze** in Azure Blob / local fallback -> **Silver** in MySQL 8.0 -> **Gold** views & spatial tables), orchestrated by **Azure Container Apps Scheduled Job** (`@weekly` in production) and **Apache Airflow 3.x** (local Docker Compose), exposed via **FastAPI**, and presented in **Streamlit 1.67.x** (Python 3.12+) on **Azure Container Apps** (`WorkloadProfiles` Consumption) with **ACR** + **GitHub Actions OIDC**.
- **Design targets:** ~10K restaurants at MVP, **100,000-restaurant ceiling**, **5–20 concurrent users**, <2s filtered search latency, **95% availability goal**, **7-day Gold freshness threshold**.
- **Increment 1 scope (complete & deployed):** End-to-end platform on the **Zomato** dataset fetched programmatically via the Kaggle API (`@weekly` change-checked schedule), deployed on Azure (`polandcentral`) with GitHub Actions CI (`ci.yml`) and OIDC ACR builds (`build-push-acr.yml`). Multi-source schema columns (`source_id`, `source_restaurant_id`, `match_group_id`) are in place; integrating Source 2, cross-source matching, and license-based view routing belong to Increment 2.
- **Legacy prototypes (`_incoming/`):** Read-only reference drafts (`_incoming/zomato/`, `_incoming/Zomato(...)`). Do **not** import from `_incoming/` or copy monolithic anti-patterns (such as SQL inside Streamlit or routers).

## 2. Target Repository Layout & Strict Import Boundaries

```text
.github/workflows/ CI quality gates (ci.yml) & OIDC ACR image builds (build-push-acr.yml)
config/            Committed non-secret settings (settings.toml) & cuisine map (cuisine_map.csv)
docker/            Local Docker MySQL init scripts (paired with root docker-compose.yml)
pipeline/          ETL modules: ingestion/, transform/, quality/, load/, settings.py, constants.py, Dockerfile(s)
pipeline/dags/     Airflow 3.x DAG definitions (task wiring ONLY — no business logic)
sql/               Numbered rebuildable MySQL 8.0 scripts (000_reset.sql, 001_..., 002_...)
web/backend/       FastAPI 3-tier app: routers/, services/, repositories/, schemas/, settings.py, constants.py, Dockerfile
web/streamlit/     Streamlit 1.67.x app: app.py, api_client.py, settings.py, constants.py, pages/, components/, .streamlit/, Dockerfile
tests/             pytest suite mirroring pipeline/, web/backend/, web/streamlit/ + test_architecture.py + test_streamlit_smoke.py
docs/              Authoritative specifications & runbooks (see Section 3 routing table)
```

### Import Isolation Rules (enforced by `tests/test_architecture.py`)

| Package | MUST NOT import | Data / DB rule |
| --- | --- | --- |
| `pipeline/` (except `dags/`) | `fastapi`, `streamlit`, `airflow`, `web.*` | Uses `pymysql` in load modules only |
| `pipeline/dags/` | Heavy runtime work at module parse time | Wires `pipeline.*` callables; uses `AIRFLOW_CONN_*` hooks by `conn_id` |
| `web/backend/routers/` & `services/` | `pymysql`, `sqlalchemy`, `streamlit`, `airflow`, `pipeline.*` | Routers -> Services -> Repositories; SQL lives **only** in `repositories/` |
| `web/streamlit/` | `pymysql`, `sqlalchemy`, `web.backend.*`, `pipeline.*` | Calls FastAPI strictly over HTTP via `web/streamlit/api_client.py` (only file importing an HTTP client); holds **zero** DB credentials |

## 3. Authoritative Task Routing ("Read Before Coding")

Load only the documents and skills relevant to your current task:

| Task area | Read first |
| --- | --- |
| **Any Python, SQL, API, or test code** | [`docs/CODE_STYLE.md`](docs/CODE_STYLE.md) |
| **Any Streamlit UI, page, map, chart, or theme** | [`.agents/skills/developing-with-streamlit/SKILL.md`](.agents/skills/developing-with-streamlit/SKILL.md) **AND** [`docs/UI_UX.md`](docs/UI_UX.md) |
| **Architecture, ERD, API routes, observability** | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| **Ingestion, Kaggle API fetch, schedules, Bronze** | [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) |
| **Validation, quarantine, 15% gate, Silver transforms** | [`docs/DATA_QUALITY_RULES.md`](docs/DATA_QUALITY_RULES.md) |
| **Cuisine normalization & NLP vocabulary check** | [`docs/CUISINE_VOCABULARY.md`](docs/CUISINE_VOCABULARY.md) |
| **Env vars, `settings.py`, `config/settings.toml`, Airflow connections** | [`docs/SECRETS.md`](docs/SECRETS.md) and [`.env.example`](.env.example) |
| **Local Docker Compose & Python execution** | [`docs/RUN_LOCAL.md`](docs/RUN_LOCAL.md) |
| **Azure deployment (CLI, Agentic/MCP, Portal UI) & troubleshooting** | [`docs/DEPLOY_AZURE.md`](docs/DEPLOY_AZURE.md) |
| **Testing strategy, CI quality gates & E2E checklist** | [`docs/TESTING.md`](docs/TESTING.md) |
| **Requirements, priorities (MoSCoW), & sprint scope** | [`docs/SRS.md`](docs/SRS.md) and [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) |
| **Branches, commits, & PR checklist** | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

## 4. Non-Negotiable Engineering Invariants

### Configuration, Secrets & Constants (`docs/SECRETS.md`)

- **Three homes, zero overlap:**
  1. **Secrets & environment endpoints** -> OS environment variables (`.env` locally, GitHub Secrets in CI, Azure Key Vault references in prod), catalogued in `.env.example` with `replace_with_...` placeholders.
  2. **Portable non-secret tunables** (timeouts, limits, schedules, dataset IDs, thresholds, paths) -> `config/settings.toml` (committed).
  3. **Named Python constants** (rule names, bounds, and constant defaults like `NLP_TIMEOUT_SECONDS = 5`, `QUERY_LOG_MAX_CHARS = 220`, `MAX_QUARANTINE_RATE = 0.15`, `GOLD_MAX_AGE_DAYS = 7`) -> `<package>/constants.py`.
- **Single reader:** Only `<package>/settings.py` (`pydantic-settings`, `SecretStr`, fail-fast with no defaults on secrets) may read `os.environ`, `os.getenv`, or `config/settings.toml`. Never use `st.secrets`.
- **Airflow connections:** Docker-injected `AIRFLOW_CONN_*` env vars (`AIRFLOW_CONN_MYSQL_PIPELINE`, `AIRFLOW_CONN_AZURE_BLOB_BRONZE`) referenced strictly by `conn_id` via native hooks/sensors (`MySqlHook`, `WasbHook`, `WasbBlobSensor`). Never store config in Airflow Variables or credentials in DAGs/XCom.

### Data, Pipeline & SQL (`docs/DATA_SOURCES.md`, `docs/DATA_QUALITY_RULES.md`, `docs/CODE_STYLE.md`)

- **Programmatic & incremental:** Fetch datasets by code (never manual downloads). Check upstream version metadata + SHA-256 checksum before loading (`skipped_unchanged`). Write Bronze append-only (`<source>/<yyyy-mm-dd>/<batch_id>/<file>`). Upsert Silver on `(source_id, source_restaurant_id)` skipping unchanged `record_hash` rows and advancing `last_seen_batch_id`.
- **15% quality gate:** Quarantine `reject` rows in `data_quality_issues` with `rule_name`, `severity`, `reason`, and JSON `raw_payload`. If `rejected_records / records_read > 0.15`, abort Silver/Gold promotion and record `quality_gate_failed`.
- **Domain types:**
  - **Time:** UTC timezone-aware `datetime.now(UTC)` everywhere.
  - **Money:** `Decimal` / `DECIMAL(14, 2)`, never `float`. Derive ISO 4217 `currency_code` from the country lookup (never free-text `Dollar($)`). Keep original `avg_cost_for_two` + `currency_code` and compute batch-pinned `avg_cost_for_two_usd` (`fx_rate`, `fx_rate_date`) for cross-country filtering/sorting.
  - **Ratings:** Convert Zomato `0` (`Not rated`) to `NULL`. Never store or display unrated venues as `0`.
  - **Coordinates & Spatial:** Variables/columns use `(latitude, longitude)` order; Silver stores `DECIMAL(9, 6)` (`NULL` when `0` or out of range). Gold map tables store `location POINT SRID 4326 NOT NULL` with a `SPATIAL INDEX`, built via `ST_SRID(POINT(longitude, latitude), 4326)` (**note:** `POINT(lng, lat)` is longitude-first, whereas SRID 4326 WKT `POLYGON` from `bounding_box_wkt()` is latitude-first). Filter with `MBRContains` + `ST_Distance_Sphere`.
- **PyMySQL & SQL scripts:** InnoDB, `utf8mb4` / `utf8mb4_0900_ai_ci`, parameterized `%(name)s` queries only (never string formatting, never `pandas.to_sql(..., if_exists="replace")`, never SQLAlchemy). One connection per request; read-only DB user for FastAPI, separate write user for pipeline. Enforce verified TLS via `ssl.create_default_context()` when `MYSQL_TLS_ENABLED=TRUE`. Schema lives in numbered rebuildable scripts in `sql/` (no `ALTER` migrations; keep `;` out of SQL comments/strings; use `SQL SECURITY INVOKER` on Gold views).

### FastAPI, NLP & Observability (`docs/ARCHITECTURE.md`, `docs/CODE_STYLE.md`)

- **Routes:** Under `/api` in `kebab-case`, `snake_case` params/JSON, no version prefix (FastAPI and Streamlit co-deploy from the same commit; migrate callers in the same PR). Include `GET /api/health` (`{"status": "ok"}`) and `GET /api/pipeline/status`. Routes using PyMySQL MUST be plain `def`, never `async def`. Paginated responses return `{items, total, limit, offset}` with a unique tie-breaker in `ORDER BY`.
- **Constrained NLP:** Two-tier Hugging Face pipeline — local pre-baked `all-MiniLM-L6-v2` ONNX semantic hybrid (always-on, \$0) + optional `HuggingFaceAdapter` (`NLPAdapter.parse(query) -> SearchParams` with `extra="forbid"`, `NLP_TIMEOUT_SECONDS = 5`, `MAX_NLP_INPUT_CHARS = 500`, temperature `0`), off-topic domain guardrails, stateless `previous_params` follow-up refinement, validated against known locations and canonical cuisines (`docs/CUISINE_VOCABULARY.md`), falling back to `RuleBasedParser` on timeout/error/invalid output. Never generate or execute LLM SQL.
- **Logging:** Module-level loggers emitting **JSON lines** (`timestamp`, `level`, `logger`, `message`, plus `run_id`, `batch_id`, `source_id`, `rule_name`). No `print` (`T20`). Never log secrets; truncate user NLP queries to **220 characters** (`QUERY_LOG_MAX_CHARS = 220`).

### Streamlit Presentation (`docs/UI_UX.md`, `.agents/skills/developing-with-streamlit/SKILL.md`)

- **Editorial / Paper & Ink dual-theme** configured solely in `web/streamlit/.streamlit/config.toml` (`enableAgentApi = false`). Zero raw HTML/CSS (`unsafe_allow_html=True`, `st.html`, `streamlit.components` are blocked by `tests/test_architecture.py`), zero colorful emojis in headings/nav/buttons (use `:material/...:` icons).
- **Modern Streamlit 1.67.x APIs:** Single `st.set_page_config(..., initial_sidebar_state="auto")`, `st.navigation`, and `st.Page` in `web/streamlit/app.py`. Use `width="stretch"` or `width="content"` (**never** deprecated `use_container_width`), `st.columns(..., wrap=True)`, `st.grid`, and `st.form` for multi-filter queries. Place primary controls in-page so screens work at ~375 px mobile and desktop across Chrome, Edge, and Firefox.
- **Data honesty & safety:** Render untrusted strings via `st.text` / `st.dataframe` (or escaped Markdown); show `Unrated` for `NULL` ratings, original currency alongside USD comparisons, source + license attribution, interpreted `SearchParams`, and a staleness notice if Gold data exceeds 7 days; pair every map/chart with a table/text equivalent.

## 5. Quality Gates, Commands & Workflow

All code targets **Python >= 3.12**, line length **88**, Google-style docstrings, full type annotations, McCabe complexity **<= 18**, explicit DataFrame names (`restaurants_df`, `silver_df` — never bare `df`), `pathlib.Path`, UTF-8, LF line endings, and a final newline.

```bash
# Lint & format check (configured in pyproject.toml; scoped to Python packages)
ruff check pipeline web tests
ruff format --check pipeline web tests

# Static type checking
mypy .

# Test suite (unit, architecture boundaries, DAG import, Streamlit AppTest smoke tests)
pytest -v
```

- **Branches:** `<type>/<area>-<short-description>` (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`; areas: `pipeline`, `sql`, `backend`, `streamlit`, `web`, `infra`, `docs`).
- **Commits:** Conventional Commits (`<type>(<area>): <imperative summary under 72 chars>`).
- **Same-PR sync rule:** Adding/removing an env var updates `.env.example`; adding/removing a tunable updates `config/settings.toml`; changing behavior updates `docs/`.
